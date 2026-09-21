# 本番の MariaDB は Ubuntu 24.04 LTS の LXC 上で apt の mariadb-server を
# 使っている（README参照）。開発用コンテナも同じ Ubuntu 24.04 + apt パッケージ
# に揃える (ADR-028)。
FROM ubuntu:24.04

# postinst が Docker ビルド中にサービス起動を試みて失敗/ハングするのを防ぐ
# (Debian系パッケージをコンテナ内でインストールする際の定番対策)。
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       mariadb-server \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/lib/mysql/*

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME /var/lib/mysql
EXPOSE 3306

ENTRYPOINT ["docker-entrypoint.sh"]
