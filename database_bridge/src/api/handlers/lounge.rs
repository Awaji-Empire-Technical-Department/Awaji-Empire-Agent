// api/handlers/lounge.rs
// Phase 3: セッション最終順位申告方式。
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
// GET /lounge/sessions
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
// POST /lounge/sessions/{id}/exclude
// ============================================================
#[derive(Deserialize)]
pub struct ExcludePlayerRequest {
    pub user_id: i64,
}

pub async fn exclude_player(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
    Json(payload): Json<ExcludePlayerRequest>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::toggle_exclude_player(&state.pool, session_id, payload.user_id).await {
        Ok(excluded) => {
            let _ = state.tx.send(json!({
                "type":       "lounge.member_excluded",
                "session_id": session_id,
                "user_id":    payload.user_id.to_string(),
                "excluded":   excluded,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok","excluded":excluded})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /lounge/sessions/{id}/final-scores/report
// ============================================================
#[derive(Deserialize)]
pub struct ReportFinalScoreRequest {
    pub user_id: i64,
    pub final_rank: i8,
}

pub async fn report_final_score(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
    Json(payload): Json<ReportFinalScoreRequest>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::report_final_score(&state.pool, session_id, payload.user_id, payload.final_rank).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type":       "lounge.final_score_reported",
                "session_id": session_id,
                "user_id":    payload.user_id.to_string(),
                "final_rank": payload.final_rank,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /lounge/sessions/{id}/final-scores
// ============================================================
pub async fn get_final_scores(
    State(pool): State<MySqlPool>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_final_scores(&pool, session_id).await {
        Ok(scores) => (StatusCode::OK, Json(json!(scores))),
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
// POST /lounge/sessions/{id}/finish
// ============================================================
pub async fn finish_session(
    State(state): State<AppState>,
    Path(session_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    // MMR 計算・更新（申告済み・非除外プレイヤーのみ）
    let results = match lounge_repo::calc_and_apply_mmr(&state.pool, session_id).await {
        Ok(r) => r,
        Err(e) => return map_err(e),
    };

    // セッションを finished に更新し total_sessions をインクリメント
    if let Err(e) = lounge_repo::finish_session(&state.pool, session_id).await {
        return map_err(e);
    }

    // 称号付与・Discordロール同期はPython側で行う
    let _ = state.tx.send(json!({
        "type":       "lounge.session_finished",
        "session_id": session_id,
        "results":    results,
    }).to_string());

    (StatusCode::OK, Json(json!({"status":"ok","results":results})))
}

// ============================================================
// GET /lounge/players/{user_id}
// ============================================================
pub async fn get_player(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match lounge_repo::get_lounge_player(&pool, user_id).await {
        Ok(p) => (StatusCode::OK, Json(json!({
            "user_id":       p.user_id,
            "mmr":           p.mmr,
            "peak_mmr":      p.peak_mmr,
            "total_races":   p.total_races,
            "total_sessions": p.total_sessions,
        }))),
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
