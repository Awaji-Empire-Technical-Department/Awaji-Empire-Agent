// db/response_repo.rs
// Why: survey_responses テーブルへの操作を集約する。

use sqlx::mysql::MySqlPool;

use super::models::{BridgeResult, SurveyResponse};

/// SQL で DATETIME を文字列として取得するためのカラムリスト。
const SELECT_COLUMNS: &str = "id, survey_id, user_id, user_name, answers, CAST(submitted_at AS CHAR) as submitted_at, dm_sent";

/// 特定のアンケートに対する全回答を取得する。
pub async fn find_by_survey(pool: &MySqlPool, survey_id: i64) -> BridgeResult<Vec<SurveyResponse>> {
    let sql = format!("SELECT {} FROM survey_responses WHERE survey_id = ? ORDER BY submitted_at DESC", SELECT_COLUMNS);
    let responses = sqlx::query_as::<_, SurveyResponse>(&sql)
        .bind(survey_id)
        .fetch_all(pool)
        .await?;

    Ok(responses)
}

/// 特定のユーザーがそのアンケートに回答済みか確認し、回答を返す。
pub async fn find_answers_by_user(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
) -> BridgeResult<Option<SurveyResponse>> {
    // user_id は BIGINT なのでパース
    let user_id_int = user_id.parse::<i64>().unwrap_or(0);
    
    let sql = format!("SELECT {} FROM survey_responses WHERE survey_id = ? AND user_id = ?", SELECT_COLUMNS);
    let response = sqlx::query_as::<_, SurveyResponse>(&sql)
        .bind(survey_id)
        .bind(user_id_int)
        .fetch_optional(pool)
        .await?;

    Ok(response)
}

/// DM 送信済みフラグを更新する。
pub async fn mark_dm_sent(pool: &MySqlPool, response_id: i64) -> BridgeResult<()> {
    sqlx::query("UPDATE survey_responses SET dm_sent = TRUE WHERE id = ?")
        .bind(response_id)
        .execute(pool)
        .await?;

    Ok(())
}
