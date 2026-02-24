# services/log_service.py
# Why: log_operation は DB INSERT を伴う副作用処理のため services/ に配置。
#      Phase 3-B 以降、Rust Bridge 経由で記録する。
import logging
from typing import Any

from .bridge_client import bridge_client

logger = logging.getLogger(__name__)


class LogService:
    """操作ログをDBに記録するサービス。
    
    内部で bridge_client を通じ、Rust の database_bridge プロセスと通信する。
    """

    @staticmethod
    async def log_operation(
        pool: Any,
        user_id: str,
        user_name: str,
        command: str,
        detail: str,
    ) -> bool:
        """操作ログをDBに記録する。"""
        res = await bridge_client.request(
            "POST",
            "/logs",
            json={
                "user_id": user_id,
                "user_name": user_name,
                "command": command,
                "detail": detail
            }
        )
        return res is not None

    @staticmethod
    async def get_recent_logs(pool: Any, limit: int = 30) -> list:
        """最近の操作ログを取得する。"""
        res = await bridge_client.request("GET", "/logs", params={"limit": limit})
        return res if isinstance(res, list) else []
