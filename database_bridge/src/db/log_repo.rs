// db/log_repo.rs
// Why: operation_logs テーブルへの INSERT をここに集約する。
//      Python の `LogService.log_operation()` に相当。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeResult};

/// 操作ログを operation_logs テーブルに INSERT する。
///
/// Python: `LogService.log_operation()`
pub async fn insert(
    pool: &MySqlPool,
    user_id: &str,
    user_name: &str,
    command: &str,
    detail: &str,
) -> BridgeResult<()> {
    sqlx::query!(
        "INSERT INTO operation_logs (user_id, user_name, command, detail) VALUES (?, ?, ?, ?)",
        user_id,
        user_name,
        command,
        detail,
    )
    .execute(pool)
    .await?;

    Ok(())
}

/// 最新の operation_logs を件数指定で取得する。
///
/// Why: webapp/dashboard_query.rs から呼ばれる集計クエリ。
pub async fn find_recent(pool: &MySqlPool, limit: u32) -> BridgeResult<Vec<super::models::OperationLog>> {
    let logs = sqlx::query_as!(
        super::models::OperationLog,
        "SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT ?",
        limit,
    )
    .fetch_all(pool)
    .await?;

    Ok(logs)
}
