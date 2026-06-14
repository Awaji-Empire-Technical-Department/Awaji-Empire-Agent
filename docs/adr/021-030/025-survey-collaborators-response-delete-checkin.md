# ADR-025: スタッフ共同編集 / 回答削除 / 当日モード（チェックイン）

- **ステータス**: 採用
- **作成日**: 2026-06-14
- **作成者**: Wanyaldee

---

## コンテキスト

オフ会の参加集計にイベント参加フォーム（ADR-021）を本格運用するにあたり、
実運用で不足していた3点を補う。

1. **スタッフ共同編集** — フォームは単一 `owner_id` のみが編集・管理可能で、
   チーム運営でオーナー以外がイベント管理（応募確認・割り当て・通知）に関与できなかった。
2. **回答削除** — 回答者が選択を間違えても自分で取り消す手段がなかった。
3. **当日モード** — オフ会当日の受付（来場確認）を記録する仕組みがなかった。

本システムは Python(webapp) が DB を直接持たず、すべて Rust Bridge（`database_bridge`）
経由で通信する。各機能とも DB → Rust repo → Rust handler → Python service → route → template
の全レイヤーを縦断する。

---

## 決定内容

### 1. スタッフ共同編集（survey_collaborators）

- 新テーブル `survey_collaborators(survey_id, user_id, added_at)`（マイグレーション 012）。
- スタッフの指定は **ユーザー名検索 → 追加** 方式。検索ディレクトリは既存の
  `user_networks` テーブル（ダッシュボードログイン時に `discord_id`/`username` を同期）を流用。
  → 別途メンバー同期基盤を新設せず、既存資産で実現（KISS）。
- 権限モデル:
  | 操作 | 許可範囲 |
  |---|---|
  | フォーム編集 / イベント管理 / 応募確認 / 割り当て / 通知 / 当日受付 | オーナー **または** スタッフ |
  | スタッフの追加・削除 | **オーナーのみ** |
  | フォーム削除・公開トグル | **オーナーのみ**（破壊的・公開制御のため据え置き） |
- Python 側は各ルートで `owner_id == user_id` OR `SurveyService.is_collaborator(...)` を判定。
  `survey_repo::delete` の owner 照合は維持し、削除はオーナー専用を Rust 層でも担保。

### 2. 回答削除（本人＋管理者）

- **本人**: フォーム画面（既存回答あり時）に「この回答を削除」ボタン。
  `POST /survey/delete_my_response` がセッションの user_id で本人の回答のみ削除。
  Rust `response_repo::delete_by_user` が survey_id + user_id 照合で削除し、
  紐づく `event_participants` も `event_repo::delete_participant_by_response` で併せて削除。
- **管理者**: イベント管理画面の応募行に削除ボタン。
  `DELETE /event/<event_id>/api/participant/<id>` をオーナー/スタッフ権限で保護し、
  参加者とアンケート回答を `event_repo::delete_participant_and_response` で削除。

### 3. 当日モード（チェックイン）

- `event_participants.checked_in_at DATETIME NULL` を追加（マイグレーション 013）。
- 管理画面に「当日モード（受付）」リンク → 専用ページ `GET /event/<id>/checkin`。
  承認済み参加者を部ごとに一覧し、大きなトグルで受付（来場/取消）。
  → 当日に開きっぱなしで使う想定のため、管理画面のクエリ分岐ではなく専用ルートとした。
- `POST /event/<id>/api/participant/<pid>/checkin` が `checked_in_at` を NOW()/NULL に更新。
- CSV エクスポートに「来場」列を追加。

---

## 検討した代替案

### スタッフを Discord ロール / 環境変数で指定

- **却下理由**: ロール指定は対象フォームを限定できず、環境変数は UI を持てない。
  フォーム単位で運営メンバーを選べる「ユーザー名検索＋テーブル」方式が運用に合う。

### 回答削除を管理者のみに限定

- **却下理由**: 「間違えた本人がすぐ直したい」という主目的を満たせない。本人削除を主とし、
  管理者削除を補助とした。

### 当日モードを既存の応募一覧に列追加のみで実装

- **却下理由**: 当日の受付端末では「承認済みだけを大きく・タップしやすく」表示したい。
  管理画面の高密度テーブルとは UI 要件が異なるため専用ページを採用。

---

## 影響範囲

| レイヤー | 主な変更 |
|---|---|
| DB | `migrations/012_survey_collaborators.sql`, `013_event_checkin.sql` |
| Rust models | `EventParticipant.checked_in_at` 追加 |
| Rust repo | `survey_repo`(collaborator/user検索), `response_repo`(delete), `event_repo`(checkin/delete) |
| Rust handler/route | `handlers/mod.rs`・`handlers/event.rs`・`api/mod.rs` にエンドポイント追加 |
| Python service | `survey_service`・`event_service` にラッパー追加 |
| Python route | `routes/survey.py`（権限共通化・スタッフAPI・本人削除・CSV来場列）, `routes/event.py`（権限緩和・当日モード・checkin/delete API） |
| Template/JS | `edit.html`+`staff_collaborators.js`, `form.html`, `event_admin.html`+`event_admin.js`, `event_checkin.html`（新規） |
| Docs | `EVENT_FORM_MANUAL.md` 追記, 本 ADR |

---

## 追補: ギルドメンバーの一括同期

スタッフ検索の母集団 `user_networks` をダッシュボードのログイン者だけに依存させず、
**Bot がギルド全メンバーを一括同期**するようにした。

- Bot は `intents.members` を持つため、メンバー取得は**ゲートウェイのチャンク**（キャッシュ）を
  使い、Discord への REST 呼び出しは発生しない（約650人でもゲートウェイ1チャンク程度）。
- DB 書き込みは 1 件ずつ HTTP すると同人数分の往復になるため、**バッチ upsert** を新設。
  `POST /lobby/bulk_sync_users` → `lobby_repo::bulk_sync_usernames` が
  `INSERT ... VALUES (...),(...) ON DUPLICATE KEY UPDATE username=VALUES(username)` を実行。
  Bot 側は 200 件ずつ送信するため、650人なら Bridge 呼び出しは 4 回程度。
- `user_networks.email` は `NOT NULL`。新規行は `email=''` で作成し、既存行の email/virtual_ip は
  上書きしない（Discord はメールを提供しないため username のみ更新）。
- 実行契機: Bot 起動時に1回（`on_ready`、再接続では重複実行しないようフラグでガード）＋
  管理者用スラッシュコマンド `/sync_members` で任意に再同期可能。
- 回答削除・参加者削除は物理削除。監査が必要になった場合は操作ログ（`LogService`）への記録、
  もしくは論理削除への移行を検討する。
