// api/handlers/event.rs
// イベント参加フォーム機能の HTTP ハンドラー。

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::db::event_repo;
use super::internal_error;

// ============================================================
// イベント作成
// ============================================================

#[derive(Deserialize)]
pub struct CreateEventRequest {
    pub survey_id: i32,
    pub title: String,
    pub fee: Option<i32>,
    pub notes: Option<String>,
    /// 部制なし用の集合場所（住所・場所名）
    pub location: Option<String>,
    /// 部制なし用の開始日時
    pub event_date: Option<String>,
    /// 部制なし用の終了日時（None → event_date + 2時間でカレンダーURL生成）
    pub end_date: Option<String>,
    /// 応募締切（None → 無期限）
    pub application_deadline: Option<String>,
    pub sessions: Option<Vec<CreateSessionRequest>>,
}

#[derive(Deserialize)]
pub struct CreateSessionRequest {
    pub name: String,
    pub event_date: Option<String>,
    /// 終了日時（None → event_date + 2時間）
    pub end_date: Option<String>,
    pub location: Option<String>,
    pub capacity: Option<i32>,
}

/// POST /events
pub async fn create_event(
    State(pool): State<MySqlPool>,
    Json(payload): Json<CreateEventRequest>,
) -> (StatusCode, Json<Value>) {
    let event_id = match event_repo::insert_event(
        &pool,
        payload.survey_id,
        &payload.title,
        payload.fee,
        payload.notes.as_deref(),
        payload.location.as_deref(),
        payload.event_date.as_deref(),
        payload.end_date.as_deref(),
        payload.application_deadline.as_deref(),
    )
    .await
    {
        Ok(id) => id,
        Err(e) => return internal_error(e),
    };

    // 部の登録
    if let Some(sessions) = payload.sessions {
        for s in sessions {
            if let Err(e) = event_repo::insert_session(
                &pool,
                event_id,
                &s.name,
                s.event_date.as_deref(),
                s.end_date.as_deref(),
                s.location.as_deref(),
                s.capacity,
            )
            .await
            {
                return internal_error(e);
            }
        }
    }

    (StatusCode::CREATED, Json(json!({"status": "ok", "event_id": event_id})))
}

// ============================================================
// イベント取得
// ============================================================

/// GET /events/:id
pub async fn get_event(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    let event = match event_repo::find_event_by_id(&pool, event_id).await {
        Ok(e) => e,
        Err(e) => return internal_error(e),
    };
    let sessions = match event_repo::find_sessions_by_event(&pool, event_id).await {
        Ok(s) => s,
        Err(e) => return internal_error(e),
    };
    (StatusCode::OK, Json(json!({"event": event, "sessions": sessions})))
}

/// GET /events/by-survey/:survey_id
pub async fn get_event_by_survey(
    State(pool): State<MySqlPool>,
    Path(survey_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match event_repo::find_event_by_survey(&pool, survey_id).await {
        Ok(Some(event)) => {
            let sessions = match event_repo::find_sessions_by_event(&pool, event.id).await {
                Ok(s) => s,
                Err(e) => return internal_error(e),
            };
            (StatusCode::OK, Json(json!({"event": event, "sessions": sessions})))
        }
        Ok(None) => (StatusCode::NOT_FOUND, Json(json!({"status": "not_found"}))),
        Err(e) => internal_error(e),
    }
}

// ============================================================
// イベント更新 (PUT /events/:id)
// ============================================================

#[derive(Deserialize)]
pub struct UpdateEventRequest {
    pub title: String,
    pub fee: Option<i32>,
    pub notes: Option<String>,
    pub location: Option<String>,
    pub event_date: Option<String>,
    pub end_date: Option<String>,
    pub application_deadline: Option<String>,
    pub sessions: Option<Vec<CreateSessionRequest>>,
}

/// PUT /events/:id
pub async fn update_event(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
    Json(payload): Json<UpdateEventRequest>,
) -> (StatusCode, Json<Value>) {
    if let Err(e) = event_repo::update_event(
        &pool,
        event_id,
        &payload.title,
        payload.fee,
        payload.notes.as_deref(),
        payload.location.as_deref(),
        payload.event_date.as_deref(),
        payload.end_date.as_deref(),
        payload.application_deadline.as_deref(),
    )
    .await
    {
        return internal_error(e);
    }

    // 部を全削除して再挿入
    if let Err(e) = event_repo::delete_sessions_by_event(&pool, event_id).await {
        return internal_error(e);
    }
    if let Some(sessions) = payload.sessions {
        for s in sessions {
            if let Err(e) = event_repo::insert_session(
                &pool,
                event_id,
                &s.name,
                s.event_date.as_deref(),
                s.end_date.as_deref(),
                s.location.as_deref(),
                s.capacity,
            )
            .await
            {
                return internal_error(e);
            }
        }
    }

    (StatusCode::OK, Json(json!({"status": "ok"})))
}

// ============================================================
// イベントステータス更新
// ============================================================

#[derive(Deserialize)]
pub struct UpdateStatusRequest {
    pub status: String,
}

/// PATCH /events/:id/status
pub async fn update_event_status(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
    Json(payload): Json<UpdateStatusRequest>,
) -> (StatusCode, Json<Value>) {
    match event_repo::update_event_status(&pool, event_id, &payload.status).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => internal_error(e),
    }
}

