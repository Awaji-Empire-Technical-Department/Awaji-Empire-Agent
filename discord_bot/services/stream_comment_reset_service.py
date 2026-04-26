# services/stream_comment_reset_service.py
# Why: #配信コメント リセット機能の I/O 操作（Discord API + DB Bridge）を集約する。
#      cog.py / logic.py から呼ばれる副作用付き処理をステートレスに提供する。

import logging
from typing import Any, Dict, Optional

import discord

from .bridge_client import bridge_client, BridgeUnavailableError

logger = logging.getLogger(__name__)


class StreamCommentResetService:
    """#配信コメント リセット機能の I/O サービス。

    設計原則:
    - ステートレス: @staticmethod で実装
    - ctx 非依存: discord.Guild, discord.TextChannel 等を引数に取る
    """

    # ================================================================
    # Discord API 操作
    # ================================================================

    @staticmethod
    async def delete_channel(channel: discord.TextChannel, reason: str) -> bool:
        """チャンネルを削除する。

        Returns:
            成功なら True、Forbidden なら False。
        """
        try:
            await channel.delete(reason=reason)
            return True
        except discord.Forbidden:
            logger.warning(
                "[StreamCommentReset] チャンネル削除権限なし channel=%s(%s)",
                channel.name, channel.id,
            )
            return False
        except discord.HTTPException as e:
            logger.error(
                "[StreamCommentReset] チャンネル削除失敗 channel=%s(%s): %s",
                channel.name, channel.id, e,
            )
            return False

    @staticmethod
    async def create_channel(
        guild: discord.Guild,
        *,
        name: str,
        category: Optional[discord.CategoryChannel],
        position: int,
        topic: Optional[str],
        overwrites: Dict[Any, discord.PermissionOverwrite],
        reason: str,
    ) -> Optional[discord.TextChannel]:
        """テキストチャンネルを作成する。

        Returns:
            作成されたチャンネル。失敗時は None。
        """
        try:
            new_channel = await guild.create_text_channel(
                name=name,
                category=category,
                position=position,
                topic=topic,
                overwrites=overwrites,
                reason=reason,
            )
            logger.info(
                "[StreamCommentReset] チャンネル作成成功 channel=%s(%s)",
                new_channel.name, new_channel.id,
            )
            return new_channel
        except discord.Forbidden as e:
            logger.error(
                "[StreamCommentReset] チャンネル作成権限エラー guild=%s(%s) error=%s",
                guild.name, guild.id, e,
            )
            return None
        except discord.HTTPException as e:
            logger.error(
                "[StreamCommentReset] チャンネル作成失敗 guild=%s(%s) status=%s error=%s",
                guild.name, guild.id, getattr(e, 'status', 'unknown'), e,
            )
            return None

    @staticmethod
    async def send_reset_notification(channel: discord.TextChannel) -> bool:
        """リセット完了通知を新チャンネルに送信する。"""
        try:
            await channel.send(
                "🔄 **チャンネルリセット完了**\n"
                "毎月恒例のリセットを実施しました。今月もコメントよろしくお願いします！\n"
                "通知OFF設定をお願いします！\n"
                "（設定方法: チャンネル名右の歯車アイコン → 通知設定 → 「このチャンネルの通知をミュートする」をON）"
            )
            return True
        except discord.HTTPException as e:
            logger.warning("[StreamCommentReset] 通知送信失敗: %s", e)
            return False

    @staticmethod
    async def send_admin_report(
        guild: discord.Guild,
        report_channel_name: str,
        message: str,
    ) -> bool:
        """管理者チャンネルにレポートを送信する。"""
        report_ch = discord.utils.get(guild.text_channels, name=report_channel_name)
        if not report_ch:
            logger.info(
                "[StreamCommentReset] レポートチャンネル未検出 name=%s guild=%s(%s)",
                report_channel_name, guild.name, guild.id,
            )
            return False

        try:
            await report_ch.send(message)
            return True
        except discord.Forbidden:
            logger.warning(
                "[StreamCommentReset] レポート送信権限なし channel=%s(%s)",
                report_ch.name, report_ch.id,
            )
            return False
        except discord.HTTPException as e:
            logger.warning("[StreamCommentReset] レポート送信失敗: %s", e)
            return False

    @staticmethod
    async def fix_bot_permissions(
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> bool:
        """Bot の channel overwrite を Self Heal で修復する。"""
        try:
            await channel.set_permissions(
                bot_member,
                manage_roles=True,
                manage_messages=True,
                view_channel=True,
                send_messages=True,
                reason="Self Heal: Bot 権限の自動復元",
            )
            return True
        except discord.Forbidden:
            logger.warning(
                "[StreamCommentReset] Self Heal 失敗: 権限不足 channel=%s(%s)",
                channel.name, channel.id,
            )
            return False
        except discord.HTTPException as e:
            logger.error("[StreamCommentReset] Self Heal 失敗: %s", e)
            return False

    # ================================================================
    # DB Bridge 操作
    # ================================================================

    @staticmethod
    async def log_to_db(
        triggered_by: str,
        event_type: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """リセットログを DB に記録する。

        Bridge 障害時はリセット処理を中断しない（警告のみ）。
        """
        try:
            res = await bridge_client.request(
                "POST",
                "/reset_logs",
                json={
                    "triggered_by": triggered_by,
                    "event_type": event_type,
                    "status": status,
                    "error_message": error_message,
                },
            )
            return res is not None
        except BridgeUnavailableError:
            logger.warning("[StreamCommentReset] DB Bridge 接続失敗 — ログ記録スキップ")
            return False

    @staticmethod
    async def check_month_reset(year: int, month: int) -> bool:
        """指定年月に成功済みリセットがあるか DB で確認する。

        Bridge 障害時は False（未実行扱い）を返す。
        """
        try:
            res = await bridge_client.request(
                "GET",
                "/reset_logs/check_month",
                params={"year": year, "month": month},
            )
            if isinstance(res, dict):
                return res.get("reset_done", False)
            return False
        except BridgeUnavailableError:
            logger.warning("[StreamCommentReset] DB Bridge 接続失敗 — 月次チェックスキップ")
            return False
