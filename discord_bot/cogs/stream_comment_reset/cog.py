# cogs/stream_comment_reset/cog.py
# Role: Interface Layer (cogs/README.md 準拠)
# - Discord イベントリスナー・スラッシュコマンド・定時タスクの定義
# - 具体的な処理は logic.py へ委譲

import os
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands, Permissions
from discord.ext import commands, tasks

from .logic import (
    StreamCommentResetLogic,
    STREAM_COMMENT_CHANNEL_NAME,
    ADMIN_REPORT_CHANNEL_NAME,
    JST,
)

logger = logging.getLogger(__name__)

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
TARGET_USER_ID = int(os.getenv("TARGET_USER_ID", "0"))
ADMIN_ROLE_NAME = "管理者"
FALLBACK_HOUR_JST = 6


class StreamCommentResetCog(commands.Cog):
    """#配信コメント チャンネル月次リセット機能 (Interface Layer)

    - on_message: VoiceKeeper 寝落ち集計報告を検知して主トリガー発火
    - fallback_reset: 毎月21日 06:00 JST のフォールバック cron
    - on_guild_channel_update: Self Heal（Bot 権限の自動復元）
    - /reset_stream_comments: 管理者向けスラッシュコマンド
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_reset_month: int | None = None
        self._pending_reset: bool = False
        self.fallback_reset.start()

    def cog_unload(self):
        self.fallback_reset.cancel()

    # ================================================================
    # 主トリガー: VoiceKeeper 報告検知
    # ================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """VoiceKeeper が寝落ち集計報告を投稿したら月次リセットを実行する。"""
        if not StreamCommentResetLogic.is_voice_keeper_report(message):
            return

        now = datetime.now(JST)
        if now.day != 20:
            return  # 毎月20日のみ主トリガー発火

        await self._try_monthly_reset(triggered_by="voice_keeper")

    # ================================================================
    # フォールバック cron
    # ================================================================

    @tasks.loop(hours=24)
    async def fallback_reset(self):
        """毎月2日 06:00 JST に未リセットなら補完実行する。"""
        if not StreamCommentResetLogic.should_fallback_run():
            return
        await self._try_monthly_reset(triggered_by="fallback_scheduler")

    @fallback_reset.before_loop
    async def before_fallback_reset(self):
        await self.bot.wait_until_ready()

    # ================================================================
    # Self Heal
    # ================================================================

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ):
        """#配信コメント の権限変更を検知し、Bot 権限を自動修復する。"""
        bot_member = after.guild.me
        if not StreamCommentResetLogic.needs_self_heal(after, bot_member):
            return

        await StreamCommentResetLogic.execute_self_heal(
            channel=after,
            bot_member=bot_member,
            guild=after.guild,
        )

    # ================================================================
    # 予約リセット: 配信終了検知
    # ================================================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """ホストが VC を退室したとき、予約済みリセットがあれば自動実行する。"""
        if member.id != TARGET_USER_ID:
            return
        if not (before.channel is not None and after.channel is None):
            return
        if not self._pending_reset:
            return

        self._pending_reset = False
        await self._try_monthly_reset(triggered_by="pending_on_stream_end", force=True)

    # ================================================================
    # スラッシュコマンド
    # ================================================================

    @app_commands.command(
        name="reset_stream_comments",
        description="【管理者専用】#配信コメント チャンネルを即時リセットします",
    )
    @app_commands.describe(dry_run="True にするとプレビューのみ（実際には削除しない）")
    @app_commands.default_permissions()  # = Permissions(0): 全員非表示
    @app_commands.checks.has_role(ADMIN_ROLE_NAME)
    async def reset_stream_comments(
        self,
        interaction: discord.Interaction,
        dry_run: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            await interaction.followup.send("❌ ギルドが見つかりません。", ephemeral=True)
            return

        # 配信中フェールセーフ: ホストが VC 在席中は予約して終了後に自動実行
        if not dry_run and StreamCommentResetLogic.is_host_in_vc(guild, TARGET_USER_ID):
            self._pending_reset = True
            await interaction.followup.send(
                "⏳ 配信中のため即時実行できません。配信終了後（ホストが VC を退室した時点）に自動でリセットします。",
                ephemeral=True,
            )
            return

        if dry_run:
            channel = discord.utils.get(guild.text_channels, name=STREAM_COMMENT_CHANNEL_NAME)
            if channel is None:
                await interaction.followup.send("❌ 対象チャンネルが見つかりません。", ephemeral=True)
                return
            overwrites = StreamCommentResetLogic.build_overwrites(guild)
            preview = "\n".join(
                f"- {target.name}: allow={ow.pair()[0].value}, deny={ow.pair()[1].value}"
                for target, ow in overwrites.items()
            )
            await interaction.followup.send(
                f"🔍 **[Dry Run] リセットプレビュー**\n"
                f"対象チャンネル: #{channel.name}\n"
                f"カテゴリ: {channel.category}\n"
                f"**設定予定の overwrite:**\n{preview}",
                ephemeral=True,
            )
            return

        success, msg = await StreamCommentResetLogic.execute_reset(
            guild=guild,
            triggered_by=str(interaction.user),
        )
        if success:
            self._last_reset_month = datetime.now(JST).month
            await interaction.followup.send(
                "✅ リセットを実行しました。`#bot-log` を確認してください。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"❌ リセット失敗: {msg}", ephemeral=True)

    @reset_stream_comments.error
    async def reset_stream_comments_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        # defer されていない場合のみ response を使用
        if not interaction.response.is_done():
            if isinstance(error, app_commands.MissingRole):
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    f"❌ このコマンドは `{ADMIN_ROLE_NAME}` ロールのみ実行できます。",
                    ephemeral=True,
                )
            else:
                logger.error("[StreamCommentReset] コマンドエラー: %s", error)
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    f"❌ 予期しないエラーが発生しました: `{error}`",
                    ephemeral=True,
                )
        else:
            logger.error("[StreamCommentReset] コマンドエラー (defer済み): %s", error)

    # ================================================================
    # 内部ヘルパー
    # ================================================================

    async def _try_monthly_reset(self, triggered_by: str, force: bool = False):
        """当月未リセットであればリセットを実行する。force=True のとき冪等チェックをスキップする。"""
        now = datetime.now(JST)

        # メモリ上の冪等チェック（管理者による明示的な予約実行はスキップ）
        if not force and StreamCommentResetLogic.is_already_reset(self._last_reset_month, now):
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            logger.warning("[StreamCommentReset] ギルド未検出 GUILD_ID=%s", GUILD_ID)
            return

        success, _ = await StreamCommentResetLogic.execute_reset(
            guild=guild,
            triggered_by=triggered_by,
        )
        if success:
            self._last_reset_month = now.month
