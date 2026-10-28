# ADR-028: Docker Compose による開発環境の再現

- **ステータス**: 採用
- **作成日**: 2026-09-22
- **作成者**: Wanyaldee
- **ブランチ**: `fix/stream-comment-reset-fallback-silent-skip`

---

## 背景 (Context)

開発環境（MariaDB / database_bridge / discord_bot / webapp）を各自のマシンで
再現できるようにしたい。本番は Proxmox 上の単一 LXC ホストで、
`database_bridge` (Rust) / `bot.py` / `webapp.py` の3プロセスが systemd
ユニット (`infra/*.service`) として動き、すべて `127.0.0.1` 経由で通信する
（MariaDB のみ別 LXC）。

調査の結果、次の2点が Docker Compose 化の設計を左右することが分かった。

1. **Bridge のアドレスが3箇所で固定**されている。
   - `database_bridge/src/main.rs:54`: `SocketAddr::from(([127, 0, 0, 1], 7878))`
   - `discord_bot/services/bridge_client.py:12`: `BRIDGE_BASE_URL = "http://127.0.0.1:7878"`
   - `discord_bot/webapp.py:51`: `BRIDGE_WS_URL = "ws://127.0.0.1:7878/ws/hyouibana"`
   - `.env.example` の `BRIDGE_HOST`/`BRIDGE_PORT` は実際には一切参照されておらず、
     設定項目として死んでいる。
2. **`database_bridge/migrations/` が `003_*.sql` から始まっている**。
   `surveys` テーブルを作る 001/002 相当のマイグレーションがリポジトリに
   存在せず、まっさらな DB では `012_survey_collaborators.sql` の
   `FOREIGN KEY (survey_id) REFERENCES surveys(id)` が失敗する
   （`infra/db-init/README.md` に詳細）。過去の手動適用の記録が失われたもので、
   今回の作業では実際のスキーマを推測して補完することはしない
   （推測で書いた場合、本番と食い違うスキーマを「正」として配布するリスクが
   本物のスキーマ欠落より悪い）。

## 決定事項 (Decision)

`docker-compose.yml` に2サービスを定義する。

- `mariadb`: `infra/mariadb/` でラップした MariaDB 公式イメージ。
- `app`: `database_bridge` / `bot.py` / `webapp.py` を **同一コンテナ内**で
  `infra/app-entrypoint.sh` から起動する。アプリケーションコードは一切
  変更しない。

```yaml
# docker-compose.yml (抜粋)
app:
  build:
    context: .
    dockerfile: infra/app.Dockerfile
  env_file: ./discord_bot/.env
  environment:
    DB_HOST: mariadb
  ports:
    - "5000:5000"
  depends_on:
    mariadb:
      condition: service_healthy
```

```bash
# infra/app-entrypoint.sh (抜粋)
database_bridge &
BRIDGE_PID=$!
# ... /health をポーリングして起動待ち ...
cd /app
uv run bot.py &
BOT_PID=$!
uv run webapp.py &
WEBAPP_PID=$!
trap 'kill "$BRIDGE_PID" "$BOT_PID" "$WEBAPP_PID" 2>/dev/null' TERM INT
wait -n "$BRIDGE_PID" "$BOT_PID" "$WEBAPP_PID"
```

```dockerfile
# infra/app.Dockerfile / infra/mariadb/Dockerfile (抜粋)
# 両方とも本番と同じ Ubuntu 24.04 をベースイメージにする。
FROM ubuntu:24.04 AS bridge-builder   # rustup で Rust を導入して cargo build
FROM ubuntu:24.04                     # apt の python3.12 で uv sync / uv run
FROM ubuntu:24.04                     # apt の mariadb-server (mariadb)
```

```bash
# infra/mariadb/docker-entrypoint.sh (抜粋)
# 公式 mariadb イメージを使わないため、初期化ロジックを自前で持つ。
if [ -z "$(ls -A "$DATADIR" 2>/dev/null)" ]; then
    mariadb-install-db --user=mysql --datadir="$DATADIR" \
        --auth-root-authentication-method=normal >/dev/null
    mariadbd --user=mysql --datadir="$DATADIR" --skip-networking --socket="$SOCKET" &
    # ... 起動待ち ...
    mariadb --socket="$SOCKET" -uroot <<-EOSQL
        CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4;
        ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
        CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
        GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
        FLUSH PRIVILEGES;
EOSQL
    # ... /docker-entrypoint-initdb.d/*.sql を適用 ...
fi
exec mariadbd --user=mysql --datadir="$DATADIR" --bind-address=0.0.0.0
```

## 根拠 (Reason)

