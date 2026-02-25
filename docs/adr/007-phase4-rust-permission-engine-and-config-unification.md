# ADR-007: Phase 4 — 権限エンジンの Rust 移行・SQLAlchemy 撤去・設定の .env 統一

- **日付**: 2026-02-25
- **ステータス**: 承認済み
- **ブランチ**: `feature/phase4-rust-migration`

---

## 1. 背景

Phase 3 で Rust Bridge (IPC/HTTP) による DB アクセスの基盤を確立したが、以下の課題が残存していた。

1. **権限判定ロジックが Python 側に残存**: `permission_service.py` が Discord.py の `PermissionOverwrite` 属性を直接比較しており、将来の変更に対して脆弱だった。
2. **mass_mute の直接 DB 接続**: `MassMuteLogic.save_log_to_db()` と `create_table_if_not_exists()` が `mysql-connector-python` を直接使用し、Rust Bridge を迂回していた。
3. **設定の二重管理**: チャンネル名等の設定が `config.py`（Python モジュール）と `.env` の両方に分散し、サーバー上での手動管理が必要だった。

---

## 2. 決定事項

### 2.1 権限エンジンの Rust 移行 (Phase 4.2)

Discord の権限ビット（allow/deny bitmask）の比較・評価ロジックを Rust Bridge に集約した。

- **新設**: `database_bridge/src/db/permission_repo.rs`
  - チャンネル名ポリシー管理（`MUTE_ONLY` / `READ_ONLY`）
  - ビットフラグ比較による `needs_repair` 判定
- **追加**: `POST /permissions/evaluate` エンドポイント
  - Input: `{ channel_name, current_allow, current_deny }`
  - Output: `{ needs_repair, target_allow, target_deny, reason }`
- **変更**: `discord_bot/services/permission_service.py`
  - `needs_repair()` を async 化し、Rust Bridge へ HTTP 委譲

### 2.2 SQLAlchemy および MySQL ドライバの完全撤去 (Phase 4.3)

Python プロセスから DB ドライバを完全に排除した。

- **削除**: `discord_bot/services/database.py`（SQLAlchemy エンジン設定ファイル）
- **削除**: `discord_bot/bot.py` の `get_db_connection()` メソッド
- **変更**: `mass_mute/logic.py`
  - `create_table_if_not_exists()` を削除
  - `save_log_to_db()` を async 化し、`LogService` 経由の Rust Bridge 呼び出しへ置換
- **変更**: `requirements.txt` / `pyproject.toml`
  - `SQLAlchemy`、`mysql-connector-python`、`PyMySQL`、`greenlet` を削除

### 2.3 設定の .env への統一

`config.py` モジュールへの依存を廃止し、すべての設定を `.env` に一元化した。

- **変更**: `discord_bot/bot.py`
  - `from config import ADMIN_USER_ID, GUILD_ID` → `os.getenv()`
- **変更**: `discord_bot/cogs/mass_mute/cog.py`
  - `from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES` → `os.getenv()`
  - チャンネル名はカンマ区切りで `.env` に記述し、起動時にリスト変換
- **変更**: `database_bridge/src/db/permission_repo.rs`
  - `let mute_only_names = [...]` のハードコードを廃止
  - `env_csv("MUTE_ONLY_CHANNEL_NAMES")` で `.env` から動的に読み込む形式へ変更
- **新設**: `.env.example`
  - 全環境変数のサンプルを一元管理するテンプレートファイルを作成

---

## 3. 採用理由

1. **疎結合の完成**: Python は Discord API と UI 配信に特化し、DB への直接接続がゼロになった。`ARCHITECTURE.md` に定義した「Python = Interface Layer / Rust = Logic + Data Layer」の方針が完全に実現した。
2. **設定の Single Source of Truth**: `.env` ファイルへの一元化により、SSH でのサーバー設定変更が容易になった。コードを再デプロイせずにチャンネル名を追加・変更できる。
3. **ビット演算による正確な比較**: Rust での権限評価は Discord の公式仕様（v10 Permission Flags）に基づくビット演算で行われ、Python の属性比較による不整合を排除できる。
4. **依存関係の最小化**: DB ドライバを削除することで、Python プロセスの起動速度の向上とセキュリティリスクの低減が期待できる。

---

## 4. 影響と注意事項

### デプロイ順序

Rust Bridge の `/permissions/evaluate` が稼働していない状態で Python 側をデプロイすると、自己修復機能が停止する。**Rust → Python の順でデプロイすること。**

### .env への追記が必要なキー

SSH でサーバーに入り、以下を `.env` に追記すること。

```env
ADMIN_USER_ID=000000000000000000
GUILD_ID=000000000000000000
MUTE_ONLY_CHANNEL_NAMES=配信コメント
READ_ONLY_CHANNEL_NAMES=参加ログ
```

### config.py の残存

`config.py` 本体はまだ削除していない（Python コードからの参照はゼロになった）。`.env` への移行完了後、次のスプリントで物理削除する。

---

## 5. 関連ドキュメント

- `ADR-002`: Rust Database Bridge 基盤の設計
- `ADR-006`: マスミュート自己修復 (Self-unblocking) の設計
- `ARCHITECTURE.md`: Python/Rust 役割分担ポリシー
- `.env.example`: 全環境変数のサンプル
