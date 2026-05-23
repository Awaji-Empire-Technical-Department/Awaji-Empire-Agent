// api/mod.rs
// Why: API エンドポイントのルーティングを集約する。

pub mod handlers;

use axum::{
    routing::{get, post, patch, delete},
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
        .nest("/tournament", tournament_routes())
        .nest("/lounge", lounge_routes())
        .nest("/titles", title_routes())
        .route("/ws/hyouibana", get(handlers::ws::ws_handler))
        .route("/logs", get(handlers::list_recent_logs).post(handlers::log_operation))
        .nest("/reset_logs", reset_log_routes())
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

/// リセットログ関連のルーティング。
fn reset_log_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(handlers::reset_log::list_reset_logs).post(handlers::reset_log::insert_reset_log))
        .route("/check_month", get(handlers::reset_log::check_month))
}

/// 汎用大会関連のルーティング。
fn tournament_routes() -> Router<AppState> {
    Router::new()
        .route("/games", get(handlers::tournament::list_game_titles))
        .route("/rooms/{passcode}/standings", get(handlers::tournament::get_standings))
        .route("/matches/{match_id}/scores/report", post(handlers::tournament::report_score))
        .route("/matches/{match_id}/scores", get(handlers::tournament::list_scores))
        .route("/matches/{match_id}/approve", patch(handlers::tournament::approve_match))
}

/// 称号関連のルーティング。
fn title_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(handlers::tournament::list_titles).post(handlers::tournament::upsert_title))
        .route("/{title_id}", delete(handlers::tournament::delete_title))
        .route("/{title_id}/discord_role", patch(handlers::tournament::update_discord_role))
        .route("/player/{user_id}", get(handlers::tournament::get_player_titles))
        .route("/player/{user_id}/grant", post(handlers::tournament::grant_title))
        .route("/player/{user_id}/grant-rank", post(handlers::tournament::grant_rank_title))
        .route("/player/{user_id}/grant-tournament", post(handlers::tournament::grant_tournament_title))
        .route("/player/{user_id}/active", get(handlers::tournament::get_active_title).post(handlers::tournament::set_active_title).delete(handlers::tournament::clear_active_title))
}

/// ラウンジ関連のルーティング。
fn lounge_routes() -> Router<AppState> {
    Router::new()
        .route("/sessions", get(handlers::lounge::list_sessions).post(handlers::lounge::create_session))
        .route("/sessions/{id}", get(handlers::lounge::get_session))
        .route("/sessions/{id}/finish", post(handlers::lounge::finish_session))
        .route("/sessions/{id}/members", post(handlers::lounge::add_member).get(handlers::lounge::list_members))
        .route("/sessions/{id}/exclude", post(handlers::lounge::exclude_player))
        .route("/sessions/{id}/final-scores", get(handlers::lounge::get_final_scores))
        .route("/sessions/{id}/final-scores/report", post(handlers::lounge::report_final_score))
        .route("/sessions/{id}/standings", get(handlers::lounge::get_standings))
        .route("/sessions/{id}/teams", post(handlers::lounge::create_team).get(handlers::lounge::list_teams))
        .route("/players/{user_id}", get(handlers::lounge::get_player))
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