- **すべてのイメージを `ubuntu:24.04` にした理由**: README に記載の本番構成
  （`OS: Ubuntu 24.04 LTS / MariaDB (LXC)`）と揃えることで、「Docker では
  動くが本番の Ubuntu だと動かない」という差分を開発時点で検出できるように
  する（例: apt パッケージのバージョン差、glibc 差）。Rust は Ubuntu の apt
  版 rustc が古い可能性があるため rustup で導入し、MariaDB は逆に
  公式 Docker イメージ（Debian ベース）ではなく apt の `mariadb-server`
  （`10.11.14-MariaDB-0ubuntu0.24.04.1`、実機ビルドで確認）を使うことで
  本番と同じパッケージ由来のバイナリになる。
- **MariaDB を自前の `docker-entrypoint.sh` で初期化する理由**: 公式
  `mariadb` Docker イメージが持つ初期化ロジック（`MARIADB_ROOT_PASSWORD`
  等の環境変数処理、`docker-entrypoint-initdb.d` 対応）は Debian ベースの
  独自実装であり、`ubuntu:24.04` + apt の `mariadb-server` にはそのまま
  移植できない。データディレクトリが空のときだけ
  `mariadb-install-db` → 一時起動 → `CREATE DATABASE` / パスワード設定 →
  `/docker-entrypoint-initdb.d/*.sql` 適用 → 停止、という最小限の手順を
  実装し、２回目以降の起動（ボリュームにデータが残っている場合）は
  そのまま `mariadbd` を起動するだけにした。
- **`CREATE USER IF NOT EXISTS 'root'@'%'` を追加した理由**:
  `mariadb-install-db --auth-root-authentication-method=normal` が作るのは
  `'root'@'localhost'` のみで、別コンテナ（`app`）から TCP 越しに接続すると
  `Host '...' is not allowed to connect to this MariaDB server` で拒否
  される（実機で確認）。`app` は Docker ネットワーク経由の別ホストとして
  接続するため、`'root'@'%'` にも同じパスワードを設定する必要がある。
- **同一コンテナに3プロセスをまとめた理由**: 最初はサービスごとに
  コンテナを分け、`network_mode: "service:database_bridge"` で
  discord_bot/webapp を bridge のネットワーク名前空間に参加させる案を
  検証した（コード変更ゼロを維持できるため）。実機検証すると、
  名前空間を共有する側のコンテナでは Docker の埋め込みDNS
  (`127.0.0.11`) が機能せず、`mariadb` はおろか `discord.com` すら
  名前解決できなかった（`docker exec ... python3 -c "socket.gethostbyname('mariadb')"`
  が `Temporary failure in name resolution` で失敗、対して名前空間の
  所有者である `database_bridge` 自身は成功する非対称な挙動を確認）。
  同一コンテナにまとめれば、`app` は compose ネットワークの正規のメンバーに
  なるため DNS が普通に機能し、かつ `127.0.0.1:7878` 固定のコードにも
  一切手を入れずに済む。本番も同一ホスト上で3プロセスが `127.0.0.1`
  経由で通信する構成であり、単一コンテナはその構成をそのまま写した形になる。
- **`wait -n "$BRIDGE_PID" "$BOT_PID" "$WEBAPP_PID"` で3プロセスいずれかの
  終了をコンテナ終了として扱う理由**: bridge がマイグレーション失敗で
  `std::process::exit(1)` する場合や、`DISCORD_TOKEN` が未設定/無効で
  `bot.py` が即座に終了する場合、他の2プロセスだけゾンビ状態で
  動き続けるより、`restart: unless-stopped` でコンテナごと再起動させ、
  ログで異常に気付けるようにした方が「動いているように見えて実は
  壊れている」状態を避けられる。
- **`docker-entrypoint-wrapper.sh` で `DB_NAME`/`DB_PASS` を
  `MARIADB_DATABASE`/`MARIADB_ROOT_PASSWORD` にマッピングした理由**:
  `discord_bot/.env` の `DB_USER=root, DB_PASS=`（空）という既定値と、
  MariaDB 公式イメージが要求する `MARIADB_ROOT_PASSWORD` の間には
  そのままでは対応がない。`docker-compose.yml` の `environment:` に
  `${DB_PASS}` と書いても、compose の変数展開はプロジェクトルートの
  `.env`（今回は存在しない）しか見ないため、`discord_bot/.env` の値を
  拾えず空文字にフォールバックしてしまう（実機で
  `Access denied for user 'root'@'...' (using password: NO)` を確認済み）。
  コンテナ内で `env_file` 経由の実際の環境変数を読んでからマッピングする
  ことで、`discord_bot/.env` を唯一の情報源に保てる。
- **`MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=yes` を常に設定する理由**:
  `.env.example` の既定値 `DB_PASS=`（空）をそのまま使ったときに
  MariaDB 公式イメージが「パスワード未設定はエラー」として起動を拒否する
  のを防ぐため。`DB_PASS` に値を入れれば `MARIADB_ROOT_PASSWORD` が
  その値になり、空パスワード許可フラグは無視されるだけなので、
  空・非空どちらでも同じ設定で動く。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| サービスごとに分離したコンテナ + `network_mode: "service:database_bridge"` | 実機検証で DNS が機能しないことを確認したため不採用（上記根拠を参照）。 |
