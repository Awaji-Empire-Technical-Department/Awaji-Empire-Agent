# 旧コード ロジックリファレンス

> [!NOTE]
> Phase 2 アーキテクチャ刷新で削除・移行されたファイルのロジックを記録するドキュメント。
> セキュリティ・リソース節約の観点から `.example` ファイルは保持せず、
> ロジックの概要をこのドキュメントに集約する。
> 完全なコードは Git 履歴（`feature/refactor-services-layer` ブランチ）から参照可能。

---

## 1. `cogs/filter.py`（削除）

**目的**: 特定チャンネル（`CODE_CHANNEL_ID`）で添付ファイルなしメッセージを自動削除

```python
# FilterCog のコアロジック
# - on_message イベントで CODE_CHANNEL_ID を監視
# - 添付ファイルがなければ message.delete() で削除
# - 削除時に管理者へ DM で警告通知
# - config.py の CODE_CHANNEL_ID, ADMIN_USER_ID を使用

@commands.Cog.listener()
async def on_message(self, message):
    if message.author.bot: return
    if message.channel.id != self.code_channel_id: return
    if not message.attachments:
        await message.delete()
        # 管理者にDMで警告
```

**削除理由**: 仕様変更により不要（Phase 2 §5）

---

## 2. `cogs/mass_mute.py`（→ `cogs/mass_mute/` ディレクトリ化）

**移行先**: `cogs/mass_mute/cog.py` + `cogs/mass_mute/logic.py` + `services/permission_service.py`

```python
# 旧 MassMuteCog の構造
# - 権限定義: SEND_OK_OVERWRITE, SEND_NG_OVERWRITE
# - __init__: daily_mute_check.start(), create_table_if_not_exists()
# - execute_mute_logic(trigger):
#   1. MUTE_ONLY_CHANNEL_NAMES → SEND_OK_OVERWRITE を適用
#   2. READ_ONLY_MUTE_CHANNEL_NAMES → SEND_NG_OVERWRITE を適用
#   3. DBにログ保存 (mute_logs テーブル)
#   4. 管理者にEmbed DM送信
# - daily_mute_check: UTC 0:00/8:00/16:00 に実行（※JST変換ミスあり→修正済み）
# - on_guild_channel_create: pass のみ（未実装）
```

**変更点**: 自己修復機能追加、services層分離、定時タスクのJST修正

---

## 3. `cogs/survey.py`（→ `cogs/survey/` ディレクトリ化）

**移行先**: `cogs/survey/cog.py` + `cogs/survey/logic.py`

```python
# 旧 SurveyCog の構造
# - cog_load: aiomysql プール作成
# - survey_group: /survey グループコマンド
#   - /survey create: ダッシュボードURL案内
#   - /survey list: 稼働中アンケート一覧表示
#   - /survey my_active: 自分の稼働中アンケート表示
#   - /survey announce: 管理者用周知コマンド
# - DB操作: self.pool を直接使用（→ SurveyService に移行）
```

---

## 4. `cogs/voice_keeper/main.py`（→ `cogs/voice_keeper/cog.py`）

**移行先**: `cogs/voice_keeper/cog.py` + `cogs/voice_keeper/logic.py`

```python
# 旧 VoiceKeeper (main.py) の構造
# - _env_int, _env_bool: 環境変数読込ヘルパー
# - __init__: TARGET_USER_ID, ACTIVE_START/END_HOUR, TIMEOUT_SECONDS 設定
# - _watch_and_execute(guild_id, channel_id):
#   1. timeout_seconds 秒待機
#   2. ホストが元VCに戻っていれば何もしない
#   3. 時間外ならスキップ
#   4. service.kick_all_non_bots → service.send_report → service.log_summary
# - on_voice_state_update: ターゲットユーザーのVC退出/移動を検知→タイマー開始
```

**変更点**: logic.py に watch_and_execute を移動、services/ 層に I/O 操作を移動

---

## 5. `cogs/voice_keeper/services.py`（→ `services/voice_keeper_service.py`）

**移行先**: `services/voice_keeper_service.py`

```python
# 旧 VoiceKeeperService の構造（インスタンスメソッド）
# - __init__(report_channel_name): メンバ変数で report_channel_name を保持
# - kick_all_non_bots(channel): Bot以外を move_to(None) で切断
# - send_report(guild, kicked_count): レポートチャンネルに集計送信
# - log_summary(...): ログ出力
```

**変更点**: 全メソッドを `@staticmethod` 化。`report_channel_name` は引数として受け取る設計に変更

---

## 6. `database.py`（→ `services/database.py`）

**移行先**: `services/database.py`

```python
# 旧 database.py の構造
# - config.py の DB_CONFIG をインポートして接続URL構築
# - SQLAlchemy Engine を create_engine() で作成
# - get_engine() で Engine を返す
```

**変更点**: `config.py` の `DB_CONFIG` 依存をやめ、環境変数から直接構築

---

## 7. `utils.py`（→ `services/log_service.py`）

**移行先**: `services/log_service.py`

```python
# 旧 utils.py の構造
# - log_operation(pool, user, command, detail):
#   - user は Dict[str, Any]（user['id'], user['name']）
#   - aiomysql で operation_logs テーブルに INSERT
```

**変更点**: `user` 辞書の引数を `user_id: str` + `user_name: str` に分離（ctx 非依存化）

---

## 8. `routes/survey.py`（薄層化）

**移行先**: DB操作→`services/survey_service.py`、DM→`services/notification_service.py`、`parse_questions`→`common/survey_utils.py`

```python
# 旧 routes/survey.py の構造（414行）
# - send_dm_notification: httpx で Discord API 直叩き
# - parse_questions: JSON パース + サニタイズ
# - ルート関数内に aiomysql の直接操作が混在
#   - create_new, edit_survey, save_survey, toggle_status, delete_survey
#   - view_form, submit_response, view_results, download_csv
```

**変更点**: ルーティング関数は「交通整理」に徹し、約260行に削減
