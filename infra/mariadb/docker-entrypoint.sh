#!/bin/bash
# Why: 本番と同じ Ubuntu 24.04 の apt パッケージ (mariadb-server) を使うため、
#      MariaDB公式Dockerイメージの初期化ロジック (docker-entrypoint.sh) が
#      使えない。discord_bot/.env (DB_NAME / DB_USER / DB_PASS) を唯一の
#      情報源として、データディレクトリが空のときだけ初期化する最小限の
#      代替実装 (ADR-028)。DB_USER=root 以外を使う場合は、このスクリプトに
#      ユーザー作成処理を追加すること。
set -e

DATADIR=/var/lib/mysql
SOCKET=/run/mysqld/mysqld.sock
DB_NAME="${DB_NAME:-bot_db}"
DB_ROOT_PASSWORD="${DB_PASS:-}"

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

if [ -z "$(ls -A "$DATADIR" 2>/dev/null)" ]; then
    echo "[entrypoint] initializing MariaDB data directory..."
    mariadb-install-db \
        --user=mysql \
        --datadir="$DATADIR" \
        --auth-root-authentication-method=normal \
        >/dev/null

    mariadbd --user=mysql --datadir="$DATADIR" --skip-networking --socket="$SOCKET" &
    tmp_pid=$!

    echo "[entrypoint] waiting for temporary server to accept connections..."
    for _ in $(seq 1 30); do
        if mariadb-admin --socket="$SOCKET" ping >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    mariadb --socket="$SOCKET" -uroot <<-EOSQL
        CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4;
        ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
        -- app コンテナは別ホストから TCP 接続するため 'root'@'%' も作成する。
        CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
        GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
        FLUSH PRIVILEGES;
EOSQL

    if [ -d /docker-entrypoint-initdb.d ]; then
        for f in /docker-entrypoint-initdb.d/*; do
            [ -e "$f" ] || continue
            case "$f" in
                *.sql)
                    echo "[entrypoint] applying $f"
                    mariadb --socket="$SOCKET" -uroot --password="$DB_ROOT_PASSWORD" "$DB_NAME" < "$f"
                    ;;
                *.sh)
                    echo "[entrypoint] running $f"
                    . "$f"
                    ;;
                *)
                    echo "[entrypoint] skipping $f (unsupported extension)"
                    ;;
            esac
        done
    fi

    mariadb-admin --socket="$SOCKET" -uroot --password="$DB_ROOT_PASSWORD" shutdown
    wait "$tmp_pid" || true
    echo "[entrypoint] initialization complete."
fi

exec mariadbd --user=mysql --datadir="$DATADIR" --bind-address=0.0.0.0
