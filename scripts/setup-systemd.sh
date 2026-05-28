#!/bin/bash

# setup-systemd.sh
# Why: infra/ 配下の全 .service ファイルを /etc/systemd/system/ へインストールし enable する。
#      CI/CD から呼ばれることを前提とし、サービスの追加・変更はこのスクリプト1本で完結させる。

INFRA_DIR="/Awaji-Empire-Agent/infra"
SYSTEMD_DIR="/etc/systemd/system"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo)"
    exit 1
fi

echo "--- Setting up systemd services from ${INFRA_DIR} ---"

for SOURCE_PATH in "${INFRA_DIR}"/*.service; do
    [ -f "${SOURCE_PATH}" ] || continue

    SERVICE_NAME="$(basename "${SOURCE_PATH}")"
    TARGET_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"

    echo "Copying ${SERVICE_NAME} → ${TARGET_PATH}"
    cp "${SOURCE_PATH}" "${TARGET_PATH}"

    echo "Enabling ${SERVICE_NAME}..."
    systemctl enable "${SERVICE_NAME}"
done

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "✅ All services installed successfully."
