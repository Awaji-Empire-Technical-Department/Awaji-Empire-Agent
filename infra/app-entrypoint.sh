#!/bin/bash
# Why: database_bridge (Rust) / bot.py / webapp.py の3プロセスを同一コンテナ内で
#      起動する。本番の systemd 3ユニット構成 (infra/*.service) を単一コンテナに
#      写したもので、127.0.0.1 経由のアプリ間通信をコード変更なしで成立させる
#      (ADR-028)。
set -e

database_bridge &
BRIDGE_PID=$!

echo "[entrypoint] waiting for database_bridge on :7878 ..."
for _ in $(seq 1 30); do
    if python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:7878/health', timeout=1)" >/dev/null 2>&1; then
        echo "[entrypoint] database_bridge is up"
        break
    fi
    sleep 1
done

cd /app
uv run bot.py &
BOT_PID=$!

uv run webapp.py &
WEBAPP_PID=$!

trap 'kill "$BRIDGE_PID" "$BOT_PID" "$WEBAPP_PID" 2>/dev/null' TERM INT

wait -n "$BRIDGE_PID" "$BOT_PID" "$WEBAPP_PID"
