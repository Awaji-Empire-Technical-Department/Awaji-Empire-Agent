// bot/survey_handler.rs
// Why: Discord Bot 固有のロジック（UPSERT・ owner 照合付きステータス切替）を格納する。

use sqlx::mysql::MySqlPool;

use crate::db::{models::BridgeResult, models::BridgeError, survey_repo};

/// アンケート回答を UPSERT する（UNIQUE KEY: survey_id + user_id を前提）。
pub async fn upsert_response(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
    user_name: &str,
    answers: &serde_json::Value,
) -> BridgeResult<i64> {
    let answers_json = serde_json::to_string(answers)?;
    // user_id は DB 側で BIGINT なので i64 にパースする。
    let user_id_int = user_id.parse::<i64>().unwrap_or(0);

    let result = sqlx::query(
        r#"
        INSERT INTO survey_responses
            (survey_id, user_id, user_name, answers, submitted_at, dm_sent)
        VALUES (?, ?, ?, ?, NOW(), FALSE)
        ON DUPLICATE KEY UPDATE
            answers     = VALUES(answers),
            submitted_at = NOW(),
            dm_sent     = FALSE
        "#,
    )
    .bind(survey_id)
    .bind(user_id_int)
    .bind(user_name)
    .bind(answers_json)
    .execute(pool)
    .await
    .map_err(BridgeError::Sqlx)?;

    Ok(result.last_insert_id() as i64)
}

/// アンケートの公開/非公開を切り替える（owner_id 照合付き）。
pub async fn toggle_status(
    pool: &MySqlPool,
    survey_id: i64,
    owner_id: &str,
) -> BridgeResult<bool> {
    let survey = survey_repo::find_by_id(pool, survey_id).await?;

    if survey.owner_id != owner_id {
        return Err(BridgeError::PermissionDenied);
    }

    let new_status = !survey.is_active;

    sqlx::query("UPDATE surveys SET is_active = ? WHERE id = ?")
        .bind(new_status)
        .bind(survey_id)
        .execute(pool)
        .await
        .map_err(BridgeError::Sqlx)?;

    Ok(new_status)
}
