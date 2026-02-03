# cogs/mass_mute/logic.py
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Optional

import discord
from services.permission import PermissionService


@dataclass(frozen=True)
class MuteExecutionResult:
    success_list: List[str]
    error_list: List[str]
    status: str              # "SUCCESS" / "WARNING" / "ERROR"
    details: str             # DBに保存する短い概要
    fatal_reason: str = ""   # 致命的に実行できない場合の理由（権限確保失敗など）


class MassMuteLogic:
    @staticmethod
    async def execute(
        guild: discord.Guild,
        bot_member: discord.Member,
        mute_only_channel_names: List[str],
        read_only_mute_channel_names: List[str],
        send_ok_overwrite: discord.PermissionOverwrite,
        send_ng_overwrite: discord.PermissionOverwrite,
    ) -> MuteExecutionResult:
        everyone_role = guild.default_role

        success_list: List[str] = []
        error_list: List[str] = []

        # 権限自己修復は「どれか1チャンネル」を足場にして試す
        # (guild.me が manage_roles を持っていればロール付与で回復する想定)
        sample_channel: Optional[discord.TextChannel] = None
        if guild.text_channels:
            sample_channel = guild.text_channels[0]

        if sample_channel is not None:
            ensure = await PermissionService.ensure_manage_channels(sample_channel, bot_member)
            if not ensure.ok:
                # ここで詰む場合は、以降の set_permissions がほぼ全滅するので終了
                return MuteExecutionResult(
                    success_list=[],
                    error_list=[ensure.reason],
                    status="ERROR",
                    details="Auto-fix failed; cannot proceed.",
                    fatal_reason=ensure.reason,
                )

        # --- 1) 送信許可チャンネル ---
        for name in mute_only_channel_names:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel is None:
                continue

            try:
                await channel.set_permissions(everyone_role, overwrite=send_ok_overwrite)
                success_list.append(f"#{name} (許可)")
            except discord.Forbidden:
                # 一度だけ自己修復→リトライ
                ensure = await PermissionService.ensure_manage_channels(channel, bot_member)
                if ensure.ok:
                    try:
                        await channel.set_permissions(everyone_role, overwrite=send_ok_overwrite)
                        success_list.append(f"#{name} (許可)")
                        continue
                    except Exception as e:
                        error_list.append(f"#{name}: {e}")
                else:
                    error_list.append(f"#{name}: {ensure.reason}")
            except Exception as e:
                error_list.append(f"#{name}: {e}")

        # --- 2) 送信禁止チャンネル ---
        for name in read_only_mute_channel_names:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel is None:
                continue

            try:
                await channel.set_permissions(everyone_role, overwrite=send_ng_overwrite)
                success_list.append(f"#{name} (禁止)")
            except discord.Forbidden:
                ensure = await PermissionService.ensure_manage_channels(channel, bot_member)
                if ensure.ok:
                    try:
                        await channel.set_permissions(everyone_role, overwrite=send_ng_overwrite)
                        success_list.append(f"#{name} (禁止)")
                        continue
                    except Exception as e:
                        error_list.append(f"#{name}: {e}")
                else:
                    error_list.append(f"#{name}: {ensure.reason}")
            except Exception as e:
                error_list.append(f"#{name}: {e}")

        status = "SUCCESS" if not error_list else "WARNING"
        details = f"Success: {len(success_list)}, Errors: {len(error_list)}"

        return MuteExecutionResult(
            success_list=success_list,
            error_list=error_list,
            status=status,
            details=details,
        )
