import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)

class VoiceKeeperService:
    def __init__(self, report_channel_name: str):
        self.report_channel_name = report_channel_name

    async def find_report_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        return discord.utils.get(guild.text_channels, name=self.report_channel_name)

    async def kick_all_non_bots(self, channel: discord.abc.GuildChannel) -> int:
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
                    getattr(channel, "name", "?"), channel.id
                )
            except discord.HTTPException as e:
                logger.warning(
                    "[VoiceKeeper] Failed to move member in vc=%s(%s): %s",
                    getattr(channel, "name", "?"), channel.id, e
                )
        return count

    async def send_report(self, guild: discord.Guild, kicked_count: int) -> bool:
        report_ch = await self.find_report_channel(guild)
        if not report_ch:
            logger.info(
                "[VoiceKeeper] Report channel not found name=%s guild=%s(%s)",
                self.report_channel_name, guild.name, guild.id
            )
            return False

        msg = "【寝落ち集計】\n" f"今回の犠牲者は **{kicked_count}人** でした。おやすみなさい。"
        try:
            await report_ch.send(msg)
            return True
        except discord.Forbidden:
            logger.warning(
                "[VoiceKeeper] Missing permission to send message channel=%s(%s)",
                report_ch.name, report_ch.id
            )
            return False
        except discord.HTTPException as e:
            logger.warning("[VoiceKeeper] Failed to send report message: %s", e)
            return False

    def log_summary(
        self,
        *,
        reason: str,
        guild: discord.Guild,
        voice_channel: discord.abc.GuildChannel,
        host: Optional[discord.Member],
        kicked_count: int,
        report_sent: bool,
    ) -> None:
        # 犠牲者情報は出さない（人数のみ）
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
