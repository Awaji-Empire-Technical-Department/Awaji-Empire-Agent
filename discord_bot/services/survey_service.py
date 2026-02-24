# services/survey_service.py
# Why: DB直接操作を廃止し、Rust Bridge (IPC) 経由に切り替える。
#      Phase 3-B 以降、Python 側は DB 接続を持たない。
import logging
from typing import Any, Dict, List, Optional

from .bridge_client import bridge_client

logger = logging.getLogger(__name__)


class SurveyService:
    """アンケート操作のエントリポイント。
    
    内部で bridge_client を通じ、Rust の database_bridge プロセスと通信する。
    """

    @staticmethod
    async def create_survey(pool: Any, owner_id: str) -> Optional[int]:
        """新規アンケートを作成する。"""
        res = await bridge_client.request("POST", "/surveys", json={"owner_id": owner_id})
        return res.get("id") if res else None

    @staticmethod
    async def get_survey(pool: Any, survey_id: int) -> Optional[Dict[str, Any]]:
        """アンケートをIDで取得する。"""
        return await bridge_client.request("GET", f"/surveys/{survey_id}")

    @staticmethod
    async def get_surveys_by_owner(
        pool: Any,
        owner_id: str,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """オーナーIDでアンケート一覧を取得する。"""
        res = await bridge_client.request(
            "GET", 
            "/surveys", 
            params={"owner_id": owner_id, "active_only": active_only}
        )
        return res if isinstance(res, list) else []

    @staticmethod
    async def get_active_surveys(pool: Any) -> List[Dict[str, Any]]:
        """稼働中の全アンケートを取得する。"""
        # 現在はオーナー指定なしで active を取るエンドポイントはないが
        # 元の logic に合わせるため、必要なら Rust 側を拡張するか
        # ここでは空リストを返す（TODO: 必要に応じて Rust 側を追加）
        logger.warning("get_active_surveys is currently not implemented for all owners in bridge")
        return []

    @staticmethod
    async def update_survey(
        pool: Any,
        survey_id: int,
        title: str,
        questions_json: str,
    ) -> bool:
        """アンケートのタイトルと質問を更新する。"""
        import json
        try:
            questions = json.loads(questions_json)
        except:
            questions = []
            
        res = await bridge_client.request(
            "PATCH", 
            f"/surveys/{survey_id}", 
            json={"title": title, "questions": questions}
        )
        return res is not None

    @staticmethod
    async def toggle_status(pool: Any, survey_id: int, owner_id: str) -> bool:
        """アンケートの公開/非公開を切り替える。"""
        res = await bridge_client.request(
            "POST", 
            f"/surveys/{survey_id}/toggle", 
            json={"owner_id": owner_id}
        )
        return res is not None

    @staticmethod
    async def delete_survey(pool: Any, survey_id: int, owner_id: str) -> bool:
        """アンケートを削除する。"""
        res = await bridge_client.request(
            "DELETE", 
            f"/surveys/{survey_id}", 
            params={"owner_id": owner_id}
        )
        return res is not None

    @staticmethod
    async def get_owner_id(pool: Any, survey_id: int) -> Optional[str]:
        """アンケートのオーナーIDを取得する。"""
        res = await bridge_client.request("GET", f"/surveys/{survey_id}")
        return str(res.get("owner_id")) if res else None

    @staticmethod
    async def save_response(
        pool: Any,
        survey_id: int,
        user_id: str,
        user_name: str,
        answers: Dict[str, Any],
    ) -> Optional[int]:
        """アンケート回答を保存（既存ならUPDATE、新規ならINSERT）。"""
        res = await bridge_client.request(
            "POST", 
            "/surveys/responses/upsert", 
            json={
                "survey_id": survey_id,
                "user_id": user_id,
                "user_name": user_name,
                "answers": answers
            }
        )
        return res.get("id") if res else None

    @staticmethod
    async def mark_dm_sent(pool: Any, response_id: int) -> bool:
        """回答レコードのDM送信済みフラグを立てる。"""
        res = await bridge_client.request("PATCH", f"/surveys/responses/{response_id}/dm_sent")
        return res is not None

    @staticmethod
    async def get_responses(
        pool: Any,
        survey_id: int,
    ) -> List[Dict[str, Any]]:
        """アンケートの全回答を取得する。"""
        res = await bridge_client.request("GET", f"/surveys/{survey_id}/responses")
        return res if isinstance(res, list) else []

    @staticmethod
    async def get_existing_answers(
        pool: Any,
        survey_id: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """ユーザーの既存回答を取得する。"""
        res = await bridge_client.request("GET", f"/surveys/{survey_id}/responses/{user_id}")
        return res if isinstance(res, dict) else {}
