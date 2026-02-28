// api/mod.rs
// Why: API エンドポイントのルーティングを集約する。

pub mod handlers;

use axum::{
    routing::{get, post, patch},
    Router,
};
use sqlx::MySqlPool;
use tokio::sync::broadcast;

#[derive(Clone)]
pub struct AppState {
    pub pool: MySqlPool,
    pub tx: broadcast::Sender<String>,
}

impl axum::extract::FromRef<AppState> for MySqlPool {
    fn from_ref(state: &AppState) -> MySqlPool {
        state.pool.clone()
    }
}

/// アプリケーション全体のルーターを構築する。
pub fn create_router(pool: MySqlPool) -> Router {
    let (tx, _rx) = broadcast::channel(100);
    let state = AppState { pool, tx };

    Router::new()
        .route("/health", get(handlers::health_check))
        .nest("/surveys", survey_routes())
        .nest("/lobby", lobby_routes())
        .route("/ws/hyouibana", get(handlers::ws::ws_handler))
        .route("/logs", get(handlers::list_recent_logs).post(handlers::log_operation))
        .with_state(state)
}

/// ロビー関連のルーティング。
fn lobby_routes() -> Router<AppState> {
    Router::new()
        .route("/sync_user", post(crate::api::handlers::lobby::sync_user))
        .route("/rooms", get(crate::api::handlers::lobby::list_rooms).post(crate::api::handlers::lobby::create_room))
        .route("/rooms/{passcode}", get(crate::api::handlers::lobby::get_room).patch(crate::api::handlers::lobby::update_room).delete(crate::api::handlers::lobby::delete_room))
        .route("/rooms/{passcode}/start", post(crate::api::handlers::lobby::start_tournament))
        .route("/rooms/{passcode}/members/{user_id}/status", patch(crate::api::handlers::lobby::update_member_status))
        .route("/rooms/{passcode}/matches", get(crate::api::handlers::lobby::list_matches).post(crate::api::handlers::lobby::create_match))
        .route("/matches/{match_id}/winner", post(crate::api::handlers::lobby::report_winner))
        .route("/join", post(crate::api::handlers::lobby::join_lobby))
        .route("/join/{passcode}", get(crate::api::handlers::lobby::list_members))
}

/// アンケート関連のルーティング。
fn survey_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(handlers::list_surveys).post(handlers::create_survey))
        .route("/{id}", get(handlers::get_survey).patch(handlers::update_survey).delete(handlers::delete_survey))
        .route("/{id}/toggle", post(handlers::toggle_survey_status))
        .route("/{id}/responses", get(handlers::list_responses))
        .route("/{id}/responses/{user_id}", get(handlers::get_user_answers))
        .route("/responses/upsert", post(handlers::upsert_response))
        .route("/responses/{id}/dm_sent", patch(handlers::mark_dm_sent))
}
