pub mod lobby;
// api/handlers.rs
// Why: 蜷・お繝ｳ繝峨・繧､繝ｳ繝医・螳溯｣・ｒ縺薙％縺ｫ髮・ｴ・☆繧九・

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
// 蜈ｱ騾壹Ξ繧ｹ繝昴Φ繧ｹ
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
// 繝上Φ繝峨Λ螳溯｣・
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
    questions: Value, // JSON 蝙九→縺励※蜿励￠蜿悶ｋ
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

    match survey_repo::update(&pool, id, &payload.title, &questions_str).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct ToggleStatusRequest {
    owner_id: String,
}

/// POST /surveys/:id/toggle
pub async fn toggle_survey_status(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
    Json(payload): Json<ToggleStatusRequest>,
) -> (StatusCode, Json<Value>) {
    match survey_handler::toggle_status(&pool, id, &payload.owner_id).await {
        Ok(new_status) => (StatusCode::OK, Json(json!({"status": "ok", "is_active": new_status}))),
        Err(e) => map_bridge_error(e),
    }
}

/// DELETE /surveys/:id
pub async fn delete_survey(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
    Query(query): Query<ToggleStatusRequest>, // owner_id 繧偵け繧ｨ繝ｪ縺ｧ蜿励￠蜿悶ｋ
) -> (StatusCode, Json<Value>) {
    match survey_repo::delete(&pool, id, &query.owner_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}

/// GET /surveys/:id/responses
pub async fn list_responses(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match response_repo::find_by_survey(&pool, id).await {
        Ok(responses) => (StatusCode::OK, Json(json!(responses))),
        Err(e) => map_bridge_error(e),
    }
}

/// GET /surveys/:id/responses/:user_id
pub async fn get_user_answers(
    State(pool): State<MySqlPool>,
    Path((survey_id, user_id)): Path<(i64, String)>,
) -> (StatusCode, Json<Value>) {
    match response_repo::find_answers_by_user(&pool, survey_id, &user_id).await {
        Ok(answers_opt) => {
            let answers: Value = match answers_opt {
                Some(s) => serde_json::from_slice(&s.answers).unwrap_or(json!({})),
                None => json!({}),
            };
            (StatusCode::OK, Json(answers))
        },
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct UpsertResponseRequest {
    survey_id: i64,
    user_id: String,
    user_name: String,
    answers: Value,
}

/// POST /surveys/responses/upsert
pub async fn upsert_response(
    State(pool): State<MySqlPool>,
    Json(payload): Json<UpsertResponseRequest>,
) -> (StatusCode, Json<Value>) {
    match survey_handler::upsert_response(
        &pool,
        payload.survey_id,
        &payload.user_id,
        &payload.user_name,
        &payload.answers,
    ).await {
        Ok(id) => (StatusCode::OK, Json(json!({"id": id}))),
        Err(e) => map_bridge_error(e),
    }
}

/// PATCH /surveys/responses/:id/dm_sent
pub async fn mark_dm_sent(
    State(pool): State<MySqlPool>,
    Path(id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match response_repo::mark_dm_sent(&pool, id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct ListLogsQuery {
    limit: Option<u32>,
}

/// GET /logs
pub async fn list_recent_logs(
    State(pool): State<MySqlPool>,
    Query(query): Query<ListLogsQuery>,
) -> (StatusCode, Json<Value>) {
    let limit = query.limit.unwrap_or(30);
    match log_repo::find_recent(&pool, limit).await {
        Ok(logs) => (StatusCode::OK, Json(json!(logs))),
        Err(e) => map_bridge_error(e),
    }
}

#[derive(Deserialize)]
pub struct LogOperationRequest {
    user_id: String,
    user_name: String,
    command: String,
    detail: String,
}

/// POST /logs
pub async fn log_operation(
    State(pool): State<MySqlPool>,
    Json(payload): Json<LogOperationRequest>,
) -> (StatusCode, Json<Value>) {
    match log_repo::insert(&pool, &payload.user_id, &payload.user_name, &payload.command, &payload.detail).await {
        Ok(_) => (StatusCode::CREATED, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}
