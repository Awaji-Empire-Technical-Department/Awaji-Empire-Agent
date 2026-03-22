# ADR 011: #配信コメント チャンネル月次リセット機能

## ステータス

実装済 (Implemented)

## 背景と課題 (Context & Problem Statement)

Discord サーバー「淡路帝国」の `#配信コメント` チャンネルは配信中のコメント用途で使用されるが、月をまたいで古いコメントが蓄積し続ける問題があった。

1. **手動リセットの運用負荷**: これまでチャンネルの整理は管理者が手動で行っており、忘れがちで運用コストが高かった。
2. **権限の脆弱性**: チャンネルの overwrite 設定が外部から変更された場合、Bot が必要な権限を失い機能不全に陥る可能性があった。
3. **メッセージ一括削除の限界**: Discord API の `bulk_delete_messages` は 14 日以上前のメッセージに使えず、大量メッセージ削除はレート制限に抵触しやすい。

## 意思決定 (Decision)

### 1. リセット方式: チャンネル削除→再作成

メッセージ削除ではなく **チャンネル自体を削除→同名で再作成** する方式を採用。

* **不採用案**: `bulk_delete_messages` による段階的削除 — 14 日制限・レート制限・処理時間の問題で却下。
* **採用案**: `guild.create_text_channel` による再作成 — 1 回の API コールで完結し、overwrite もリセット時に正規状態に復元できる。

### 2. トリガー設計: VoiceKeeper 報告検知 + フォールバック cron

リセットタイミングは「配信終了直後」が最適だが、配信終了を直接検知する手段がないため、既存の VoiceKeeper 機能の寝落ち集計報告を間接的なトリガーとして活用する。

* **主トリガー**: `on_message` で VoiceKeeper が `#配信コメント` に投稿する寝落ち集計報告（キーワード `寝落ち` を含む Bot メッセージ）を検知 — 毎月 1 日のみ発火。
* **フォールバック**: `tasks.loop(hours=24)` で毎月 2 日 06:00 JST に未リセットなら補完実行。2 日を過ぎた場合はスラッシュコマンドのみ。
* **冪等性**: `_last_reset_month` で当月リセット済みかをメモリ上で追跡し、二重実行を防止。

### 3. Self Heal: Bot 権限の自動復元

`on_guild_channel_update` イベントで `#配信コメント` の変更を監視し、Bot の `manage_roles` overwrite が除去された場合に即座に再設定する。MassMute の Self Heal パターンを踏襲。

### 4. アーキテクチャ: 1 機能 1 ディレクトリ (README 準拠)

仕様書 v1.5.0 では単一ファイル `cogs/stream_comment_reset.py` と記載されていたが、プロジェクトの README 方針「1 機能 1 ディレクトリ」に準拠し、以下の 3 層に分離した。

| 層 | ファイル | 責務 |
|---|---------|------|
| Interface | `cogs/stream_comment_reset/cog.py` | イベントリスナー・スラッシュコマンド・cron 定義 |
| Logic | `cogs/stream_comment_reset/logic.py` | トリガー判定・overwrite 構築・リセット実行の指揮 |
| Service | `services/stream_comment_reset_service.py` | Discord API 操作・Bridge 通信（ステートレス） |

### 5. DB ログ: Rust Bridge 経由の永続化

リセット・Self Heal の実行ログを `stream_comment_reset_log` テーブルに記録。既存の `log_repo` / `LogService` パターンを踏襲し、Rust 側に `reset_log_repo` + ハンドラを追加。

* エンドポイント: `POST /reset_logs`（記録）, `GET /reset_logs`（一覧）, `GET /reset_logs/check_month`（当月実行済み判定）

## 結果 (Consequences)

### ポジティブな影響

* **運用自動化**: 月次リセットが完全自動化され、管理者の手動作業が不要になった。
* **耐障害性**: VoiceKeeper 報告 → フォールバック cron → スラッシュコマンドの 3 段構えにより、いずれかのトリガーが失敗しても対応可能。
* **権限の堅牢性**: Self Heal により、外部からの権限変更に対して Bot が自律的に復旧する。
* **仕様書との整合**: ディレクトリ構成の差分は仕様書 §4.1 を更新することで解消済み。

### ネガティブな影響 / 留意点

* **メモリ上の冪等性**: `_last_reset_month` は Bot 再起動時にリセットされる。DB の `check_month` エンドポイントを活用した永続的な冪等チェックへの移行を推奨（仕様書にも Note あり）。
* **cargo 未検証**: 実装環境に Rust ツールチェーンがないため、コンパイル検証はデプロイ環境で実施する必要がある。
* **Discord サーバー設定**: `/reset_stream_comments` コマンドは `default_member_permissions=Permissions(0)` で全員非表示にしているが、初回デプロイ時にサーバー設定 → アプリの統合で `管理者` ロールに許可を設定する手動作業が必要。
