# tests/test_bridge_client.py
# services/bridge_client.py のユニットテスト
# - BridgeUnavailableError が正しい条件でraiseされること
# - API エラー (4xx/5xx) では BridgeUnavailableError を raise せず None を返すこと
import sys
import os
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx
from services.bridge_client import BridgeClient, BridgeUnavailableError


class TestBridgeClientUnavailable(IsolatedAsyncioTestCase):
    """Bridge への接続失敗時に BridgeUnavailableError がraiseされること"""

    async def test_connect_error_raises_bridge_unavailable(self):
        """httpx.ConnectError が発生した場合 BridgeUnavailableError をraiseする"""
        client = BridgeClient()

        async def raise_connect_error(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient.request", new=raise_connect_error):
            with self.assertRaises(BridgeUnavailableError):
                await client.request("GET", "/health")

    async def test_timeout_raises_bridge_unavailable(self):
        """httpx.TimeoutException が発生した場合 BridgeUnavailableError をraiseする"""
        client = BridgeClient()

        async def raise_timeout(*args, **kwargs):
            raise httpx.TimeoutException("Request timed out")

        with patch("httpx.AsyncClient.request", new=raise_timeout):
            with self.assertRaises(BridgeUnavailableError):
                await client.request("GET", "/surveys")

    async def test_read_error_raises_bridge_unavailable(self):
        """httpx.ReadError (RequestError の一種) でも BridgeUnavailableError をraiseする"""
        client = BridgeClient()

        async def raise_read_error(*args, **kwargs):
            raise httpx.ReadError("Connection reset by peer")

        with patch("httpx.AsyncClient.request", new=raise_read_error):
            with self.assertRaises(BridgeUnavailableError):
                await client.request("POST", "/surveys")


class TestBridgeClientAPIError(IsolatedAsyncioTestCase):
    """Bridge が稼働中だが API エラー (4xx/5xx) を返した場合は None を返す"""

    def _make_mock_response(self, status_code: int, json_data: dict = None):
        """モックレスポンスを作成するヘルパー"""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        if json_data is not None:
            mock_resp.json.return_value = json_data
        else:
            mock_resp.json.side_effect = Exception("No JSON")
        return mock_resp

    async def test_404_returns_none_not_unavailable(self):
        """404 レスポンスは BridgeUnavailableError を raise せず None を返す"""
        client = BridgeClient()
        mock_resp = self._make_mock_response(404, {"message": "Not found"})

        async def mock_request(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.request", new=mock_request):
            result = await client.request("GET", "/surveys/9999")
        self.assertIsNone(result)

    async def test_500_returns_none_not_unavailable(self):
        """500 レスポンスは BridgeUnavailableError を raise せず None を返す"""
        client = BridgeClient()
        mock_resp = self._make_mock_response(500, {"message": "Internal error"})

        async def mock_request(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.request", new=mock_request):
            result = await client.request("GET", "/surveys")
        self.assertIsNone(result)

    async def test_200_returns_json(self):
        """正常な 200 レスポンスは JSON を返す"""
        client = BridgeClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        async def mock_request(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.request", new=mock_request):
            result = await client.request("GET", "/health")
        self.assertEqual(result, {"status": "ok"})

    async def test_204_returns_true(self):
        """204 No Content レスポンスは True を返す"""
        client = BridgeClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        async def mock_request(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.request", new=mock_request):
            result = await client.request("DELETE", "/surveys/1")
        self.assertTrue(result)


if __name__ == '__main__':
    import unittest
    unittest.main()
