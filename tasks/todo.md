# イベントフォーム拡張: スタッフ共同編集 / 回答削除 / 当日モード（2026-06-14）

## ステータス: 実装完了（DB適用・動作検証待ち）

- [x] DBマイグレーション `012_survey_collaborators.sql` / `013_event_checkin.sql`
- [x] Rust: `EventParticipant.checked_in_at`、survey_repo（collaborator/ユーザー検索）、response_repo（delete）、event_repo（checkin/delete）
- [x] Rust handler/route: スタッフAPI・ユーザー検索・本人回答削除・参加者削除・チェックイン（`cargo build` 通過）
- [x] Python service: survey_service / event_service ラッパー
- [x] Python route: 権限共通化（オーナー or スタッフ）、スタッフ管理API、本人回答削除、当日モード、checkin/delete API、CSV「来場」列
- [x] Template/JS: edit.html + staff_collaborators.js、form.html（回答削除）、event_admin.html + event_admin.js（削除・当日リンク）、event_checkin.html（新規）
- [x] ドキュメント: ADR-025、ADR README、EVENT_FORM_MANUAL.md
- [x] ギルドメンバー一括同期: lobby_repo.bulk_sync_usernames、`POST /lobby/bulk_sync_users`、LobbyService.bulk_sync_users、bot.py（on_ready 1回 + `/sync_members` コマンド）

### 残（デプロイ時）
- [ ] 本番/ステージング MySQL へ 012・013 を適用
- [ ] スタッフ追加→別アカウントで編集/管理アクセス、非スタッフ403 を実機確認
- [ ] 回答削除（本人・管理者）、当日モードのチェックイン動作を実機確認

---

# Phase 1 / Phase 2 実装計画

## ステータス: 実装完了（コードレビュー・DB適用待ち）

---

## Phase 1: 汎用大会システム + 称号システム

