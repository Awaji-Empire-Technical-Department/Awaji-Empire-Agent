import os
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional, Tuple

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchKey:
    guild_id: int
    channel_id: int  # 「ホストが抜けた元のVC」


class VoiceKeeper(commands.Cog):
    """
    VoiceKeeper: 寝落ち切断機能

    - TARGET_USER_ID が VC から退出 or 別VCへ移動したら、その「元のVC」を5分後に再チェック
    - ホストが元のVCへ戻っていなければ、元のVCに残る Bot以外全員を切断し、人数を報告
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # env
        self.target_user_id = int(os.getenv("TARGET_USER_ID", "0"))
        self.active_start_hour = int(os.getenv("ACTIVE_START_HOUR", "1"))
        self.active_end_hour = int(os.getenv("ACTIVE_END_HOUR", "6"))
        self.report_channel_name = os.getenv("REPORT_CHANNEL_NAME", "配信コメント")

        # 監視タイマー（同じギルド・同じ元VCで二重起動しない）
        self._tasks: Dict[WatchKey, asyncio.Task] = {}

        # JST固定（必要なら将来 env 化してもOK）
        self._tz = ZoneInfo("Asia/Tokyo")

    # ----------------------------
    # Utility
    # ----------------------------
    def _is_active_time(self) -> bool:
        """稼働時間内か判定（深夜帯で日跨ぎも考慮）"""
        now = datetime.now(self._tz)
        h = now.hour

        start = self.active_start_hour % 24
        end = self.active_end_hour % 24

        if start == end:
            # 0〜24全時間稼働、と解釈（運用的に便利）
            return True

        if start < end:
            # 例: 1〜6
            return start <= h < end
        else:
            # 例: 22〜6（日跨ぎ）
            return (h >= start) or (h < end)

    def _get_member_current_vc_id(self, member: discord.Member) -> Optional[int]:
        if member.voice and member.voice.channel:
            return member.voice.channel.id
        return None

    async def _find_report_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch = discord.utils.get(guild.text_channels, name=self.report_channel_name)
        return ch

    def _cancel_task(self, key: WatchKey) -> None:
        task = self._tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

    # ----------------------------
    # Core logic
    # ----------------------------
    async def _watch_and_kick(self, guild_id: int, channel_id: int):
        key = WatchKey(guild_id=guild_id, channel_id=channel_id)

        try:
            await asyncio.sleep(300)  # 5分

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return

            # チャンネル取得（元のVC）
            channel = guild.get_channel(channel_id)
            if channel is None or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                return

            # ホストが元のVCに戻っているなら何もしない
            target = guild.get_member(self.target_user_id)
            if target is not None:
                current_vc_id = self._get_member_current_vc_id(target)
                if current_vc_id == channel_id:
                    return  # 戻っていたのでキャンセル扱い（= 何もしない）

            # まだ稼働時間内でなければ、何もしない（5分の間に時間外になったケース）
            if not self._is_active_time():
                return

            # 残っている Bot以外を切断
            victims = [m for m in channel.members if not m.bot]
            count = 0

            for member in victims:
                try:
                    await member.move_to(None, reason="VoiceKeeper: 寝落ち切断")
                    count += 1
                except discord.Forbidden:
                    logger.warning("Missing permission to move member: %s", member)
                except discord.HTTPException as e:
                    logger.warning("Failed to move member %s: %s", member, e)

            # 報告
            report_ch = await self._find_report_channel(guild)
            if report_ch:
                msg = (
                    "【寝落ち集計】\n"
                    f"今回の犠牲者は **{count}人** でした。おやすみなさい。"
                )
                try:
                    await report_ch.send(msg)
                except discord.Forbidden:
                    logger.warning("Missing permission to send message in: %s", report_ch)
                except discord.HTTPException as e:
                    logger.warning("Failed to send report message: %s", e)

        except asyncio.CancelledError:
            # ホストが戻った等でキャンセル
            return
        finally:
            # 完了・キャンセルどちらでも後始末
            self._tasks.pop(key, None)

    # ----------------------------
    # Events
    # ----------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # 無効設定なら何もしない
        if self.target_user_id == 0:
            return

        # 監視対象以外は無視
        if member.id != self.target_user_id:
            return

        # 稼働時間外は無視
        if not self._is_active_time():
            return

        # before channel（元のVC）
        before_ch = before.channel
        after_ch = after.channel

        # VCに関係ない変化は無視
        if before_ch is None and after_ch is None:
            return

        # 「退出」または「別VCへ移動」した時
        # - 退出: before!=None and after==None
        # - 移動: before!=None and after!=None and before.id!=after.id
        if before_ch is None:
            # before が無い = 元のVCが無いので監視対象にならない
            return

        if after_ch is not None and after_ch.id == before_ch.id:
            # 同じVC内のミュート等変化
            return

        # この時点で「元のVC」は before_ch
        key = WatchKey(guild_id=member.guild.id, channel_id=before_ch.id)

        # 既に同じ元VCでタイマーが走ってたら、張り替え（最新の退出を優先）
        self._cancel_task(key)

        # タイマー開始
        task = asyncio.create_task(self._watch_and_kick(member.guild.id, before_ch.id))
        self._tasks[key] = task


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceKeeper(bot))
