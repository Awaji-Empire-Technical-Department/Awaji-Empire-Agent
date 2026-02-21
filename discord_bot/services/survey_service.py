# services/survey_service.py
# Why: DB操作（CRUD）は副作用を伴うため services/ に配置。
#      旧 routes/survey.py から DB 操作ロジックを抽出。
import json
import logging
from typing import Any, Dict, List, Optional

import aiomysql

logger = logging.getLogger(__name__)


class SurveyService:
    """アンケートDB操作の汎用サービス。

    設計原則:
    - ステートレス: @staticmethod で実装
    - ctx 非依存: pool と プリミティブ型を引数に取る
    """

    @staticmethod
    async def create_survey(pool: aiomysql.Pool, owner_id: str) -> Optional[int]:
        """新規アンケートを作成する。

        Returns:
            作成されたアンケートのID。失敗時は None。
        """
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO surveys (owner_id, title, questions, is_active, created_at) "
                        "VALUES (%s, '無題のアンケート', '[]', FALSE, NOW())",
                        (owner_id,),
                    )
                    return cur.lastrowid
        except Exception as e:
            logger.error("Failed to create survey: %s", e)
            return None

    @staticmethod
    async def get_survey(pool: aiomysql.Pool, survey_id: int) -> Optional[Dict[str, Any]]:
        """アンケートをIDで取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
                    return await cur.fetchone()
        except Exception as e:
            logger.error("Failed to get survey %s: %s", survey_id, e)
            return None

    @staticmethod
    async def get_surveys_by_owner(
        pool: aiomysql.Pool,
        owner_id: str,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """オーナーIDでアンケート一覧を取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if active_only:
                        await cur.execute(
                            "SELECT * FROM surveys WHERE owner_id = %s AND is_active = 1 ORDER BY created_at DESC",
                            (owner_id,),
                        )
                    else:
                        await cur.execute(
                            "SELECT * FROM surveys WHERE owner_id = %s ORDER BY created_at DESC",
                            (owner_id,),
                        )
                    return await cur.fetchall()
        except Exception as e:
            logger.error("Failed to get surveys for owner %s: %s", owner_id, e)
            return []

    @staticmethod
    async def get_active_surveys(pool: aiomysql.Pool) -> List[Dict[str, Any]]:
        """稼働中の全アンケートを取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT * FROM surveys WHERE is_active = 1 ORDER BY created_at DESC"
                    )
                    return await cur.fetchall()
        except Exception as e:
            logger.error("Failed to get active surveys: %s", e)
            return []

    @staticmethod
    async def update_survey(
        pool: aiomysql.Pool,
        survey_id: int,
        title: str,
        questions_json: str,
    ) -> bool:
        """アンケートのタイトルと質問を更新する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE surveys SET title=%s, questions=%s WHERE id=%s",
                        (title, questions_json, survey_id),
                    )
            return True
        except Exception as e:
            logger.error("Failed to update survey %s: %s", survey_id, e)
            return False

    @staticmethod
    async def toggle_status(pool: aiomysql.Pool, survey_id: int, owner_id: str) -> bool:
        """アンケートの公開/非公開を切り替える。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT owner_id, is_active FROM surveys WHERE id=%s",
                        (survey_id,),
                    )
                    row = await cur.fetchone()
                    if not row or str(row["owner_id"]) != str(owner_id):
                        return False
                    new_status = not row["is_active"]
                    await cur.execute(
                        "UPDATE surveys SET is_active=%s WHERE id=%s",
                        (new_status, survey_id),
                    )
            return True
        except Exception as e:
            logger.error("Failed to toggle survey %s: %s", survey_id, e)
            return False

    @staticmethod
    async def delete_survey(pool: aiomysql.Pool, survey_id: int, owner_id: str) -> bool:
        """アンケートを削除する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT owner_id FROM surveys WHERE id=%s", (survey_id,)
                    )
                    row = await cur.fetchone()
                    if not row or str(row["owner_id"]) != str(owner_id):
                        return False
                    await cur.execute("DELETE FROM surveys WHERE id=%s", (survey_id,))
            return True
        except Exception as e:
            logger.error("Failed to delete survey %s: %s", survey_id, e)
            return False

    @staticmethod
    async def get_owner_id(pool: aiomysql.Pool, survey_id: int) -> Optional[str]:
        """アンケートのオーナーIDを取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT owner_id FROM surveys WHERE id=%s", (survey_id,)
                    )
                    row = await cur.fetchone()
                    return str(row[0]) if row else None
        except Exception as e:
            logger.error("Failed to get owner for survey %s: %s", survey_id, e)
            return None

    @staticmethod
    async def save_response(
        pool: aiomysql.Pool,
        survey_id: int,
        user_id: str,
        user_name: str,
        answers: Dict[str, Any],
    ) -> Optional[int]:
        """アンケート回答を保存（既存ならUPDATE、新規ならINSERT）。

        Returns:
            レスポンスのID。失敗時は None。
        """
        try:
            answers_json = json.dumps(answers, ensure_ascii=False)
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # 既存回答チェック
                    await cur.execute(
                        "SELECT id FROM survey_responses WHERE survey_id=%s AND user_id=%s",
                        (survey_id, user_id),
                    )
                    existing_row = await cur.fetchone()

                    if existing_row:
                        response_id = existing_row["id"]
                        await cur.execute(
                            "UPDATE survey_responses SET answers=%s, submitted_at=NOW(), dm_sent=FALSE WHERE id=%s",
                            (answers_json, response_id),
                        )
                    else:
                        await cur.execute(
                            "INSERT INTO survey_responses (survey_id, user_id, user_name, answers, submitted_at, dm_sent) "
                            "VALUES (%s, %s, %s, %s, NOW(), FALSE)",
                            (survey_id, user_id, user_name, answers_json),
                        )
                        response_id = cur.lastrowid

                    return response_id
        except Exception as e:
            logger.error("Failed to save response for survey %s: %s", survey_id, e)
            return None

    @staticmethod
    async def mark_dm_sent(pool: aiomysql.Pool, response_id: int) -> bool:
        """回答レコードのDM送信済みフラグを立てる。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE survey_responses SET dm_sent=TRUE WHERE id=%s",
                        (response_id,),
                    )
            return True
        except Exception as e:
            logger.error("Failed to mark DM sent for response %s: %s", response_id, e)
            return False

    @staticmethod
    async def get_responses(
        pool: aiomysql.Pool,
        survey_id: int,
    ) -> List[Dict[str, Any]]:
        """アンケートの全回答を取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT * FROM survey_responses WHERE survey_id=%s ORDER BY submitted_at DESC",
                        (survey_id,),
                    )
                    return await cur.fetchall()
        except Exception as e:
            logger.error("Failed to get responses for survey %s: %s", survey_id, e)
            return []

    @staticmethod
    async def get_existing_answers(
        pool: aiomysql.Pool,
        survey_id: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """ユーザーの既存回答を取得する。"""
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT answers FROM survey_responses WHERE survey_id=%s AND user_id=%s",
                        (survey_id, user_id),
                    )
                    row = await cur.fetchone()
                    if row:
                        return json.loads(row["answers"])
                    return {}
        except Exception as e:
            logger.error(
                "Failed to get existing answers for survey %s, user %s: %s",
                survey_id, user_id, e,
            )
            return {}
