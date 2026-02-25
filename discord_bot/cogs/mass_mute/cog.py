# cogs/mass_mute/cog.py
# Role: Interface Layer (cogs/README.md 準拠)
# - Discordイベントリスナーと定時タスクの定義のみ
# - 具体的な処理は logic.py へ委譲
import discord
from discord.ext import commands, tasks
import datetime
import logging
import os
from dotenv import load_dotenv

from .logic import MassMuteLogic

load_dotenv()

ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')

# .env にカンマ区切りで記載されたチャンネル名をリストに変換する。
# 例) MUTE_ONLY_CHANNEL_NAMES=配信コメント,mute_only
def _csv(key: str) -> list[str]:
    return [s.strip() for s in os.getenv(key, '').split(',') if s.strip()]

MUTE_ONLY_CHANNEL_NAMES      = _csv('MUTE_ONLY_CHANNEL_NAMES')
READ_ONLY_MUTE_CHANNEL_NAMES = _csv('READ_ONLY_MUTE_CHANNEL_NAMES')

logger = logging.getLogger(__name__)


class MassMuteCog(commands.Cog):
    """通知マスミュート機能 (Interface Layer)

    Discordイベントの受付と定時タスクの管理を担当。
    権限操作・自己修復のロジックは MassMuteLogic に委譲する。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.owner_id = int(ADMIN_USER_ID)
        self.daily_mute_check.start()

        # Why: DB テーブル作成は副作用だが、Cog初期化時に1度だけ実行する特殊ケース。
        #      logic.py に委譲しつつ bot.get_db_connection を渡す。
        MassMuteLogic.create_table_if_not_exists(bot)

    def cog_unload(self):
        self.daily_mute_check.cancel()

    # ------------------------------------------------------------------
    #  ヘルパー
    # ------------------------------------------------------------------
    async def _send_admin_dm(self, embed: discord.Embed):
        """管理者にDMを送信するヘルパー"""
        try:
            owner = await self.bot.fetch_user(self.owner_id)
            if owner:
                await owner.send(embed=embed)
        except Exception as e:
            logger.error("[MassMute DM ERROR] %s", e)

    # ------------------------------------------------------------------
    #  自己修復トリガー1: チャンネル作成時
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """新規チャンネルが対象名に一致すれば即座に権限を設定する。

        Why: FEATURE_MASS_MUTE.md §3「チャンネル作成時（動的な自動適用）」の要件。
        """
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        everyone_role = guild.default_role

        result = await MassMuteLogic.handle_channel_created(
            channel=channel,
            everyone_role=everyone_role,
            mute_channel_names=MUTE_ONLY_CHANNEL_NAMES,
            readonly_channel_names=READ_ONLY_MUTE_CHANNEL_NAMES,
        )

        if result:
            embed = MassMuteLogic.build_result_embed(
                trigger="Channel Created",
                results=[result],
            )
            await self._send_admin_dm(embed)

    # ------------------------------------------------------------------
    #  自己修復トリガー2: チャンネル権限変更時
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ):
        """チャンネルの権限が変更された場合、期待値と異なれば修復する。

        Why: 「チャンネルの管理」権限を持つユーザーが権限を変更した場合に、
             定義済み権限を自動的に復元する自己修復機能。
        """
        if not isinstance(after, discord.TextChannel):
            return

        everyone_role = after.guild.default_role

        result = await MassMuteLogic.handle_channel_updated(
            channel=after,
            everyone_role=everyone_role,
            mute_channel_names=MUTE_ONLY_CHANNEL_NAMES,
            readonly_channel_names=READ_ONLY_MUTE_CHANNEL_NAMES,
        )

        if result and result.action == "repaired":
            embed = MassMuteLogic.build_result_embed(
                trigger="Self-Heal (Channel Update)",
                results=[result],
            )
            await self._send_admin_dm(embed)

    # ------------------------------------------------------------------
    #  自己修復トリガー3: ロール権限変更時
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """@everyone ロールの権限が変更された場合、全対象チャンネルを再チェックする。

        Why: 「ロールの管理」権限でデフォルトロールが変更されると、
             チャンネルごとの上書きが意図通り機能しなくなる可能性がある。
             @everyone のみを監視し、無関係なロール変更は無視する。
        """
        # @everyone 以外のロール変更は無視
        if after.id != after.guild.id:
            return

        guild = after.guild
        everyone_role = guild.default_role

        results = await MassMuteLogic.handle_role_updated(
            guild=guild,
            everyone_role=everyone_role,
            mute_channel_names=MUTE_ONLY_CHANNEL_NAMES,
            readonly_channel_names=READ_ONLY_MUTE_CHANNEL_NAMES,
        )

        # 修復が発生した場合のみ通知
        repaired = [r for r in results if r.action == "repaired"]
        if repaired:
            embed = MassMuteLogic.build_result_embed(
                trigger="Self-Heal (Role Update)",
                results=repaired,
            )
            await self._send_admin_dm(embed)

    # ------------------------------------------------------------------
    #  メイントリガー: 一括ミュート実行
    # ------------------------------------------------------------------
    async def execute_mute_logic(self, trigger: str):
        """全対象チャンネルへ権限を一括適用する。"""
        if not self.bot.guilds:
            return

        guild = self.bot.guilds[0]
        everyone_role = guild.default_role

        # 事前権限チェック: 不足している場合は管理者にDMして処理を中止しない
        # (処理は続行するが管理者に警告を送る)
        from services.permission_service import PermissionService
        missing_perms = PermissionService.preflight_check(guild)
        if missing_perms:
            warn_embed = discord.Embed(
                title="⚠️ マスミュート: 権限不足の警告",
                description="以下の権限が Bot に付与されていないため、チャンネル権限の設定が失敗する可能性があります。",
                color=0xff9800,
            )
            warn_embed.add_field(
                name="不足している権限",
                value="\n".join(f"• {p}" for p in missing_perms),
                inline=False,
            )
            warn_embed.add_field(
                name="対処方法",
                value="Discord サーバー設定 → ロール → [Bot のロール] → 権限 で上記を有効にしてください。",
                inline=False,
            )
            logger.warning("[MassMute] 権限不足: %s", missing_perms)
            await self._send_admin_dm(warn_embed)

        results = await MassMuteLogic.execute_mute(
            guild=guild,
            everyone_role=everyone_role,
            mute_channel_names=MUTE_ONLY_CHANNEL_NAMES,
            readonly_channel_names=READ_ONLY_MUTE_CHANNEL_NAMES,
        )

        # DBへのログ保存
        MassMuteLogic.save_log_to_db(self.bot, trigger, results)

        # 管理者への完了通知DM
        embed = MassMuteLogic.build_result_embed(trigger=trigger, results=results)
        await self._send_admin_dm(embed)

    # ------------------------------------------------------------------
    #  定時タスク（日本時間 0:00, 8:00, 16:00 → UTC 15:00, 23:00, 7:00）
    # ------------------------------------------------------------------
    @tasks.loop(time=[
        datetime.time(15, 0, tzinfo=datetime.timezone.utc),  # JST 0:00
        datetime.time(23, 0, tzinfo=datetime.timezone.utc),  # JST 8:00
        datetime.time(7, 0, tzinfo=datetime.timezone.utc),   # JST 16:00
    ])
    async def daily_mute_check(self):
        await self.execute_mute_logic("Daily Task")

    @daily_mute_check.before_loop
    async def before_daily_mute_check(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    #  診断コマンド: Bot の権限状態をチェックして管理者に報告する
    # ------------------------------------------------------------------
    @commands.command(name="mute_check")
    @commands.is_owner()
    async def mute_check_command(self, ctx: commands.Context):
        """Bot のマスミュート権限を診断して報告する。

        本番デプロイ前のセルフ診断コマンド。
        オーナーのみ実行可能。
        使用例: !mute_check
        """
        if not self.bot.guilds:
            await ctx.send("❌ Bot がサーバーに参加していません。")
            return

        guild = self.bot.guilds[0]
        from services.permission_service import PermissionService
        missing = PermissionService.preflight_check(guild)

        embed = discord.Embed(
            title="🔍 マスミュート 権限診断レポート",
            color=0x4caf50 if not missing else 0xf44336,
        )

        if not missing:
            embed.description = "✅ 必要な権限はすべて付与されています。"
        else:
            embed.description = "❌ 以下の権限が不足しています。"
            embed.add_field(
                name="不足権限",
                value="\n".join(f"• {p}" for p in missing),
                inline=False,
            )
            embed.add_field(
                name="対処方法",
                value=(
                    "Discord サーバー設定 → ロール → Bot のロール → 権限 タブ\n"
                    "→ `ロールの管理` と `チャンネルの管理` を **ON** にしてください。"
                ),
                inline=False,
            )

        # 対象チャンネルの存在と権限の精密確認
        all_target = list(MUTE_ONLY_CHANNEL_NAMES) + list(READ_ONLY_MUTE_CHANNEL_NAMES)
        found_lines = []
        for n in all_target:
            ch = discord.utils.get(guild.text_channels, name=n)
            if not ch:
                found_lines.append(f"❌ #{n} (チャンネルが見つかりません)")
            else:
                ch_missing = PermissionService.preflight_check(guild, ch)
                if not ch_missing:
                    found_lines.append(f"✅ #{n}")
                else:
                    found_lines.append(f"⚠️ #{n} (権限不足: {', '.join(ch_missing)})")
        
        channel_status = "\n".join(found_lines) or "(対象チャンネルなし)"
        embed.add_field(name="対象チャンネル診断", value=channel_status, inline=False)

        await ctx.send(embed=embed)
