import discord
from discord.ext import commands
import asyncio
# 🚨 修正点: DISCORD_BOT_TOKENはconfig.pyから削除し、ADMIN_USER_IDのみインポート
from config import ADMIN_USER_ID

# コグ（拡張機能）のリスト
COGS = [
    "cogs.filter",
    "cogs.mass_mute"
]

# Botのインスタンスを作成
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def load_cogs():
    """定義されたコグをロードする"""
    for cog_name in COGS:
        try:
            await bot.load_extension(cog_name)
            print(f"LOADED: {cog_name} をロードしました。")
        except Exception as e:
            print(f"ERROR: {cog_name} のロードに失敗しました。")
            print(f"Traceback: {e}")

def get_token_from_file(filename="token.txt"):
    """token.txtファイルからトークンを読み込む"""
    try:
        with open(filename, 'r') as f:
            token = f.read().strip()
            return token
    except FileNotFoundError:
        print(f"Error: Token file '{filename}' not found.")
        return None
    except Exception as e:
        print(f"Error reading token file: {e}")
        return None

@bot.event
async def on_ready():
    """BotがDiscordに接続を完了したときに実行される"""
    print('-------------------------------------')
    print('Bot Name: {0.user.name}'.format(bot))
    print('Bot ID: {0.user.id}'.format(bot))
    print('-------------------------------------')
    
    # --- 1. 起動完了DMを管理者へ送信 (fetch_userで確実に取得) ---
    owner = None
    try:
        owner_id_int = int(ADMIN_USER_ID)
        owner = await bot.fetch_user(owner_id_int) 
    except Exception as e:
        print(f"Error fetching owner user for startup DM: {e}")

    if owner:
        try:
            embed = discord.Embed(
                title="Bot起動完了",
                description=f"Bot **{bot.user.name}** が正常に起動しました。",
                color=0x4caf50 
            )
            await owner.send(embed=embed)
            print("Startup DM sent to owner.")
        except Exception as e:
            print(f"Failed to send startup DM to owner: {e}")
    else:
        print("Warning: Owner user not found or ID is invalid. Could not send startup DM.")
    
    # --- 2. コグのロード ---
    await load_cogs()

    # --- 3. mass_mute コグの起動時チェックを明示的に実行 (競合回避) ---
    if 'cogs.mass_mute' in bot.extensions:
        mass_mute_cog = bot.get_cog("MassMuteCog")
        if mass_mute_cog:
            # mass_muteコグのexecute_mute_logicを直接呼び出す
            await mass_mute_cog.execute_mute_logic("Startup (via bot.py)")
            print("Initial Startup Mute Check Triggered.")
        else:
            print("Warning: MassMuteCog not found after loading.")


if __name__ == '__main__':
    bot_token = get_token_from_file()
    
    if bot_token:
        try:
            bot.run(bot_token)
        except discord.LoginFailure:
            print("Error: Invalid token in token.txt")
        except Exception as e:
            print(f"An unexpected error occurred during bot execution: {e}")
    else:
        print("Bot execution aborted due to missing or invalid token.")
