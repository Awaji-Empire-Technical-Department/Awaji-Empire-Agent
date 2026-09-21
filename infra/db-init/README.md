# infra/db-init/

MariaDB コンテナの初回起動時（データボリュームが空の場合のみ）に、
公式イメージの `docker-entrypoint-initdb.d` フック経由で自動実行される
`*.sql` / `*.sh` を置くディレクトリです。

## 現状

`database_bridge/migrations/` は `003_*.sql` から始まっており、
`surveys` / `operation_logs` など一部のコアテーブルを作成するマイグレーションが
リポジトリに含まれていません（過去に手動適用されたまま追跡されなくなったため）。

そのため、まっさらな MariaDB コンテナ上では `sqlx::migrate!` 自体は成功しますが、
アンケート機能・操作ログ機能などはテーブル未作成でエラーになります。

## 使い方

既存の開発 / 本番 DB からスキーマダンプを取得できる場合は、
このディレクトリに `001_base_schema.sql` のようなファイルとして配置してください。
ファイル名の昇順で実行されます。

```bash
mysqldump --no-data --routines --triggers \
  -h <host> -u <user> -p <db_name> > infra/db-init/001_base_schema.sql
```

配置後、`docker compose down -v` でボリュームを作り直してから
`docker compose up --build` すると反映されます。
