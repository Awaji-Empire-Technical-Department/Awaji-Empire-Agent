# 📜 Changelog

このプロジェクトのすべての重要な変更は、このファイルに記録されます。
形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づいています。

## [1.8.0] - 2026-06-14

イベント参加フォームの運用機能を大幅強化。スタッフ共同編集・回答削除・当日受付・メンバー同期を追加。設計記録: `docs/adr/024`, `025`

### Added

- **スタッフ共同編集**（ADR-025）
  - フォーム編集画面の「共同編集スタッフ」からユーザー名検索でスタッフを追加し、編集・イベント管理・割り当て・通知・当日受付の権限を共有
  - 共有されたフォームをスタッフ側ダッシュボードの「アンケート管理」に表示（「共有」バッジ・「○○さんから共有」・共有元バナー）
  - スタッフ追加時に本人へ Discord DM 通知（共有元・編集リンク付き）
  - スタッフの追加削除・フォーム削除・公開切替はオーナー専用
- **回答の削除**（ADR-025）
  - 回答者本人がフォームから自分の回答を取り消し可能（間違い回答の救済。紐づく応募登録も削除）
  - 管理者（オーナー/スタッフ）がイベント管理画面から応募を削除可能
- **当日モード（チェックイン）**（ADR-025）
  - オフ会当日の受付専用ページを追加。承認済み参加者を部ごとに一覧し、来場をタップで記録
  - CSV エクスポートに「来場」列を追加
- **ギルドメンバー一括同期**
  - Bot 起動時の自動同期と管理者用スラッシュコマンド `/sync_members`。ゲートウェイのキャッシュを使い Discord REST 呼び出しは 0 回、DB 書き込みはバッチ upsert に集約
- **回答リンクの共有/コピーボタン**
  - ダッシュボードのアンケート管理・イベント管理画面・回答ページの3か所からワンタップでコピー
- **回答フローのギルドチェック緩和**（ADR-024）
  - 回答ページに限りサーバー未加入の Discord アカウントでも回答可能（オフ会集計の取りこぼし防止）。管理系画面は従来通り加入必須
  - 回答送信後の DM を応募内容の「控え」として位置づけ

### Fixed

- **CI/CD で Rust 変更が反映されない**: `deploy.yml` が `database_bridge.service` を再起動しておらず、`cargo build` した新バイナリが古いプロセスのまま動作していた。bridge を依存サービスより先に restart するよう修正（LESSON-007）
- **webapp からの DM が届かない**: `routes/survey.py`・`routes/event.py` が廃止済みの `token.txt` に依存しており `DISCORD_BOT_TOKEN=None` で送信スキップしていた。`.env` の `DISCORD_TOKEN` 優先に統一（ADR-023 移行漏れ・LESSON-008）

### Changed

- 回答リンク共有ボタンをクリップボードへの自動コピー優先に統一（全画面で挙動を揃え、文言を「回答リンクをコピー」に）

---

## [1.7.1] - 2026-06-04

ドキュメント整備・VoiceKeeper ボイスチャンネル内OpenChatへの報告対応。

### Fixed

- **VoiceKeeper**: `REPORT_CHANNEL_NAME` に指定されたチャンネルがテキストチャンネルに存在しない場合、同名のボイスチャンネル内 OpenChat へフォールバックして報告を送信するよう修正（`services/voice_keeper_service.py`）

### Changed

- **FEATUREドキュメント**: フローチャートを PNG 画像から Mermaid 図に移行（`FEATURE_VOICE_KEEPER.md`, `FEATURE_MASS_MUTE.md`）
- **FEATURE_FILTER.md**: メッセージフィルタリング機能を廃止済みとしてマーク

---

## [1.7.0] - 2026-05-25

イベント参加フォームシステムの完成・改善実装。設計記録: `docs/adr/021`, `022`

### Added

- **イベント参加フォームシステム**（ADR-021）
  - 既存アンケートに「イベント参加フォームとして作成する」チェックを追加し、オフ会・イベント向け参加管理機能を有効化
  - **部制対応**: 部制なし（1回開催）と部制あり（複数回・時間帯別）を切り替え可能
  - **Discord 認証必須**: 参加者を Discord ユーザー ID で一意に特定し DM 通知
  - **自動割り当て**: 希望部・定員をもとに一括割り当て。承認・否認済みはスキップ
  - **結果通知 DM**: 承認・否認・補欠ごとに異なるメッセージを一斉送信。Google Calendar / Outlook リンクを同梱
  - **参加者確認ページ**: トークンベース URL で参加者が結果をいつでも自己確認可能
  - **締切自動処理スケジューラー**: 応募締切を過ぎたイベントのステータスを毎時0分に自動で `closed` に変更（ADR-022）
  - **イベント管理画面**: 応募者一覧・割り当て・通知・CSV ダウンロードを1画面に集約

