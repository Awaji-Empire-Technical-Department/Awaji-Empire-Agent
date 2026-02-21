# tests/test_permission_service.py
# PermissionService のユニットテスト
# - needs_repair の権限判定ロジック
# - check_and_repair の呼び出しフロー
# - 異常系（Forbidden エラー）
import sys
import os
import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import discord
from services.permission_service import PermissionResult, PermissionService


class TestNeedsRepair(TestCase):
    """PermissionService.needs_repair のテスト"""

    def _make_channel_with_overwrite(self, overwrite: discord.PermissionOverwrite):
        """指定した PermissionOverwrite を返すモックチャンネルを作成する"""
        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "test-channel"
        channel.overwrites_for = MagicMock(return_value=overwrite)
        return channel

    def test_no_repair_needed_when_identical(self):
        """権限が完全一致する場合、修復不要"""
        expected = discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
            mention_everyone=False, manage_webhooks=False,
        )
        current = discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
            mention_everyone=False, manage_webhooks=False,
        )
        channel = self._make_channel_with_overwrite(current)
        role = MagicMock(spec=discord.Role)

        result = PermissionService.needs_repair(channel, role, expected)
        self.assertFalse(result)

    def test_repair_needed_when_different(self):
        """send_messages が期待値と異なる場合、修復が必要"""
        expected = discord.PermissionOverwrite(
            read_messages=True, send_messages=False,
            mention_everyone=False, manage_webhooks=False,
        )
        current = discord.PermissionOverwrite(
            read_messages=True, send_messages=True,  # 期待は False
            mention_everyone=False, manage_webhooks=False,
        )
        channel = self._make_channel_with_overwrite(current)
        role = MagicMock(spec=discord.Role)

        result = PermissionService.needs_repair(channel, role, expected)
        self.assertTrue(result)

    def test_repair_needed_when_mention_everyone_changed(self):
        """mention_everyone が True に変更された場合、修復が必要"""
        expected = discord.PermissionOverwrite(
            mention_everyone=False,
        )
        current = discord.PermissionOverwrite(
            mention_everyone=True,  # 期待は False
        )
        channel = self._make_channel_with_overwrite(current)
        role = MagicMock(spec=discord.Role)

        result = PermissionService.needs_repair(channel, role, expected)
        self.assertTrue(result)

    def test_no_repair_when_none_fields_ignored(self):
        """expected で None のフィールドは比較対象外"""
        expected = discord.PermissionOverwrite(
            read_messages=True,
            # send_messages は None（未指定）→ 比較対象外
        )
        current = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=False,  # None なので無視される
        )
        channel = self._make_channel_with_overwrite(current)
        role = MagicMock(spec=discord.Role)

        result = PermissionService.needs_repair(channel, role, expected)
        self.assertFalse(result)


class TestApplyPermission(TestCase):
    """PermissionService.apply_permission のテスト"""

    def test_successful_apply(self):
        """正常に権限を適用できる場合"""
        channel = AsyncMock(spec=discord.TextChannel)
        channel.name = "test-channel"
        role = MagicMock(spec=discord.Role)
        overwrite = discord.PermissionOverwrite(read_messages=True)

        result = asyncio.run(
            PermissionService.apply_permission(channel, role, overwrite)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "applied")
        self.assertEqual(result.channel_name, "test-channel")
        channel.set_permissions.assert_awaited_once_with(role, overwrite=overwrite)

    def test_forbidden_error(self):
        """権限不足でForbiddenが発生する場合"""
        channel = AsyncMock(spec=discord.TextChannel)
        channel.name = "restricted-channel"
        channel.set_permissions.side_effect = discord.Forbidden(
            MagicMock(status=403), "Missing Permissions"
        )
        role = MagicMock(spec=discord.Role)
        overwrite = discord.PermissionOverwrite(read_messages=True)

        result = asyncio.run(
            PermissionService.apply_permission(channel, role, overwrite)
        )

        self.assertFalse(result.success)
        self.assertIn("Missing permissions", result.error)


class TestCheckAndRepair(TestCase):
    """PermissionService.check_and_repair のテスト"""

    def test_skip_when_no_repair_needed(self):
        """修復不要な場合はスキップ"""
        overwrite = discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
        )
        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "ok-channel"
        channel.overwrites_for = MagicMock(return_value=overwrite)
        # set_permissions を AsyncMock にしておく（呼ばれないはずだが念のため）
        channel.set_permissions = AsyncMock()
        role = MagicMock(spec=discord.Role)

        result = asyncio.run(
            PermissionService.check_and_repair(channel, role, overwrite)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "skipped")
        channel.set_permissions.assert_not_awaited()

    def test_repair_when_needed(self):
        """修復が必要な場合は set_permissions を呼ぶ"""
        expected = discord.PermissionOverwrite(
            read_messages=True, send_messages=False,
        )
        current = discord.PermissionOverwrite(
            read_messages=True, send_messages=True,  # 異なる
        )
        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "broken-channel"
        channel.overwrites_for = MagicMock(return_value=current)
        channel.set_permissions = AsyncMock()
        role = MagicMock(spec=discord.Role)

        result = asyncio.run(
            PermissionService.check_and_repair(channel, role, expected)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "repaired")
        channel.set_permissions.assert_awaited_once_with(role, overwrite=expected)


class TestPermissionResult(TestCase):
    """PermissionResult dataclass のテスト"""

    def test_success_result(self):
        r = PermissionResult(channel_name="ch", success=True, action="applied")
        self.assertTrue(r.success)
        self.assertIsNone(r.error)

    def test_error_result(self):
        r = PermissionResult(channel_name="ch", success=False, action="applied", error="fail")
        self.assertFalse(r.success)
        self.assertEqual(r.error, "fail")

    def test_frozen(self):
        """frozen=True なので属性変更は不可"""
        r = PermissionResult(channel_name="ch", success=True, action="applied")
        with self.assertRaises(AttributeError):
            r.success = False


if __name__ == '__main__':
    import unittest
    unittest.main()
