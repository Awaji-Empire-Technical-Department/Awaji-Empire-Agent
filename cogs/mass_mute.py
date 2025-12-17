import discord
from discord.ext import commands, tasks
import asyncio
import datetime
from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES

# 1. 【許可用】通知オフ + メッセージ送信「可」 (配信コメント等)
SEND_OK_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=True,     # 明示的に許可
    mention_everyone=False, # 通知抑制
    manage_webhooks=False
)

# 2. 【禁止用】通知オフ + メッセージ送信「不可」 (参加ログ等)
SEND_NG_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=False,    # 明示的に禁止
    mention_everyone=False, # 通知抑制
    manage_webhooks=False
)

class MassMuteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = int(ADMIN_USER_ID)
        self.daily_mute_check.start()

    def cog_unload(self):
        self.daily_mute_check.cancel()

    async def execute_mute_logic(self, trigger: str):
        if not self.bot.guilds: return
        guild = self.bot.guilds[0]
        everyone_role = guild.default_role
        
        success_count = 0
        errors = []

        # A. 送信を許可するチャンネルの処理
        for name in MUTE_ONLY_CHANNEL_NAMES:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                try:
                    await channel.set_permissions(everyone_role, overwrite=SEND_OK_OVERWRITE)
                    success_count += 1
                except Exception as e:
                    errors.append(f"#{name}: {e}")

        # B. 送信を禁止するチャンネルの処理
        for name in READ_ONLY_MUTE_CHANNEL_NAMES:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                try:
                    await channel.set_permissions(everyone_role, overwrite=SEND_NG_OVERWRITE)
                    success_count += 1
                except Exception as e:
                    errors.append(f"#{name}: {e}")

        # 結果をDM送信
        owner = await self.bot.fetch_user(self.owner_id)
        if owner:
            msg = f"🛡️ **通知制御実行** ({trigger})\n成功: {success_count}件"
            if errors:
                msg += f"\n❌ エラー:\n" + "\n".join(errors)
            await owner.send(msg)

    @tasks.loop(time=[datetime.time(0, 0, tzinfo=datetime.timezone.utc)]) # 適宜時間は調整
    async def daily_mute_check(self):
        await self.execute_mute_logic("Daily Task")

async def setup(bot):
    await bot.add_cog(MassMuteCog(bot))
