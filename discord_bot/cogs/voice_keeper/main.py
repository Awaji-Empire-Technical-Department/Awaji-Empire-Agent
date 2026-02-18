"""
VoiceKeeper main module
- Discordイベント監視（on_voice_state_update）
- タスク管理（タイマー開始/キャンセル）
- 実処理は services.py に委譲
"""

import os
import asyncio
import logging
from zoneinfo import ZoneInfo
from typing import Dict, Optional

import discord
from discord.ext import commands

from common.time_utils import is_active_time
from common.types import WatchKey

from .services import VoiceKeeperService

logger = logging.getLogger(__name__)

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_bool(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "on")


class VoiceKeeper(commands.Cog):
    """
    - TARGET_USER_ID が VC 退出/移動 -> 元VCを AFK_TIMEOUT_SECONDS 後に再チェック
    - ホストが戻ってなければ bot以外を切断して人数を報告
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # .env（ここで直接読む）
        self.target_user_id = _env_int("TARGET_USER_ID", 0)
        self.active_start_hour = _env_int("ACTIVE_START_HOUR", 1)
        self.active_end_hour = _env_int("ACTIVE_END_HOUR", 6)
        self.timeout_seconds = _env_int("AFK_TIMEOUT_SECONDS", 300)
        self.report_channel_name = os.getenv("REPORT_CHANNEL_NAME", "配信コメント")
        self.debug_log = _env_bool("VK_DEBUG_LOG", "0")  # 任意（無ければ0でOK）

        self.service = VoiceKeeperService(self.report_channel_name)

        self._tasks: Dict[WatchKey, asyncio.Task] = {}
        self._tz = ZoneInfo("Asia/Tokyo")

    def _active_now(self) -> bool:
        return is_active_time(self.active_start_hour, self.active_end_hour, self._tz)

    def _get_member_current_vc_id(self, member: discord.Member) -> Optional[int]:
        if member.voice and member.voice.channel:
            return member.voice.channel.id
        return None

    def _cancel_task(self, key: WatchKey) -> None:
        task = self._tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

    async def _watch_and_execute(self, guild_id: int, channel_id: int):
        key = WatchKey(guild_id=guild_id, channel_id=channel_id)

        try:
            await asyncio.sleep(self.timeout_seconds)

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return

            channel = guild.get_channel(channel_id)
            if channel is None or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                return

            host = guild.get_member(self.target_user_id)

            # ホストが元VCに戻ってるなら何もしない
            if host is not None and self._get_member_current_vc_id(host) == channel_id:
                if self.debug_log:
                    logger.debug("[VoiceKeeper] skip: host returned guild=%s(%s) vc=%s(%s)", guild.name, guild.id, channel.name, channel.id)
                return

            # 待ってる間に時間外になったら何もしない（安全側）
            if not self._active_now():
                if self.debug_log:
                    logger.debug("[VoiceKeeper] skip: out of active time after delay guild=%s(%s) vc=%s(%s)", guild.name, guild.id, channel.name, channel.id)
                return

            kicked_count = await self.service.kick_all_non_bots(channel)
            report_sent = await self.service.send_report(guild, kicked_count)

            self.service.log_summary(
                reason="executed",
                guild=guild,
                voice_channel=channel,
                host=host,
                kicked_count=kicked_count,
                report_sent=report_sent,
            )

        except asyncio.CancelledError:
            return
        finally:
            self._tasks.pop(key, None)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 無効設定
        if self.target_user_id == 0:
            return

        # 監視対象のみ
        if member.id != self.target_user_id:
            return

        # 稼働時間外は無視
        if not self._active_now():
            return

        before_ch = before.channel
        after_ch = after.channel

        if before_ch is None and after_ch is None:
            return

        # 同一VC内の変化（ミュート等）は無視
        if before_ch is not None and after_ch is not None and before_ch.id == after_ch.id:
            return

        # 退出/移動のときだけ（元VC=before）
        if before_ch is None:
            return

        key = WatchKey(guild_id=member.guild.id, channel_id=before_ch.id)

        # 張り替え（最新を優先）
        self._cancel_task(key)
        self._tasks[key] = asyncio.create_task(self._watch_and_execute(member.guild.id, before_ch.id))

        if self.debug_log:
            logger.debug(
                "[VoiceKeeper] timer started guild=%s(%s) vc=%s(%s) host=%s(%s)",
                member.guild.name, member.guild.id,
                before_ch.name, before_ch.id,
                member.name, member.id,
            )
