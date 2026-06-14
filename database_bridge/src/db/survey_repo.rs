// db/survey_repo.rs
// Why: surveys テーブルへの純粋な CRUD をここに集約する。

use serde_json::{json, Value};
use sqlx::{mysql::MySqlPool, Row};
use tracing::error;

use super::models::{BridgeError, BridgeResult, Survey};

/// SQL で DATETIME を文字列として取得するためのカラムリスト。
/// Why: sqlx は DATETIME 型を直接 String にデコードできないため、DB 側で変換する。
const SELECT_COLUMNS: &str = "id, owner_id, title, questions, is_active, CAST(created_at AS CHAR) as created_at";

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
    let sql = format!("SELECT {} FROM surveys WHERE id = ?", SELECT_COLUMNS);
    sqlx::query_as::<_, Survey>(&sql)
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
    let sql = if owner_id == "ALL" {
        if active_only == Some(true) {
            format!("SELECT {} FROM surveys WHERE is_active = 1 ORDER BY created_at DESC", SELECT_COLUMNS)
        } else {
            format!("SELECT {} FROM surveys ORDER BY created_at DESC", SELECT_COLUMNS)
        }
    } else {
        if active_only == Some(true) {
            format!("SELECT {} FROM surveys WHERE owner_id = ? AND is_active = 1 ORDER BY created_at DESC", SELECT_COLUMNS)
        } else {
            format!("SELECT {} FROM surveys WHERE owner_id = ? ORDER BY created_at DESC", SELECT_COLUMNS)
        }
    };

    let mut query = sqlx::query_as::<_, Survey>(&sql);
    if owner_id != "ALL" {
        query = query.bind(owner_id);
    }

    Ok(query.fetch_all(pool).await?)
}

/// 稼働中（is_active = 1）の全アンケートを取得する。
pub async fn find_active(pool: &MySqlPool) -> BridgeResult<Vec<Survey>> {
    let sql = format!("SELECT {} FROM surveys WHERE is_active = 1 ORDER BY created_at DESC", SELECT_COLUMNS);
    let surveys = sqlx::query_as::<_, Survey>(&sql)
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

// ============================================================
// スタッフ共同編集（survey_collaborators）
// ============================================================

/// スタッフ（共同編集者）を追加する。重複は無視。
pub async fn add_collaborator(pool: &MySqlPool, survey_id: i64, user_id: i64) -> BridgeResult<()> {
    sqlx::query("INSERT IGNORE INTO survey_collaborators (survey_id, user_id) VALUES (?, ?)")
        .bind(survey_id)
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// スタッフを削除する。
pub async fn remove_collaborator(pool: &MySqlPool, survey_id: i64, user_id: i64) -> BridgeResult<()> {
    sqlx::query("DELETE FROM survey_collaborators WHERE survey_id = ? AND user_id = ?")
        .bind(survey_id)
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// スタッフ一覧を {user_id, username} の配列で返す。username は user_networks から解決。
pub async fn list_collaborators(pool: &MySqlPool, survey_id: i64) -> BridgeResult<Vec<Value>> {
    let rows = sqlx::query(
        "SELECT c.user_id, u.username \
         FROM survey_collaborators c \
         LEFT JOIN user_networks u ON c.user_id = u.discord_id \
         WHERE c.survey_id = ? ORDER BY c.added_at",
    )
    .bind(survey_id)
    .fetch_all(pool)
    .await?;

    let list = rows
        .iter()
        .map(|row| {
            let user_id: i64 = row.try_get("user_id").unwrap_or(0);
            let username: Option<String> = row.try_get("username").ok();
            // user_id は JS 側で誤差なく扱えるよう文字列で返す
            json!({"user_id": user_id.to_string(), "username": username})
        })
        .collect();
    Ok(list)
}

/// 指定ユーザーがそのアンケートのスタッフか判定する。
pub async fn is_collaborator(pool: &MySqlPool, survey_id: i64, user_id: i64) -> BridgeResult<bool> {
    let row = sqlx::query("SELECT 1 FROM survey_collaborators WHERE survey_id = ? AND user_id = ? LIMIT 1")
        .bind(survey_id)
        .bind(user_id)
        .fetch_optional(pool)
        .await?;
    Ok(row.is_some())
}

/// ユーザー名（部分一致）でユーザーを検索する。スタッフ追加候補の提示に使用。
pub async fn search_users_by_username(pool: &MySqlPool, q: &str) -> BridgeResult<Vec<Value>> {
    let pattern = format!("%{q}%");
    let rows = sqlx::query(
        "SELECT discord_id, username FROM user_networks \
         WHERE username LIKE ? AND username IS NOT NULL \
         ORDER BY username LIMIT 20",
    )
    .bind(pattern)
    .fetch_all(pool)
    .await?;

    let list = rows
        .iter()
        .map(|row| {
            let discord_id: i64 = row.try_get("discord_id").unwrap_or(0);
            let username: Option<String> = row.try_get("username").ok();
            json!({"user_id": discord_id.to_string(), "username": username})
        })
        .collect();
    Ok(list)
}
