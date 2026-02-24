# services/bridge_client.py
# Why: Rust で実装された database_bridge (IPC) への HTTP クライアント。
#      各サービス (SurveyService, LogService) はこのクライアントを介して DB 操作を行う。

import logging
import httpx
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Rust ブリッジのデフォルトアドレス
BRIDGE_BASE_URL = "http://127.0.0.1:7878"


class BridgeUnavailableError(Exception):
    """
    Rust Bridge (database_bridge) への接続が失敗したことを示す例外。
    Why: httpx.RequestError (ConnectError / TimeoutException 等) と、
         通常の API エラー (4xx / 5xx) を呼び出し元で区別するため専用例外を定義した。
         route 層はこの例外を捕捉して maintenance.html を返す。
    """
    pass


class BridgeClient:
    """database_bridge API へのラッパークライアント。"""

    def __init__(self, base_url: str = BRIDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Union[Dict[str, Any], Any]]:
        """
        API リクエストを送信する。

        Raises:
            BridgeUnavailableError: Bridge プロセスへの接続自体が失敗した場合
                                    (ConnectError / Timeout 等)。
                                    呼び出し元はこれを捕捉してメンテナンスページを返すこと。
        Returns:
            dict | True | None:
                - dict: 正常レスポンス (JSON)
                - True: 204 No Content (成功)
                - None: 4xx / 5xx などの API エラー（Bridge 自体は稼働中）
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params
                )

                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        logger.error(
                            "Bridge API Error (%s %s): %s - %s",
                            method, url, response.status_code, error_data.get("message", "Unknown error")
                        )
                    except Exception:
                        logger.error("Bridge API Error (%s %s): %s", method, url, response.status_code)
                    return None

                # 204 No Content 等の場合は True を返す（成功の意）
                if response.status_code == 204:
                    return True

                return response.json()

        except httpx.RequestError as e:
            # Bridge プロセス自体が停止していると判断できるエラー
            logger.error("Bridge Connection Error (%s %s): %s", method, url, e)
            raise BridgeUnavailableError(
                f"Rust Bridge への接続に失敗しました: {e}"
            ) from e
        except Exception as e:
            logger.exception("Unexpected error in BridgeClient: %s", e)
            return None


# シングルトンインスタンス
bridge_client = BridgeClient()
