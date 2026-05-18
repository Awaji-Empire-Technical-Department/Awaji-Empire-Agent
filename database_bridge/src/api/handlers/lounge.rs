// api/handlers/lounge.rs
// Why: ラウンジシステムのHTTPハンドラ。
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::api::AppState;
use crate::db::{lounge_repo, models::BridgeError};

fn map_err(err: BridgeError) -> (StatusCode, Json<Value>) {
    match err {
        BridgeError::NotFound(msg) => (StatusCode::NOT_FOUND, Json(json!({"status":"error","message":msg}))),
        BridgeError::PermissionDenied => (StatusCode::FORBIDDEN, Json(json!({"status":"error","message":"permission denied"}))),
        BridgeError::Sqlx(e) => {
            tracing::error!("DB error: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"status":"error","message":e.to_string()})))
        },
        BridgeError::Json(e) => (StatusCode::BAD_REQUEST, Json(json!({"status":"error","message":format!("invalid json: {}", e)}))),
    }
}

// ============================================================
// POST /lounge/sessions
// ============================================================
#[derive(Deserialize)]
pub struct CreateSessionRequest {
    pub room_id: String,
    pub mode: Option<String>,
    pub total_races: Option<i8>,
    pub host_id: i64,
}

pub async fn create_session(
    State(pool): State<MySqlPool>,
    Json(payload): Json<CreateSessionRequest>,
) -> (StatusCode, Json<Value>) {
    let mode = payload.mode.as_deref().unwrap_or("ffa");
    let total_races = payload.total_races.unwrap_or(12);
    match lounge_repo::create_session(&pool, &payload.room_id, mode, total_races, payload.host_id).await {
        Ok(id) => (StatusCode::OK, Json(json!({"status":"ok","session_id":id}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions  (アクティブセッション一覧)
// ============================================================
pub async fn list_sessions(State(pool): State<MySqlPool>) -> (StatusCode, Json<Value>) {
    match lounge_repo::list_active_sessions(&pool).await {
        Ok(sessions) => (StatusCode::OK, Json(json!(sessions))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}
// ============================================================
pub async fn get_session(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_session(&pool, session_id).await {
        Ok(session) => (StatusCode::OK, Json(json!(session))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// PATCH /lounge/sessions/{id}/next-race
// ============================================================
pub async fn next_race(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::advance_session_race(&state.pool, session_id).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "lounge.race_advanced",
                "session_id": session_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/sessions/{id}/members
// ============================================================
#[derive(Deserialize)]
pub struct AddMemberRequest {
    pub user_id: i64,
}

pub async fn add_member(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
    Json(payload): Json<AddMemberRequest>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::add_session_member(&pool, session_id, payload.user_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"ok"}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}/members
// ============================================================
pub async fn list_members(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::list_session_members(&pool, session_id).await {
        Ok(members) => (StatusCode::OK, Json(json!(members))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/sessions/{id}/races
// ============================================================
#[derive(Deserialize)]
pub struct CreateRaceRequest {
    pub course_name: String,
}

/// コース正規化：レインボーロード系を統一キーに変換
fn normalize_course_key(name: &str) -> String {
    let lower = name.to_lowercase();
    if lower.contains("rainbow road") || lower.contains("レインボーロード") {
        return "rainbow_road".to_string();
    }
    lower.replace(' ', "_").replace('　', "_")
}

pub async fn create_race(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
    Json(payload): Json<CreateRaceRequest>,
) -> (StatusCode, Json<Value>) {
    let course_key = normalize_course_key(&payload.course_name);

    // コース重複チェック
    let is_new = match lounge_repo::check_and_register_course(&state.pool, session_id, &course_key).await {
        Ok(v) => v,
        Err(e) => return map_err(e),
    };

    let session = match lounge_repo::get_session(&state.pool, session_id).await {
        Ok(s) => s,
        Err(e) => return map_err(e),
    };
    let next_race_num = session.current_race + 1;

    match lounge_repo::create_race(&state.pool, session_id, next_race_num, &payload.course_name).await {
        Ok(race_id) => {
            let _ = state.tx.send(json!({
                "type": "lounge.race_created",
                "session_id": session_id,
                "race_id": race_id,
                "race_number": next_race_num,
                "course_name": payload.course_name,
                "duplicate_course": !is_new,
            }).to_string());
            (StatusCode::OK, Json(json!({
                "status": "ok",
                "race_id": race_id,
                "duplicate_course": !is_new,
            })))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/races/{race_id}/scores/report
// ============================================================
#[derive(Deserialize)]
pub struct ReportScoreRequest {
    pub user_id: i64,
    pub position: i8,
}

pub async fn report_score(
    State(state): State<AppState>,
    Path(race_id): Path<i64>,
    Json(payload): Json<ReportScoreRequest>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::report_score(&state.pool, race_id, payload.user_id, payload.position).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "lounge.score_reported",
                "race_id": race_id,
                "user_id": payload.user_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/races/{race_id}/disconnect
// ============================================================
#[derive(Deserialize)]
pub struct DisconnectRequest {
    pub user_id: i64,
}

pub async fn report_disconnect(
    State(state): State<AppState>,
    Path(race_id): Path<i64>,
    Json(payload): Json<DisconnectRequest>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::report_disconnect(&state.pool, race_id, payload.user_id).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "lounge.disconnect_reported",
                "race_id": race_id,
                "user_id": payload.user_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// PATCH /lounge/races/{race_id}/approve
// ============================================================
pub async fn approve_race(
    State(state): State<AppState>,
    Path(race_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::approve_race_scores(&state.pool, race_id).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "lounge.race_approved",
                "race_id": race_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}/standings
// ============================================================
pub async fn get_standings(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_session_standings(&pool, session_id).await {
        Ok(standings) => (StatusCode::OK, Json(json!(standings))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}/team-standings
// ============================================================
pub async fn get_team_standings(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_team_standings(&pool, session_id).await {
        Ok(standings) => (StatusCode::OK, Json(json!(standings))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}/course-history
// ============================================================
pub async fn get_course_history(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_course_history(&pool, session_id).await {
        Ok(history) => (StatusCode::OK, Json(json!(history))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/sessions/{id}/teams
// ============================================================
#[derive(Deserialize)]
pub struct CreateTeamRequest {
    pub tag: String,
    pub member_ids: Vec<i64>,
}

pub async fn create_team(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
    Json(payload): Json<CreateTeamRequest>,
) -> (StatusCode, Json<Value>) {
    let team_id = match lounge_repo::create_team(&pool, session_id, &payload.tag).await {
        Ok(id) => id,
        Err(e) => return map_err(e),
    };
    for uid in &payload.member_ids {
        if let Err(e) = lounge_repo::add_team_member(&pool, team_id, *uid).await {
            return map_err(e);
        }
    }
    (StatusCode::OK, Json(json!({"status":"ok","team_id":team_id})))
}

// ============================================================
// GET /lounge/sessions/{id}/teams
// ============================================================
pub async fn list_teams(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::list_teams(&pool, session_id).await {
        Ok(teams) => (StatusCode::OK, Json(json!(teams))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/races/{race_id}/scores
// ============================================================
pub async fn list_race_scores(
    State(pool): State<MySqlPool>,
    Path(race_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::list_race_scores(&pool, race_id).await {
        Ok(scores) => (StatusCode::OK, Json(json!(scores))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/sessions/{id}/finish
// ============================================================
pub async fn finish_session(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    if let Err(e) = lounge_repo::finish_session(&state.pool, session_id).await {
        return map_err(e);
    }
    // 称号付与・Discordロール同期はPython側で行う（Discord API呼び出しを一箇所に集約するため）
    let _ = state.tx.send(json!({
        "type": "lounge.session_finished",
        "session_id": session_id,
    }).to_string());
    (StatusCode::OK, Json(json!({"status":"ok"})))
}
