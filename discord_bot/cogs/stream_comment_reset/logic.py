# cogs/stream_comment_reset/logic.py
# Why: #配信コメント リセット機能のビジネスロジック。
#      ctx 非依存・ステートレスな @staticmethod で実装し、
#      I/O は services/stream_comment_reset_service.py に委譲する。

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import discord

from services.stream_comment_reset_service import StreamCommentResetService

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# ============================================================
# 定数（仕様書 §4.2 準拠）
# ============================================================

STREAM_COMMENT_CHANNEL_NAME = os.getenv("STREAM_COMMENT_CHANNEL_NAME", "配信コメント")
ADMIN_REPORT_CHANNEL_NAME = os.getenv("ADMIN_REPORT_CHANNEL_NAME", "bot-log")
VOICE_KEEPER_REPORT_KEYWORD = os.getenv("VOICE_KEEPER_REPORT_KEYWORD", "寝落ち")
BOT_ROLE_NAME = os.getenv("BOT_ROLE_NAME", "Bot")

CHANNEL_OVERWRITES_SPEC: List[Dict[str, Any]] = [
    {"target": "everyone", "allow": ["view_channel", "send_messages"], "deny": []},
    {"target": "bot",      "allow": ["view_channel", "send_messages",
                                     "manage_messages", "manage_roles"], "deny": []},
]


