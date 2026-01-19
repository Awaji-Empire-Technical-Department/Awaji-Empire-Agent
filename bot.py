import discord
from discord.ext import commands
import asyncio
import os
import mysql.connector
from dotenv import load_dotenv
from config import ADMIN_USER_ID, GUILD_ID

# .envファイルを読み込む
load_dotenv()

# コグ（拡張機能）のリスト
COGS = [
    "cogs.filter",
    "cogs.mass_mute",
    "cogs.survey",
    "cogs.voice_keeper"
]

class MyBot(commands.Bot):
    def __init__(self):
        # インテンツの設定
        intents = discord.Intents.default()
        intents.members = True 
        intents.message_content = True 
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """
        Bot起動時に一度だけ実行される初期化処理。
        """
        for cog_name in COGS:
            try:
                await self.load_extension(cog_name)
                print(f"LOADED: {cog_name} をロードしました。")
            except Exception as e:
                print(f"ERROR: {cog_name} のロードに失敗しました。")
                print(f"Traceback: {e}")

        # config.py の GUILD_ID をチェック
        if GUILD_ID:
            try:
                # 特定のサーバー(ギルド)にだけコマンドを登録・同期
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"Command tree synced to guild {GUILD_ID} successfully.")
            except Exception as e:
                print(f"Failed to sync to guild: {e}")
        else:
            # IDがない場合は、これまで通りグローバル同期
            try:
                await self.tree.sync()
                print("Command tree synced globally.")
            except Exception as e:
                print(f"Failed to global sync: {e}")

    # --- 追加: DB接続用メソッド ---
    def get_db_connection(self):
        """MySQLへの接続オブジェクトを返す"""
        return mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS')
        )

# Botインスタンスの作成
bot = MyBot()

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
    """BotがDiscordに接続・再接続したときに実行される"""
    print('--- Bot is starting up ---', flush=True) # flushを追加
    print('-------------------------------------')
    print('Bot Name: {0.user.name}'.format(bot))
    print('Bot ID: {0.user.id}'.format(bot))
    print('-------------------------------------')
    
    # --- DB接続テスト (起動時に一度だけ確認) ---
    try:
        conn = bot.get_db_connection()
        if conn.is_connected():
            print("✅ Database connection successful!")
            conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

    # --- 1. 起動/再接続DMを管理者へ送信 ---
    owner = None
    try:
        owner_id_int = int(ADMIN_USER_ID)
        owner = await bot.fetch_user(owner_id_int) 
    except Exception as e:
        print(f"Error fetching owner user: {e}")

    if owner:
        try:
            status = "再起動/再接続" if bot.is_ready() else "起動完了"
            embed = discord.Embed(
                title=f"Bot {status}",
                description=f"Bot **{bot.user.name}** がオンラインになりました。",
                color=0x4caf50 
            )
            await owner.send(embed=embed)
        except Exception as e:
            print(f"Failed to send status DM to owner: {e}")
    
    # --- 2. mass_mute の実行 ---
    if 'cogs.mass_mute' in bot.extensions:
        mass_mute_cog = bot.get_cog("MassMuteCog")
        if mass_mute_cog:
            asyncio.create_task(mass_mute_cog.execute_mute_logic("Startup/Reconnected"))


if __name__ == '__main__':
    bot_token = get_token_from_file()
    
    if bot_token:
        try:
            bot.run(bot_token, reconnect=True)
        except discord.LoginFailure:
            print("Error: Invalid token in token.txt")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    else:
        print("Bot execution aborted due to missing or invalid token.")
