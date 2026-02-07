# 📜 Changelog

このプロジェクトのすべての重要な変更は、このファイルに記録されます。
形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づいています。

## [Unreleased]

### Added

- (Experimental) 次世代データアクセス層の設計検討を開始
  - 目的: システムのメモリ安全性向上と型安全性の確保
  - 背景: Ubuntu 26.04 LTS のコアシステム Rust 導入トレンドへの適応
  - 参照: [Ubuntu、26.04 LTSのコアシステムにRustを導入へ - ZDNET Japan](https://japan.zdnet.com/article/35243565/)
- `ARCHITECTURE.md` への Rust 移行ロードマップの追記

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
