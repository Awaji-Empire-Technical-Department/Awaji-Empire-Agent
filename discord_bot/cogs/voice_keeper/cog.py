# cogs/voice_keeper/cog.py
# Role: Interface Layer (cogs/README.md 準拠)
# - Discordイベント（on_voice_state_update）の定義のみ
# - 具体的な処理は logic.py へ委譲
# - 旧 main.py から分離

import os
import asyncio
import logging
from typing import Dict

import discord
from discord.ext import commands

from .logic import VoiceKeeperLogic

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
    """寝落ち切断機能 (Interface Layer)

    TARGET_USER_ID が VC 退出/移動 → 元VCを AFK_TIMEOUT_SECONDS 後に再チェック。
    ホストが戻ってなければ bot以外を切断して人数を報告する。
    イベント定義のみを行い、処理は VoiceKeeperLogic に委譲。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # .env から設定読み込み
        self.target_user_id = _env_int("TARGET_USER_ID", 0)
        self.active_start_hour = _env_int("ACTIVE_START_HOUR", 1)
        self.active_end_hour = _env_int("ACTIVE_END_HOUR", 6)
        self.timeout_seconds = _env_int("AFK_TIMEOUT_SECONDS", 300)
        self.report_channel_name = os.getenv("REPORT_CHANNEL_NAME", "配信コメント")
        self.debug_log = _env_bool("VK_DEBUG_LOG", "0")

        # タスク管理用辞書（guild_id+channel_id → asyncio.Task）
        from common.types import WatchKey
        self._tasks: Dict[WatchKey, asyncio.Task] = {}

    def _cancel_task(self, key) -> None:
        task = self._tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

    # ------------------------------------------------------------------
    #  イベント: ボイス状態変更
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """ターゲットユーザーのVC退出/移動を検知し、タイマーを開始する。"""
        # 無効設定
        if self.target_user_id == 0:
            return

        # 監視対象のみ
        if member.id != self.target_user_id:
            return

        # 稼働時間外は無視
        if not VoiceKeeperLogic.is_active_now(
            self.active_start_hour, self.active_end_hour
        ):
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

        from common.types import WatchKey
        key = WatchKey(guild_id=member.guild.id, channel_id=before_ch.id)

        # 張り替え（最新を優先）
        self._cancel_task(key)
        self._tasks[key] = asyncio.create_task(
            VoiceKeeperLogic.watch_and_execute(
                bot=self.bot,
                guild_id=member.guild.id,
                channel_id=before_ch.id,
                target_user_id=self.target_user_id,
                timeout_seconds=self.timeout_seconds,
                active_start_hour=self.active_start_hour,
                active_end_hour=self.active_end_hour,
                report_channel_name=self.report_channel_name,
                debug_log=self.debug_log,
                cleanup_callback=lambda: self._tasks.pop(key, None),
            )
        )

        if self.debug_log:
            logger.debug(
                "[VoiceKeeper] timer started guild=%s(%s) vc=%s(%s) host=%s(%s)",
                member.guild.name, member.guild.id,
                before_ch.name, before_ch.id,
                member.name, member.id,
            )
