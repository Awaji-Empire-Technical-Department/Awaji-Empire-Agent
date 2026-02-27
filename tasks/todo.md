# Todo: Phase 3 - Rust Database Bridge

## ブランチ: `feature/phase3-rust-bridge`

---

## Phase 3-A: `db/` 層の実装（✅ 設計完了 / ✅ 実装完了）

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
  - [x] ホスト権限委譲、選手/スタッフ役割、CSV出力、最終承認フローを追記
- [ ] データベースマイグレーションの作成 (`database_bridge/migrations/003_lobby_tables.sql`)
- [ ] Rust Bridge: `LobbyRoom`, `LobbyMember` モデルとリポジトリの実装
- [ ] Rust Bridge: `POST /lobby/rooms` で `mode`, `title` パラメータをサポート
- [ ] Rust Bridge: `GET /lobby/export` (CSV出力) の実装
- [ ] Webapp: `dashboard.html` にロビー作成・一覧コンポーネントを追加
- [ ] Webapp: `lobby.html` での役割選択（選手/スタッフ）の実装
- [ ] Webapp: ホスト専用操作（権限譲渡、CSV出力、最終承認）の実装
- [ ] Bot: 大会終了（承認時）の優勝ロール動的付与ロジック実装
- [x] DB/Rust/Python/UI: ロビーの「説明書き(Description)」機能のフルスタック実装 (仕様追加)

## Phase 4.1: ロビーシステムの不具合修正・仕様補完 (The Plan)

### 1. Cloudflare WARP IPが切断後も表示され続ける問題

**原因**: `webapp.py`においてCloudflareの`/devices` APIを使用しIPを取得しているが、デバイス情報の`ip`フィールドは現在WARPに接続中かどうかに関わらず情報を保持し続けるため、切断後も以前のIPが表示される。
**解決策検討**:

- **案A**: CFからの最終通信日時（last_seen）を見て判定する（一定時間経過で未接続扱い）。
- **案B**: ダッシュボード上に「WARP接続情報を手動でクリアする」ボタンを設置し、ユーザーが意図的にIPを消せるようにする（確実）。
*(※ ユーザーに方針を確認し決定する)*

### 2. 有効期限を過ぎたロビーが自動的に破棄されない問題

**原因**: ダッシュボード一覧（`find_active_rooms`）からは消えるが、DBから削除されておらず、個別URLではアクセスできる。
**解決策**:

- `find_room_by_passcode` クエリに `expires_at > NOW()` 条件を追加し、期限切れはNotFoundにする。
- 一覧取得など定期的な処理の前に、`DELETE FROM matchmaking_rooms WHERE expires_at <= NOW()` を実行して遅延評価的に自動破棄する。

### 3. 自由対戦モードで大会モード限定のメニューが出現している問題

**原因**: `lobby.html` の「ホスト管理メニュー」のUI描画において、モード分岐が行われていない。
**解決策**:

- `lobby.html`内の「最終結果の承認」「CSVエクスポート」のブロックを `{% if room.get('mode') == 'tournament' %}` で囲み、大会モード時のみ表示する。

### 4. 大会を開始するためのメニューがない問題

**原因**: 練習から実大会への移行を想定した `tournament_start_at` を更新するフロー・UIが存在しない。
**解決策**:

- [x] Rust: `lobby_repo.rs` と APIに `start_tournament` エンドポイントを実装し、`tournament_start_at` を現在時刻に更新。
- [x] Python: `routes/lobby.py` に大会開始アクションを追加。
- [x] UI: `lobby.html` のホスト向けメニューに「▶ 大会を開始する」ボタンを追加。開始済みの場合は「大会進行中」と表示を切り替える。

### 5. 追加実装 (Wanyaldeeフィードバック: 2026-02-27)

- [x] **WARP IPのリアルタイム更新**: Discordログイン同期時(`webapp.py`)にCloudflareのデバイス情報から `last_seen` を確認し、一定時間（例：10分）内の最新IPのみを有効として取得する。対戦のための「確実なIP」を提供する。
- [x] **IPコピーボタン**: `lobby.html`のメンバー一覧（対戦相手）に、IP（Game Link）をクリップボードにコピーするボタンを追加する。
- [x] **ユーザー名の表示**: 参加メンバー一覧で無機質なユーザーIDではなく、Discordのユーザー名（サーバーネーム）を表示する。
  - [x] DB `user_networks` テーブルに `username VARCHAR(255)` を追加（マイグレーション `004_lobby_updates.sql` 作成）。
  - [x] `webapp.py` の同期時にユーザー名を保存し、ロビーのメンバー取得時(`get_members`)にJOINして返すようRust Bridgeを修正する。