// ============================================================
// 参加者
// ============================================================

#[derive(Deserialize)]
pub struct UpsertParticipantRequest {
    pub user_id: i64,
    pub response_id: Option<i32>,
    pub preferred_session_ids: Option<String>,
    pub access_token: String,
}

/// POST /events/:id/participants
pub async fn upsert_participant(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
    Json(payload): Json<UpsertParticipantRequest>,
) -> (StatusCode, Json<Value>) {
    match event_repo::upsert_participant(
        &pool,
        event_id,
        payload.user_id,
        payload.response_id,
        payload.preferred_session_ids.as_deref(),
        &payload.access_token,
    )
    .await
    {
        Ok(id) => (StatusCode::OK, Json(json!({"status": "ok", "id": id}))),
        Err(e) => internal_error(e),
    }
}

/// GET /events/:id/participants
pub async fn list_participants(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match event_repo::find_participants_by_event(&pool, event_id).await {
        Ok(ps) => (StatusCode::OK, Json(json!(ps))),
        Err(e) => internal_error(e),
    }
}

/// GET /events/participant/:token
pub async fn get_participant_by_token(
    State(pool): State<MySqlPool>,
    Path(token): Path<String>,
) -> (StatusCode, Json<Value>) {
    match event_repo::find_participant_by_token(&pool, &token).await {
        Ok(p) => (StatusCode::OK, Json(json!(p))),
        Err(_) => (StatusCode::NOT_FOUND, Json(json!({"status": "not_found"}))),
    }
}

#[derive(Deserialize)]
pub struct UpdateParticipantRequest {
    pub approval: String,
    pub session_id: Option<i32>,
    pub personal_note: Option<String>,
}

/// PATCH /events/participant/:participant_id
pub async fn update_participant(
    State(pool): State<MySqlPool>,
    Path(participant_id): Path<i32>,
    Json(payload): Json<UpdateParticipantRequest>,
) -> (StatusCode, Json<Value>) {
    match event_repo::update_participant_approval(
        &pool,
        participant_id,
        &payload.approval,
        payload.session_id,
        payload.personal_note.as_deref(),
    )
    .await
    {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => internal_error(e),
    }
}

/// PATCH /events/participant/:participant_id/notified
pub async fn mark_participant_notified(
    State(pool): State<MySqlPool>,
    Path(participant_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match event_repo::mark_notified(&pool, participant_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => internal_error(e),
    }
}

// ============================================================
// 自動割り当て
// ============================================================

/// POST /events/:id/auto-assign
pub async fn auto_assign(
    State(pool): State<MySqlPool>,
    Path(event_id): Path<i32>,
) -> (StatusCode, Json<Value>) {
    match event_repo::auto_assign(&pool, event_id).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok"}))),
        Err(e) => internal_error(e),
    }
}
