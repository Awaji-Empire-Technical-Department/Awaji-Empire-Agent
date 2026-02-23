# 管理者設定
ADMIN_USER_ID = "738880478823841932"
CODE_CHANNEL_ID = "1447584603425476720"

# 英数字8ケタのパターン（オレマシンナンバー）
# ^:行頭, [A-Za-z0-9]:英数字, {8}:8文字, $:行末
CODE_PATTERN = r"^[A-Za-z0-9]{8}$"

# 通知抑制設定 (mass_mute.py用)
MUTE_ONLY_CHANNEL_NAMES = ["mute_only"]
READ_ONLY_MUTE_CHANNEL_NAMES = ["readonly"]


# テスト/開発用サーバーのID (整数でも文字列でもOKですが、コード内でint変換します)
GUILD_ID = "1456211776495419493"
