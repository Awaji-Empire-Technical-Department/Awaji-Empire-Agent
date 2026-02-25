# Phase 3-D: 緊急ホットフィックス（アンケート修復 & マスミュート自己修復）仕様書

- **ブランチ**: `feature/phase3d-hotfix`
- **ステータス**: ✅ 完了
- **完了日**: 2026-02-25
- **前提**: Phase 3-C（デプロイ・検証）が完了していること
- **経緯**: Phase 4 に計画していた「フェーズ 4.1: 緊急バグ修正」の内容を、高優先度の課題として Phase 3-D (Hotfix) として前倒し実施し、完遂した。

---

## 1. 目的

Phase 3 で稼働した Rust Bridge を経由したテスト環境において、以下の 2 つの問題がすでに発生している。
これらは **ユーザー体験を直接損なう** 重大な不具合であるため、Rust 移行の残作業（Phase 4 本来の目的）より優先して対処する。

| # | 問題 | 影響 |
|---|------|------|
| 1 | アンケート回答数がダッシュボードに 0 件表示される | アンケート機能が事実上使用不能 |
| 2 | 自己修復（マスミュート）が `Missing permissions` で失敗する | チャンネル権限が修復されず、ミュート漏れが発生しうる |

---

## 2. ホットフィックス 1: アンケート回答取得の修正

### 2.1 事象

ユーザーが Discord 上でアンケートに回答し、完了通知 DM を受け取っている。  
しかし、管理ダッシュボード上の「回答数」が **0 件** のまま表示される。

### 2.2 原因の推定と調査対象

```
Python (webapp.py) → GET /surveys/{id}/responses → Rust Bridge → DB
```

この呼び出しチェーン上のいずれかで問題が発生していると推定される。

| 優先度 | 疑惑箇所 | 詳細 |
|--------|---------|------|
| 🔴 高 | `response_repo::find_by_survey` のクエリ結果 | `submitted_at` カラムが `OffsetDateTime` にマッピングされず、sqlx が結果セットを外部エラーとしてスキップしている可能性 |
| 🔴 高 | `find_answers_by_user` の型変換 | `answers` カラムを `Vec<u8>` で取得後 `String::from_utf8_lossy` で変換しているが、空バイト列が返るケースの確認 |
| 🟡 中 | `GET /surveys/{id}/responses` エンドポイント | Python 側の `survey_service.py::get_responses()` が `res` を list と判定できず `[]` を返している可能性 |
| 🟡 中 | Rust Bridge バイナリの再起動漏れ | コード修正後にバイナリが古いまま稼働している |
| 🟢 低 | DB のデータ不在 | そもそも `survey_responses` テーブルにレコードが挿入されていない |

### 2.3 調査手順（診断コマンド案）

**ステップ 1: DB の直接確認（テストサーバーで実行）**

```sql
-- 回答レコードが存在するか確認
SELECT id, survey_id, user_id, submitted_at FROM survey_responses LIMIT 10;

-- submitted_at のカラム型確認
DESCRIBE survey_responses;
```

**ステップ 2: Rust Bridge ログの確認**

```bash
journalctl -u database_bridge -n 100 --no-pager | grep -E "(ERROR|WARN|sqlx)"
```

**ステップ 3: HTTP レスポンスの直接確認**

```bash
curl -s http://127.0.0.1:7878/surveys/{id}/responses | python3 -m json.tool
```

### 2.4 確定した解決策

#### 解決策 A: Rust Bridge 側の型デコード修正 (ADR-005)

sqlx と MariaDB の型互換性を確保するため、以下の修正を適用した。
- **DATETIME**: `OffsetDateTime` はタイムゾーン情報の有無でデコードエラーになるため、SQL 側で `CAST(column AS CHAR)` を行い、Rust 側では `String` として受け取る方式へ統一。
- **LONGTEXT**: MariaDB の `LONGTEXT`/`MEDIUMTEXT` は `BLOB` と判定されるため、Rust 構造体で `Vec<u8>` として受け取り、API レベルで `serde_json::from_slice` を用いてデコード。
- **BIGINT**: `user_id` は DB 側で `BIGINT` のため、Rust 構造体およびハンドラで `i64` を使用するように修正。

#### 解決策 B: DB 文字化けの解消

接続 URL に `?charset=utf8mb4` を追加し、日本語のアンケートタイトルや選択肢が `?????` になる問題を解消した。

#### 解決策 C: 重複回答の防止と正常な保存

`survey_responses` 表に `(survey_id, user_id)` の UNIQUE KEY が不足していたため、`INSERT ... ON DUPLICATE KEY UPDATE` が機能せず、常に新規挿入（重複）が発生していた。
- **対処**: 手動マイグレーションにより UNIQUE KEY を追加。手順を `setup-production.md` に記録。

### 2.5 修正後の結果

- ダッシュボードの回答数が正しく集計されるようになった。
- 既存回答の上書き（Upsert）が正常に機能するようになった。


---

## 3. ホットフィックス 2: マスミュート自己修復の権限エラー解消

### 3.1 事象

Bot 起動時（`on_ready`）・定時タスク（`daily_mute_check`）・チャンネル更新時（`on_guild_channel_update`）の  
自己修復プロセスにおいて、`discord.Forbidden: Missing permissions to edit channel` が発生し、  
一部チャンネル（`#mute_only`, `#readonly` 系）の権限調整に失敗している。

