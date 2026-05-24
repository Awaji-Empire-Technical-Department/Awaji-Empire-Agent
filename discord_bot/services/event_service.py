# services/event_service.py
# イベント参加フォーム機能のエントリポイント。bridge_client 経由で Rust と通信する。

import secrets
from typing import Any, Dict, List, Optional

from .bridge_client import bridge_client


class EventService:

    # ============================================================
    # イベント
    # ============================================================

    @staticmethod
    async def create_event(
        survey_id: int,
        title: str,
        fee: Optional[int] = None,
        notes: Optional[str] = None,
        location: Optional[str] = None,
        event_date: Optional[str] = None,
        end_date: Optional[str] = None,
        application_deadline: Optional[str] = None,
        sessions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[int]:
        """イベントを作成し、event_id を返す。"""
        res = await bridge_client.request(
            "POST",
            "/events",
            json={
                "survey_id": survey_id,
                "title": title,
                "fee": fee,
                "notes": notes,
                "location": location,
                "event_date": event_date,
                "end_date": end_date,
                "application_deadline": application_deadline,
                "sessions": sessions or [],
            },
        )
        return res.get("event_id") if res else None

    @staticmethod
    async def get_event(event_id: int) -> Optional[Dict[str, Any]]:
        """event_id でイベント（部含む）を取得する。"""
        return await bridge_client.request("GET", f"/events/{event_id}")

    @staticmethod
    async def get_event_by_survey(survey_id: int) -> Optional[Dict[str, Any]]:
        """survey_id に紐づくイベントを取得する。存在しなければ None。"""
        res = await bridge_client.request("GET", f"/events/by-survey/{survey_id}")
        if res and res.get("status") == "not_found":
            return None
        return res

    @staticmethod
    async def update_event(
        event_id: int,
        title: str,
        fee: Optional[int] = None,
        notes: Optional[str] = None,
        location: Optional[str] = None,
        event_date: Optional[str] = None,
        end_date: Optional[str] = None,
        application_deadline: Optional[str] = None,
        sessions: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """イベント情報（部含む）を上書き更新する。"""
        res = await bridge_client.request(
            "PUT",
            f"/events/{event_id}",
            json={
                "title": title,
                "fee": fee,
                "notes": notes,
                "location": location,
                "event_date": event_date,
                "end_date": end_date,
                "application_deadline": application_deadline,
                "sessions": sessions or [],
            },
        )
        return res is not None and res.get("status") == "ok"

    @staticmethod
    async def update_status(event_id: int, status: str) -> bool:
        """イベントステータスを更新する。status: draft|open|closed"""
        res = await bridge_client.request(
            "PATCH", f"/events/{event_id}/status", json={"status": status}
        )
        return res is not None

    # ============================================================
    # 参加者
    # ============================================================

    @staticmethod
    async def register_participant(
        event_id: int,
        user_id: int,
        response_id: Optional[int],
        preferred_session_ids: Optional[List[int]],
    ) -> Optional[str]:
        """参加者を登録し、個人確認ページ用 access_token を返す。"""
        import json as _json
        token = secrets.token_urlsafe(32)
        preferred_json = _json.dumps(preferred_session_ids) if preferred_session_ids else None
        res = await bridge_client.request(
            "POST",
            f"/events/{event_id}/participants",
            json={
                "user_id": user_id,
                "response_id": response_id,
                "preferred_session_ids": preferred_json,
                "access_token": token,
            },
        )
        return token if res and res.get("status") == "ok" else None

    @staticmethod
    async def get_my_participation(event_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザー自身の参加レコードを取得する。未登録なら None。"""
        res = await bridge_client.request("GET", f"/events/{event_id}/participants/by-user/{user_id}")
        if res and res.get("status") == "not_found":
            return None
        return res

    @staticmethod
    async def list_participants(event_id: int) -> List[Dict[str, Any]]:
        """イベントの参加者一覧を取得する。"""
        res = await bridge_client.request("GET", f"/events/{event_id}/participants")
        return res if isinstance(res, list) else []

    @staticmethod
    async def get_participant_by_token(token: str) -> Optional[Dict[str, Any]]:
        """access_token で参加者情報を取得する。"""
        res = await bridge_client.request("GET", f"/events/participant/by-token/{token}")
        if res and res.get("status") == "not_found":
            return None
        return res

    @staticmethod
    async def update_participant(
        participant_id: int,
        approval: str,
        session_id: Optional[int] = None,
        personal_note: Optional[str] = None,
    ) -> bool:
        """参加者の承認状況・割り当て部・個人メモを更新する。"""
        res = await bridge_client.request(
            "PATCH",
            f"/events/participant/{participant_id}",
            json={
                "approval": approval,
                "session_id": session_id,
                "personal_note": personal_note,
            },
        )
        return res is not None

    @staticmethod
    async def mark_notified(participant_id: int) -> bool:
        """DM送信済みフラグを立てる。"""
        res = await bridge_client.request(
            "PATCH", f"/events/participant/{participant_id}/notified"
        )
        return res is not None

    # ============================================================
    # 自動割り当て
    # ============================================================

    @staticmethod
    async def auto_assign(event_id: int) -> bool:
        """希望部優先の自動割り当てを実行する。"""
        res = await bridge_client.request("POST", f"/events/{event_id}/auto-assign")
        return res is not None and res.get("status") == "ok"
