# services/permission_service.py
# Why: パーミッション操作は副作用を伴うI/O処理であり、services/ に配置する。
#      mass_mute 以外の Cog からも再利用可能な汎用サービスとして設計。
import logging
from dataclasses import dataclass
from typing import List, Optional

import discord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PermissionResult:
    """権限操作の結果を表す値オブジェクト。

    Why: 呼び出し元に生のAPIエラーを投げず、構造化された結果を返す
         （services/README.md のエラーハンドリング規約）。
    """
    channel_name: str
    success: bool
    action: str  # "applied" | "repaired" | "skipped"
    error: Optional[str] = None


class PermissionService:
    """チャンネル権限操作の汎用サービス。

    設計原則:
    - ステートレス: メンバ変数を持たず @staticmethod で実装
    - ctx 非依存: discord.Guild, discord.Role 等のモデルオブジェクトを引数に取る
    """

    @staticmethod
    def preflight_check(guild: discord.Guild, channel: Optional[discord.TextChannel] = None) -> list[str]:
        """Bot が権限操作を行うのに必要な権限を確認し、不足リストを返す。"""
        me = guild.me
        perms = channel.permissions_for(me) if channel else me.guild_permissions
        
        missing = []
        if not perms.manage_roles:
            missing.append("Manage Roles / Manage Permissions (ロールの管理 / 権限の管理)")
        if not perms.manage_channels:
            missing.append("Manage Channels (チャンネルの管理)")
        return missing

    @staticmethod
    async def repair_self_if_blocked(channel: discord.TextChannel) -> bool:
        """Bot 自身がチャンネル内の「権限の管理」を拒否されている場合、
        サーバーレベルの「ロールの管理」権限を使って自身の制限を解除する。

        Why: 本機能の真の「自己修復」。サーバー権限さえあれば、チャンネルごとの
             手動設定ミスを Bot が自分で直して進むことができる。
        """
        me = channel.guild.me
        
        # 1. サーバーレベルの権限があるか確認
        if not me.guild_permissions.manage_roles:
            return False # サーバーレベルで権限がない場合はどうしようもない
        
        # 2. 現在のチャンネル内での実効権限を確認
        perms = channel.permissions_for(me)
        if perms.manage_roles:
            return True # 既に権限があるので修復不要
            
        logger.info("[PermissionService] Bot is blocked in #%s. Attempting to unblock itself using server-wide Manage Roles.", channel.name)
        try:
            # 3. 自身のメンバー上書き設定で「権限の管理」を強制許可に設定
            await channel.set_permissions(me, manage_roles=True, reason="Self-healing: Unblocking bot's own permission to manage channel.")
            return True
        except Exception as e:
            logger.error("[PermissionService] Failed to unblock itself in #%s: %s", channel.name, e)
            return False

    @staticmethod
    async def apply_permission(
        channel: discord.TextChannel,
        role: discord.Role,
        overwrite: discord.PermissionOverwrite,
    ) -> PermissionResult:
        """単一チャンネルに対して権限上書きを適用する。

        Args:
            channel: 対象テキストチャンネル
            role: 権限を設定するロール（通常は @everyone）
            overwrite: 適用する権限上書きオブジェクト
        """
        try:
            await channel.set_permissions(role, overwrite=overwrite)
            return PermissionResult(
                channel_name=channel.name,
                success=True,
                action="applied",
            )
        except discord.Forbidden:
            # --- 自己修復試行 ---
            if await PermissionService.repair_self_if_blocked(channel):
                try:
                    await channel.set_permissions(role, overwrite=overwrite)
                    return PermissionResult(channel_name=channel.name, success=True, action="applied")
                except discord.Forbidden:
                    pass # 修復したが依然として失敗

            # ここに到達した場合は本当に権限不足
            missing = PermissionService.preflight_check(channel.guild, channel)
            missing_str = ", ".join(missing) if missing else "不明 (ロール順位が低い、若しくは 2FA 設定の問題の可能性)"
            msg = (
                f"Missing permissions to edit channel #{channel.name}. "
                f"不足権限(チャンネル内): [{missing_str}]. "
                f"チャンネル設定の「権限」タブで Bot のロールに '権限の管理' を許可してください。"
            )
            logger.warning("[PermissionService] %s", msg)
            return PermissionResult(
                channel_name=channel.name,
                success=False,
                action="applied",
                error=msg,
            )
        except discord.HTTPException as e:
            msg = f"HTTP error on #{channel.name}: {e}"
            logger.warning("[PermissionService] %s", msg)
            return PermissionResult(
                channel_name=channel.name,
                success=False,
                action="applied",
                error=msg,
            )

    @staticmethod
    def needs_repair(
        channel: discord.TextChannel,
        role: discord.Role,
        expected: discord.PermissionOverwrite,
    ) -> bool:
        """チャンネルの現在の権限上書きが期待値と一致するか判定する。

        Why: 自己修復機能の核。on_guild_channel_update 等で呼ばれ、
             current と expected を比較して差異があれば True を返す。
             判定は純粋な比較だがチャンネルの状態参照を伴うため services に配置。

        Args:
            channel: チェック対象チャンネル
            role: 比較対象のロール
            expected: 期待される権限上書き
        Returns:
            修復が必要なら True
        """
        current = channel.overwrites_for(role)

        # PermissionOverwrite の各権限値を比較
        # Why: discord.py の PermissionOverwrite.__eq__ はインスタンス比較のため、
        #      個々の権限フィールドを比較する必要がある。
        for perm, value in expected:
            if value is not None and getattr(current, perm) != value:
                return True
        return False

    @staticmethod
    async def check_and_repair(
        channel: discord.TextChannel,
        role: discord.Role,
        expected: discord.PermissionOverwrite,
    ) -> PermissionResult:
        """権限の差異を検知し、必要があれば修復する。

        Args:
            channel: チェック対象チャンネル
            role: 比較対象のロール
            expected: 期待される権限上書き
        Returns:
            修復が実行されたか、またはスキップされたかを示す結果
        """
        if not PermissionService.needs_repair(channel, role, expected):
            return PermissionResult(
                channel_name=channel.name,
                success=True,
                action="skipped",
            )

        logger.info(
            "[PermissionService] Repairing permissions for #%s (role: %s)",
            channel.name,
            role.name,
        )
        try:
            await channel.set_permissions(role, overwrite=expected)
            return PermissionResult(
                channel_name=channel.name,
                success=True,
                action="repaired",
            )
        except discord.Forbidden:
            # --- 自己修復試行 ---
            if await PermissionService.repair_self_if_blocked(channel):
                try:
                    await channel.set_permissions(role, overwrite=expected)
                    return PermissionResult(channel_name=channel.name, success=True, action="repaired")
                except discord.Forbidden:
                    pass

            missing = PermissionService.preflight_check(channel.guild, channel)
            missing_str = ", ".join(missing) if missing else "不明 (ロール順位が低い、若しくは 2FA 設定の問題の可能性)"
            msg = (
                f"Missing permissions to repair #{channel.name}. "
                f"不足権限(チャンネル内): [{missing_str}]"
            )
            logger.warning("[PermissionService] %s", msg)
            return PermissionResult(
                channel_name=channel.name,
                success=False,
                action="repaired",
                error=msg,
            )
        except discord.HTTPException as e:
            msg = f"HTTP error repairing #{channel.name}: {e}"
            logger.warning("[PermissionService] %s", msg)
            return PermissionResult(
                channel_name=channel.name,
                success=False,
                action="repaired",
                error=msg,
            )

    @staticmethod
    async def enforce_all(
        guild: discord.Guild,
        role: discord.Role,
        channel_overwrites: List[tuple],
    ) -> List[PermissionResult]:
        """全対象チャンネルに一括で権限を適用する。

        Args:
            guild: 対象ギルド
            role: 権限を設定するロール
            channel_overwrites: [(channel_name, overwrite), ...] のリスト
        Returns:
            各チャンネルの操作結果リスト
        """
        results = []
        for channel_name, overwrite in channel_overwrites:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel is None:
                results.append(PermissionResult(
                    channel_name=channel_name,
                    success=False,
                    action="applied",
                    error="Channel not found",
                ))
                continue
            result = await PermissionService.apply_permission(channel, role, overwrite)
            results.append(result)
        return results

    @staticmethod
    async def repair_all(
        guild: discord.Guild,
        role: discord.Role,
        channel_overwrites: List[tuple],
    ) -> List[PermissionResult]:
        """全対象チャンネルの権限を検査し、差異があれば修復する。

        Args:
            guild: 対象ギルド
            role: 権限を設定するロール
            channel_overwrites: [(channel_name, overwrite), ...] のリスト
        Returns:
            各チャンネルの操作結果リスト（修復 or スキップ）
        """
        results = []
        for channel_name, overwrite in channel_overwrites:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel is None:
                # チャンネルが存在しない場合はスキップ（エラーではない）
                continue
            result = await PermissionService.check_and_repair(channel, role, overwrite)
            results.append(result)
        return results
