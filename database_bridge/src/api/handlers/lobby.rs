// api/handlers/lobby.rs
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

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
// GET /lobby/rooms
// ---------------------------------------------------------
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
                    room.gamelink = Some(GameLinkFormatter::format(ip));
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
    State(pool): State<MySqlPool>,
    Json(payload): Json<CreateRoomRequest>,
) -> (StatusCode, Json<Value>) {
    let expires = payload.expires_in_hours.unwrap_or(24);
    match lobby_repo::insert_room(&pool, &payload.passcode, payload.host_id, &payload.mode, &payload.title, payload.description.as_deref(), expires).await {
        Ok(_) => {
            // 自動的にHostをメンバー(staff)として追加する
            let _ = lobby_repo::upsert_member(&pool, &payload.passcode, payload.host_id, "staff").await;
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
                room.gamelink = Some(GameLinkFormatter::format(ip));
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
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
    Json(payload): Json<UpdateRoomRequest>,
) -> (StatusCode, Json<Value>) {
    if let Some(new_host_id) = payload.new_host_id {
        if let Err(e) = lobby_repo::transfer_host(&pool, &passcode, new_host_id).await {
            return map_bridge_error(e);
        }
        // 新しいHostを自動的にstaffにする
        let _ = lobby_repo::upsert_member(&pool, &passcode, new_host_id, "staff").await;
    }

    if let Some(is_approved) = payload.is_approved {
        if let Err(e) = lobby_repo::update_room_approval(&pool, &passcode, is_approved).await {
            return map_bridge_error(e);
        }
    }

    (StatusCode::OK, Json(json!({"status": "ok"})))
}

// ---------------------------------------------------------
// GET /lobby/join/{passcode}  (Members list)
// ---------------------------------------------------------
pub async fn list_members(
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::find_members(&pool, &passcode).await {
        Ok(members) => (StatusCode::OK, Json(json!(members))),
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
    State(pool): State<MySqlPool>,
    Json(payload): Json<JoinLobbyRequest>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::upsert_member(&pool, &payload.passcode, payload.user_id, &payload.role).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}

// ---------------------------------------------------------
// DELETE /lobby/rooms/{passcode}
// ---------------------------------------------------------
pub async fn delete_room(
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match lobby_repo::delete_room(&pool, &passcode).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => map_bridge_error(e),
    }
}
