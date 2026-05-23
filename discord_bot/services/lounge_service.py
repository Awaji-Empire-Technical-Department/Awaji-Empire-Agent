# services/lounge_service.py
from typing import Any, Dict, List, Optional
from services.bridge_client import bridge_client


class LoungeService:
    @staticmethod
    async def list_active_sessions() -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", "/lounge/sessions")
        return res if res else []

    @staticmethod
    async def create_session(room_id: str, host_id: int, mode: str = "ffa", total_races: int = 12) -> Optional[int]:
        res = await bridge_client.request("POST", "/lounge/sessions", json={
            "room_id": room_id, "host_id": host_id, "mode": mode, "total_races": total_races,
        })
        return res.get("session_id") if res else None

    @staticmethod
    async def get_session(session_id: int) -> Optional[Dict[str, Any]]:
        return await bridge_client.request("GET", f"/lounge/sessions/{session_id}")

    @staticmethod
    async def add_member(session_id: int, user_id: int) -> bool:
        res = await bridge_client.request("POST", f"/lounge/sessions/{session_id}/members", json={"user_id": user_id})
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def list_members(session_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/lounge/sessions/{session_id}/members")
        return res if res else []

    @staticmethod
    async def report_final_score(session_id: int, user_id: int, final_rank: int) -> bool:
        res = await bridge_client.request(
            "POST", f"/lounge/sessions/{session_id}/final-scores/report",
            json={"user_id": user_id, "final_rank": final_rank},
        )
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def get_final_scores(session_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/lounge/sessions/{session_id}/final-scores")
        return res if res else []

    @staticmethod
    async def exclude_player(session_id: int, user_id: int) -> Optional[bool]:
        res = await bridge_client.request(
            "POST", f"/lounge/sessions/{session_id}/exclude",
            json={"user_id": user_id},
        )
        if res and res.get("status") == "ok":
            return res.get("excluded")
        return None

    @staticmethod
    async def finish_session(session_id: int) -> Optional[Dict[str, Any]]:
        """セッション終了。{"status":"ok","results":[...]} を返す。失敗時は None。"""
        return await bridge_client.request("POST", f"/lounge/sessions/{session_id}/finish")

    @staticmethod
    async def get_standings(session_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/lounge/sessions/{session_id}/standings")
        return res if res else []

    @staticmethod
    async def get_player(user_id: int) -> Optional[Dict[str, Any]]:
        return await bridge_client.request("GET", f"/lounge/players/{user_id}")

    @staticmethod
    async def create_team(session_id: int, tag: str, member_ids: List[int]) -> Optional[int]:
        res = await bridge_client.request(
            "POST", f"/lounge/sessions/{session_id}/teams",
            json={"tag": tag, "member_ids": member_ids},
        )
        return res.get("team_id") if res else None

    @staticmethod
    async def list_teams(session_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/lounge/sessions/{session_id}/teams")
        return res if res else []
