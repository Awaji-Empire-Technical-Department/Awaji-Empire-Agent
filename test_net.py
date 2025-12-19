import socket
import requests
import time
import sys

print("--- ネットワーク診断開始 ---")

# 1. DNS解決テスト
print("\n[Step 1] DNS解決テスト (discord.com)")
try:
    ip = socket.gethostbyname("discord.com")
    print(f"✅ 成功: discord.com -> {ip}")
except Exception as e:
    print(f"❌ 失敗: DNS解決ができませんでした。 {e}")
    sys.exit(1)

# 2. PythonでのHTTPS接続テスト (IPv6無効化なし)
print("\n[Step 2] 通常のHTTPS接続テスト")
try:
    start = time.time()
    # タイムアウトを5秒に設定
    r = requests.get("https://discord.com/api/v10/gateway", timeout=5)
    print(f"✅ 成功: ステータスコード {r.status_code} (所要時間: {time.time() - start:.2f}秒)")
except Exception as e:
    print(f"❌ 失敗: 接続できませんでした。 {e}")

# 3. IPv4強制パッチを当ててテスト
print("\n[Step 3] IPv4強制パッチ適用後のテスト")
import requests.packages.urllib3.util.connection as urllib3_cn
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

try:
    start = time.time()
    r = requests.get("https://discord.com/api/v10/gateway", timeout=5)
    print(f"✅ 成功: ステータスコード {r.status_code} (所要時間: {time.time() - start:.2f}秒)")
except Exception as e:
    print(f"❌ 失敗: パッチを当てても接続できませんでした。 {e}")

print("\n--- 診断終了 ---")
