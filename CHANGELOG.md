# 📜 Changelog

このプロジェクトのすべての重要な変更は、このファイルに記録されます。
形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づいています。

## [Unreleased]

### Phase 4 Preview (Upcoming)

- **Python ロジックの Rust 移譲**: 残りの Python ロジック（Discord Cog 等）を順次 Rust Bridge へ移行し、Python 側を疎結合なゲートウェイへと進化させる。
- **モニタリング強化**: Rust 側での詳細なメトリクス収集とロギングの改良。

## [1.4.0] - 2026-02-26 (予定)

Phase 3-C 完了。Rust Bridge を DB 操作の中核として正式採用し、CI/CD による自動デプロイ体制を確立。

### Added

- **Phase 3-C: Rust Bridge 完全統合とデプロイ自動化**
  - **HTTP IPC による分散構成**: Python Bot/Webapp が Rust Bridge 経由でデータベースを操作する疎結合アーキテクチャへの完全移行。
  - **CI/CD パイプライン強化**: GitHub Actions (`deploy.yml`) による自動ビルド・デプロイ・サービス登録（systemd）フローを構築。
  - **自動セットアップスクリプト**: `scripts/setup-systemd.sh` を新設し、サービス登録と再起動手順をコード化。
  - **メンテナンスモード**: Rust Bridge 停止時、Webapp に統一デザインのメンテナンスページ (`templates/maintenance.html`) を表示する機能を実装。
  - **デプロイメントドキュメント**: 本番環境セットアップおよび自動デプロイ用の `sudoers` 設定手順を `docs/Specifications/setup-production.md` に集約。

### Changed

- **Rust Bridge の堅牢化**
  - **シリアライズ修正**: `OffsetDateTime` を JSON 時に RFC3339 形式の文字列として出力するよう修正（日付表示バグの解消）。
  - **MariaDB JSON 互換性**: MariaDB から BLOB として返される JSON カラムを `Vec<u8>` で受け、適切にデコードするよう修正。
  - **Axum 0.8 対応**: ルーティング構文の変更 (`/{id}`) に対応し、ランタイムパニックを防止。
- **CSS 分割リファクタリング**: `static/style.css` を 7 つの単一責任ファイル（base, layout, components 等）に分割し、デザインの拡張性を向上。
- **依存関係管理**: `uv` 使用時のパーミッションエラーを防ぐため、CI 時に `.venv` の所有権を自動修復するステップを追加。

### Fixed

- **デプロイ・ブロッキング修正**: 自動デプロイ中に `sudo` パスワードを要求され CI が停止する問題を、`sudoers` 設定と `deploy.yml` の `--non-interactive` 化により解消。
- **日付フォーマット不一致**: 以前のビルドで日付が数値配列になっていた問題を RFC3339 形式に統一。
- **未使用コード削除**: Rust 側のビルドウオーニング（`blob_to_string`）を解消し、バイナリをクリーン化。

## [1.3.0] - 2026-02-23

本番投入バージョン。Phase 2 アーキテクチャ刷新・フォームバグ修正・Rust DB ブリッジ基盤の3本柱を含む大規模リリース。

### Added

- **Phase 2 — アーキテクチャ刷新** (`feature/phase2-architecture-refactoring`)
  - `services/` 層を新設し、DB・権限・通知・ログ・VoiceKeeperの責務を分離
    - `services/permission_service.py` — 権限操作サービス（自己修復の核）
    - `services/survey_service.py` — アンケート DB CRUD
    - `services/notification_service.py` — DM 送信サービス
    - `services/log_service.py` — 操作ログ記録サービス
    - `services/database.py` — DB 接続（トップレベルから移動）
    - `services/voice_keeper_service.py` — VoiceKeeper I/O サービス
  - `cogs/mass_mute/` をディレクトリ化し、**自己修復（Self-Healing）機能**を追加
    - `on_guild_channel_create` — 新規チャンネル作成を即座に権限設定
    - `on_guild_channel_update` — 外部変更を検知し定義済み権限に自動復元
    - `on_guild_role_update` — @everyone ロール変更時に全対象チャンネルを再検証
  - `cogs/survey/` をディレクトリ化（`cog.py` + `logic.py` 分離）
  - `cogs/voice_keeper/` を `cog.py` + `logic.py` に統一し `services/` 層に対応
  - `common/survey_utils.py` 新設（`parse_questions` 純粋関数）
  - ユニットテスト 20件追加
    - `tests/test_permission_service.py`（11件）
    - `tests/test_survey_utils.py`（9件）
  - 設計記録: `docs/adr/001-phase2-architecture-refactoring.md`（ADR-001）

- **Phase 3-A — Rust DB Bridge スケルトン実装** (`feature/phase3-rust-bridge`)
  - `database_bridge/` Rust クレート新設（将来の Python DB 層の Rust 移行基盤）
    - `Cargo.toml`: sqlx (mysql feature)、thiserror、tracing を採用
    - `src/lib.rs`: crate root（db / bot / webapp モジュール公開）
    - `src/db/{models, connection, survey_repo, response_repo, log_repo}.rs`
    - `src/bot/survey_handler.rs`: UPSERT + `toggle_status`（Bot 固有）
    - `src/webapp/dashboard_query.rs`: `tokio::try_join!` 並列クエリ（Webapp 固有）
    - `src/main.rs`: CLI ヘルスチェック・エントリポイント
  - 設計記録: `docs/adr/002-phase3-rust-database-bridge.md`（ADR-002）
  - 仕様書: `docs/Specifications/phase3-rust-database-bridge.md`

