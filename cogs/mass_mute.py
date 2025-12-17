import discord
from discord.ext import commands, tasks
import asyncio
import datetime
from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES

# 権限オブジェクトの定義
SEND_OK_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=True,
    mention_everyone=False,
    manage_webhooks=False
)

SEND_NG_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=False,
    mention_everyone=False,
    manage_webhooks=False
)

class MassMuteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = int(ADMIN_USER_ID)
        self.daily_mute_check.start()

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
        if not isinstance(channel, discord.TextChannel): return
        
        target = None
        mode = ""
        if channel.name in MUTE_ONLY_CHANNEL_NAMES:
            target, mode = SEND_OK_OVERWRITE, "送信許可"
        elif channel.name in READ_ONLY_MUTE_CHANNEL_NAMES:
            target, mode = SEND_NG_OVERWRITE, "送信禁止"

        if target:
            await asyncio.sleep(1)
            try:
                await channel.set_permissions(channel.guild.default_role, overwrite=target)
                embed = discord.Embed(
                    title="🆕 チャンネル自動設定完了",
                    description=f"新しく作成されたチャンネル **#{channel.name}** を検知し、権限を自動適用しました。\n設定モード: `{mode}`",
                    color=0x3498db
                )
                await self._send_admin_dm(embed)
            except Exception as e:
                print(f"[AUTO-MUTE ERROR] {e}")

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

        # --- 🚨 修正点: 管理者への完了通知DMを作成 🚨 ---
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
