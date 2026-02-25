// db/log_repo.rs
// Why: operation_logs テーブルへの操作を集約する。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeResult, OperationLog};

/// SQL で DATETIME を文字列として取得するためのカラムリスト。
const SELECT_COLUMNS: &str = "id, user_id, user_name, command, detail, CAST(created_at AS CHAR) as created_at";

/// 操作ログを operation_logs テーブルに INSERT する。
pub async fn insert(
    pool: &MySqlPool,
    user_id: &str,
    user_name: &str,
    command: &str,
    detail: &str,
) -> BridgeResult<()> {
    sqlx::query(
        "INSERT INTO operation_logs (user_id, user_name, command, detail) VALUES (?, ?, ?, ?)",
    )
    .bind(user_id)
    .bind(user_name)
    .bind(command)
    .bind(detail)
    .execute(pool)
    .await?;

    Ok(())
}

/// 最新の operation_logs を件数指定で取得する。
pub async fn find_recent(pool: &MySqlPool, limit: u32) -> BridgeResult<Vec<OperationLog>> {
    let sql = format!("SELECT {} FROM operation_logs ORDER BY created_at DESC LIMIT ?", SELECT_COLUMNS);
    let logs = sqlx::query_as::<_, OperationLog>(&sql)
        .bind(limit)
        .fetch_all(pool)
        .await?;

    Ok(logs)
}
