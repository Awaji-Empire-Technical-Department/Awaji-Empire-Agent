# cogs/mass_mute/logic.py
# Role: Business Logic Layer (cogs/README.md 準拠)
# - 具体的なミュート処理・自己修復ロジック
# - ctx 非依存、discord.Guild / discord.Role 等のモデルオブジェクトを引数に取る
# - 権限の実操作は services/permission_service.py に委譲
import datetime
import logging
from typing import List, Optional

import discord

from services.permission_service import PermissionResult, PermissionService

logger = logging.getLogger(__name__)

# 権限オブジェクトの定義
# Why: 仕様で定義された権限テンプレート。MUTE_ONLY は送信可能だが
#      mention_everyone と manage_webhooks を無効化。
#      READ_ONLY はさらに send_messages も無効化。
SEND_OK_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=True,
    mention_everyone=False,
    manage_webhooks=False,
)

SEND_NG_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,
    send_messages=False,
    mention_everyone=False,
    manage_webhooks=False,
)


def _build_channel_overwrites(
    mute_channel_names: List[str],
    readonly_channel_names: List[str],
) -> List[tuple]:
    """チャンネル名と権限上書きのペアリストを構築する。

    Why: enforce_all / repair_all の引数形式に変換する共通ヘルパー。
         純粋関数だが discord.PermissionOverwrite に依存するため
         common/ ではなく logic.py に配置。
    """
    pairs = []
    for name in mute_channel_names:
        pairs.append((name, SEND_OK_OVERWRITE))
    for name in readonly_channel_names:
        pairs.append((name, SEND_NG_OVERWRITE))
    return pairs


class MassMuteLogic:
    """通知マスミュート機能のビジネスロジック。

    設計原則:
    - @staticmethod で実装（ステートレス）
    - ctx 非依存
    - 権限操作は PermissionService に委譲
    """

    @staticmethod
    async def execute_mute(
        guild: discord.Guild,
        everyone_role: discord.Role,
        mute_channel_names: List[str],
        readonly_channel_names: List[str],
    ) -> List[PermissionResult]:
        """全対象チャンネルへ権限を一括適用する。

        Bot起動時・定時タスクで呼ばれるメインロジック。
        """
        channel_overwrites = _build_channel_overwrites(
            mute_channel_names, readonly_channel_names
        )
        return await PermissionService.enforce_all(
            guild=guild,
            role=everyone_role,
            channel_overwrites=channel_overwrites,
        )

    @staticmethod
    async def handle_channel_created(
        channel: discord.TextChannel,
        everyone_role: discord.Role,
        mute_channel_names: List[str],
        readonly_channel_names: List[str],
    ) -> Optional[PermissionResult]:
        """新規チャンネルが対象名に一致すれば権限を設定する。

        Returns:
            権限が適用された場合は結果、対象外なら None。
        """
        overwrite = None
        if channel.name in mute_channel_names:
            overwrite = SEND_OK_OVERWRITE
        elif channel.name in readonly_channel_names:
            overwrite = SEND_NG_OVERWRITE

        if overwrite is None:
            return None

        logger.info(
            "[MassMute] New channel #%s matches target list, applying permissions.",
            channel.name,
        )
        return await PermissionService.apply_permission(
            channel=channel,
            role=everyone_role,
            overwrite=overwrite,
        )

    @staticmethod
    async def handle_channel_updated(
        channel: discord.TextChannel,
        everyone_role: discord.Role,
        mute_channel_names: List[str],
        readonly_channel_names: List[str],
    ) -> Optional[PermissionResult]:
        """チャンネル更新時に権限が期待値と異なれば修復する。

        自己修復機能の核: 「チャンネルの管理」権限による外部変更を検知・復元。

        Returns:
            修復/スキップされた場合は結果、対象外なら None。
        """
        expected = None
        if channel.name in mute_channel_names:
            expected = SEND_OK_OVERWRITE
        elif channel.name in readonly_channel_names:
            expected = SEND_NG_OVERWRITE

        if expected is None:
            return None

        return await PermissionService.check_and_repair(
            channel=channel,
            role=everyone_role,
            expected=expected,
        )

    @staticmethod
    async def handle_role_updated(
        guild: discord.Guild,
        everyone_role: discord.Role,
        mute_channel_names: List[str],
        readonly_channel_names: List[str],
    ) -> List[PermissionResult]:
        """ロール変更時に全対象チャンネルの権限を再チェック・修復する。

        自己修復機能: 「ロールの管理」権限で @everyone が変更された場合に
        全対象チャンネルのチャンネルごとの上書き（overwrite）が正しいか検証する。
        """
        channel_overwrites = _build_channel_overwrites(
            mute_channel_names, readonly_channel_names
        )
        return await PermissionService.repair_all(
            guild=guild,
            role=everyone_role,
            channel_overwrites=channel_overwrites,
        )

    @staticmethod
    def build_result_embed(
        trigger: str,
        results: List[PermissionResult],
    ) -> discord.Embed:
        """操作結果を管理者DM用 Embed に変換する。

        Why: Embed生成はDiscord固有だが副作用なし（APIコールなし）。
             cog.py ではなく logic.py に配置してテスト可能にする。
        """
        success_list = [r for r in results if r.success]
        error_list = [r for r in results if not r.success]

        color = 0x4caf50  # green
        if error_list:
            color = 0xf44336  # red

        embed = discord.Embed(
            title="🛡️ 通知抑制処理 完了報告",
            description=f"実行トリガー: **{trigger}**",
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        if success_list:
            lines = []
            for r in success_list:
                label = "修復" if r.action == "repaired" else "適用"
                lines.append(f"#{r.channel_name} ({label})")
            embed.add_field(name="✅ 成功", value="\n".join(lines), inline=False)

        if error_list:
            lines = [f"#{r.channel_name}: {r.error}" for r in error_list]
            embed.add_field(name="❌ エラー", value="\n".join(lines), inline=False)

        if not success_list and not error_list:
            embed.description += "\n対象のチャンネルが見つかりませんでした。"

        return embed

    @staticmethod
    def create_table_if_not_exists(bot) -> None:
        """ログ保存用のテーブルがなければ作成する。

        Why: Bot起動時に1度だけ呼ばれる。bot.get_db_connection() を使うため
             完全にステートレスにはできないが、bot オブジェクトを引数として
             受け取ることで ctx 非依存を維持。
        """
        try:
            conn = bot.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mute_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    trigger_name VARCHAR(50),
                    executed_at DATETIME,
                    status VARCHAR(20),
                    details TEXT
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("[MassMute] DB Table check OK.")
        except Exception as e:
            logger.error("[MassMute] DB Init Error: %s", e)

    @staticmethod
    def save_log_to_db(
        bot,
        trigger: str,
        results: List[PermissionResult],
    ) -> None:
        """操作結果をDBに保存する。

        Why: DB書き込みは副作用だが、mysql.connector（同期ドライバ）を使用するため
             services/log_service.py（aiomysql ベース）とは別系統。
             将来的にはDB統合時に一本化する。
        """
        try:
            conn = bot.get_db_connection()
            cursor = conn.cursor()
            error_count = sum(1 for r in results if not r.success)
            success_count = sum(1 for r in results if r.success)
            status = "SUCCESS" if error_count == 0 else "WARNING"
            details = f"Success: {success_count}, Errors: {error_count}"

            cursor.execute(
                "INSERT INTO mute_logs (trigger_name, executed_at, status, details) VALUES (%s, %s, %s, %s)",
                (trigger, datetime.datetime.now(), status, details),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("[MassMute] DB Error saving log: %s", e)
