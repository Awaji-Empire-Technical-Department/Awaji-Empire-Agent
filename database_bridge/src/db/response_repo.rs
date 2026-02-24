// db/response_repo.rs
// Why: survey_responses テーブルへの純粋な CRUD をここに集約する。
//      UPSERT ロジック（Bot 固有）は bot/survey_handler.rs に分離している。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeError, BridgeResult, SurveyResponse};

/// アンケートの全回答を取得する。
///
/// Python: `SurveyService.get_responses()`
pub async fn find_by_survey(pool: &MySqlPool, survey_id: i64) -> BridgeResult<Vec<SurveyResponse>> {
    let responses = sqlx::query_as!(
        SurveyResponse,
        "SELECT * FROM survey_responses WHERE survey_id = ? ORDER BY submitted_at DESC",
        survey_id,
    )
    .fetch_all(pool)
    .await?;

    Ok(responses)
}

/// ユーザーの既存回答 JSON 文字列を取得する。
///
/// Python: `SurveyService.get_existing_answers()`
/// 回答がなければ `None` を返す。
pub async fn find_answers_by_user(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
) -> BridgeResult<Option<String>> {
    let row = sqlx::query!(
        "SELECT answers FROM survey_responses WHERE survey_id = ? AND user_id = ?",
        survey_id,
        user_id,
    )
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|r| r.answers))
}

/// 回答レコードの DM 送信済みフラグを立てる。
///
/// Python: `SurveyService.mark_dm_sent()`
pub async fn mark_dm_sent(pool: &MySqlPool, response_id: i64) -> BridgeResult<()> {
    sqlx::query!(
        "UPDATE survey_responses SET dm_sent = TRUE WHERE id = ?",
        response_id,
    )
    .execute(pool)
    .await?;

    Ok(())
}

/// 既存回答レコードを UPDATE する（UPSERT の UPDATE 分岐。bot/ から呼ばれる）。
pub(crate) async fn update_response(
    pool: &MySqlPool,
    response_id: i64,
    answers_json: &str,
) -> BridgeResult<()> {
    sqlx::query!(
        "UPDATE survey_responses SET answers = ?, submitted_at = NOW(), dm_sent = FALSE WHERE id = ?",
        answers_json,
        response_id,
    )
    .execute(pool)
    .await?;

    Ok(())
}

/// 新規回答レコードを INSERT する（UPSERT の INSERT 分岐。bot/ から呼ばれる）。
pub(crate) async fn insert_response(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
    user_name: &str,
    answers_json: &str,
) -> BridgeResult<i64> {
    let result = sqlx::query!(
        r#"
        INSERT INTO survey_responses
            (survey_id, user_id, user_name, answers, submitted_at, dm_sent)
        VALUES (?, ?, ?, ?, NOW(), FALSE)
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
