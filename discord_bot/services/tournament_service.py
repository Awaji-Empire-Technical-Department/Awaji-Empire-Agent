# services/tournament_service.py
from typing import Any, Dict, List, Optional
from services.bridge_client import bridge_client


class TournamentService:
    @staticmethod
    async def list_game_titles() -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", "/tournament/games")
        return res if res else []

    @staticmethod
    async def report_score(match_id: int, user_id: int, position: int) -> bool:
        res = await bridge_client.request(
            "POST", f"/tournament/matches/{match_id}/scores/report",
            json={"user_id": user_id, "position": position}
        )
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def approve_match(match_id: int) -> bool:
        res = await bridge_client.request("PATCH", f"/tournament/matches/{match_id}/approve")
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def list_match_scores(match_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/tournament/matches/{match_id}/scores")
        return res if res else []

    @staticmethod
    async def get_standings(passcode: str) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/tournament/rooms/{passcode}/standings")
        return res if res else []


class TitleService:
    @staticmethod
    async def list_all() -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", "/titles")
        return res if res else []

    @staticmethod
    async def upsert(
        name: str,
        description: Optional[str],
        unlock_type: str,
        unlock_threshold: Optional[int],
        discord_role_id: Optional[str],
        display_order: int = 0,
        title_id: Optional[int] = None,
    ) -> Optional[int]:
        payload = {
            "name": name,
            "description": description,
            "unlock_type": unlock_type,
            "unlock_threshold": unlock_threshold,
            "discord_role_id": discord_role_id,
            "display_order": display_order,
        }
        if title_id is not None:
            payload["id"] = title_id
        res = await bridge_client.request("POST", "/titles", json=payload)
        return res.get("id") if res else None

    @staticmethod
    async def delete(title_id: int) -> bool:
        res = await bridge_client.request("DELETE", f"/titles/{title_id}")
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def get_player_titles(user_id: int) -> List[Dict[str, Any]]:
        res = await bridge_client.request("GET", f"/titles/player/{user_id}")
        return res if res else []

    @staticmethod
    async def grant(user_id: int, title_id: int) -> bool:
        res = await bridge_client.request(
            "POST", f"/titles/player/{user_id}/grant",
            json={"title_id": title_id}
        )
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def set_active(user_id: int, title_id: int) -> bool:
        res = await bridge_client.request(
            "POST", f"/titles/player/{user_id}/active",
            json={"title_id": title_id}
        )
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def get_active(user_id: int) -> Optional[Dict[str, Any]]:
        return await bridge_client.request("GET", f"/titles/player/{user_id}/active")
