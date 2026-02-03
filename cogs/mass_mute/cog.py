# cogs/mass_mute/cog.py
from __future__ import annotations

import datetime
import discord
from discord.ext import commands, tasks

from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES
from .logic import MassMuteLogic

SEND_OK_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True, send_messages=True, mention_everyone=False, manage_webhooks=False
)
SEND_NG_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True, send_messages=False, mention_everyone=False, manage_webhooks=False
)


class MassMuteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.owner_id = int(ADMIN_USER_ID)

        self.daily_mute_check.start()
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
        """管理者にDMを送信するヘルパー"""
        try:
            owner = await self.bot.fetch_user(self.owner_id)
            if owner:
                await owner.send(embed=embed)
        except Exception as e:
            print(f"[DM ERROR] {e}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        # 元のコードがあるならここへ移植（現状は省略のままでOK）
        pass

    async def execute_mute_logic(self, trigger: str):
        if not self.bot.guilds:
            return

        guild = self.bot.guilds[0]
        if guild.me is None:
            return

        # --- Logicへ委譲 ---
        result = await MassMuteLogic.execute(
            guild=guild,
            bot_member=guild.me,
            mute_only_channel_names=list(MUTE_ONLY_CHANNEL_NAMES),
            read_only_mute_channel_names=list(READ_ONLY_MUTE_CHANNEL_NAMES),
            send_ok_overwrite=SEND_OK_OVERWRITE,
            send_ng_overwrite=SEND_NG_OVERWRITE,
        )

        # --- DBへのログ保存 ---
        try:
            conn = self.bot.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO mute_logs (trigger_name, executed_at, status, details) VALUES (%s, %s, %s, %s)",
                (trigger, datetime.datetime.now(), result.status, result.details)
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
            color=0x4caf50 if result.status == "SUCCESS" else (0xff9800 if result.status == "WARNING" else 0xf44336),
            timestamp=discord.utils.utcnow()
        )

        if result.success_list:
            embed.add_field(name="✅ 成功", value="\n".join(result.success_list), inline=False)

        if result.error_list:
            embed.add_field(name="❌ エラー", value="\n".join(result.error_list), inline=False)

        if not result.success_list and not result.error_list:
            embed.description += "\n対象のチャンネルが見つかりませんでした。"

        await self._send_admin_dm(embed)

    @tasks.loop(time=[
        datetime.time(0, 0, tzinfo=datetime.timezone.utc),
        datetime.time(8, 0, tzinfo=datetime.timezone.utc),
        datetime.time(16, 0, tzinfo=datetime.timezone.utc)
    ])
    async def daily_mute_check(self):
        await self.execute_mute_logic("Daily Task")


async def setup(bot: commands.Bot):
    await bot.add_cog(MassMuteCog(bot))
