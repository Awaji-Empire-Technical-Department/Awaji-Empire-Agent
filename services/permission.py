# services/permission.py
from __future__ import annotations

import logging
from dataclasses import dataclass
import discord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnsureResult:
    ok: bool
    reason: str = ""


class PermissionService:
    """
    Discord API I/O を伴う権限チェック + 自己修復サービス

    自己修復の基本方針:
      - Botがguildレベルで Manage Roles を持つ場合
      - Bot自身に「manage_channels を持つ修復用ロール」を付与して権限を回復する
    """

    REPAIR_ROLE_NAME = "AEABot - SelfRepair"

    @staticmethod
    async def ensure_manage_channels(
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> EnsureResult:
        guild = channel.guild
        if guild is None:
            return EnsureResult(False, "This function must be used in a guild channel.")

        # 1) すでに操作可能ならOK
        perms = channel.permissions_for(bot_member)
        if perms.administrator or perms.manage_channels:
            return EnsureResult(True)

        # 2) 自己修復の前提：Botが Manage Roles を持っているか
        gp = bot_member.guild_permissions
        if not (gp.administrator or gp.manage_roles):
            return EnsureResult(
                False,
                "Auto-fix failed: Bot lacks 'Manage Roles' (or Administrator) at guild level."
            )

        # 3) 修復用ロール取得 or 作成
        repair_role = discord.utils.get(guild.roles, name=PermissionService.REPAIR_ROLE_NAME)

        try:
            if repair_role is None:
                perms_obj = discord.Permissions.none()
                perms_obj.manage_channels = True  # チャンネルoverwrite編集に必要
                repair_role = await guild.create_role(
                    name=PermissionService.REPAIR_ROLE_NAME,
                    permissions=perms_obj,
                    reason="Auto-fix: create self-repair role (manage_channels)",
                )

            # 4) ロール階層チェック
            # Botは「自分のトップロールより下のロール」しか付与できない
            if repair_role >= bot_member.top_role and not gp.administrator:
                return EnsureResult(
                    False,
                    "Auto-fix failed: Role hierarchy prevents assigning the repair role. "
                    "Move bot's top role above the repair role (or grant Administrator)."
                )

            # 5) Bot自身に付与
            if repair_role not in bot_member.roles:
                await bot_member.add_roles(
                    repair_role,
                    reason="Auto-fix: grant self manage_channels via repair role",
                )

            # 6) 再評価
            perms2 = channel.permissions_for(bot_member)
            if perms2.administrator or perms2.manage_channels:
                logger.info("Auto-fix succeeded: manage_channels ensured via role.")
                return EnsureResult(True)

            return EnsureResult(False, "Auto-fix attempted but still missing manage_channels.")

        except discord.Forbidden:
            logger.exception("Auto-fix failed: Forbidden while creating/assigning roles.")
            return EnsureResult(
                False,
                "Auto-fix failed: Forbidden. Check bot has Manage Roles and role position is high enough."
            )
        except discord.HTTPException as e:
            logger.exception("Auto-fix failed: HTTPException.")
            return EnsureResult(False, f"Auto-fix failed: HTTPException: {e}")
