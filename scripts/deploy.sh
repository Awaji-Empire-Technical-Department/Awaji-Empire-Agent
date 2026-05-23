#!/bin/bash
# deploy.sh
# Awaji Empire Agent デプロイスクリプト
#
# 使い方:
#   sudo bash /Awaji-Empire-Agent/scripts/deploy.sh
#
# 実行内容:
#   1. git pull で最新コードを取得
#   2. Rust Bridge をビルド & サービス再起動
#   3. nginx 設定を適用・リロード（WebSocket 対応含む）
#   4. Python webapp (Quart) サービスを再起動

set -euo pipefail

# ============================================================
# 設定（環境に合わせて変更）
# ============================================================
REPO_DIR="/Awaji-Empire-Agent"
WEBAPP_SERVICE="discord_webapp.service"      # Python webapp の systemd サービス名
BRIDGE_SERVICE="database_bridge.service"   # Rust bridge の systemd サービス名
NGINX_CONF_SRC="${REPO_DIR}/infra/nginx-awaji.conf"
NGINX_CONF_DEST="/etc/nginx/sites-available/awaji-empire"
NGINX_CONF_LINK="/etc/nginx/sites-enabled/awaji-empire"

# ============================================================
# 前提チェック
# ============================================================
if [[ $EUID -ne 0 ]]; then
    echo "❌  root 権限が必要です: sudo bash $0"
    exit 1
fi

echo "============================================================"
echo "  Awaji Empire Agent デプロイ開始 $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# ============================================================
# 1. 最新コードを取得
# ============================================================
echo ""
echo "▶ [1/4] git pull ..."
cd "${REPO_DIR}"
git pull --ff-only

# ============================================================
# 2. Rust Bridge ビルド & 再起動
# ============================================================
echo ""
echo "▶ [2/4] Rust Bridge ビルド ..."
cd "${REPO_DIR}/database_bridge"
cargo build --release 2>&1 | tail -5

echo "  database_bridge サービスを再起動 ..."
systemctl daemon-reload
systemctl restart "${BRIDGE_SERVICE}"
systemctl is-active --quiet "${BRIDGE_SERVICE}" \
    && echo "  ✅ ${BRIDGE_SERVICE} 起動確認" \
    || echo "  ⚠️  ${BRIDGE_SERVICE} の起動を確認できませんでした（systemctl status ${BRIDGE_SERVICE} で確認してください）"

# ============================================================
# 3. nginx 設定を適用（WebSocket 対応）
# ============================================================
echo ""
echo "▶ [3/4] nginx 設定を適用 ..."

# sites-available にコピー
cp "${NGINX_CONF_SRC}" "${NGINX_CONF_DEST}"
echo "  コピー: ${NGINX_CONF_SRC} → ${NGINX_CONF_DEST}"

# sites-enabled にシンボリックリンクがなければ作成
if [ ! -L "${NGINX_CONF_LINK}" ]; then
    ln -sf "${NGINX_CONF_DEST}" "${NGINX_CONF_LINK}"
    echo "  シンボリックリンク作成: ${NGINX_CONF_LINK}"
fi

# 既存のデフォルト設定を無効化（競合する場合）
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    rm -f "/etc/nginx/sites-enabled/default"
    echo "  デフォルト設定を無効化"
fi

# 設定テスト & リロード
nginx -t && systemctl reload nginx \
    && echo "  ✅ nginx リロード完了（WebSocket 対応済み）" \
    || { echo "  ❌ nginx 設定エラー。ロールバックしてください。"; exit 1; }

# ============================================================
# 4. Python webapp 再起動
# ============================================================
echo ""
echo "▶ [4/4] Python webapp 再起動 ..."
if systemctl is-active --quiet "${WEBAPP_SERVICE}" 2>/dev/null \
   || systemctl list-unit-files --quiet "${WEBAPP_SERVICE}" 2>/dev/null | grep -q "${WEBAPP_SERVICE}"; then
    systemctl restart "${WEBAPP_SERVICE}"
    systemctl is-active --quiet "${WEBAPP_SERVICE}" \
        && echo "  ✅ ${WEBAPP_SERVICE} 起動確認" \
        || echo "  ⚠️  ${WEBAPP_SERVICE} の起動を確認できませんでした"
else
    echo "  ⚠️  ${WEBAPP_SERVICE} が見つかりません"
    echo "     手動で webapp を再起動してください"
    echo "     例: systemctl restart awaji-webapp"
fi

# ============================================================
# 完了
# ============================================================
echo ""
echo "============================================================"
echo "  ✅ デプロイ完了 $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
