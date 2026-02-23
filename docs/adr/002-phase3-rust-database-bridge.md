# ADR-002: Phase 3 Rust Database Bridge 導入

- **日付**: 2026-02-23
- **ステータス**: 承認済み（設計確定・実装着手）
- **ブランチ**: `feature/phase3-rust-bridge`
- **関連仕様書**: [phase3-rust-database-bridge.md](../Specifications/phase3-rust-database-bridge.md)
- **supersedes**: なし（ADR-001 の「将来の Rust 移行」方針を具体化するもの）

---

## 1. 背景

ADR-001（Phase 2）で Python の `services/` 層に DB 操作を集約した。これにより副作用が隔離されたが、以下の問題が残存する。

| 課題 | 現状 | 深刻度 |
| :--- | :--- | :--- |
| **型安全性の欠如** | サービス層の返り値が `Dict[str, Any]` や `Optional[...]`。実行時まで構造の誤りを検出できない | 高 |
| **複数プールの乱立** | `SurveyLogic` (Bot 側) と `webapp.py` が独立して `aiomysql.Pool` を生成。接続数が管理できない | 高 |
| **UPSERT の非効率** | `save_response()` が SELECT → 分岐 → INSERT/UPDATE の 2 RTT。Bot のレスポンス遅延に影響 | 中 |
| **ダッシュボードの直列クエリ** | `webapp.py::index()` の surveys・logs クエリが直列実行 | 中 |
| **DBドライバの不統一** | `bot.py` が同期の `mysql.connector`、`webapp.py` が非同期の `aiomysql` と混在 | 中 |

---

## 2. 決定事項

**Python の DB 操作ロジックを Rust クレート `database_bridge` へ段階的に移譲する。**

---

## 3. 設計判断

### 3.1 モジュール分割方針：3 層構造の採用

**判断**: `database_bridge/src/` を以下の 3 層に分割する。

```text
db/      ← アプリ非依存の純粋 CRUD（両アプリから参照）
bot/     ← Discord Bot 固有ロジック（db/ を参照・webapp/ に非依存）
webapp/  ← Web ダッシュボード固有ロジック（db/ を参照・bot/ に非依存）
```

**採用理由**:

- `bot/` と `webapp/` を互いに依存させないことで循環依存を防ぐ
- `db/` に共通 CRUD を集約することで、両アプリが同一クエリを重複実装するのを防ぐ
- Python の `services/` 層の思想（副作用の隔離）を Rust でも踏襲し、移行コストを最小化する

**検討した代替案**:

- **単一ファイル構成**: 小規模だが将来の機能追加時に再分割が必要になる。採用せず。
- **Bot / Webapp を統合した単一ライブラリ**: 依存が混在し、テストが複雑化する。採用せず。

---

### 3.2 DB ドライバ：`sqlx` + `mysql` feature の採用

**判断**: `sqlx 0.8` の `mysql` feature（MariaDB 対応）を使用する。

**採用理由**:

- **コンパイル時クエリ検証**: `query!` マクロが SQL を型チェックし、実行前に誤りを検出できる
- **async/await ネイティブ**: tokio との親和性が高く、GIL のある Python と根本的に異なる真の並列 I/O が得られる
- **`FromRow` derivation**: テーブル行を Struct に直接マッピングでき、`Dict[str, Any]` のアンパック操作が不要になる

**採用しなかった代替案**:

- **`diesel`**: 同期 ORM。tokio ベースの非同期アーキテクチャに適合しない。採用せず。
- **`sea-orm`**: 高レベルで有力だが、sqlx との二重依存になる。Phase 3 では sqlx 直接使用でシンプルに保つ。

> ⚠️ **発見した既存の誤り**: 元の `Cargo.toml` には `"postgres"` feature が設定されていたが、
> プロジェクトの DB は **MariaDB** である。本 ADR の実装と同時に `"mysql"` へ修正した。

---

### 3.3 UPSERT 最適化：`ON DUPLICATE KEY UPDATE` の採用

**判断**: `bot::survey_handler::upsert_response()` において、SELECT → 分岐 → INSERT/UPDATE の 2 RTT パターンを、MariaDB の `INSERT ... ON DUPLICATE KEY UPDATE` 1 文に置き換える。

**前提条件**: `survey_responses` テーブルに `UNIQUE KEY (survey_id, user_id)` が存在すること。

**採用理由**:

- ネットワーク往復回数を 2 → 1 に削減（特に Bot の Discord インタラクション 3 秒タイムアウト内での安定性向上）
- アトミックな操作となり、SELECT と UPDATE の間にレースコンディションが生じない

**検討した代替案**:

