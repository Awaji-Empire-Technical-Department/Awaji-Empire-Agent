---
name: docker-visual-verification
description: 単体テスト・ユニットテストが完了した後、Docker Composeでコンテナを起動し目視確認を行う手順
---

# Docker Compose での目視確認

このリポジトリでコードを変更した場合、**自動テストが通っただけでは完了と
しない**。テストは「壊れていないか」しか見ておらず、実際にコンテナを
起動してユーザーが触る経路（Webダッシュボード・Bot のログイン等）が
本当に動くかは目視でしか確認できない。

## 手順

### 1. 自動テストを先に実行する

- Python (`discord_bot/`): `cd discord_bot && uv run pytest`
- Rust (`database_bridge/`): `cd database_bridge && cargo test`

変更した箇所に対応するテストが存在する場合は必ず実行し、失敗を解消して
から次のステップに進む。対応するテストが無い変更については、その旨を
報告に明記する（「テスト無し、目視のみで確認」）。

### 2. Docker Compose でコンテナを起動する

```bash
docker compose up --build -d
docker compose ps
```

`docker compose ps` で全サービスが `Up`（`mariadb` は `healthy`）に
なっていることを確認する。`Restarting` を繰り返している場合はログを見て
原因を特定してから先に進む。

```bash
docker compose logs -f app
docker compose logs mariadb
```

### 3. 目視確認する

変更内容に応じて、実際に動作を確認する。コマンドの出力を貼り付けるだけで
済ませず、**何を確認して何が見えたか**を報告する。

- **Web ダッシュボード / routes / templates を変更した場合**:
  `http://localhost:5000` をブラウザで開く（または
  `curl -i http://localhost:5000/対象パス`）。変更した画面・API の
  レスポンスが期待通りかを直接確認する。
- **Discord Bot (`bot.py` / `cogs/`) を変更した場合**:
  `docker compose logs app` で `discord.client` のログイン成功ログ
  （`logging in using static token` の後にエラーが出ていないこと）を
  確認する。実際に Discord 上でコマンド/イベントを発火できる場合は
  それも行う。
- **database_bridge (Rust) を変更した場合**:
  `docker compose logs app` で `✅ Database migrations applied
  successfully.` と `📡 Listening on 127.0.0.1:7878` が出ていることを
  確認し、関連する API を `curl` 等で叩いて期待したレスポンスが返るかを
  確認する。
- **マイグレーションを追加した場合**:
  `docker compose down -v` でボリュームごと作り直してから
  `docker compose up --build -d` し、まっさらな DB に対してマイグレーション
  が最後まで成功することを確認する
  （既知の欠落については `infra/db-init/README.md` 参照）。

### 4. 後片付け

```bash
docker compose down -v
```

検証用に一時的なスタブファイル（`infra/db-init/` への仮のスキーマ等）を
置いた場合は、確認後に必ず削除する。配布物に憶測で書いたスキーマや
テスト専用の値を残さない。

## 報告時の注意

- 「動くはずです」で済ませない。実際に確認したコマンドと結果を報告する。
- 確認できなかった項目（例: 実際の Discord トークンが無くログインまでは
  未確認、など）は「未検証」として明示する。
