// api/handlers/lobby.rs
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::api::AppState;
use crate::db::{lobby_repo, models::BridgeError};
use crate::lobby::game_link::GameLinkFormatter;

// Error mapping (copied from handlers.rs for brevity, though ideally extracted to a shared module)
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
        BridgeError::Sqlx(e) => {
            tracing::error!("Database error: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        },
        BridgeError::Json(e) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"status": "error", "message": format!("invalid json: {}", e)})),
        ),
    }
}

// ---------------------------------------------------------
// POST /lobby/sync_user
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct SyncUserRequest {
    discord_id: i64,
    email: String,
    username: Option<String>,
    virtual_ip: Option<String>,
}

pub async fn sync_user(
    State(state): State<AppState>,
    Json(payload): Json<SyncUserRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::sync_user_network(&state.pool, payload.discord_id, &payload.email, payload.username.as_deref(), payload.virtual_ip.as_deref()).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "user_synced", "user_id": payload.discord_id}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// GET /lobby/rooms
// ---------------------------------------------------------
pub async fn list_rooms(State(pool): State<MySqlPool>) -> (StatusCode, Json<Value>) {
    /* 
    let query = r#"
        SELECT m.passcode, m.host_id, m.mode, m.title, m.description, 
               CAST(m.tournament_start_at AS CHAR) as tournament_start_at, 
               m.is_approved, CAST(m.expires_at AS CHAR) as expires_at,
               u.virtual_ip
        FROM matchmaking_rooms m
        LEFT JOIN user_networks u ON m.host_id = u.discord_id
        WHERE m.expires_at > NOW()
    "#;
    */

    match lobby_repo::find_active_rooms(&pool).await {
        Ok(mut rooms) => {
            for room in &mut rooms {
                if let Some(ref ip) = room.virtual_ip {
                    room.gamelink = GameLinkFormatter::format(ip);
                }
            }
            (StatusCode::OK, Json(json!(rooms)))
        }
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// POST /lobby/rooms
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct CreateRoomRequest {
    passcode: String,
    host_id: i64,
    mode: String,
    title: String,
    description: Option<String>,
    expires_in_hours: Option<u32>,
}

pub async fn create_room(
    State(state): State<AppState>,
    Json(payload): Json<CreateRoomRequest>,
) -> (StatusCode, Json<Value>) {
    let expires = payload.expires_in_hours.unwrap_or(24);
    match lobby_repo::insert_room(&state.pool, &payload.passcode, payload.host_id, &payload.mode, &payload.title, payload.description.as_deref(), expires).await {
        Ok(_) => {
            // 自動的にHostをメンバー(staff)として追加する
            let _ = lobby_repo::upsert_member(&state.pool, &payload.passcode, payload.host_id, "staff").await;
            let _ = state.tx.send(json!({"type": "room_created", "passcode": payload.passcode}).to_string());
            (StatusCode::CREATED, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// GET /lobby/rooms/{passcode}
// ---------------------------------------------------------
pub async fn get_room(
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::find_room_by_passcode(&pool, &passcode).await {
        Ok(mut room) => {
            if let Some(ref ip) = room.virtual_ip {
                room.gamelink = GameLinkFormatter::format(ip);
            }
            (StatusCode::OK, Json(json!(room)))
        }
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// PATCH /lobby/rooms/{passcode}
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct UpdateRoomRequest {
    new_host_id: Option<i64>,
    is_approved: Option<bool>,
}

pub async fn update_room(
    State(state): State<AppState>,
    Path(passcode): Path<String>,
    Json(payload): Json<UpdateRoomRequest>,
) -> (StatusCode, Json<Value>) {
    if let Some(new_host_id) = payload.new_host_id {
        if let Err(e) = lobby_repo::transfer_host(&state.pool, &passcode, new_host_id).await {
            return map_bridge_error(e);
        }
        // 新しいHostを自動的にstaffにする
        let _ = lobby_repo::upsert_member(&state.pool, &passcode, new_host_id, "staff").await;
    }

    if let Some(is_approved) = payload.is_approved {
        if let Err(e) = lobby_repo::update_room_approval(&state.pool, &passcode, is_approved).await {
            return map_bridge_error(e);
        }
    }

    let _ = state.tx.send(json!({"type": "room_updated", "passcode": passcode}).to_string());
    (StatusCode::OK, Json(json!({"status": "ok"})))
}

// ---------------------------------------------------------
// POST /lobby/rooms/{passcode}/start
// ---------------------------------------------------------
pub async fn start_tournament(
    State(state): State<AppState>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::start_tournament(&state.pool, &passcode).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "tournament_started", "passcode": passcode}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// GET /lobby/join/{passcode}  (Members list)
// ---------------------------------------------------------
pub async fn list_members(
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::find_members(&pool, &passcode).await {
        Ok(mut members) => {
            for member in &mut members {
                if let Some(ref ip) = member.virtual_ip {
                    member.gamelink = GameLinkFormatter::format(ip);
                }
            }
            (StatusCode::OK, Json(json!(members)))
        }
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// POST /lobby/join
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct JoinLobbyRequest {
    passcode: String,
    user_id: i64,
    role: String, // 'player' or 'staff'
}

pub async fn join_lobby(
    State(state): State<AppState>,
    Json(payload): Json<JoinLobbyRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::upsert_member(&state.pool, &payload.passcode, payload.user_id, &payload.role).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "member_joined", "passcode": payload.passcode, "user_id": payload.user_id}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// DELETE /lobby/rooms/{passcode}
// ---------------------------------------------------------
pub async fn delete_room(
    State(state): State<AppState>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::delete_room(&state.pool, &passcode).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "room_deleted", "passcode": passcode}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// PATCH /lobby/rooms/{passcode}/members/{user_id}/status
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct UpdateMemberStatusRequest {
    status: String,
}

pub async fn update_member_status(
    State(state): State<AppState>,
    Path((passcode, user_id)): Path<(String, i64)>,
    Json(payload): Json<UpdateMemberStatusRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::update_member_status(&state.pool, &passcode, user_id, &payload.status).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "member_status_updated", "passcode": passcode, "user_id": user_id, "status": payload.status}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// GET /lobby/rooms/{passcode}/matches
// ---------------------------------------------------------
pub async fn list_matches(
    State(state): State<AppState>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::get_tournament_matches(&state.pool, &passcode).await {
        Ok(matches) => (StatusCode::OK, Json(json!(matches))),
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// POST /lobby/rooms/{passcode}/matches
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct CreateMatchRequest {
    player1_id: Option<i64>,
    player2_id: Option<i64>,
    round_num: i32,
    match_index: i32,
    win_condition: i32,
}

pub async fn create_match(
    State(state): State<AppState>,
    Path(passcode): Path<String>,
    Json(payload): Json<CreateMatchRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::insert_tournament_match(&state.pool, &passcode, payload.player1_id, payload.player2_id, payload.round_num, payload.match_index, payload.win_condition).await {
        Ok(match_id) => {
            let _ = state.tx.send(json!({"type": "match_created", "passcode": passcode, "match_id": match_id}).to_string());
            (StatusCode::CREATED, Json(json!({"status": "ok", "match_id": match_id})))
        },
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// POST /lobby/matches/{match_id}/winner
// ---------------------------------------------------------
#[derive(Deserialize)]
pub struct ReportWinnerRequest {
    winner_id: i64,
    score1: i32,
    score2: i32,
}

pub async fn report_winner(
    State(state): State<AppState>,
    Path(match_id): Path<i32>,
    Json(payload): Json<ReportWinnerRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::report_match_winner(&state.pool, match_id, payload.winner_id, payload.score1, payload.score2).await {
        Ok(_) => {
            let _ = state.tx.send(json!({"type": "match_winner_reported", "match_id": match_id, "winner_id": payload.winner_id}).to_string());
            (StatusCode::OK, Json(json!({"status": "ok"})))
        },
        Err(e) => map_bridge_error(e),
    }
}