- SELECT → 分岐維持: Python との対称性はあるが最適化の意義がない。採用せず。
- `REPLACE INTO`: 既存行を DELETE → INSERT するため `id` が変わり、DM 送信済みフラグ等のリレーション整合性が崩れる。採用せず。

---

### 3.4 並列クエリ：`tokio::try_join!` の採用

**判断**: `webapp::dashboard_query::fetch_dashboard_data()` において、surveys クエリと logs クエリを `tokio::try_join!` で同時発行する。

**採用理由**:

- Python の直列実行（合計レイテンシ = クエリA時間 + クエリB時間）に対し、Rust では合計 = max(クエリA, クエリB) に短縮
- 両クエリに依存関係がないため並列化に問題なし

---

### 3.5 エラー型：`thiserror` による `BridgeError` enum の採用

**判断**: `Result<T, BridgeError>` を全関数の返り値とし、`None 返し` / `false 返し` を廃止する。

**採用理由**:

- Python 側では `try/except + None 返し` のため、呼び出し元がエラー原因を判定できなかった
- `BridgeError::PermissionDenied` / `::NotFound` / `::Sqlx` と型レベルでエラー種別を表現し、呼び出し元が適切にハンドリングできる
- `#[from]` による自動変換で `?` 演算子が使えるためボイラープレートを排除

---

### 3.6 移行戦略：段階的フェーズ分割

**判断**: 一括移行ではなく Phase 3-A〜E の 5 段階で進める。

| フェーズ | 内容 | Python への影響 |
| :--- | :--- | :--- |
| **3-A** | Rust クレートのスケルトン実装（本 ADR） | なし |
| **3-B** | Python ↔ Rust ブリッジ方式の決定（PyO3/IPC/gRPC） | 未定 |
| **3-C** | Bot 側 DB 直接呼び出しを Rust 経由に変更 | `survey_service.py` が shim 化 |
| **3-D** | Webapp 側の直 SQL を廃止 | `webapp.py` の SQL を削除 |
| **3-E** | `aiomysql` 依存を完全削除 | `requirements.txt` から除去 |

**採用理由**:

- 段階的移行により、既存の Discord Bot と Webapp を無停止で継続稼働させながら開発できる
- 各フェーズで動作確認ができ、問題の局所化が容易

---

## 4. 変更前後の構造

### Before（Python のみ）

```text
discord_bot/
├── services/
│   ├── database.py         # SQLAlchemy engine（ほぼ未使用）
│   ├── survey_service.py   # CRUD（aiomysql）
│   └── log_service.py      # ログ INSERT（aiomysql）
├── bot.py                  # get_db_connection()（mysql.connector・同期）
└── webapp.py               # 直 SQL（aiomysql）

database_bridge/
└── src/
    └── main.rs             # 空のスタブ
```

### After（Phase 3-A 完了時点）

```text
database_bridge/
└── src/
    ├── lib.rs
    ├── main.rs              # CLI ヘルスチェックエントリ
    ├── db/
    │   ├── mod.rs
    │   ├── connection.rs    # プール生成・ヘルスチェック
    │   ├── models.rs        # Struct 定義・BridgeError
    │   ├── survey_repo.rs   # surveys CRUD
    │   ├── response_repo.rs # survey_responses CRUD
    │   └── log_repo.rs      # operation_logs INSERT/取得
    ├── bot/
    │   ├── mod.rs
    │   └── survey_handler.rs # UPSERT + toggle_status
    └── webapp/
        ├── mod.rs
        └── dashboard_query.rs # tokio::try_join! 並列クエリ
```

> Python 側（`services/` 等）は Phase 3-A 時点では**変更なし**。

---

## 5. 未解決事項（Phase 3-B 以降で決定）

| 課題 | 候補 | 決定時期 |
|------|------|---------|
| Python ↔ Rust の呼び出し方式 | HTTP-based IPC (127.0.0.1) | [ADR-003](003-phase3b-python-rust-ipc-method.md) |
| `questions` JSON の確定スキーマ | `form.html` / `form.js` から逆算 | Phase 3-A 完了前 |
| CI での `sqlx` コンパイル時検証 | `SQLX_OFFLINE=true` + `.sqlx/` ディレクトリ | Phase 3-A 完了時 |

---

## 6. 結論

Python の DB アクセス層を Rust へ移行することで、**型安全性・パフォーマンス・接続管理の一元化**を達成する。
Phase 3-A（本 ADR）では Rust クレートのスケルトンを確立し、Python 側への影響をゼロにした状態で基盤を整備する。
Python ↔ Rust のブリッジ方式は Phase 3-B で別途 ADR を起票する。
