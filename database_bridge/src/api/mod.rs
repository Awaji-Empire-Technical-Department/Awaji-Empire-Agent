// api/mod.rs
// Why: API エンドポイントのルーティングを集約する。

pub mod handlers;

use axum::{
    routing::{get, post, patch, delete},
    Router,
};
use sqlx::MySqlPool;

/// アプリケーション全体のルーターを構築する。
pub fn create_router(pool: MySqlPool) -> Router {
    Router::new()
        .route("/health", get(handlers::health_check))
        .nest("/surveys", survey_routes())
        .route("/logs", get(handlers::list_recent_logs).post(handlers::log_operation))
        .with_state(pool)
}

/// アンケート関連のルーティング。
fn survey_routes() -> Router<MySqlPool> {
    Router::new()
        .route("/", get(handlers::list_surveys).post(handlers::create_survey))
        .route("/:id", get(handlers::get_survey).patch(handlers::update_survey).delete(handlers::delete_survey))
        .route("/:id/toggle", post(handlers::toggle_survey_status))
        .route("/:id/responses", get(handlers::list_responses))
        .route("/:id/responses/:user_id", get(handlers::get_user_answers))
        .route("/responses/upsert", post(handlers::upsert_response))
        .route("/responses/:id/dm_sent", patch(handlers::mark_dm_sent))
}
