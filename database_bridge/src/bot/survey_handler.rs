// bot/survey_handler.rs
// Why: Discord Bot 固有のロジック（UPSERT・ owner 照合付きステータス切替）を格納する。
//      これらの処理は「Bot のコンテキストでのみ意味を持つ複合操作」であり、
//      純粋な CRUD とは分けることで db/ の単一責任を維持する。

use sqlx::mysql::MySqlPool;

use crate::db::{models::BridgeResult, models::BridgeError, response_repo, survey_repo};

/// アンケート回答を UPSERT する（UNIQUE KEY: survey_id + user_id を前提）。
///
/// Python: `SurveyService.save_response()`
///
/// 改善点: Python では SELECT → if 分岐 → UPDATE/INSERT の 2 RTT だったが、
///         Rust では INSERT ... ON DUPLICATE KEY UPDATE で 1 RTT に削減。
pub async fn upsert_response(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
    user_name: &str,
    answers: &serde_json::Value,
) -> BridgeResult<i64> {
    let answers_json = serde_json::to_string(answers)?;

    // ON DUPLICATE KEY UPDATE: UNIQUE KEY (survey_id, user_id) が設定されている前提。
    // last_insert_id() は INSERT 時は新規 ID、UPDATE 時は既存 ID を返す（MariaDB 仕様）。
    let result = sqlx::query!(
        r#"
        INSERT INTO survey_responses
            (survey_id, user_id, user_name, answers, submitted_at, dm_sent)
        VALUES (?, ?, ?, ?, NOW(), FALSE)
        ON DUPLICATE KEY UPDATE
            answers     = VALUES(answers),
            submitted_at = NOW(),
            dm_sent     = FALSE
        "#,
        survey_id,
        user_id,
        user_name,
        answers_json,
    )
    .execute(pool)
    .await
    .map_err(BridgeError::Sqlx)?;

    Ok(result.last_insert_id() as i64)
}

/// アンケートの公開/非公開を切り替える（owner_id 照合付き）。
///
/// Python: `SurveyService.toggle_status()`
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

    sqlx::query!(
        "UPDATE surveys SET is_active = ? WHERE id = ?",
        new_status,
        survey_id,
    )
    .execute(pool)
    .await
    .map_err(BridgeError::Sqlx)?;

    Ok(new_status)
}
