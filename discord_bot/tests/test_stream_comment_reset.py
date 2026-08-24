# tests/test_stream_comment_reset.py
# StreamCommentReset のユニットテスト
# - should_fallback_run: 毎月21日06:00 JST のみ True
# - check_already_reset_this_month: DB照会結果の伝播
# - Cog.cog_load: DB照会結果によるインメモリ冪等性状態の復元
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cogs.stream_comment_reset.logic import StreamCommentResetLogic
from cogs.stream_comment_reset.cog import StreamCommentResetCog

JST = timezone(timedelta(hours=9))


class TestShouldFallbackRun(IsolatedAsyncioTestCase):
    """StreamCommentResetLogic.should_fallback_run のテスト"""

    def test_true_on_day21_hour6(self):
        now = datetime(2026, 8, 21, 6, 30, tzinfo=JST)
        self.assertTrue(StreamCommentResetLogic.should_fallback_run(now))

    def test_false_on_other_day(self):
        now = datetime(2026, 8, 20, 6, 30, tzinfo=JST)
        self.assertFalse(StreamCommentResetLogic.should_fallback_run(now))

    def test_false_on_other_hour(self):
        now = datetime(2026, 8, 21, 7, 0, tzinfo=JST)
        self.assertFalse(StreamCommentResetLogic.should_fallback_run(now))


class TestCheckAlreadyResetThisMonth(IsolatedAsyncioTestCase):
    """StreamCommentResetLogic.check_already_reset_this_month のテスト"""

    async def test_delegates_to_service_with_year_month(self):
        now = datetime(2026, 8, 21, 6, 0, tzinfo=JST)
        with patch(
            "cogs.stream_comment_reset.logic.StreamCommentResetService.check_month_reset",
            new=AsyncMock(return_value=True),
        ) as mock_check:
            result = await StreamCommentResetLogic.check_already_reset_this_month(now)

        self.assertTrue(result)
        mock_check.assert_awaited_once_with(2026, 8)

    async def test_returns_false_when_not_reset(self):
        now = datetime(2026, 8, 21, 6, 0, tzinfo=JST)
        with patch(
            "cogs.stream_comment_reset.logic.StreamCommentResetService.check_month_reset",
            new=AsyncMock(return_value=False),
        ):
            result = await StreamCommentResetLogic.check_already_reset_this_month(now)

        self.assertFalse(result)


class TestCogLoad(IsolatedAsyncioTestCase):
    """StreamCommentResetCog.cog_load のテスト（Bot再起動直後の冪等性復元）"""

    def _make_cog(self):
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        cog = StreamCommentResetCog(bot=bot)
        self.addCleanup(cog.fallback_reset.cancel)
        return cog

    async def test_restores_last_reset_month_when_already_reset(self):
        cog = self._make_cog()
        with patch(
            "cogs.stream_comment_reset.cog.StreamCommentResetLogic.check_already_reset_this_month",
            new=AsyncMock(return_value=True),
        ):
            await cog.cog_load()

        self.assertEqual(cog._last_reset_month, datetime.now(JST).month)

    async def test_leaves_last_reset_month_none_when_not_reset(self):
        cog = self._make_cog()
        with patch(
            "cogs.stream_comment_reset.cog.StreamCommentResetLogic.check_already_reset_this_month",
            new=AsyncMock(return_value=False),
        ):
            await cog.cog_load()

        self.assertIsNone(cog._last_reset_month)


if __name__ == '__main__':
    import unittest
    unittest.main()
