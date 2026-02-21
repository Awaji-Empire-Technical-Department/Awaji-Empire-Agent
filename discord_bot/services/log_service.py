# services/log_service.py
# Why: log_operation は DB INSERT を伴う副作用処理のため services/ に配置。
#      旧 utils.py から移動。
import logging
from typing import Dict, Any

import aiomysql

logger = logging.getLogger(__name__)


class LogService:
    """操作ログをDBに記録するサービス。

    設計原則:
    - ステートレス: @staticmethod で実装
    - ctx 非依存: user 情報は辞書として受け取る
    """

    @staticmethod
    async def log_operation(
        pool: aiomysql.Pool,
        user_id: str,
        user_name: str,
        command: str,
        detail: str,
    ) -> bool:
        """操作ログをDBに記録する。

        Args:
            pool: aiomysql コネクションプール
            user_id: 操作ユーザーのID（文字列）
            user_name: 操作ユーザー名
            command: 実行されたコマンド名
            detail: 操作の詳細
        Returns:
            ログ記録が成功したかどうか
        """
        if not pool:
            return False
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO operation_logs (user_id, user_name, command, detail) VALUES (%s, %s, %s, %s)",
                        (user_id, user_name, command, detail),
                    )
            return True
        except Exception as e:
            logger.error("Failed to log operation: %s", e)
            return False