- **部制なし定員設定**（ADR-022）
  - `events.capacity` カラムを追加。自動割り当て時に上限を考慮し、超過分は補欠登録

- **フォームUI改善**（ADR-022）
  - 部ごとの集合場所を選択UIに併記
  - 残席数をリアルタイム表示、満席の部は選択不可に
  - タイトルカードをフォーム最上部（Discordログインより前）に移動

- **イベント特化CSVエクスポート**
  - イベントフォームのCSVに参加意思・状態（承認/否認/補欠）・割り当て部・希望部の列を追加

- **運用マニュアル**: `docs/EVENT_FORM_MANUAL.md`（管理者向け・参加者向け両方）

### Fixed

- **自動割り当て後にDOMが更新されない**: APIレスポンスから直接DOM更新するよう変更（ページリロード前に即反映）
- **Google Calendar の時刻が9時間ずれる**: `Z`（UTC）サフィックスをJST時刻に誤付与していた。ローカル時刻形式に修正
- **Outlook URL で Discord Markdown 崩れ**: `「」` 等の日本語文字でURLパーサーが誤作動し `~~text~~` の打ち消し線が発生。`<URL>` 形式でラップし解消

---

## [1.6.0] - 2026-05-23

マリオカートワールド ラウンジシステム Phase 3 — 申告方式刷新・MMR・称号の完全実装。
設計記録: `docs/adr/018` 〜 `020`

### Added

- **ラウンジ最終順位申告方式**（ADR-018）
  - レースごとの申告フローを廃止。12レース終了後に最終順位（1〜24位）を1回だけ申告する方式に変更
  - MMRデルタテーブル: 全順位プラスのみ（1位 +150 〜 24位 +5 参加賞）。身内向け運用のためマイナスなし
  - ホストによる参加者「除外」機能: 接続障害等でMMR対象外にしたいプレイヤーをワンタップで除外
  - `lounge_session_final_scores` テーブル追加・廃止テーブル（`lounge_race_results` / `lounge_race_scores` / `lounge_course_history`）DROP
  - WS イベント: `lounge.final_score_reported`, `lounge.member_excluded` を新設

- **ダッシュボードへのMMR表示**
  - ラウンジ参加履歴があるユーザーのダッシュボードに現在MMR・最高MMR・参加回数カードを表示

- **セッション結果モーダルの改善**
  - 「合計ポイント」表示を廃止し「MMR増加 (+X)」「現在のMMR」に変更
  - セッション終了後にページをリロードしても結果モーダルが表示される

### Fixed

- **覇者称号が付与されない問題**（ADR-020）
  - セッション1位のプレイヤーに `grant_tournament_win` を呼び出すよう修正
  - `grant_rank`（MMRベース）と `grant_tournament_win`（優勝回数ベース）の両方を付与対象に

- **非ホストの結果モーダルが自動表示されない問題**（ADR-019, 020）
  - WS 単一経路への依存をやめ、WS受信・API成功・ポーリングの3経路でモーダルを表示
  - `resultModalShown` フラグで二重表示を防止

- **モバイルUI: ボタンレイアウトの崩れ**（ADR-019）
  - `#staff-panel` → `#action-panel` セレクタ修正
  - タッチターゲット `min-height: 48px` 確保
  - 申告フォームの select + ボタン行をモバイルで縦並びに変更

- **WS切断中の申告状況消失**
  - WS切断中は10秒ポーリングで申告状況を補完
  - WS再接続時に `pollTick()` で切断中の差分を一括同期

### Changed

- **`lounge_session_members`**: `excluded` カラム追加（migration 008）
- **`lounge_players`**: `total_sessions` のインクリメントを除外プレイヤー以外に限定

---

## [1.5.1] - 2026-05-16

配信中リセット予約方式への変更。設計記録: `docs/adr/014-stream-comment-reset-streaming-guard.md`

### Changed

- **`/reset_stream_comments` の配信中動作を予約方式に変更**
  - 従来: 配信中（ホスト VC 在席中）はコマンドをブロックしてエラーメッセージを返すのみ。
  - 変更後: `_pending_reset` フラグを立てて予約し、ホストが VC を退室した時点（`on_voice_state_update`）で自動実行。
  - 月次自動リセット（VoiceKeeper 報告・fallback cron）の動作は変更なし。
  - `_try_monthly_reset` に `force: bool` 引数を追加。予約実行時は冪等チェックをスキップ。

## [1.5.0] - 2026-04-20

