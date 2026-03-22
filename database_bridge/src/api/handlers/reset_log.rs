// api/handlers/reset_log.rs
// Why: stream_comment_reset_log のエンドポイント実装。

use axum::extract::{Query, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::db::reset_log_repo;

use super::internal_error;

// ============================================================
// リクエスト型
// ============================================================

#[derive(Deserialize)]
pub struct InsertResetLogRequest {
    pub triggered_by: String,
    pub event_type: String,
    pub status: String,
    pub error_message: Option<String>,
}

#[derive(Deserialize)]
pub struct ListResetLogsQuery {
    pub limit: Option<u32>,
}

#[derive(Deserialize)]
pub struct CheckMonthQuery {
    pub year: i32,
    pub month: u32,
}

// ============================================================
// ハンドラ
// ============================================================

/// POST /reset_logs
pub async fn insert_reset_log(
    State(pool): State<MySqlPool>,
    Json(payload): Json<InsertResetLogRequest>,
) -> (StatusCode, Json<Value>) {
    match reset_log_repo::insert(
        &pool,
        &payload.triggered_by,
        &payload.event_type,
        &payload.status,
        payload.error_message.as_deref(),
    )
    .await
    {
        Ok(_) => (StatusCode::CREATED, Json(json!({"status": "ok"}))),
        Err(e) => internal_error(e),
    }
}

/// GET /reset_logs
pub async fn list_reset_logs(
    State(pool): State<MySqlPool>,
    Query(query): Query<ListResetLogsQuery>,
) -> (StatusCode, Json<Value>) {
    let limit = query.limit.unwrap_or(30);
    match reset_log_repo::find_recent(&pool, limit).await {
        Ok(logs) => (StatusCode::OK, Json(json!(logs))),
        Err(e) => internal_error(e),
    }
}

/// GET /reset_logs/check_month
pub async fn check_month(
    State(pool): State<MySqlPool>,
    Query(query): Query<CheckMonthQuery>,
) -> (StatusCode, Json<Value>) {
    match reset_log_repo::find_latest_by_month(&pool, query.year, query.month).await {
        Ok(Some(log)) => (
            StatusCode::OK,
            Json(json!({"reset_done": true, "latest_log": log})),
        ),
        Ok(None) => (
            StatusCode::OK,
            Json(json!({"reset_done": false, "latest_log": null})),
        ),
        Err(e) => internal_error(e),
    }
}
