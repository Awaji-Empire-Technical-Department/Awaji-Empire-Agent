# 本番は Ubuntu 24.04 LTS の同一ホスト上で database_bridge / bot.py / webapp.py
# の3プロセスが systemd サービス (infra/*.service) として動き、127.0.0.1
# 経由で通信する。database_bridge / webapp.py / bridge_client.py は接続先を
# 127.0.0.1:7878 に固定しているため (ADR-028)、開発用コンテナでもこの3プロセス
# を同一コンテナ内で動かし、アプリコードには一切手を入れない。
# ベースイメージも本番と同じ Ubuntu 24.04 に揃える。

FROM ubuntu:24.04 AS bridge-builder
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /bridge
COPY database_bridge/ .
RUN cargo build --release

FROM ubuntu:24.04
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates python3.12 python3.12-venv \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY --from=bridge-builder /bridge/target/release/database_bridge /usr/local/bin/database_bridge

WORKDIR /app
# 依存関係だけを先に解決してレイヤーキャッシュを効かせる（uv公式推奨パターン）。
COPY discord_bot/pyproject.toml discord_bot/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY discord_bot/ .
RUN uv sync --frozen
ENV PATH="/app/.venv/bin:${PATH}"

COPY infra/app-entrypoint.sh /usr/local/bin/app-entrypoint.sh
RUN chmod +x /usr/local/bin/app-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/app-entrypoint.sh"]
