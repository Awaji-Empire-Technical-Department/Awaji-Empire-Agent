pub mod lobby;

// api/handlers.rs (now as mod.rs inside handlers/)
// Why: 各エンドポイントの実装をここに集約する。

use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;
use tracing::error;

use crate::db::{models::BridgeError, survey_repo, response_repo, log_repo};
use crate::bot::survey_handler;

// ============================================================
// 共通レスポンス
// ============================================================

fn internal_error<E: std::fmt::Display>(err: E) -> (StatusCode, Json<Value>) {
    error!("Internal server error: {}", err);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"status": "error", "message": err.to_string()})),
    )
}

fn map_bridge_error(err: BridgeError) -> (StatusCode, Json<Value>) {
    match err {
        BridgeError::NotFound(msg) => (
            StatusCode::NOT_FOUND,
            Json(json!({"status": "error", "message": msg})),
        ),
        BridgeError::PermissionDenied => (
            StatusCode::FORBIDDEN,
            Json(json!({"status": "error", "message": "permission denied"})),
        ),
        BridgeError::Sqlx(e) => internal_error(e),
        BridgeError::Json(e) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"status": "error", "message": format!("invalid json: {}", e)})),
        ),
    }
}

// ============================================================
// ハンドラ実装
// ============================================================

/// GET /health
pub async fn health_check(State(pool): State<MySqlPool>) -> (StatusCode, Json<Value>) {
    if crate::db::connection::health_check(&pool).await {
        (StatusCode::OK, Json(json!({"status": "ok"})))
    } else {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status": "error", "message": "database connection check failed"})),
        )
    }
}

#[derive(Deserialize)]
pub struct ListSurveysQuery {
    owner_id: String,
    active_only: Option<bool>,
}

/// GET /surveys
pub async fn list_surveys(
    State(pool): State<MySqlPool>,
    Query(query): Query<ListSurveysQuery>,
) -> (StatusCode, Json<Value>) {
    match survey_repo::find_by_owner(&pool, &query.owner_id, query.active_only).await {
        Ok(surveys) => (StatusCode::OK, Json(json!(surveys))),
        Err(e) => map_bridge_error(e),
    }
}

/// GET /surveys/:id
pub async fn get_survey(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match survey_repo::find_by_id(&pool, id).await {
        Ok(survey) => (StatusCode::OK, Json(json!(survey))),
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct CreateSurveyRequest {
    owner_id: String,
}

/// POST /surveys
pub async fn create_survey(
    State(pool): State<MySqlPool>,
    Json(payload): Json<CreateSurveyRequest>,
) -> (StatusCode, Json<Value>) {
    match survey_repo::insert(&pool, &payload.owner_id).await {
        Ok(id) => (StatusCode::CREATED, Json(json!({"id": id}))),
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct UpdateSurveyRequest {
    title: String,
    questions: Value, // JSON 型として受け取る
}

/// PATCH /surveys/:id
pub async fn update_survey(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
    Json(payload): Json<UpdateSurveyRequest>,
) -> (StatusCode, Json<Value>) {
    let questions_str = match serde_json::to_string(&payload.questions) {
        Ok(s) => s,
        Err(e) => return (StatusCode::BAD_REQUEST, Json(json!({"status": "error", "message": e.to_string()}))),
    };

    match survey_repo::update(&pool,
