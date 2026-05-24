# ADR-022: イベント締切自動処理・部制トグルUI

- **ステータス**: 採用
- **作成日**: 2026-05-25
- **作成者**: Wanyaldee
- **関連ドキュメント**: [ADR-021](021-event-form-system.md)

---

## コンテキスト

ADR-021 で実装したイベント参加フォームシステムには以下の運用上の課題が残っていた。

1. **締切処理が手動**: `application_deadline` はDB保存されているが、締切を過ぎても自動処理は行われず、オーナーが手動で「自動割り当て実行」→「Discord DM一斉通知」ボタンを押す必要があった。
2. **補欠（waitlist）の扱いが不明確**: 締切後に waitlist となった参加者への通知方法が定義されていなかった。
3. **部制なしのUIが不完全**: 部なし（`event_sessions` 0件）でも締切・日時・場所を設定したい場合、「部を追加」ボタンのみの設計では直感的でなかった。また、部制なしと n部制 の切り替えが明示的でなく、誤操作で設定が失われるケースがあった。

---

## 決定内容

### 1. 締切自動処理スケジューラー（bot.py）

`bot.py` の `on_ready` で非同期バックグラウンドタスクを起動し、**60秒毎**に以下を実行する。

```
1. Bridge GET /events/pending-deadline で締切済みイベントを取得
   （status が 'draft' または 'open' かつ application_deadline <= NOW()）
2. auto_assign を実行（希望部優先の自動割り当て）
3. status を 'closed' に更新
4. 参加者全員に Discord DM を送信
   - accepted  → 参加確定 + カレンダーURL
   - waitlist  → 参加不可通知（補欠繰り上げなし）
   - rejected  → 参加不可通知
5. 送信済みの参加者は notified_at をマークし二重送信を防ぐ
```

**補欠の扱い**: waitlist = 締切時点で確定できなかった = 実質不参加として通知する設計とした。空きが出た場合は管理者が手動で `accepted` に変更し、個別通知ボタンで対応する。

**スケジューラー選定**: `APScheduler` などのライブラリは導入せず、`asyncio.create_task` + `asyncio.sleep(60)` のシンプルなループとした。依存ライブラリを増やさず、Bot 起動中のみ有効な動作として十分なため。

### 2. Bridge: GET /events/pending-deadline

```sql
SELECT ... FROM events
WHERE status IN ('draft','open')
  AND application_deadline IS NOT NULL
  AND application_deadline <= NOW()
```

このエンドポイントはスケジューラー専用。一般ユーザーからのアクセスを想定しない。

### 3. 部制なし / n部制トグルUI（edit.html + edit_survey.js）

編集画面のイベント設定セクションに「部制なし（全員共通）」「n部制」のラジオボタンを追加。

| モード | 表示される設定項目 |
|---|---|
| 部制なし | 開始日時・終了日時・集合場所（イベント全体共通） |
| n部制 | 部リスト（部ごとに名称・日時・場所・定員） |

切り替え時の動作：
- n部制 → 部制なし: 全体共通の日時フィールドを表示し、部リストを非表示
- 部制なし → n部制: 部リストを表示。空の場合は「1部」を自動追加

保存時は `syncEventJson()` が `sessionMode` に応じて `sessions: []`（部制なし）または部リストをJSON化する。

### 4. 日時フォーマット変換（edit_survey.js）

DBから返る日時は `"YYYY-MM-DD HH:MM:SS"` 形式だが、HTML `datetime-local` が受け付けるのは `"YYYY-MM-DDTHH:MM"` 形式。`toDatetimeLocal()` ヘルパーで変換して復元することで、編集画面を開き直した際に日時フィールドが正しく表示されるようにした。

---

## 検討した代替案

### 締切スケジューラー: APScheduler を使う

- **却下理由**: 今回の用途（1分毎の軽量ポーリング）に対してライブラリの導入コストが不釣り合い。`asyncio.sleep` ループで十分なシンプルさを保てる。

### 補欠の自動繰り上げ

- **却下理由**: 繰り上げ判断（キャンセルの確認・通知のタイミング）は人間の判断を挟む方が適切。自動化によるトラブルリスクを避ける。管理者が手動で `accepted` に変更した後、個別DM送信で対応できる。

### 部制の専用フラグ（`sessions_enabled` カラム）

- **却下理由**: `event_sessions` の件数（0件=部制なし）で十分に状態を表現できる。専用フラグはスキーマを複雑にするだけで利点が少ない。UI上のラジオトグルは `sessions` 配列の `[]` / 非空 で保存時に自動的に反映される。

---

## 将来的な改善候補（未実装）

### 部制なし時の定員設定

現在、`events` テーブルには `capacity` カラムが存在しないため、部制なしイベントでは定員を設定できない。参加者が一定数を超える場合に waitlist を発生させたいケースがあるため、以下の対応が必要。

- DB: `events` テーブルに `capacity INT NULL` カラムを追加（migration）
- Rust: `insert_event` / `update_event` / `auto_assign` に capacity を組み込む（部制なし時に accepted 数が capacity を超えたら waitlist へ）
- Python: `EventService` の create/update に `capacity` パラメータを追加
- UI: edit.html の「部制なし」モードに定員フィールドを追加

### 回答フォームでの部ごとの集合場所表示

現在、フォーム回答画面（`form.html`）のイベント詳細カードには部ごとの日時は表示しているが、集合場所（`location`）が表示されていない。参加者が部を選ぶ際の重要情報であるため表示すべき。

- `form.html` の部選択セクション（`event_session` ループ）に `{% if s.location %}📍 {{ s.location }}{% endif %}` を追加

### 回答フォームでの定員・残席表示

現在、フォームには定員・残席数が表示されておらず、満席の部を選択できてしまう。以下の対応が必要。

- `view_form` ルートで `EventService.get_session_stats(event_id)` を追加し、部ごとの残席数を取得してテンプレートに渡す
- `form.html` で残席数を表示し、残席 0 の部のチェックボックスを disabled にする
- 残席数は `event_participants` の `approval = 'accepted'` の件数と `capacity` の差分で算出する（既存の `session_stats` ロジックを `event_admin.html` から流用）

---

## 影響範囲

| レイヤー | 変更内容 |
|---|---|
| DB | 変更なし（既存テーブルの `application_deadline` / `status` を活用） |
| Rust | `db/event_repo.rs`: `find_events_past_deadline()` 追加 |
| Rust | `api/handlers/event.rs`: `list_events_past_deadline` ハンドラー追加 |
| Rust | `api/mod.rs`: `GET /events/pending-deadline` ルート追加 |
| Python | `services/event_service.py`: `get_events_past_deadline()` 追加 |
| Python | `bot.py`: `_event_deadline_scheduler()` バックグラウンドタスク追加 |
| テンプレート | `edit.html`: 部制なし/n部制ラジオボタン、日時フィールド分離 |
| JS | `edit_survey.js`: `toDatetimeLocal()`, `applySessionMode()`, 部制トグルロジック更新 |
