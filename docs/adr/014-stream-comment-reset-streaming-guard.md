# ADR 014: 配信中リセットガード（フェールセーフ）

## ステータス

実装済 (Implemented)

## 背景

`/reset_stream_comments` スラッシュコマンドを配信中に誤発火させてしまった際、チャンネル削除→再作成によって Discord がリスナー全員に通知を送り、その通知音が作業等を妨害するという問題が発生した。

通知の無効化を試みたが Discord の仕様上、チャンネル再作成通知はユーザー側の設定に依存するため、Bot 側から完全に回避する手段がなかった。

## 決定

`/reset_stream_comments`（`dry_run=False`）実行時に、`TARGET_USER_ID` が VC に在席中であれば即座にブロックする。

- **配信中の定義**: `TARGET_USER_ID`（社畜天狗）が任意の VC チャンネルに在席している状態
- **配信終了の定義**: Voice Keeper が寝落ち集計報告を投稿した時点（= `is_host_in_vc` が `False` になる）
- `dry_run=True` は破壊的操作を伴わないため、配信中でも許可する
- 自動トリガー（VoiceKeeper 報告・fallback cron）は設計上すでに配信終了後にのみ発火するため対象外

## 実装

- `logic.py`: `StreamCommentResetLogic.is_host_in_vc(guild, target_user_id) -> bool` を追加
- `cog.py`: `reset_stream_comments` コマンドに `is_host_in_vc` チェックを追加、ブロック時は ephemeral でエラーを返す

## 却下した選択肢

**A. 配信フラグをメモリ上で管理する**
- `on_voice_state_update` で `is_streaming` フラグを更新する案
- ホストの VC 入室は VoiceKeeper が監視していないため追加実装が必要
- Bot 再起動でフラグが消失するリスクがある
- リアルタイムの `member.voice` チェックで十分なため不採用

**B. 配信中の通知を完全に抑制する**
- Discord API にはチャンネル再作成通知を Bot 側から抑止する手段がない
- 根本解決にならないため不採用

## トレードオフ

- ホストが VC に居る間は管理者による緊急リセットも不可能になる
- これは意図的な制約（配信中は通知音の方が問題）
- 緊急時は `dry_run=True` でプレビューを確認し、配信終了後に実行する運用で対応