class StreamCommentResetLogic:
    """#配信コメント リセット機能のビジネスロジック。

    設計原則:
    - ctx 非依存: discord.Guild / discord.TextChannel 等を引数に取る
    - I/O は StreamCommentResetService に委譲
    """

    # ================================================================
    # トリガー判定
    # ================================================================

    @staticmethod
    def is_voice_keeper_report(message: discord.Message) -> bool:
        """メッセージが VoiceKeeper の寝落ち集計報告かどうかを判定する。"""
        if not message.author.bot:
            return False
        if not isinstance(message.channel, discord.TextChannel):
            return False
        if message.channel.name != STREAM_COMMENT_CHANNEL_NAME:
            return False
        if VOICE_KEEPER_REPORT_KEYWORD not in (message.content or ""):
            return False
        return True

    @staticmethod
    def should_fallback_run(now: Optional[datetime] = None) -> bool:
        """フォールバック cron が実行すべきタイミングか判定する。
        毎月21日 06:00 JST のみ True。
        """
        if now is None:
            now = datetime.now(JST)
        return now.day == 21 and now.hour == 6

    @staticmethod
    def is_already_reset(last_reset_month: Optional[int], now: Optional[datetime] = None) -> bool:
        """当月リセット済みかをメモリ上の値で判定する。"""
        if now is None:
            now = datetime.now(JST)
        return last_reset_month == now.month

    # ================================================================
    # overwrite 構築
    # ================================================================

    @staticmethod
    def build_overwrites(guild: discord.Guild) -> Dict[Any, discord.PermissionOverwrite]:
        """CHANNEL_OVERWRITES_SPEC を discord.PermissionOverwrite に変換する。"""
        overwrites: Dict[Any, discord.PermissionOverwrite] = {}

        for spec in CHANNEL_OVERWRITES_SPEC:
            target_key: str = spec["target"]

            if target_key == "everyone":
                target = guild.default_role
            elif target_key == "bot":
                # Bot メンバーに対して権限を設定
                target = discord.utils.get(guild.roles, name=BOT_ROLE_NAME)
                if target is None:
                    logger.warning(
                        "[StreamCommentReset] Bot ロール '%s' が見つかりません — スキップ",
                        BOT_ROLE_NAME,
                    )
                    continue
            else:
                role_name = target_key.split("role:")[1]
                target = discord.utils.get(guild.roles, name=role_name)
                if target is None:
                    logger.warning(
                        "[StreamCommentReset] ロール '%s' が見つかりません — スキップ",
                        role_name,
                    )
                    continue

            allow_perms = {p: True for p in spec["allow"]}
            deny_perms = {p: False for p in spec["deny"]}
            overwrites[target] = discord.PermissionOverwrite(**{**allow_perms, **deny_perms})

        return overwrites

    # ================================================================
    # リセット実行
    # ================================================================

    @staticmethod
    async def execute_reset(
        guild: discord.Guild,
        triggered_by: str,
    ) -> Tuple[bool, str]:
        """チャンネル削除→再作成のリセットを実行する。

        Returns:
            (成功フラグ, ステータスメッセージ)
        """
        svc = StreamCommentResetService

        channel = discord.utils.get(guild.text_channels, name=STREAM_COMMENT_CHANNEL_NAME)
        if channel is None:
            error_msg = "対象チャンネルが見つかりません"
            await svc.send_admin_report(
                guild, ADMIN_REPORT_CHANNEL_NAME,
                f"[StreamCommentReset] ❌ {error_msg}",
            )
            await svc.log_to_db(triggered_by, "monthly_reset", "failed", error_msg)
            return False, error_msg

        # 元の位置情報を退避
        category = channel.category
        position = channel.position
        topic = channel.topic

        # チャンネル削除
        deleted = await svc.delete_channel(channel, reason="月次リセット by Awaji Empire Agent")
        if not deleted:
            error_msg = "チャンネル削除権限がありません"
            await svc.send_admin_report(
                guild, ADMIN_REPORT_CHANNEL_NAME,
                f"[StreamCommentReset] ❌ {error_msg}",
            )
            await svc.log_to_db(triggered_by, "monthly_reset", "failed", error_msg)
            return False, error_msg

        # overwrite 構築 + チャンネル再作成
        overwrites = StreamCommentResetLogic.build_overwrites(guild)

        new_channel = await svc.create_channel(
            guild,
            name=STREAM_COMMENT_CHANNEL_NAME,
            category=category,
            position=position,
            topic=topic,
            overwrites=overwrites,
            reason="月次リセット by Awaji Empire Agent",
        )
        if new_channel is None:
            error_msg = "チャンネル再作成に失敗しました"
            await svc.send_admin_report(
                guild, ADMIN_REPORT_CHANNEL_NAME,
                f"[StreamCommentReset] ❌ {error_msg}（チャンネルは削除済み — 手動復旧が必要）",
            )
            await svc.log_to_db(triggered_by, "monthly_reset", "failed", error_msg)
            return False, error_msg

        # リセット通知
        await svc.send_reset_notification(new_channel)

        # 管理者レポート
        now = datetime.now(JST)
        trigger_label = StreamCommentResetLogic._trigger_label(triggered_by)
        await svc.send_admin_report(
            guild, ADMIN_REPORT_CHANNEL_NAME,
            f"[StreamCommentReset] ✅ 月次リセット完了\n"
            f"- 実行日時 : {now.strftime('%Y-%m-%d %H:%M:%S')} JST\n"
            f"- トリガー : {trigger_label}\n"
            f"- 処理内容 : チャンネル削除 → 再作成 + overwrite 再設定",
        )

        # DB ログ
        event_type = "manual_reset" if triggered_by not in ("voice_keeper", "fallback_scheduler") else "monthly_reset"
        await svc.log_to_db(triggered_by, event_type, "success")

        return True, "リセット完了"

    # ================================================================
    # 配信中判定（フェールセーフ）
    # ================================================================

    @staticmethod
    def is_host_in_vc(guild: discord.Guild, target_user_id: int) -> bool:
        """ホストが現在 VC に在席しているか（= 配信中か）を返す。
        配信中は手動リセットをブロックするフェールセーフで使用する。
        """
        if target_user_id == 0:
            return False
        member = guild.get_member(target_user_id)
        if member is None:
            return False
        return member.voice is not None and member.voice.channel is not None

    # ================================================================
    # Self Heal 判定・実行
    # ================================================================

    @staticmethod
    def needs_self_heal(
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> bool:
        """Self Heal が必要かどうかを判定する。"""
        if channel.name != STREAM_COMMENT_CHANNEL_NAME:
            return False
        overwrite = channel.overwrites_for(bot_member)
        return overwrite.manage_roles is not True

    @staticmethod
    async def execute_self_heal(
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
        guild: discord.Guild,
    ) -> bool:
        """Self Heal を実行する。"""
        svc = StreamCommentResetService

        healed = await svc.fix_bot_permissions(channel, bot_member)
        now = datetime.now(JST)

        if healed:
            await svc.send_admin_report(
                guild, ADMIN_REPORT_CHANNEL_NAME,
                f"[StreamCommentReset] ⚠️ Self Heal 発動\n"
                f"- 検知日時 : {now.strftime('%Y-%m-%d %H:%M:%S')} JST\n"
                f"- 対象     : #{channel.name}\n"
                f"- 原因     : Bot の manage_roles overwrite が除去されていました\n"
                f"- 対応     : channel overwrite を自動再設定しました",
            )
            await svc.log_to_db("self_heal", "self_heal", "success")
            return True

        await svc.send_admin_report(
            guild, ADMIN_REPORT_CHANNEL_NAME,
            f"[StreamCommentReset] ❌ Self Heal 失敗: Bot に manage_roles 権限がありません",
        )
        await svc.log_to_db("self_heal", "self_heal", "failed", "Forbidden")
        return False

    # ================================================================
    # ヘルパー
    # ================================================================

    @staticmethod
    def _trigger_label(triggered_by: str) -> str:
        """管理者レポート用のトリガーラベルを生成する。"""
        if triggered_by == "voice_keeper":
            return "voice_keeper（VoiceKeeper 寝落ち集計報告を検知）"
        if triggered_by == "fallback_scheduler":
            return "fallback_scheduler（配信なし or 主トリガー未発火のため補完）"
        return f"{triggered_by}（Discord ユーザー）"