### 3.2 原因の推定

現在の `PermissionService.apply_permission()` / `check_and_repair()` は  
`discord.Forbidden` 発生時に **ログを出力して `success=False` を返す** だけであり、根本原因を特定しない。

```python
# services/permission_service.py 現状
except discord.Forbidden:
    msg = f"Missing permissions to edit channel #{channel.name}"
    logger.warning("[PermissionService] %s", msg)
    return PermissionResult(..., success=False, error=msg)
```

**根本原因の候補**:

| 原因 | 説明 | 確認方法 |
|------|------|---------|
| **ロール階層不足** | Bot の最高ロールが `@everyone` より上位でない（通常は問題にならないが念のため確認） | Discord サーバー設定 → ロール → 順序確認 |
| **「チャンネルの管理」権限不足** | Bot のロールにギルドまたはチャンネルレベルで「チャンネルの管理」「権限の管理」が付与されていない | Bot のロール設定確認 |
| **カテゴリによる権限ロック** | 親カテゴリで権限が「同期」状態にあり、Botの overwrite が上書きできない | 対象チャンネル → 権限 → 「カテゴリと同期」の状態確認 |

### 3.4 確定した解決策 (ADR-006)

単なる警告通知に留まらず、Bot が自律的に環境を復旧する **「セルフ・アンブロッキング」** 機能を実装した。

1.  **事前診断**: `!mute_check` コマンドを実装。サーバー設定および各チャンネル内での Bot 権限を精密診断し、不足があれば具体的な是正アクションを表示する。
2.  **実行時エラー検知**: `Forbidden` (権限不足) を検知した際、サーバーレベルの「ロールの管理（Manage Roles）」権限があるか確認。
3.  **自律的制限解除**: 権限がある場合、Bot 自身を対象チャンネルの「メンバー設定上書き（Member Overwrites）」として登録し、「権限の管理（Manage Permissions）」を強制許可に設定。
4.  **自動リトライ**: 自身のブロックを解除した後、本来の権限設定処理を再試行する。

### 3.5 修正後の結果

- チャンネル固有設定で Bot が拒否されている場合でも、サーバー権限さえあれば Bot が自ら解決して処理を完遂できるようになった。
- 不可能なレベルの権限不足（サーバー全体の権限欠落）は、管理者へ詳細な DM 通知が飛ぶようになった。


---

## 4. 実装タスク一覧

### 4.1 調査フェーズ（実装前に必ず実施）

- [ ] **[Survey]** テスト DB で `survey_responses` テーブルの中身と `submitted_at` の型を確認
- [ ] **[Survey]** `curl` で `/surveys/{id}/responses` を直接叩き、Rust Bridge のレスポンスを確認
- [ ] **[Survey]** Rust Bridge の systemd ログを確認し、sqlx エラーがないか検証
- [ ] **[MassMute]** Discord サーバーで Bot のロール権限（「チャンネルの管理」「権限の管理」）を確認
- [ ] **[MassMute]** 問題発生チャンネルが「カテゴリと権限を同期」状態になっていないか確認

### 4.2 実装フェーズ（調査結果に応じて選択）

| タスク | 対象ファイル | 種別 |
|-------|------------|------|
| `submitted_at` 型問題の修正 | `database_bridge/src/db/models.rs` | Rust |
| Rust Bridge ビルド・再起動 | サーバー作業 | インフラ |
| `permission_service.py` にセルフチェック追加 | `discord_bot/services/permission_service.py` | Python |
| `permission_service.py` の Forbidden ハンドラ強化 | `discord_bot/services/permission_service.py` | Python |
| `bot.py` に起動時セルフチェック呼び出し追加 | `discord_bot/bot.py` | Python |
| `survey_service.py` のエラーロギング強化 | `discord_bot/services/survey_service.py` | Python |

### 4.3 テストフェーズ

- [ ] **[Survey]** `tests/` にアンケート回答取得シナリオのユニットテストを追加
- [ ] **[MassMute]** `tests/test_permission_service.py` にセルフチェック関数のテストを追加
- [ ] **E2E**: テスト環境でアンケート回答 → ダッシュボード確認を実施
- [ ] **E2E**: Bot 再起動後のミュート適用ログを確認

---

## 5. Phase 4 との関係

本 Phase 3-D が完了した後、Phase 4 の `フェーズ 4.1: 緊急バグ修正` は **完了済み** として扱う。  
Phase 4 では引き続き以下のみを対象とする。

| Phase 4 残作業 | 内容 |
|---------------|------|
| フェーズ 4.2 | 権限エンジンの Rust 移行 |
| フェーズ 4.3 | ログと通知の統合（Rust 化） |

---

## 6. 関連ドキュメント

- `docs/Specifications/phase3c-deployment-and-verification.md`（前フェーズ仕様）
- `docs/Specifications/phase4-migration-and-bugfix.md`（Phase 4 仕様書 ※ §2.1/2.2 を本仕様に前倒し）
- `discord_bot/services/permission_service.py`
- `discord_bot/services/survey_service.py`
- `discord_bot/cogs/mass_mute/logic.py`
- `database_bridge/src/db/response_repo.rs`
- `database_bridge/src/api/handlers.rs`
