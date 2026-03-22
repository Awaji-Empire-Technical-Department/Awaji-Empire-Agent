// db/reset_log_repo.rs
// Why: stream_comment_reset_log テーブルへの CRUD を集約する。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeResult, ResetLog};

/// SQL で DATETIME を文字列として取得するためのカラムリスト。
const SELECT_COLUMNS: &str =
    "id, CAST(executed_at AS CHAR) as executed_at, triggered_by, event_type, status, error_message";

/// リセットログを INSERT する。
pub async fn insert(
    pool: &MySqlPool,
    triggered_by: &str,
    event_type: &str,
    status: &str,
    error_message: Option<&str>,
) -> BridgeResult<()> {
    sqlx::query(
        "INSERT INTO stream_comment_reset_log (triggered_by, event_type, status, error_message) VALUES (?, ?, ?, ?)",
    )
    .bind(triggered_by)
    .bind(event_type)
    .bind(status)
    .bind(error_message)
    .execute(pool)
    .await?;

    Ok(())
}

/// 最新のリセットログを件数指定で取得する。
pub async fn find_recent(pool: &MySqlPool, limit: u32) -> BridgeResult<Vec<ResetLog>> {
    let sql = format!(
        "SELECT {} FROM stream_comment_reset_log ORDER BY executed_at DESC LIMIT ?",
        SELECT_COLUMNS
    );
    let logs = sqlx::query_as::<_, ResetLog>(&sql)
        .bind(limit)
        .fetch_all(pool)
        .await?;

    Ok(logs)
}

/// 指定年月の最新ログを 1 件取得する（当月リセット済み判定用）。
pub async fn find_latest_by_month(
    pool: &MySqlPool,
    year: i32,
    month: u32,
) -> BridgeResult<Option<ResetLog>> {
    let sql = format!(
        "SELECT {} FROM stream_comment_reset_log \
         WHERE event_type IN ('monthly_reset', 'manual_reset') \
           AND status = 'success' \
           AND YEAR(executed_at) = ? AND MONTH(executed_at) = ? \
         ORDER BY executed_at DESC LIMIT 1",
        SELECT_COLUMNS
    );
    let log = sqlx::query_as::<_, ResetLog>(&sql)
        .bind(year)
        .bind(month)
        .fetch_optional(pool)
        .await?;

    Ok(log)
}
