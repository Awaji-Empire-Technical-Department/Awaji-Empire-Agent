// db/tournament_repo.rs
// Why: 汎用大会・称号システム向けのDB操作をカプセル化する。
use sqlx::MySqlPool;
use crate::db::models::{
    BridgeResult, BridgeError,
    GameTitle, MatchScore, PointTable,
    Title, TitleWithStatus,
};

// ============================================================
// game_titles
// ============================================================

pub async fn list_game_titles(pool: &MySqlPool) -> BridgeResult<Vec<GameTitle>> {
    let titles = sqlx::query_as::<_, GameTitle>(
        "SELECT id, name, match_type, max_players, score_type, is_active FROM game_titles WHERE is_active = TRUE ORDER BY id"
    )
    .fetch_all(pool)
    .await?;
    Ok(titles)
}

// ============================================================
// match_scores
// ============================================================

pub async fn upsert_match_score(
    pool: &MySqlPool,
    match_id: i32,
    user_id: i64,
    position: i8,
) -> BridgeResult<()> {
    sqlx::query(
        "INSERT INTO match_scores (match_id, user_id, position, status)
         VALUES (?, ?, ?, 'pending')
         ON DUPLICATE KEY UPDATE position = VALUES(position), status = 'pending'"
    )
    .bind(match_id)
    .bind(user_id)
    .bind(position)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn approve_match_scores(pool: &MySqlPool, match_id: i32) -> BridgeResult<()> {
    // ポイントを point_tables から計算して確定する
    sqlx::query(
        r#"UPDATE match_scores ms
           JOIN tournament_matches tm ON ms.match_id = tm.match_id
           JOIN matchmaking_rooms mr ON tm.room_passcode = mr.passcode
           JOIN point_tables pt ON pt.game_title_id = mr.game_title_id AND pt.position = ms.position
           SET ms.points = pt.points, ms.status = 'approved'
           WHERE ms.match_id = ?"#
    )
    .bind(match_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_match_scores(pool: &MySqlPool, match_id: i32) -> BridgeResult<Vec<MatchScore>> {
    let scores = sqlx::query_as::<_, MatchScore>(
        "SELECT id, match_id, user_id, position, points, status FROM match_scores WHERE match_id = ? ORDER BY position"
    )
    .bind(match_id)
    .fetch_all(pool)
    .await?;
    Ok(scores)
}

pub async fn get_tournament_standings(pool: &MySqlPool, passcode: &str) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT ms.user_id, u.username, SUM(ms.points) as total_points
           FROM match_scores ms
           JOIN tournament_matches tm ON ms.match_id = tm.match_id
           LEFT JOIN user_networks u ON ms.user_id = u.discord_id
           WHERE tm.room_passcode = ? AND ms.status = 'approved'
           GROUP BY ms.user_id, u.username
           ORDER BY total_points DESC"#
    )
    .bind(passcode)
    .fetch_all(pool)
    .await?;

    let result = rows.iter().map(|r| {
        use sqlx::Row;
        serde_json::json!({
            "user_id": r.get::<i64, _>("user_id"),
            "username": r.get::<Option<String>, _>("username"),
            "total_points": r.get::<i64, _>("total_points"),
        })
    }).collect();
    Ok(result)
}

pub async fn get_point_table(pool: &MySqlPool, game_title_id: i32) -> BridgeResult<Vec<PointTable>> {
    let pts = sqlx::query_as::<_, PointTable>(
        "SELECT game_title_id, position, points FROM point_tables WHERE game_title_id = ? ORDER BY position"
    )
    .bind(game_title_id)
    .fetch_all(pool)
    .await?;
    Ok(pts)
}

// ============================================================
// titles（称号マスタ）
// ============================================================

pub async fn list_titles(pool: &MySqlPool) -> BridgeResult<Vec<Title>> {
    let titles = sqlx::query_as::<_, Title>(
        r#"SELECT id, name, description, unlock_type, unlock_threshold, discord_role_id,
                  is_active, display_order, CAST(created_at AS CHAR) as created_at
           FROM titles ORDER BY display_order, id"#
    )
    .fetch_all(pool)
    .await?;
    Ok(titles)
}

pub async fn get_title(pool: &MySqlPool, title_id: i32) -> BridgeResult<Title> {
    sqlx::query_as::<_, Title>(
        r#"SELECT id, name, description, unlock_type, unlock_threshold, discord_role_id,
                  is_active, display_order, CAST(created_at AS CHAR) as created_at
           FROM titles WHERE id = ?"#
    )
    .bind(title_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| BridgeError::NotFound(format!("Title {} not found", title_id)))
}

pub async fn upsert_title(
    pool: &MySqlPool,
    id: Option<i32>,
    name: &str,
    description: Option<&str>,
    unlock_type: &str,
    unlock_threshold: Option<i32>,
    discord_role_id: Option<&str>,
    display_order: i32,
) -> BridgeResult<i32> {
    if let Some(existing_id) = id {
        sqlx::query(
            r#"UPDATE titles SET name=?, description=?, unlock_type=?, unlock_threshold=?,
               discord_role_id=?, display_order=? WHERE id=?"#
        )
        .bind(name).bind(description).bind(unlock_type).bind(unlock_threshold)
        .bind(discord_role_id).bind(display_order).bind(existing_id)
        .execute(pool).await?;
        Ok(existing_id)
    } else {
        let result = sqlx::query(
            r#"INSERT INTO titles (name, description, unlock_type, unlock_threshold, discord_role_id, display_order)
               VALUES (?, ?, ?, ?, ?, ?)"#
        )
        .bind(name).bind(description).bind(unlock_type).bind(unlock_threshold)
        .bind(discord_role_id).bind(display_order)
        .execute(pool).await?;
        Ok(result.last_insert_id() as i32)
    }
}

pub async fn update_title_discord_role(pool: &MySqlPool, title_id: i32, discord_role_id: &str) -> BridgeResult<()> {
    sqlx::query("UPDATE titles SET discord_role_id = ? WHERE id = ?")
        .bind(discord_role_id)
        .bind(title_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn delete_title(pool: &MySqlPool, title_id: i32) -> BridgeResult<()> {
    sqlx::query("DELETE FROM titles WHERE id = ?")
        .bind(title_id)
        .execute(pool)
        .await?;
    Ok(())
}

// ============================================================
// player_titles（獲得称号）
// ============================================================

pub async fn grant_title(pool: &MySqlPool, user_id: i64, title_id: i32) -> BridgeResult<bool> {
    let result = sqlx::query(
        "INSERT IGNORE INTO player_titles (user_id, title_id) VALUES (?, ?)"
    )
    .bind(user_id)
    .bind(title_id)
    .execute(pool)
    .await?;
    Ok(result.rows_affected() > 0)
}

pub async fn list_player_titles_with_status(
    pool: &MySqlPool,
    user_id: i64,
) -> BridgeResult<Vec<TitleWithStatus>> {
    let rows = sqlx::query(
        r#"SELECT t.id, t.name, t.description, t.unlock_type, t.unlock_threshold,
                  t.discord_role_id, t.is_active, t.display_order,
                  (pt.title_id IS NOT NULL) as earned,
                  (pat.title_id IS NOT NULL) as is_active_title
           FROM titles t
           LEFT JOIN player_titles pt ON pt.title_id = t.id AND pt.user_id = ?
           LEFT JOIN player_active_title pat ON pat.title_id = t.id AND pat.user_id = ?
           WHERE t.is_active = TRUE
           ORDER BY t.display_order, t.id"#
    )
    .bind(user_id)
    .bind(user_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    let result = rows.iter().map(|r| TitleWithStatus {
        id: r.get("id"),
        name: r.get("name"),
        description: r.get("description"),
        unlock_type: r.get("unlock_type"),
        unlock_threshold: r.get("unlock_threshold"),
        discord_role_id: r.get("discord_role_id"),
        is_active: r.get("is_active"),
        display_order: r.get("display_order"),
        earned: r.get::<bool, _>("earned"),
        is_active_title: r.get::<bool, _>("is_active_title"),
    }).collect();
    Ok(result)
}

// ============================================================
// player_active_title（装備称号）
// ============================================================

pub async fn set_active_title(
    pool: &MySqlPool,
    user_id: i64,
    title_id: i32,
) -> BridgeResult<()> {
    // 獲得済みであることを確認
    let owned = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM player_titles WHERE user_id = ? AND title_id = ?"
    )
    .bind(user_id)
    .bind(title_id)
    .fetch_one(pool)
    .await?;

    if owned == 0 {
        return Err(BridgeError::PermissionDenied);
    }

    sqlx::query(
        r#"INSERT INTO player_active_title (user_id, title_id)
           VALUES (?, ?)
           ON DUPLICATE KEY UPDATE title_id = VALUES(title_id)"#
    )
    .bind(user_id)
    .bind(title_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn get_active_title(
    pool: &MySqlPool,
    user_id: i64,
) -> BridgeResult<Option<Title>> {
    let title = sqlx::query_as::<_, Title>(
        r#"SELECT t.id, t.name, t.description, t.unlock_type, t.unlock_threshold,
                  t.discord_role_id, t.is_active, t.display_order,
                  CAST(t.created_at AS CHAR) as created_at
           FROM player_active_title pat
           JOIN titles t ON t.id = pat.title_id
           WHERE pat.user_id = ?"#
    )
    .bind(user_id)
    .fetch_optional(pool)
    .await?;
    Ok(title)
}

/// 大会優勝時に該当する称号を自動付与する
pub async fn auto_grant_tournament_titles(
    pool: &MySqlPool,
    user_id: i64,
) -> BridgeResult<Vec<i32>> {
    let win_count: i64 = sqlx::query_scalar(
        r#"SELECT COUNT(*) FROM tournament_matches WHERE winner_id = ? AND status = 'finished'"#
    )
    .bind(user_id)
    .fetch_one(pool)
    .await?;

    let candidates = sqlx::query_as::<_, Title>(
        r#"SELECT id, name, description, unlock_type, unlock_threshold, discord_role_id,
                  is_active, display_order, CAST(created_at AS CHAR) as created_at
           FROM titles
           WHERE unlock_type = 'tournament_win'
             AND unlock_threshold <= ?
             AND is_active = TRUE"#
    )
    .bind(win_count)
    .fetch_all(pool)
    .await?;

    let mut newly_granted = vec![];
    for title in candidates {
        let granted = grant_title(pool, user_id, title.id).await?;
        if granted {
            newly_granted.push(title.id);
        }
    }
    Ok(newly_granted)
}

/// ラウンジMMR変動時に該当するランク称号を自動付与（古いランク称号は保持し、新しいものを追加）
pub async fn auto_grant_lounge_rank_title(
    pool: &MySqlPool,
    user_id: i64,
    current_mmr: i32,
) -> BridgeResult<Vec<i32>> {
    let candidates = sqlx::query_as::<_, Title>(
        r#"SELECT id, name, description, unlock_type, unlock_threshold, discord_role_id,
                  is_active, display_order, CAST(created_at AS CHAR) as created_at
           FROM titles
           WHERE unlock_type = 'lounge_rank'
             AND unlock_threshold <= ?
             AND is_active = TRUE"#
    )
    .bind(current_mmr)
    .fetch_all(pool)
    .await?;

    let mut newly_granted = vec![];
    for title in candidates {
        let granted = grant_title(pool, user_id, title.id).await?;
        if granted {
            newly_granted.push(title.id);
        }
    }
    Ok(newly_granted)
}
