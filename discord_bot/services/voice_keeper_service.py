# services/voice_keeper_service.py
# Why: VoiceKeeper のI/O操作（VC切断、チャンネルへの報告送信）は副作用を伴うため
#      services/ 層に配置する。旧 cogs/voice_keeper/services.py から移動。
#      @staticmethod 化でステートレスに再設計。
import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)


class VoiceKeeperService:
    """VoiceKeeper のI/O操作サービス。

    設計原則:
    - ステートレス: @staticmethod で実装（旧版はインスタンスメソッド）
    - ctx 非依存: discord.Guild, discord.VoiceChannel 等のモデルオブジェクトを引数に取る
    """

    @staticmethod
    async def kick_all_non_bots(channel: discord.abc.GuildChannel) -> int:
        """VCからBot以外の全メンバーを切断する。

        Args:
            channel: 対象のボイスチャンネル
        Returns:
            切断に成功した人数
        """
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return 0

        victims = [m for m in channel.members if not m.bot]
        count = 0

        for m in victims:
            try:
                await m.move_to(None, reason="VoiceKeeper: 寝落ち切断")
                count += 1
            except discord.Forbidden:
                logger.warning(
                    "[VoiceKeeper] Missing permission to move members. vc=%s(%s)",
                    getattr(channel, "name", "?"), channel.id,
                )
            except discord.HTTPException as e:
                logger.warning(
                    "[VoiceKeeper] Failed to move member in vc=%s(%s): %s",
                    getattr(channel, "name", "?"), channel.id, e,
                )
        return count

    @staticmethod
    async def send_report(
        guild: discord.Guild,
        report_channel_name: str,
        kicked_count: int,
    ) -> bool:
        """寝落ち集計レポートをテキストチャンネルに送信する。

        Args:
            guild: 対象ギルド
            report_channel_name: レポート先チャンネル名
            kicked_count: 切断人数
        Returns:
            送信成功かどうか
        """
        report_ch = discord.utils.get(guild.text_channels, name=report_channel_name)
        if not report_ch:
            logger.info(
                "[VoiceKeeper] Report channel not found name=%s guild=%s(%s)",
                report_channel_name, guild.name, guild.id,
            )
            return False

        msg = f"【寝落ち集計】\n今回の犠牲者は **{kicked_count}人** でした。おやすみなさい。"
        try:
            await report_ch.send(msg)
            return True
        except discord.Forbidden:
            logger.warning(
                "[VoiceKeeper] Missing permission to send message channel=%s(%s)",
                report_ch.name, report_ch.id,
            )
            return False
        except discord.HTTPException as e:
            logger.warning("[VoiceKeeper] Failed to send report message: %s", e)
            return False

    @staticmethod
    def log_summary(
        *,
        reason: str,
        guild: discord.Guild,
        voice_channel: discord.abc.GuildChannel,
        host: Optional[discord.Member],
        kicked_count: int,
        report_sent: bool,
    ) -> None:
        """実行結果のサマリーをログ出力する。"""
        logger.info(
            "[VoiceKeeper] %s guild=%s(%s) vc=%s(%s) host=%s(%s) kicked=%s report_sent=%s",
            reason,
            guild.name, guild.id,
            getattr(voice_channel, "name", "?"), voice_channel.id,
            (host.name if host else "None"),
            (host.id if host else "None"),
            kicked_count,
            report_sent,
        )