`#配信コメント` チャンネル月次リセット機能の実装。設計記録: `docs/adr/011-stream-comment-reset.md`

### Added

- **#配信コメント チャンネル月次リセット機能**
  - **主トリガー**: VoiceKeeper の寝落ち集計報告を毎月20日に検知し、チャンネルを削除→同名・同カテゴリ・同ポジションで即時再作成。
  - **フォールバック cron**: 毎月21日 06:00 JST に未リセットであれば補完実行 (`tasks.loop(hours=24)`)。
  - **Self Heal**: `on_guild_channel_update` で Bot の `manage_roles` overwrite が除去されたことを検知し、即座に自動再付与。MassMute の Self Heal パターンを踏襲。
  - **スラッシュコマンド `/reset_stream_comments`**: `管理者` ロール限定・全員非表示 (`default_permissions=Permissions(0)`)。`dry_run` オプションで overwrite プレビューを確認可能。
  - **DB ログ**: Rust Bridge 経由で `stream_comment_reset_log` テーブルに月次リセット・Self Heal・手動リセットを記録。
  - **冪等性**: `_last_reset_month` によるメモリ上チェックで二重実行を防止。
  - 実装層: `cogs/stream_comment_reset/` (cog.py / logic.py) + `services/stream_comment_reset_service.py` + Rust `reset_log_repo`。
  - 仕様書: `docs/FEATURE_STREAM_COMMENT_RESET.md`

## [1.4.1] - 2026-02-28

Phase 4.2 & 4.3: セキュア対戦ロビーのWebSocketリアルタイム化、大会（Tournament）進行支援機能の実装。

### Added

- **WebSocket リアルタイム同期**
  - Rust バックエンド (`database_bridge`) に WebSocket エンドポイント `/ws/hyouibana` を新設。
  - フロントエンドからポーリングなしで、メンバーの入退室やステータス変更（受付中、対戦中など）をリアルタイムにUIへ反映する仕組み (`possession_lobby.js`) を導入。
- **大会進行支援機能 (Tournament Mode)**
  - トーナメント戦績を記録するためのテーブル拡張 (`100_tournament_updates.sql`)。
  - フロントエンドに `Bracketry` ライブラリを導入し、大会のトーナメント表（ブラケット）を動的に描画。
  - バックエンドからの試合結果（勝敗報告 API）の実装。
- **ステータス手動更新 API**
  - 自由対戦のホストが「受付中」や「対戦中」を宣言できる `/lobby/api/status` エンドポイントの実装。
- **Discord ロール自動付与**
  - トーナメント結果の最終承認時に、自動で Discord API を叩き「(大会名)優勝」ロールを作成・付与する機能を実装。

### Fixed

- **DB マイグレーション修正**
  - `006_tournament_updates.sql` の名前衝突によって発生した `migration partially applied` エラーを解決するため、ファイル名を `100_tournament_updates.sql` に変更し、DB修復スクリプト (`db_repair.py`) を提供。
- **フロントエンドのステータス表示バグ**
  - 初期待機時に全員が「オフライン」と表示される不具合を修正し、Jinja2 テンプレート側および JS 側で正しくステータス（オンライン・対戦中など）を判定して描画するように修正。

## [1.4.0] - 2026-02-27

Phase 3: セキュア対戦ロビーシステムの導入。Cloudflare WARP IP 同期による物理IP隠蔽と、大会進行管理機能の実装。設計記録: `docs/adr/008-secure-lobby-system.md`

### Added

- **セキュア対戦ロビー基盤 (Secure Lobby System)**
  - **Cloudflare WARP 仮想IP同期**: Discordログイン時に Cloudflare API からデバイス仮想IPを自動取得し同期する仕組みを構築。
  - **GameLinkFormatter (Rust)**: 仮想IPを『東方憑依華』専用の12桁ゼロ埋め形式（`100.096.xxx.xxx:10800`）に自動変換。
  - **ロビー管理機能**:
    - 「自由対戦モード」と「大会モード」の選択、ロビー名・説明文の動的設定。
    - ホスト権限の譲渡機能、ロビー解散（削除）機能。
    - 参加メンバーの CSV エクスポート、大会結果の最終承認。
- **IPC 通信の拡張**: Rust Bridge に `/lobby/sync_user` エンドポイントを新設し、Python からのユーザー属性（IP/メールアドレス）同期を可能に。

### Changed

- **Discord OAuth2 フロー**: Cloudflare デバイス照合のため、認証スコープに `email` を追加。
- **ロビー削除の堅牢化**: DB制約に依存せず安全に削除できるよう、Rust Bridge 側で関連レコード（メンバー・試合）を明示的に事前クリーンアップするロジックを実装。

### Fixed

