// api/handlers/tournament.rs
// Why: 汎用大会・称号システムのHTTPハンドラ。
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::api::AppState;
use crate::db::{tournament_repo, models::BridgeError};

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
// GET /tournament/games
// ============================================================
pub async fn list_game_titles(State(pool): State<MySqlPool>) -> (StatusCode, Json<Value>) {
    match tournament_repo::list_game_titles(&pool).await {
        Ok(titles) => (StatusCode::OK, Json(json!(titles))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /tournament/rooms/{passcode}/standings
// ============================================================
pub async fn get_standings(
    State(pool): State<MySqlPool>,
    Path(passcode): Path<String>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::get_tournament_standings(&pool, &passcode).await {
        Ok(standings) => (StatusCode::OK, Json(json!(standings))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// POST /tournament/matches/{match_id}/scores/report
// ============================================================
#[derive(Deserialize)]
pub struct ReportScoreRequest {
    user_id: i64,
    position: i8,
}

pub async fn report_score(
    State(state): State<AppState>,
    Path(match_id): Path<i32>,
    Json(payload): Json<ReportScoreRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::upsert_match_score(&state.pool, match_id, payload.user_id, payload.position).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "score.reported",
                "match_id": match_id,
                "user_id": payload.user_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// PATCH /tournament/matches/{match_id}/approve
// ============================================================
pub async fn approve_match(
    State(state): State<AppState>,
    Path(match_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::approve_match_scores(&state.pool, match_id).await {
        Ok(_) => {
            let _ = state.tx.send(json!({
                "type": "match.approved",
                "match_id": match_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// GET /tournament/matches/{match_id}/scores
// ============================================================
pub async fn list_scores(
    State(pool): State<MySqlPool>,
    Path(match_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::list_match_scores(&pool, match_id).await {
        Ok(scores) => (StatusCode::OK, Json(json!(scores))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: GET /titles
// ============================================================
pub async fn list_titles(State(pool): State<MySqlPool>) -> (StatusCode, Json<Value>) {
    match tournament_repo::list_titles(&pool).await {
        Ok(titles) => (StatusCode::OK, Json(json!(titles))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: POST /titles
// ============================================================
#[derive(Deserialize)]
pub struct UpsertTitleRequest {
    pub id: Option<i32>,
    pub name: String,
    pub description: Option<String>,
    pub unlock_type: String,
    pub unlock_threshold: Option<i32>,
    pub discord_role_id: Option<String>,
    pub display_order: Option<i32>,
}

pub async fn upsert_title(
    State(pool): State<MySqlPool>,
    Json(payload): Json<UpsertTitleRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::upsert_title(
        &pool,
        payload.id,
        &payload.name,
        payload.description.as_deref(),
        &payload.unlock_type,
        payload.unlock_threshold,
        payload.discord_role_id.as_deref(),
        payload.display_order.unwrap_or(0),
    ).await {
        Ok(id) => (StatusCode::OK, Json(json!({"status":"ok","id":id}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: DELETE /titles/{title_id}
// ============================================================
pub async fn delete_title(
    State(pool): State<MySqlPool>,
    Path(title_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::delete_title(&pool, title_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"ok"}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: PATCH /titles/{title_id}/discord_role  (ロールID書き戻し)
// ============================================================
#[derive(Deserialize)]
pub struct UpdateDiscordRoleRequest {
    pub discord_role_id: String,
}

pub async fn update_discord_role(
    State(pool): State<MySqlPool>,
    Path(title_id): Path<i32>,
    Json(payload): Json<UpdateDiscordRoleRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::update_title_discord_role(&pool, title_id, &payload.discord_role_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"ok"}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: POST /titles/player/{user_id}/grant-rank  (MMRベース自動付与)
// ============================================================
#[derive(Deserialize)]
pub struct GrantRankRequest {
    pub mmr: i32,
}

pub async fn grant_rank_title(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
    Json(payload): Json<GrantRankRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::auto_grant_lounge_rank_title(&pool, user_id, payload.mmr).await {
        Ok(newly_granted) => (StatusCode::OK, Json(json!({"status":"ok","newly_granted":newly_granted}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: POST /titles/player/{user_id}/grant-tournament  (大会優勝自動付与)
// ============================================================
pub async fn grant_tournament_title(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::auto_grant_tournament_titles(&pool, user_id).await {
        Ok(newly_granted) => (StatusCode::OK, Json(json!({"status":"ok","newly_granted":newly_granted}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: GET /titles/player/{user_id}  (図鑑)
// ============================================================
pub async fn get_player_titles(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::list_player_titles_with_status(&pool, user_id).await {
        Ok(titles) => (StatusCode::OK, Json(json!(titles))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: POST /titles/player/{user_id}/grant
// ============================================================
#[derive(Deserialize)]
pub struct GrantTitleRequest {
    pub title_id: i32,
}

pub async fn grant_title(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
    Json(payload): Json<GrantTitleRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::grant_title(&pool, user_id, payload.title_id).await {
        Ok(granted) => (StatusCode::OK, Json(json!({"status":"ok","newly_granted":granted}))),
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: POST /titles/player/{user_id}/active  (装備)
// ============================================================
#[derive(Deserialize)]
pub struct SetActiveTitleRequest {
    pub title_id: i32,
}

pub async fn set_active_title(
    State(state): State<AppState>,
    Path(user_id): Path<i64>,
    Json(payload): Json<SetActiveTitleRequest>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::set_active_title(&state.pool, user_id, payload.title_id).await {
        Ok(_) => {
            // 装備変更をWebSocketでブロードキャスト（他の画面でも称号が即時更新される）
            let _ = state.tx.send(json!({
                "type": "title.equipped",
                "user_id": user_id,
                "title_id": payload.title_id,
            }).to_string());
            (StatusCode::OK, Json(json!({"status":"ok"})))
        },
        Err(e) => map_err(e),
    }
}

// ============================================================
// 称号: GET /titles/player/{user_id}/active
// ============================================================
pub async fn get_active_title(
    State(pool): State<MySqlPool>,
    Path(user_id): Path<i64>,
) -> (StatusCode, Json<Value>) {
    match tournament_repo::get_active_title(&pool, user_id).await {
        Ok(Some(title)) => (StatusCode::OK, Json(json!(title))),
        Ok(None) => (StatusCode::OK, Json(json!(null))),
        Err(e) => map_err(e),
    }
}