### 完了済み
- [x] `database_bridge/migrations/006_general_tournament.sql` — game_titles, match_scores, point_tables, titles, player_titles, player_active_title
- [x] `database_bridge/src/db/models.rs` — GameTitle, MatchScore, PointTable, Title, TitleWithStatus, Lounge系Struct追加
- [x] `database_bridge/src/db/tournament_repo.rs` — 大会・称号CRUD、自動称号付与ロジック
- [x] `database_bridge/src/api/handlers/tournament.rs` — HTTPハンドラ（スコア申告・承認・称号CRUD）
- [x] `database_bridge/src/api/mod.rs` — /tournament/* /titles/* ルーター登録
- [x] `discord_bot/services/tournament_service.py` — Bridge APIラッパー
- [x] `discord_bot/routes/tournament.py` — Blueprint（大会・称号API）
- [x] `discord_bot/webapp.py` — tournament_bp / lounge_bp 登録
- [x] `discord_bot/templates/tournament.html` — 大会進行UI
- [x] `discord_bot/static/js/tournament.js` — 大会JS（外部ファイル）
- [x] `discord_bot/static/css/tournament.css`
- [x] `discord_bot/templates/dashboard.html` — 称号管理カード追加
- [x] `discord_bot/static/js/dashboard_titles.js` — 称号管理JS（外部ファイル）

## Phase 2: ラウンジシステム

### 完了済み
- [x] `database_bridge/migrations/007_lounge.sql` — lounge_* テーブル
- [x] `database_bridge/src/db/lounge_repo.rs` — ラウンジDBクエリ（MMR・セッション・レース・チーム）
- [x] `database_bridge/src/api/handlers/lounge.rs` — HTTPハンドラ（セッション・レース・申告・承認）
- [x] `database_bridge/src/api/mod.rs` — /lounge/* ルーター登録
- [x] `discord_bot/services/lounge_service.py` — Bridge APIラッパー
- [x] `discord_bot/routes/lounge.py` — Blueprint
- [x] `discord_bot/templates/lounge.html` — ラウンジ進行UI
- [x] `discord_bot/static/js/lounge.js` — ラウンジJS（外部ファイル）
- [x] `discord_bot/static/css/lounge.css`

## 残タスク（未着手）

- [ ] ADR-011 更新（docs/adr/011-general-tournament-system.md）
- [ ] ADR-013 更新（docs/adr/013-lounge-system.md）
- [ ] Discord Cog: 称号ロール自動付与のトリガー統合（Discord Bot側）
- [ ] ラウンジMMR増減計算式の詳細設計（現在は単純スコア加算）
- [ ] tournament.htmlへの Bracketry ブラケット図統合（1v1用）

---

## Phase 3: ラウンジ申告方式リファクタリング（仕様変更）

### 背景・動機

参加型配信という特性上、レースごとの順位申告はゲームの流れを止める。
「セッション終了後に最終順位を1回だけ申告 → MMR・称号表示」方式に変更する。

### 影響範囲の全体像

| レイヤー | 変更の性質 | 主要ファイル |
|---------|-----------|------------|
| DB | テーブル追加・既存テーブルの役割変更 | `migrations/008_lounge_final_score.sql` |
| Rust DB層 | 新関数追加・既存申告関数の削除/無効化 | `lounge_repo.rs` |
| Rust API層 | エンドポイント追加・削除 | `handlers/lounge.rs` |
| Python Service | ラッパー追加・削除 | `lounge_service.py` |
| Python Route | ルート追加・削除 | `routes/lounge.py` |
| JS/HTML | 申告UIを全面置換 | `lounge.js`, `lounge.html` |
| ドキュメント | 仕様変更反映 | `FEATURE_LOUNGE.md`, ADR-018 |

### 設計方針

**残すもの:**
- `lounge_sessions` — セッション管理は変わらない
- `lounge_race_results` — コース管理（重複検知）のために存続。スコア管理責任は剥奪
- `lounge_course_history` — コース重複検知は継続
- `lounge_session_members` — 参加者管理は変わらない
- `lounge_teams`, `lounge_team_members` — チーム戦は将来対応で保持

**廃止するもの:**
- `lounge_race_scores` — レースごとの個人スコア管理は不要になる
- `report_score` / `report_disconnect` / `approve_race_scores` の申告フロー
- per-race WebSocketイベント: `lounge.score_reported`, `lounge.disconnect_reported`, `lounge.race_approved`
- フロントの申告フェーズモーダル（`#modal-phase-report`）

**追加するもの:**
- `lounge_session_final_scores` テーブル（session_id, user_id, final_rank）
- 最終順位申告 API: `POST /lounge/sessions/{id}/final-scores/report`
- セッション終了トリガー: 全員申告完了 or ホストが強制終了
- MMR計算: 最終順位ベースの固定デルタテーブル
- 結果表示: MMR増減 + 称号 をセッション終了時に一括表示

### 実装ステップ（承認待ち）

> **注意**: 各ステップは必ず順番通りに実施。後ろのステップは前の完了を前提とする。

#### Step 1: DB設計（新テーブル追加）
- [x] `migrations/008_lounge_final_score.sql` を作成
  - `lounge_session_final_scores`, `excluded` カラム追加
  - `lounge_race_scores`, `lounge_race_results`, `lounge_course_history` DROP
- [x] MMRデルタを Rust 定数 `MMR_DELTA[25]` として定義

#### Step 2: Rust DB層（lounge_repo.rs）
- [x] `report_final_score()` 追加
- [x] `get_final_scores()` 追加（全メンバー + 申告状況）
- [x] `calc_and_apply_mmr()` — トランザクションで MMR 計算・更新・返却
- [x] `toggle_exclude_player()` 追加
- [x] 旧関数（create_race, report_score 等）削除

#### Step 3: Rust API層（handlers/lounge.rs）
- [x] `POST /lounge/sessions/{id}/final-scores/report` 追加
- [x] `GET /lounge/sessions/{id}/final-scores` 追加
- [x] `POST /lounge/sessions/{id}/exclude` 追加（除外トグル）
- [x] `finish_session` を `calc_and_apply_mmr → finish → WS` フローに改修
- [x] 旧ハンドラ（create_race, report_score 等）削除

#### Step 4: Python Service / Route
- [x] `lounge_service.py`: `report_final_score()`, `get_final_scores()`, `exclude_player()` 追加
- [x] `routes/lounge.py`: 新ルート追加・旧ルート削除
- [x] `_do_finish_session()` を Bridge の MMR 結果を使う形に改修

#### Step 5: フロントエンド（lounge.js / lounge.html）
- [x] per-race申告モーダル・ロジックを削除
- [x] 最終順位申告モーダル実装（全員・リアルタイム状況表示）
- [x] ホスト用: 除外ボタン・終了確定ボタン
- [x] 結果モーダルを MMR増加・現在MMR・称号表示に変更
- [x] WS イベント: `lounge.final_score_reported`, `lounge.member_excluded` 対応

#### Step 6: ドキュメント・ADR
- [x] `FEATURE_LOUNGE.md` 仕様変更反映
- [x] `docs/adr/018-lounge-final-score-reporting.md` 作成
- [x] `ADR-013` に「仕様変更: Phase 3 参照」旨を追記

### 確定事項

1. **MMRデルタ**: 全順位プラスのみ（1位+150〜24位+5）。詳細は `FEATURE_LOUNGE.md` §10 参照。
2. **未申告者**: ホストが「除外」操作でMMR対象外にできる。最下位扱いはしない。
3. **回線落ち**: 最終順位として申告するだけで良い。特別処理なし。
4. **コース申告**: 廃止。`lounge_race_results` / `lounge_course_history` も削除対象。

### 削除対象の整理（Step 1〜6 実施時に合わせて削除）

| 削除対象 | 種別 | 理由 |
|---------|------|------|
| `lounge_race_results` テーブル | DB | コース管理不要になるため |
| `lounge_race_scores` テーブル | DB | per-race スコア管理廃止 |
| `lounge_course_history` テーブル | DB | コース重複検知廃止 |
| `report_score()` / `report_disconnect()` / `approve_race_scores()` | Rust | 申告フロー廃止 |
| `POST /lounge/races/{id}/scores/report` 等 3エンドポイント | API | 同上 |
| `#modal-phase-report` / `#modal-phase-setup` | HTML/JS | UI全面置換 |
| `lounge.score_reported` / `lounge.disconnect_reported` / `lounge.race_approved` | WS | イベント廃止 |
