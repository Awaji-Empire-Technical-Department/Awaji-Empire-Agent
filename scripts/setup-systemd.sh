#!/bin/bash

# setup-systemd.sh
# Why: Automate the registration and start of the database_bridge service.

SERVICE_NAME="database_bridge.service"
SOURCE_PATH="/Awaji-Empire-Agent/infra/$SERVICE_NAME"
TARGET_PATH="/etc/systemd/system/$SERVICE_NAME"

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (sudo)"
   exit 1
fi

echo "--- Setting up $SERVICE_NAME ---"

if [ ! -f "$SOURCE_PATH" ]; then
    echo "Error: Source service file not found at $SOURCE_PATH"
    exit 1
fi

# Copy the service file
echo "Copying $SERVICE_NAME to $TARGET_PATH..."
cp "$SOURCE_PATH" "$TARGET_PATH"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start
echo "Enabling $SERVICE_NAME..."
systemctl enable "$SERVICE_NAME"

echo "Restarting $SERVICE_NAME..."
systemctl restart "$SERVICE_NAME"

echo "Checking status of $SERVICE_NAME..."
systemctl status "$SERVICE_NAME" --no-pager

echo "✅ Setup completed successfully."