- **Cloudflare API 通信**: `per_page` パラメータの制限（最大100件）に伴う API エラー (400 Bad Request) を修正。
- **Jinja2 テンプレートエラー**: ユーザーID比較時の `str()` 呼び出しをパイプラインフィルタ `|string` に修正。

## [1.3.2] - 2026-02-26

### Added

- **Rust 権限評価エンジン** (`database_bridge/src/db/permission_repo.rs`)
  - Discord 権限フラグのビット演算による `needs_repair` 判定ロジックを Rust に実装
  - `POST /permissions/evaluate` エンドポイントを追加
  - チャンネル名ポリシーは `.env` の `MUTE_ONLY_CHANNEL_NAMES` / `READ_ONLY_CHANNEL_NAMES` から動的に読み込む
- **`.env.example`**: 全環境変数（Discord Bot / DB / Rust Bridge / 権限設定）のサンプルテンプレートを新規作成

### Changed

- **Python 権限判定の Rust 委譲**: `permission_service.py` の `needs_repair()` を async 化し、Rust Bridge `POST /permissions/evaluate` へ委譲
- **mass_mute ログ記録の Rust 統合**: `MassMuteLogic.save_log_to_db()` を async 化し、`LogService`（Rust Bridge 経由）への委譲に変更
- **設定の `.env` 統一**:
  - `bot.py` の `ADMIN_USER_ID`・`GUILD_ID` を `os.getenv()` に変更
  - `mass_mute/cog.py` の `ADMIN_USER_ID`・`MUTE_ONLY_CHANNEL_NAMES`・`READ_ONLY_MUTE_CHANNEL_NAMES` を `os.getenv()` に変更

### Removed

- **`services/database.py`**: SQLAlchemy エンジン設定ファイルを削除
- **`bot.py::get_db_connection()`**: mysql-connector-python による接続メソッドを削除
- **`MassMuteLogic.create_table_if_not_exists()`**: 起動時 DDL 実行メソッドを削除
- **`MassMuteLogic.save_log_to_db()`（旧実装）**: 直接 DB 書き込みロジックを削除
- **依存ライブラリ**: `SQLAlchemy`、`mysql-connector-python`、`PyMySQL`、`greenlet` を `requirements.txt` / `pyproject.toml` から削除

## [1.3.1] - 2026-02-25

Phase 3-C および 3-D (Hotfix) 完了。Rust Bridge の型不一致修正と、マスミュート機能の「真の自己修復」ロジックを導入。

### Added

- **Phase 3-C: Rust Bridge 完全統合とデプロイ自動化**
  - **HTTP IPC による分散構成**: Python Bot/Webapp が Rust Bridge 経由でデータベースを操作するアーキテクチャへの完全移行。
  - **CI/CD パイプライン強化**: GitHub Actions による自動ビルド・デプロイフローを構築。
- **Phase 3-D: Survey Recovery およびマスミュート自己修復の強化**
  - **セルフ・アンブロッキング (Self-unblocking)**: サーバーレベルの「ロールの管理」がある場合、Botが自律的にチャンネル制限を解除するロジックを実装。
  - **診断コマンド `!mute_check`**: 本番導入前にBotの権限と対象チャンネルの状態を一括診断するコマンドを追加。
  - **設計記録の拡充**: `docs/adr/005-phase3d-survey-response-fix.md`（Survey 根本原因・対策）、`docs/adr/006-phase3d-mass-mute-self-unblocking.md`（自己修復設計）を追加。

### Changed

- **Rust Bridge の堅牢化**
  - **型不一致の根本解決**: `DATETIME` 型非互換を SQL `CAST` で、`LONGTEXT` を `Vec<u8>` で処理する堅牢なデコード設計へ移行。
- **CSS 分割リファクタリング**: デザインの拡張性向上のため、スタイルシートを機能別に分割。
- **依存関係管理**: `uv` 使用時のパーミッションエラーを防ぐため、CI 時に `.venv` の所有権を自動修復するステップを追加。

### Fixed

- **Phase 3-D: ホットフィックス (Rust Bridge/Survey/Mass Mute)**
  - **DB文字化け解消**: 接続 URL への `charset=utf8mb4` 追加により日本語化けを修正。
  - **重複回答の防止**: `survey_responses` への UNIQUE KEY 手動追加手順を確立し、上書き保存を正常化。
  - **権限エラー通知**: `Forbidden` 発生時に不足権限と対処法を管理者へ詳細通知するよう改善。
- **Phase 3-C 修正**: 自動デプロイ時の sudo 権限問題や日付フォーマットの不一致を解除。
- **未使用コード削除**: Rust 側のビルドウオーニングを解消し、バイナリをクリーン化。

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
