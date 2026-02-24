// db/log_repo.rs
// Why: operation_logs テーブルへの INSERT をここに集約する。
//      Python の `LogService.log_operation()` に相当。
//
//      Note: sqlx::query!マクロの代わりに sqlx::query() ランタイム関数を使用。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeResult, OperationLog};

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
///
/// Why: webapp/dashboard_query.rs から呼ばれる集計クエリ。
pub async fn find_recent(pool: &MySqlPool, limit: u32) -> BridgeResult<Vec<OperationLog>> {
    let logs = sqlx::query_as::<_, OperationLog>(
        "SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT ?",
    )
    .bind(limit)
    .fetch_all(pool)
    .await?;

    Ok(logs)
}