| `main.rs` の bind 先を `0.0.0.0` にし、`webapp.py`/`bridge_client.py` を未使用の `BRIDGE_HOST`/`BRIDGE_PORT` を読むよう修正 | ユーザーの選択により不採用。アプリ本体（Rust/Python）を3箇所変更することになり、Docker対応のためだけに本番コードへ手を入れる範囲が広がる。 |
| `001_base_schema.sql` 相当を推測して作成し、まっさらな DB でも全機能が動くようにする | ユーザーの選択により不採用。実際の本番スキーマ（`surveys` の列構成など）を確認できておらず、憶測で書いたスキーマを「正」として配布するリスクの方が、欠落を明示して initdb フックを用意するより大きいと判断（`infra/db-init/README.md` に委譲）。 |

## 影響 (Consequences)

### ポジティブ

- `docker compose up --build` だけで MariaDB を含む開発環境一式が起動する。
- `discord_bot/.env` を唯一の情報源として、bare-metal 実行と Docker 実行の
  両方で同じファイルを使い回せる。
- アプリケーションコード（Rust/Python）は無変更。

### ネガティブ・トレードオフ

- `app` コンテナは1コンテナに3プロセスが同居するため、本番の
  systemd 3ユニット構成ほど個別の再起動・監視の粒度は細かくない
  （ponytail: 3プロセスのうちどれか1つが落ちると `wait -n` で
  コンテナ全体が再起動する。将来 supervisord 等で個別再起動にする
  余地はあるが、開発用途では現状で十分と判断）。
- `database_bridge/migrations/` の base schema 欠落は未解決のまま
  （`infra/db-init/` にフックのみ用意）。実データに近い形で動作確認したい
  場合は、既存 DB から `mysqldump --no-data` したスキーマを
  `infra/db-init/` に置く必要がある。
- `infra/mariadb/docker-entrypoint.sh` は公式 MariaDB Docker イメージの
  初期化ロジックのうち今回必要な範囲（データディレクトリ初期化・
  root パスワード設定・`docker-entrypoint-initdb.d` 適用）のみを実装した
  最小限のものであり、`MARIADB_USER`/`MARIADB_PASSWORD` 相当の
  非root ユーザー作成や `_FILE` サフィックスでのシークレット読み込みなど、
  公式イメージが持つ機能はカバーしていない
  （ponytail: 必要になった時点で `docker-entrypoint.sh` に追加する）。
- `discord_bot/.env` に `DB_USER` として `root` 以外を設定する場合、
  `infra/mariadb/docker-entrypoint-wrapper.sh` に
  `MARIADB_USER`/`MARIADB_PASSWORD` の設定を追加する必要がある
  （現状は root 決め打ち）。

## 検証 (Verification)

- `docker compose config` で構文検証。
- `docker compose build` で `app` (rustup+cargo build → apt python3.12) /
  `mariadb` (apt mariadb-server) を `ubuntu:24.04` ベースでビルドできることを
  確認。`mariadb -V` 相当のログで `10.11.14-MariaDB-0ubuntu0.24.04.1` /
  `Ubuntu 24.04` を確認。
- `docker compose up -d` でスタック起動 → `mariadb` の healthcheck
  (`mariadb-admin ping ... --password="$DB_PASS"`) が `healthy` になるが、
  最初は `app` からの接続が `Host '...' is not allowed to connect` で拒否
  されることを確認 → `docker-entrypoint.sh` に `'root'@'%'` 作成を追加して
  解消（上記根拠を参照）。
- 修正後、`app` が `mariadb` へホスト名で接続・マイグレーション実行まで
  進むことをログで確認（`✅ Database connection pool created.` 等）。
- 実際のマイグレーション実行は `012_survey_collaborators.sql` の
  `surveys` テーブル欠落により失敗することを確認（既知の欠落、上記参照）。
  インフラ自体の健全性を切り分けるため、検証専用の最小スタブ
  （`CREATE TABLE IF NOT EXISTS surveys (id INT AUTO_INCREMENT PRIMARY KEY);`）
  を一時的に `infra/db-init/` に置いて再実行し、
  全マイグレーション成功・`database_bridge` が `127.0.0.1:7878` で
  listen・`webapp.py` が `0.0.0.0:5000` で起動・`GET /` が 302 (→
  `/login` へリダイレクト) を返すことを確認した上で、このスタブは
  削除済み（本物のスキーマではないため配布物には含めない）。
- `bot.py` は `DISCORD_TOKEN` がプレースホルダーのままだと
  `Invalid token` で終了することを確認（想定通りで、実トークン設定後の
  Discord 側ログインまでは未検証）。
