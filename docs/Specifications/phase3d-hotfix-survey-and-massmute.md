# Phase 3-D: 緊急ホットフィックス（アンケート修復 & マスミュート自己修復）仕様書

- **ブランチ**: `feature/phase3d-hotfix`
- **ステータス**: 🔴 計画中
- **作成日**: 2026-02-25
- **前提**: Phase 3-C（デプロイ・検証）が完了していること
- **経緯**: Phase 4 に計画していた「フェーズ 4.1: 緊急バグ修正」を、テスト環境での影響度を考慮して Phase 3-D として前倒し実施する。なお、本番環境では現在発生していない。

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

### 2.4 対応方針

#### 方針 A: `submitted_at` のデコード修正（最有力）

`db/models.rs` の `SurveyResponse` 構造体において、`submitted_at` の型を `OffsetDateTime` から `String` に変更し、  
Python 側に文字列のまま返す。もしくは sqlx の `time` feature が正しく有効化されているか検証する。

**Before（現状）**:
```rust
// database_bridge/src/db/models.rs
pub submitted_at: OffsetDateTime,
```

**After（修正案）**:
```rust
// OffsetDateTime マッピングが失敗する場合は String 型で受け取る
pub submitted_at: String,
```

> ⚠️ 代替案: `Cargo.toml` の sqlx に `"time"` feature が正しく指定されているか確認。  
> `features = ["runtime-tokio", "tls-rustls", "mysql", "macros", "time"]` の `"time"` が必須。

#### 方針 B: Python 側の型判定ガードを強化

`survey_service.py::get_responses()` のレスポンス判定が `isinstance(res, list)` だけでは不十分な場合、  
より防御的な実装に変更する。

```python
# Before
return res if isinstance(res, list) else []

# After（エラー詳細ロギング付き）
if isinstance(res, list):
    return res
logger.error("[SurveyService] get_responses: unexpected response type=%s, value=%r", type(res), res)
return []
```

### 2.5 成功基準

- `survey_responses` テーブルに存在するデータが、ダッシュボードの「回答数」に正しく反映される。
- `curl` で `GET /surveys/{id}/responses` を叩いて、正しい JSON 配列が返却される。

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

### 3.3 対応方針

#### 方針 A: Bot 起動時の事前セルフチェック（推奨）

`PermissionService` または `MassMuteLogic` にセルフチェック関数を追加し、  
`on_ready` 時点で Bot が必要な権限を持っているか事前検証・警告する。

**追加する関数のシグネチャ案**:
```python
# services/permission_service.py に追加
@staticmethod
async def check_bot_capabilities(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> list[str]:
    """Bot が権限操作に必要な前提条件を充たしているか検証し、
    不足している権限を文字列リストとして返す。
    
    Returns:
        不足している権限名のリスト。空リストなら全て OK。
    """
    issues = []
    
    # 1. ギルドレベルで「チャンネルの管理」権限があるか
    if not bot_member.guild_permissions.manage_channels:
        issues.append("ギルドレベルの「チャンネルの管理」権限がありません")
    
    # 2. ギルドレベルで「権限の管理」権限があるか
    if not bot_member.guild_permissions.manage_roles:
        issues.append("ギルドレベルの「権限の管理」権限がありません")
    
    return issues
```

**`cog.py::on_ready` 相当の呼び出し箇所**（`bot.py` の `on_ready` イベントに追加）:
```python
# bot.py の on_ready に追加（既存コードへの影響は最小限）
from discord_bot.cogs.mass_mute.logic import MassMuteLogic
from discord_bot.services.permission_service import PermissionService

@bot.listen("on_ready")
async def check_permissions_on_ready():
    if not bot.guilds:
        return
    guild = bot.guilds[0]
    bot_member = guild.get_member(bot.user.id)
    issues = await PermissionService.check_bot_capabilities(guild, bot_member)
    if issues:
        logger.warning("[PermissionService] ⚠️ Bot permission issues detected:")
        for issue in issues:
            logger.warning("  - %s", issue)
        # 管理者 DM で通知（オプション）
```

#### 方針 B: `Forbidden` 発生時の詳細 Audit Log 出力

エラー発生時に詳細情報を出力し、根本原因を特定しやすくする。

```python
# services/permission_service.py の Forbidden ハンドラを強化
except discord.Forbidden as e:
    msg = (
        f"Missing permissions to edit channel #{channel.name}. "
        f"Bot top role: {role.guild.me.top_role.name} (pos={role.guild.me.top_role.position}), "
        f"Target role: {role.name} (pos={role.position}). "
        f"Discord response: {e.text}"
    )
    logger.warning("[PermissionService] %s", msg)
    # 管理者への DM 通知もここで行う（方針 A と組み合わせ）
    return PermissionResult(
        channel_name=channel.name,
        success=False,
        action="applied",
        error=msg,
    )
```

### 3.4 成功基準

- Bot 起動ログおよび定時タスクのログに `Missing permissions` が **0 件** になること。
- `execute_mute_logic` の結果で全チャンネルが `success=True` になること。
- セルフチェック機能が `on_ready` 時に権限不足を事前検知できること。

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
