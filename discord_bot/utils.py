import aiomysql
from typing import Dict, Any

async def log_operation(pool: aiomysql.Pool, user: Dict[str, Any], command: str, detail: str):
    """操作ログをDBに記録する共通関数"""
    if not pool: return
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO operation_logs (user_id, user_name, command, detail) VALUES (%s, %s, %s, %s)",
                    (str(user['id']), user['name'], command, detail)
                )
    except Exception as e:
        print(f"Failed to log operation: {e}")
