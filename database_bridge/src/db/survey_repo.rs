// db/survey_repo.rs
// Why: surveys テーブルへの純粋な CRUD をここに集約する。

use sqlx::{mysql::MySqlPool, Row};
use tracing::error;

use super::models::{BridgeError, BridgeResult, Survey};

/// 新規アンケートを INSERT し、生成された ID を返す。
pub async fn insert(pool: &MySqlPool, owner_id: &str) -> BridgeResult<i64> {
    let result = sqlx::query(
        "INSERT INTO surveys (owner_id, title, questions, is_active, created_at) \
         VALUES (?, '無題のアンケート', '[]', FALSE, NOW())",
    )
    .bind(owner_id)
    .execute(pool)
    .await
    .map_err(|e| {
        error!("survey_repo::insert failed: {e}");
        BridgeError::Sqlx(e)
    })?;

    Ok(result.last_insert_id() as i64)
}

/// ID でアンケートを 1 件取得する。
pub async fn find_by_id(pool: &MySqlPool, survey_id: i64) -> BridgeResult<Survey> {
    sqlx::query_as::<_, Survey>("SELECT * FROM surveys WHERE id = ?")
        .bind(survey_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| BridgeError::NotFound(format!("survey_id={survey_id}")))
}

/// オーナー ID でアンケート一覧を取得する。
pub async fn find_by_owner(
    pool: &MySqlPool,
    owner_id: &str,
    active_only: Option<bool>,
) -> BridgeResult<Vec<Survey>> {
    let surveys = if owner_id == "ALL" {
        if active_only == Some(true) {
            sqlx::query_as::<_, Survey>(
                "SELECT * FROM surveys WHERE is_active = 1 ORDER BY created_at DESC",
            )
            .fetch_all(pool)
            .await?
        } else {
            sqlx::query_as::<_, Survey>(
                "SELECT * FROM surveys ORDER BY created_at DESC",
            )
            .fetch_all(pool)
            .await?
        }
    } else {
        if active_only == Some(true) {
            sqlx::query_as::<_, Survey>(
                "SELECT * FROM surveys WHERE owner_id = ? AND is_active = 1 ORDER BY created_at DESC",
            )
            .bind(owner_id)
            .fetch_all(pool)
            .await?
        } else {
            sqlx::query_as::<_, Survey>(
                "SELECT * FROM surveys WHERE owner_id = ? ORDER BY created_at DESC",
            )
            .bind(owner_id)
            .fetch_all(pool)
            .await?
        }
    };

    Ok(surveys)
}

/// 稼働中（is_active = 1）の全アンケートを取得する。
pub async fn find_active(pool: &MySqlPool) -> BridgeResult<Vec<Survey>> {
    let surveys = sqlx::query_as::<_, Survey>(
        "SELECT * FROM surveys WHERE is_active = 1 ORDER BY created_at DESC",
    )
    .fetch_all(pool)
    .await?;

    Ok(surveys)
}

/// タイトルと質問 JSON を更新する。
pub async fn update(
    pool: &MySqlPool,
    survey_id: i64,
    title: &str,
    questions_json: &str,
) -> BridgeResult<()> {
    sqlx::query("UPDATE surveys SET title = ?, questions = ? WHERE id = ?")
        .bind(title)
        .bind(questions_json)
        .bind(survey_id)
        .execute(pool)
        .await?;

    Ok(())
}

/// アンケートを削除する（owner_id 照合付き）。
pub async fn delete(pool: &MySqlPool, survey_id: i64, owner_id: &str) -> BridgeResult<()> {
    let survey = find_by_id(pool, survey_id).await?;

    if survey.owner_id != owner_id {
        return Err(BridgeError::PermissionDenied);
    }

    sqlx::query("DELETE FROM surveys WHERE id = ?")
        .bind(survey_id)
        .execute(pool)
        .await?;

    Ok(())
}

/// アンケートのオーナー ID を取得する。
pub async fn get_owner_id(pool: &MySqlPool, survey_id: i64) -> BridgeResult<String> {
    let row = sqlx::query("SELECT owner_id FROM surveys WHERE id = ?")
        .bind(survey_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| BridgeError::NotFound(format!("survey_id={survey_id}")))?;

    Ok(row.try_get("owner_id").map_err(BridgeError::Sqlx)?)
}
