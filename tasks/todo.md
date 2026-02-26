# Todo: Phase 3 - Rust Database Bridge

## ブランチ: `feature/phase3-rust-bridge`

---

## Phase 3-A: `db/` 層の実装（✅ 設計完了 / 🔨 実装中）

- [x] ブランチ `feature/phase3-rust-bridge` を作成
- [x] 仕様書 `docs/Specifications/phase3-rust-database-bridge.md` を作成
- [x] `Cargo.toml`: `postgres` → `mysql` feature へ変更、`thiserror` / `tracing` を追加
- [x] `src/lib.rs`: crate root（db / bot / webapp を公開）
- [x] `src/db/mod.rs`: db モジュール定義
- [x] `src/db/models.rs`: Struct 定義（Survey / Question / SurveyResponse / AnswerValue / OperationLog / BridgeError）
- [x] `src/db/connection.rs`: プール生成 + ヘルスチェック
- [x] `src/db/survey_repo.rs`: surveys テーブル CRUD
- [x] `src/db/response_repo.rs`: survey_responses テーブル CRUD
- [x] `src/db/log_repo.rs`: operation_logs INSERT + 取得
- [x] `src/bot/survey_handler.rs`: UPSERT + toggle_status（Bot 固有）
- [x] `src/webapp/dashboard_query.rs`: ダッシュボード並列クエリ（Webapp 固有）
- [x] `src/main.rs`: CLI ヘルスチェックエントリ
- [x] `cargo build` が通ることを確認（`SQLX_OFFLINE=true` または DB 接続）
- [x] `questions` JSON スキーマを `form.html` / `form.js` から確認し `Question` struct を確定

## Phase 3-B: Python ↔ Rust ブリッジの実装 (TCP IPC + systemd 自動化)

- [x] IPC 方式の選定: **候補 B (TCP IPC/HTTP)** に決定
- [x] `docs/Specifications/phase3b-python-rust-bridge.md` のステータスを更新
- [x] `infra/database_bridge.service` (systemd ユニットファイル) の作成
- [x] `scripts/setup-systemd.sh` (systemd 自動設定スクリンス) の作成
- [x] `infra/sudoers_deploy` (sudoers 設定) の作成
- [x] `database_bridge/Cargo.toml` に `axum`, `serde`, `tower-http` を追加
- [x] `database_bridge/src/main.rs` を HTTP サーバーとして実装
- [x] 各 DB 操作に対応する API エンドポイントの実装
- [x] 疎通確認 (curl によるヘルスチェック)
- [x] `deploy.yml` に `setup-systemd.sh` の呼び出しを追加

## Phase 3-C: Bot 側の DB 直接呼び出しを廃止

- [x] `cogs/survey/logic.py` の `initialize_pool` / `close_pool` を Rust に委譲
- [x] `services/survey_service.py` を Rust shim に変更

## Phase 3-D: Webapp 側の直 SQL を廃止

- [x] `webapp.py::index()` の SQL を `webapp::dashboard_query` 経由に変更

## Phase 3-E: aiomysql 依存を完全削除

- [x] `requirements.txt` から `aiomysql` を削除
- [x] `pyproject.toml` を更新

## Phase 3-F: サーバーデプロイと最終検証（🔨 次回予定）

- [ ] 仕様書 `docs/Specifications/phase3c-deployment-and-verification.md` の作成
- [ ] テストサーバーへのデプロイ実行
- [ ] `database_bridge` プロセスの稼働確認 (systemctl status)
- [ ] Bot / Webapp のログ監視 (Error が出ていないか)

## Phase 4: セキュア対戦ロビーシステム（🔨 進行中）

- [x] 仕様書 `docs/FEATURE_LOBBY.md` の更新
  - [x] 自由対戦モード / 大会モードの選択機能を追記
  - [x] ダッシュボードへのロビー一覧表示と遷移ロジックを追記
- [ ] データベースマイグレーションの作成 (`database_bridge/migrations/003_lobby_tables.sql`)
- [ ] Rust Bridge: `LobbyRoom` モデルとリポジトリの実装
- [ ] Rust Bridge: `POST /lobby/rooms` で `mode` パラメータをサポート
- [ ] Webapp: `dashboard.html` にロビー作成・一覧コンポーネントを追加
- [ ] Webapp: 一覧からの `lobby.html` への遷移実装
- [ ] Bot: 大会終了時の優勝ロール自動付与ロジック実装
