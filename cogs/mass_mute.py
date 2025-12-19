import discord
from discord.ext import commands, tasks
import asyncio
import datetime
from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES

# 権限オブジェクトの定義 (変更なし)
SEND_OK_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True, send_messages=True, mention_everyone=False, manage_webhooks=False
)
SEND_NG_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True, send_messages=False, mention_everyone=False, manage_webhooks=False
)

class MassMuteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = int(ADMIN_USER_ID)
        self.daily_mute_check.start()
        # 初回起動時にテーブルを作成しておく
        self.create_table_if_not_exists()

    def create_table_if_not_exists(self):
        """ログ保存用のテーブルがなければ作成する"""
        try:
            conn = self.bot.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mute_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    trigger_name VARCHAR(50),
                    executed_at DATETIME,
                    status VARCHAR(20),
                    details TEXT
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
            print("[MassMute] DB Table check OK.")
        except Exception as e:
            print(f"[MassMute] DB Init Error: {e}")

    async def _send_admin_dm(self, embed: discord.Embed):
        """管理者にDMを送信するヘルパー (変更なし)"""
        try:
            owner = await self.bot.fetch_user(self.owner_id)
            if owner:
                await owner.send(embed=embed)
        except Exception as e:
            print(f"[DM ERROR] {e}")

    # on_guild_channel_create は変更なしのため省略...
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        # ... (元のコードのまま) ...
        pass

    async def execute_mute_logic(self, trigger: str):
        if not self.bot.guilds: return
        guild = self.bot.guilds[0]
        everyone_role = guild.default_role
        
        success_list = []
        error_list = []

        # 1. 送信許可チャンネルの処理
        for name in MUTE_ONLY_CHANNEL_NAMES:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                try:
                    await channel.set_permissions(everyone_role, overwrite=SEND_OK_OVERWRITE)
                    success_list.append(f"#{name} (許可)")
                except Exception as e:
                    error_list.append(f"#{name}: {e}")

        # 2. 送信禁止チャンネルの処理
        for name in READ_ONLY_MUTE_CHANNEL_NAMES:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                try:
                    await channel.set_permissions(everyone_role, overwrite=SEND_NG_OVERWRITE)
                    success_list.append(f"#{name} (禁止)")
                except Exception as e:
                    error_list.append(f"#{name}: {e}")

        # --- DBへのログ保存 ---
        try:
            conn = self.bot.get_db_connection()
            cursor = conn.cursor()
            status = "SUCCESS" if not error_list else "WARNING"
            details = f"Success: {len(success_list)}, Errors: {len(error_list)}"
            
            cursor.execute(
                "INSERT INTO mute_logs (trigger_name, executed_at, status, details) VALUES (%s, %s, %s, %s)",
                (trigger, datetime.datetime.now(), status, details)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to save log: {e}")

        # --- 管理者への完了通知DM ---
        embed = discord.Embed(
            title="🛡️ 通知抑制処理 完了報告",
            description=f"実行トリガー: **{trigger}**",
            color=0x4caf50 if not error_list else 0xff9800,
            timestamp=discord.utils.utcnow()
        )
        
        if success_list:
            embed.add_field(name="✅ 成功", value="\n".join(success_list), inline=False)
        
        if error_list:
            embed.add_field(name="❌ エラー", value="\n".join(error_list), inline=False)
            embed.color = 0xf44336

        if not success_list and not error_list:
            embed.description += "\n対象のチャンネルが見つかりませんでした。"

        await self._send_admin_dm(embed)

    @tasks.loop(time=[
        datetime.time(0, 0, tzinfo=datetime.timezone.utc),
        datetime.time(8, 0, tzinfo=datetime.timezone.utc),
        datetime.time(16, 0, tzinfo=datetime.timezone.utc)
    ])
    async def daily_mute_check(self):
        await self.execute_mute_logic("Daily Task")

async def setup(bot):
    await bot.add_cog(MassMuteCog(bot))
