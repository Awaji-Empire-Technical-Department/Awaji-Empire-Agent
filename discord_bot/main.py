import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def get_token() -> str:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print(
            "[ERROR] DISCORD_TOKEN が設定されていません。\n"
            "  .env に DISCORD_TOKEN=<your_token> を追加するか、\n"
            "  scripts/migrate_token.py で token.txt から移行してください。",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def main() -> None:
    token = get_token()
    # TODO: discord.py の Bot 初期化・起動処理をここに実装する
    print(f"Bot トークン読み込み成功 (末尾4文字: ...{token[-4:]})")


if __name__ == "__main__":
    main()