- **Phase 3-B — Python-Rust ブリッジ方式調査** (`feature/phase3-rust-bridge`)
  - 仕様書: `docs/Specifications/phase3b-python-rust-bridge.md`
  - 候補 A: PyO3 (FFI)、候補 B: IPC (HTTP / Unix Socket)、候補 C: gRPC の比較表を記載
  - ステータス: 精査待ち・実装未着手

### Changed

- **`routes/survey.py` 薄層化** — Service 層に委譲し 414行 → 260行 に削減
- **`cogs/voice_keeper/`** — `cog.py` + `logic.py` 構成に一本化
- **`DASHBOARD_URL`** — http 通信から https 通信へ変更 (`refactor`)
- **`README.md`** — メッセージフィルタ機能の廃止を明記、Rust ロードマップ追記

### Removed

- **`cogs/filter.py`** — メッセージフィルタ機能を仕様変更により廃止。コードは Git 履歴で参照可能

### Fixed

- **フォームラジオボタン競合バグ** (`fix/form-radio-name-conflict`)
  - Jinja2 ネストループの `loop.index0` スコープ問題を修正
  - フォーム JS を `static/js/form.js` として外部ファイルに分離（テンプレート肥大化を防止）
  - 仕様書: `docs/Specifications/bugfix-form-radio-name.md`

### Security

- **`config.py` の Git 誤追跡を修正** — DB パスワード等の秘密情報が含まれる `config.py` がリポジトリに混入するリスクを排除
  - `.gitignore` に `**/config.py` を追加しパス変更にも堅牢化
  - セットアップスクリプトに `git rm --cached` による既存追跡解除ステップを追加（冪等対応）

## [1.2.4] - 2026-02-03

### Changed

- **フォルダ構成変更**:  
`cogs/bk_mass_mute.py`を `cogs/bk_mass_mute.py`に変更。
`cogs/mass_mute/*` の追加。
`services/permission.py` と `services/__init__.py` を追加。

## [1.2.3] - 2026-01-26

### Added

- **回答編集機能の実装**: 同一ユーザーが再度フォームを開いた際、前回の回答をプレビュー表示し、上書き修正（Upsert）できるように変更。
- **回答完了通知DM**: アンケート回答時に、Botから回答者へ「回答の控え」と「再編集用リンク」をDMで送信する機能を追加。
- **完了画面のデザイン**: 回答送信後の画面 (`submitted.html`) に `style.css` を適用し、カード型デザインに刷新。

### Changed

- **非同期処理の強化**: Webアプリケーション全体のDB接続処理を `aiomysql` を用いた完全非同期処理にリファクタリングし、タイムアウト耐性を向上。
- **Discord API連携**: Webアプリからの通知処理を `discord.py` 依存から `httpx` による直接APIコールに変更。
- **設定読み込み**: Bot Tokenの読み込み元を環境変数からルートディレクトリの `token.txt` に変更。
- **スラッシュコマンド刷新**: Discord Botのコマンド体系を `/create_survey` から `/survey [create|list|announce]` のグループコマンド形式へ移行。

### Fixed

- **DB接続エラーの解消**:
  - Proxmoxファイアウォールによるコンテナ間通信（Web VM ↔ DB CT）の遮断を解除。
  - MariaDBの `bind-address` 設定を変更し、外部接続を許可。
- **カーソル定義エラーの修正**: `create_new` や `download_csv` における `aiomysql.DictCursor` の参照方法を修正。
- **権限エラーの修正**: `/survey announce` コマンド実行時に管理者権限チェックが正しく機能するようにロール設定を案内。

## [1.2.2] - 2026-01-21

### Changed

- bot.py: 26Lines intents.voice_states を追加。

- **フォルダ構成変更**:  
`cogs/voice_keeper.py` を `cogs/voice_keeper.py.example`に変更。  
`cogs/voice_keeper/*` に`cogs/voice_keeper.py`の機能を格納。  
`common/*` 追加。  

- **FEATURE_VOICE_KEEPER.md**: 上記の修正による説明を修正、加筆。

## [1.2.1] - 2026-01-20

### Fixed

- **cogs/voice_keeper.py**: 常時稼働するよう修正。環境変数で稼働時間の設定が可能です。
- **FEATURE_VOICE_KEEPER.md**: 説明を修正。
- **README.md**: 環境変数の説明を修正。

## [1.2.0] - 2026-01-19

### Added

- **寝落ち切断機能**: `cogs/voice_keeper.py` を新規作成。

## [1.1.1] - 2025-12-31

### Fixed

- **UIデザイン最適化**: `static/style.css` のリファクタリング、それに伴う `templates` ディレクトリ内のHTMLの修正

## [1.1.0] - 2025-12-24

### Added

- **内製アンケートシステム**: Webでのフォーム作成、Discordでの回答、DB保存、CSV出力までの一連の機能を実装。
- **詳細ドキュメントの整備**: `docs/` フォルダ内にアーキテクチャ図を含む詳細仕様書を追加。
- **ハードウェア情報の追加**: `ARCHITECTURE.md` に物理サーバーのスペックを明記。

### Fixed

- **OAuth2 認証エラー**: Discord ログイン時の `400 Bad Request` を、Redirect URI の厳密な一致と Client Secret の更新、およびプロセスの再起動により解消。

## [1.0.0] - 2025-12-07

### Added

- **初期リリース**: 基本的なインフラ構成(Proxmox)の構築完了。
- **メッセージフィルタリング**: 8桁コード以外の自動削除ロジック。
- **通知マスミュート**: サーバー全体の通知権限を自動管理するタスクを実装。
