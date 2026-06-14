// db/response_repo.rs
// Why: survey_responses テーブルへの操作を集約する。

use sqlx::{mysql::MySqlPool, Row};

use super::models::{BridgeError, BridgeResult, SurveyResponse};

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

/// 回答を ID で削除する（管理者用）。
pub async fn delete_by_id(pool: &MySqlPool, response_id: i64) -> BridgeResult<()> {
    sqlx::query("DELETE FROM survey_responses WHERE id = ?")
        .bind(response_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// ユーザー本人の回答を削除する（survey_id + user_id 照合）。
/// 削除した回答の response_id を返す（None = 対象なし）。
/// Why: 呼び出し側が紐づく event_participants の削除に response_id を使う。
pub async fn delete_by_user(
    pool: &MySqlPool,
    survey_id: i64,
    user_id: &str,
) -> BridgeResult<Option<i64>> {
    let user_id_int = user_id.parse::<i64>().unwrap_or(0);

    let row = sqlx::query("SELECT id FROM survey_responses WHERE survey_id = ? AND user_id = ?")
        .bind(survey_id)
        .bind(user_id_int)
        .fetch_optional(pool)
        .await?;

    let response_id: i64 = match row {
        Some(r) => r.try_get("id").map_err(BridgeError::Sqlx)?,
        None => return Ok(None),
    };

    sqlx::query("DELETE FROM survey_responses WHERE id = ?")
        .bind(response_id)
        .execute(pool)
        .await?;

    Ok(Some(response_id))
}
