import os
from dotenv import load_dotenv

load_dotenv()

def check_var(name):
    val = os.getenv(name)
    if val is None:
        print(f"❌ {name} が見つかりません！")
        return
    
    # 前後の空白を目立たせて表示
    print(f"[{name}]")
    print(f"  値: '{val}'")
    print(f"  文字数: {len(val)}")
    
    if val.strip() != val:
        print("  ⚠️ 警告: 前後に余計なスペースが含まれています！.envを修正してください。")
    else:
        print("  ✅ フォーマットは正常です。")
    print("-" * 20)

print("--- 設定値チェック ---")
check_var("DISCORD_CLIENT_ID")
check_var("DISCORD_CLIENT_SECRET")
check_var("DISCORD_REDIRECT_URI")
