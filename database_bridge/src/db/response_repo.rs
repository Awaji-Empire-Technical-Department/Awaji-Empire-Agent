// db/response_repo.rs
// Why: survey_responses テーブルへの純粋な CRUD をここに集約する。
//      UPSERT ロジック（Bot 固有）は bot/survey_handler.rs に分離している。
//
//      Note: sqlx::query!マクロの代わりに sqlx::query() ランタイム関数を使用。

use sqlx::{mysql::MySqlPool, Row};

use super::models::{BridgeResult, SurveyResponse};

/// アンケートの全回答を取得する。
///
/// Python: `SurveyService.get_responses()`
pub async fn find_by_survey(pool: &MySqlPool, survey_id: i64) -> BridgeResult<Vec<SurveyResponse>> {
    let responses = sqlx::query_as::<_, SurveyResponse>(
        "SELECT * FROM survey_responses WHERE survey_id = ? ORDER BY submitted_at DESC",
    )
    .bind(survey_id)
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
    let row = sqlx::query(
        "SELECT answers FROM survey_responses WHERE survey_id = ? AND user_id = ?",
    )
    .bind(survey_id)
    .bind(user_id)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|r| {
        let bytes = r.try_get::<Vec<u8>, _>("answers").unwrap_or_default();
        String::from_utf8_lossy(&bytes).into_owned()
    }))
}

/// 回答レコードの DM 送信済みフラグを立てる。
///
/// Python: `SurveyService.mark_dm_sent()`
pub async fn mark_dm_sent(pool: &MySqlPool, response_id: i64) -> BridgeResult<()> {
    sqlx::query("UPDATE survey_responses SET dm_sent = TRUE WHERE id = ?")
        .bind(response_id)
        .execute(pool)
        .await?;

    Ok(())
}
