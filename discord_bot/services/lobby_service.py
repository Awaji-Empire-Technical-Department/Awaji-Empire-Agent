# services/lobby_service.py
from typing import List, Dict, Any, Optional
from services.bridge_client import bridge_client

class LobbyService:
    @staticmethod
    async def get_active_rooms() -> List[Dict[str, Any]]:
        """有効な対戦ロビー一覧を取得する"""
        res = await bridge_client.request("GET", "/lobby/rooms")
        return res if res else []

    @staticmethod
    async def get_room(passcode: str) -> Optional[Dict[str, Any]]:
        """特定のロビー情報を取得する"""
        res = await bridge_client.request("GET", f"/lobby/rooms/{passcode}")
        return res

    @staticmethod
    async def sync_user(discord_id: int, email: str, virtual_ip: Optional[str] = None) -> bool:
        """ユーザー情報(WARP IP含む)をデータベースと同期する"""
        payload = {
            "discord_id": discord_id,
            "email": email,
            "virtual_ip": virtual_ip
        }
        res = await bridge_client.request("POST", "/lobby/sync_user", json=payload)
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def create_room(passcode: str, host_id: int, mode: str, title: str, description: Optional[str] = None, expires_in_hours: int = 24) -> bool:
        """新規ロビーを作成する"""
        payload = {
            "passcode": passcode,
            "host_id": host_id,
            "mode": mode,
            "title": title,
            "description": description,
            "expires_in_hours": expires_in_hours
        }
        res = await bridge_client.request("POST", "/lobby/rooms", json=payload)
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def update_room(passcode: str, new_host_id: Optional[int] = None, is_approved: Optional[bool] = None) -> bool:
        """ロビー情報（Host権限委譲、最終承認状態）を更新する"""
        payload = {}
        if new_host_id is not None:
            payload["new_host_id"] = new_host_id
        if is_approved is not None:
            payload["is_approved"] = is_approved

        if not payload:
            return True

        res = await bridge_client.request("PATCH", f"/lobby/rooms/{passcode}", json=payload)
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def delete_room(passcode: str) -> bool:
        """ロビーを削除する"""
        res = await bridge_client.request("DELETE", f"/lobby/rooms/{passcode}")
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def get_members(passcode: str) -> List[Dict[str, Any]]:
        """ロビーの参加者一覧を取得する"""
        res = await bridge_client.request("GET", f"/lobby/join/{passcode}")
        return res if res else []

    @staticmethod
    async def join_lobby(passcode: str, user_id: int, role: str) -> bool:
        """ロビーに参加する（役割を設定）"""
        payload = {
            "passcode": passcode,
            "user_id": user_id,
            "role": role
        }
        res = await bridge_client.request("POST", "/lobby/join", json=payload)
        return res is not None and res.get("status") == "ok"
