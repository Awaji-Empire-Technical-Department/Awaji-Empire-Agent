# cogs/voice_keeper/logic.py
# Role: Business Logic Layer (cogs/README.md 準拠)
# - 寝落ち切断の具体的な判定・実行ロジック
# - ctx 非依存、services層を使用
# - 旧 main.py の _watch_and_execute から抽出
import asyncio
import logging
from typing import Callable, Optional

import discord
from discord.ext import commands

from common.time_utils import is_active_time
from zoneinfo import ZoneInfo

from services.voice_keeper_service import VoiceKeeperService

logger = logging.getLogger(__name__)

_tz = ZoneInfo("Asia/Tokyo")


class VoiceKeeperLogic:
    """寝落ち切断機能のビジネスロジック。

    設計原則:
    - @staticmethod で実装（ステートレス）
    - ctx 非依存
    - I/O操作は VoiceKeeperService に委譲
    """

    @staticmethod
    def is_active_now(start_hour: int, end_hour: int) -> bool:
        """現在時刻が稼働時間内かどうかを判定する。"""
        return is_active_time(start_hour, end_hour, _tz)

    @staticmethod
    def get_member_current_vc_id(member: discord.Member) -> Optional[int]:
        """メンバーが現在参加しているVCのIDを取得する。"""
        if member.voice and member.voice.channel:
            return member.voice.channel.id
        return None

    @staticmethod
    async def watch_and_execute(
        *,
        bot: commands.Bot,
        guild_id: int,
        channel_id: int,
        target_user_id: int,
        timeout_seconds: int,
        active_start_hour: int,
        active_end_hour: int,
        report_channel_name: str,
        debug_log: bool = False,
        cleanup_callback: Optional[Callable] = None,
    ) -> None:
        """タイムアウト後にVCを再チェックし、必要であれば全員切断する。

        Args:
            bot: Botインスタンス（ギルド/チャンネル取得用）
            guild_id: 対象ギルドID
            channel_id: 監視対象VCのID
            target_user_id: ホストユーザーID
            timeout_seconds: 待機秒数
            active_start_hour: 稼働開始時刻
            active_end_hour: 稼働終了時刻
            report_channel_name: レポート先チャンネル名
            debug_log: デバッグログ有効化フラグ
            cleanup_callback: タスク完了時のクリーンアップ関数
        """
        try:
            await asyncio.sleep(timeout_seconds)

            guild = bot.get_guild(guild_id)
            if guild is None:
                return

            channel = guild.get_channel(channel_id)
            if channel is None or not isinstance(
                channel, (discord.VoiceChannel, discord.StageChannel)
            ):
                return

            host = guild.get_member(target_user_id)

            # ホストが元VCに戻っているなら何もしない
            if host is not None and VoiceKeeperLogic.get_member_current_vc_id(host) == channel_id:
                if debug_log:
                    logger.debug(
                        "[VoiceKeeper] skip: host returned guild=%s(%s) vc=%s(%s)",
                        guild.name, guild.id, channel.name, channel.id,
                    )
                return

            # 待っている間に時間外になったら何もしない（安全側）
            if not VoiceKeeperLogic.is_active_now(active_start_hour, active_end_hour):
                if debug_log:
                    logger.debug(
                        "[VoiceKeeper] skip: out of active time after delay guild=%s(%s) vc=%s(%s)",
                        guild.name, guild.id, channel.name, channel.id,
                    )
                return

            # I/O操作は services 層に委譲
            kicked_count = await VoiceKeeperService.kick_all_non_bots(channel)
            report_sent = await VoiceKeeperService.send_report(
                guild, report_channel_name, kicked_count
            )

            VoiceKeeperService.log_summary(
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
            if cleanup_callback:
                cleanup_callback()
