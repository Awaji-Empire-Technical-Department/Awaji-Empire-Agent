// db/lounge_repo.rs
// Why: ラウンジシステム固有のDB操作をカプセル化する。
use sqlx::MySqlPool;
use crate::db::models::{
    BridgeResult, BridgeError,
    LoungeSession, LoungeRaceResult, LoungeRaceScore, LoungeTeam, LoungePlayer,
};

// ============================================================
// lounge_players（MMR管理）
// ============================================================

pub async fn ensure_lounge_player(pool: &MySqlPool, user_id: i64) -> BridgeResult<()> {
    sqlx::query(
        "INSERT IGNORE INTO lounge_players (user_id) VALUES (?)"
    )
    .bind(user_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn get_lounge_player(pool: &MySqlPool, user_id: i64) -> BridgeResult<LoungePlayer> {
    ensure_lounge_player(pool, user_id).await?;
    sqlx::query_as::<_, LoungePlayer>(
        r#"SELECT user_id, mmr, peak_mmr, total_races, total_sessions,
                  CAST(updated_at AS CHAR) as updated_at
           FROM lounge_players WHERE user_id = ?"#
    )
    .bind(user_id)
    .fetch_one(pool)
    .await
    .map_err(BridgeError::Sqlx)
}

pub async fn update_mmr(pool: &MySqlPool, user_id: i64, delta: i32) -> BridgeResult<i32> {
    ensure_lounge_player(pool, user_id).await?;
    sqlx::query(
        r#"UPDATE lounge_players
           SET mmr = GREATEST(0, mmr + ?),
               peak_mmr = GREATEST(peak_mmr, GREATEST(0, mmr + ?)),
               total_races = total_races + 1
           WHERE user_id = ?"#
    )
    .bind(delta).bind(delta).bind(user_id)
    .execute(pool)
    .await?;

    let new_mmr: i32 = sqlx::query_scalar("SELECT mmr FROM lounge_players WHERE user_id = ?")
        .bind(user_id)
        .fetch_one(pool)
        .await?;
    Ok(new_mmr)
}

// ============================================================
// lounge_sessions
// ============================================================

pub async fn create_session(
    pool: &MySqlPool,
    room_id: &str,
    mode: &str,
    total_races: i8,
    host_id: i64,
) -> BridgeResult<i64> {
    let result = sqlx::query(
        "INSERT INTO lounge_sessions (room_id, mode, total_races, host_id) VALUES (?, ?, ?, ?)"
    )
    .bind(room_id).bind(mode).bind(total_races).bind(host_id)
    .execute(pool)
    .await?;
    Ok(result.last_insert_id() as i64)
}

pub async fn list_active_sessions(pool: &MySqlPool) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT ls.id, ls.room_id, ls.mode, ls.total_races, ls.current_race, ls.status,
                  ls.host_id, u.username as host_name,
                  CAST(ls.created_at AS CHAR) as created_at,
                  COUNT(lsm.user_id) as member_count
           FROM lounge_sessions ls
           LEFT JOIN user_networks u ON u.discord_id = ls.host_id
           LEFT JOIN lounge_session_members lsm ON lsm.session_id = ls.id
           WHERE ls.status IN ('waiting', 'in_progress')
           GROUP BY ls.id
           ORDER BY ls.created_at DESC"#
    )
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| serde_json::json!({
        "id":           r.get::<i64, _>("id"),
        "room_id":      r.get::<String, _>("room_id"),
        "mode":         r.get::<String, _>("mode"),
        "total_races":  r.get::<i8, _>("total_races"),
        "current_race": r.get::<i8, _>("current_race"),
        "status":       r.get::<String, _>("status"),
        "host_id":      r.get::<i64, _>("host_id"),
        "host_name":    r.get::<Option<String>, _>("host_name"),
        "created_at":   r.get::<String, _>("created_at"),
        "member_count": r.get::<i64, _>("member_count"),
    })).collect())
}

pub async fn get_session(pool: &MySqlPool, session_id: i64) -> BridgeResult<LoungeSession> {
    sqlx::query_as::<_, LoungeSession>(
        r#"SELECT id, room_id, mode, total_races, current_race, status, host_id,
                  CAST(created_at AS CHAR) as created_at
           FROM lounge_sessions WHERE id = ?"#
    )
    .bind(session_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| BridgeError::NotFound(format!("Session {} not found", session_id)))
}

pub async fn advance_session_race(pool: &MySqlPool, session_id: i64) -> BridgeResult<()> {
    sqlx::query(
        r#"UPDATE lounge_sessions
           SET current_race = current_race + 1,
               status = CASE WHEN current_race + 1 >= total_races THEN 'finished' ELSE 'in_progress' END
           WHERE id = ?"#
    )
    .bind(session_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn finish_session(pool: &MySqlPool, session_id: i64) -> BridgeResult<()> {
    sqlx::query("UPDATE lounge_sessions SET status = 'finished' WHERE id = ?")
        .bind(session_id)
        .execute(pool)
        .await?;
    // total_sessions をインクリメント
    sqlx::query(
        r#"UPDATE lounge_players lp
           JOIN lounge_session_members lsm ON lsm.user_id = lp.user_id
           SET lp.total_sessions = lp.total_sessions + 1
           WHERE lsm.session_id = ?"#
    )
    .bind(session_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn add_session_member(pool: &MySqlPool, session_id: i64, user_id: i64) -> BridgeResult<()> {
    ensure_lounge_player(pool, user_id).await?;
    sqlx::query(
        "INSERT IGNORE INTO lounge_session_members (session_id, user_id) VALUES (?, ?)"
    )
    .bind(session_id).bind(user_id)
    .execute(pool).await?;
    Ok(())
}

pub async fn list_session_members(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT lsm.user_id, u.username, lp.mmr
           FROM lounge_session_members lsm
           LEFT JOIN user_networks u ON u.discord_id = lsm.user_id
           LEFT JOIN lounge_players lp ON lp.user_id = lsm.user_id
           WHERE lsm.session_id = ?
           ORDER BY lp.mmr DESC"#
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| serde_json::json!({
        "user_id": r.get::<i64, _>("user_id"),
        "username": r.get::<Option<String>, _>("username"),
        "mmr": r.get::<Option<i32>, _>("mmr").unwrap_or(1000),
    })).collect())
}

// ============================================================
// lounge_race_results
// ============================================================

pub async fn create_race(
    pool: &MySqlPool,
    session_id: i64,
    race_number: i8,
    course_name: &str,
) -> BridgeResult<i64> {
    let result = sqlx::query(
        "INSERT INTO lounge_race_results (session_id, race_number, course_name) VALUES (?, ?, ?)"
    )
    .bind(session_id).bind(race_number).bind(course_name)
    .execute(pool)
    .await?;
    Ok(result.last_insert_id() as i64)
}

/// セッションの最新レース（未承認含む）を返す。ページリロード時の復元用。
pub async fn get_active_race(pool: &MySqlPool, session_id: i64) -> BridgeResult<Option<serde_json::Value>> {
    let row = sqlx::query(
        r#"SELECT id, course_name, race_number
           FROM lounge_race_results
           WHERE session_id = ?
           ORDER BY race_number DESC LIMIT 1"#
    )
    .bind(session_id)
    .fetch_optional(pool)
    .await?;

    use sqlx::Row;
    Ok(row.map(|r| serde_json::json!({
        "race_id":      r.get::<i64, _>("id"),
        "course_name":  r.get::<String, _>("course_name"),
        "race_number":  r.get::<i8, _>("race_number"),
    })))
}

/// スコア一覧にユーザー名を付加して返す。
pub async fn list_race_scores_named(pool: &MySqlPool, race_result_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT lrs.user_id, u.username, lrs.position, lrs.points,
                  lrs.is_disconnect, lrs.status
           FROM lounge_race_scores lrs
           LEFT JOIN user_networks u ON u.discord_id = lrs.user_id
           WHERE lrs.race_result_id = ?
           ORDER BY lrs.position"#
    )
    .bind(race_result_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| serde_json::json!({
        "user_id":       r.get::<i64, _>("user_id"),
        "username":      r.get::<Option<String>, _>("username"),
        "position":      r.get::<Option<i8>, _>("position"),
        "points":        r.get::<Option<i32>, _>("points"),
        "is_disconnect": r.get::<bool, _>("is_disconnect"),
        "status":        r.get::<String, _>("status"),
    })).collect())
}

pub async fn list_races(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<LoungeRaceResult>> {
    sqlx::query_as::<_, LoungeRaceResult>(
        r#"SELECT id, session_id, race_number, course_name, is_void,
                  CAST(created_at AS CHAR) as created_at
           FROM lounge_race_results WHERE session_id = ? ORDER BY race_number"#
    )
    .bind(session_id)
    .fetch_all(pool)
    .await
    .map_err(BridgeError::Sqlx)
}

pub async fn void_race(pool: &MySqlPool, race_id: i64) -> BridgeResult<()> {
    sqlx::query("UPDATE lounge_race_results SET is_void = TRUE WHERE id = ?")
        .bind(race_id)
        .execute(pool)
        .await?;
    Ok(())
}

// コース重複チェック：正規化キーで確認し、重複なければ登録
pub async fn check_and_register_course(
    pool: &MySqlPool,
    session_id: i64,
    course_key: &str,
) -> BridgeResult<bool> {
    let exists: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM lounge_course_history WHERE session_id = ? AND course_key = ?"
    )
    .bind(session_id).bind(course_key)
    .fetch_one(pool)
    .await?;

    if exists > 0 {
        return Ok(false); // 重複
    }
    sqlx::query(
        "INSERT IGNORE INTO lounge_course_history (session_id, course_key) VALUES (?, ?)"
    )
    .bind(session_id).bind(course_key)
    .execute(pool)
    .await?;
    Ok(true) // 登録成功
}

pub async fn get_course_history(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<String>> {
    let keys: Vec<String> = sqlx::query_scalar(
        "SELECT course_key FROM lounge_course_history WHERE session_id = ? ORDER BY course_key"
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;
    Ok(keys)
}

// ============================================================
// lounge_race_scores
// ============================================================

pub async fn report_score(
    pool: &MySqlPool,
    race_result_id: i64,
    user_id: i64,
    position: i8,
) -> BridgeResult<()> {
    sqlx::query(
        r#"INSERT INTO lounge_race_scores (race_result_id, user_id, position, status)
           VALUES (?, ?, ?, 'pending')
           ON DUPLICATE KEY UPDATE position = VALUES(position), status = 'pending'"#
    )
    .bind(race_result_id).bind(user_id).bind(position)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn report_disconnect(
    pool: &MySqlPool,
    race_result_id: i64,
    user_id: i64,
) -> BridgeResult<()> {
    sqlx::query(
        r#"INSERT INTO lounge_race_scores
               (race_result_id, user_id, position, is_disconnect, disconnect_reported_at, status)
           VALUES (?, ?, NULL, TRUE, NOW(), 'pending')
           ON DUPLICATE KEY UPDATE
               is_disconnect = TRUE,
               disconnect_reported_at = COALESCE(disconnect_reported_at, NOW()),
               status = 'pending'"#
    )
    .bind(race_result_id).bind(user_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_race_scores(pool: &MySqlPool, race_result_id: i64) -> BridgeResult<Vec<LoungeRaceScore>> {
    sqlx::query_as::<_, LoungeRaceScore>(
        r#"SELECT id, race_result_id, user_id, position, points, is_disconnect,
                  CAST(disconnect_reported_at AS CHAR) as disconnect_reported_at, status
           FROM lounge_race_scores WHERE race_result_id = ? ORDER BY position"#
    )
    .bind(race_result_id)
    .fetch_all(pool)
    .await
    .map_err(BridgeError::Sqlx)
}

/// スコアを承認してポイントを確定する
/// game_title_id=2（マリオカートワールド）の point_tables を参照
pub async fn approve_race_scores(pool: &MySqlPool, race_result_id: i64) -> BridgeResult<()> {
    // 回線落ちプレイヤーへのCPU点付与（同キャラ重複時は報告時刻が早い順に高い点）
    // 簡略実装: 回線落ちは一律0点（CPUキャラ申告は別途report_disconnect_with_cpu_posで対応）
    sqlx::query(
        r#"UPDATE lounge_race_scores lrs
           JOIN point_tables pt ON pt.game_title_id = 2 AND pt.position = lrs.position
           SET lrs.points = pt.points, lrs.status = 'approved'
           WHERE lrs.race_result_id = ? AND lrs.is_disconnect = FALSE"#
    )
    .bind(race_result_id)
    .execute(pool)
    .await?;

    // 回線落ちは status だけ approved に（points は0のまま）
    sqlx::query(
        "UPDATE lounge_race_scores SET status = 'approved' WHERE race_result_id = ? AND is_disconnect = TRUE"
    )
    .bind(race_result_id)
    .execute(pool)
    .await?;

    // 5人以上落ちたらレース無効
    let dc_count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM lounge_race_scores WHERE race_result_id = ? AND is_disconnect = TRUE"
    )
    .bind(race_result_id)
    .fetch_one(pool)
    .await?;

    if dc_count >= 5 {
        void_race(pool, race_result_id).await?;
    }
    Ok(())
}

// ============================================================
// ランキング
// ============================================================

pub async fn get_session_standings(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT lrs.user_id, u.username, SUM(lrs.points) as total_points,
                  COUNT(CASE WHEN lrs.position = 1 THEN 1 END) as first_place_count
           FROM lounge_race_scores lrs
           JOIN lounge_race_results lrr ON lrr.id = lrs.race_result_id
           LEFT JOIN user_networks u ON u.discord_id = lrs.user_id
           WHERE lrr.session_id = ? AND lrr.is_void = FALSE AND lrs.status = 'approved'
           GROUP BY lrs.user_id, u.username
           ORDER BY total_points DESC, first_place_count DESC"#
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| serde_json::json!({
        "user_id": r.get::<i64, _>("user_id"),
        "username": r.get::<Option<String>, _>("username"),
        "total_points": r.get::<Option<i64>, _>("total_points").unwrap_or(0),
        "first_place_count": r.get::<Option<i64>, _>("first_place_count").unwrap_or(0),
    })).collect())
}

pub async fn get_team_standings(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT lt.tag, SUM(lrs.points) as team_points
           FROM lounge_race_scores lrs
           JOIN lounge_race_results lrr ON lrr.id = lrs.race_result_id
           JOIN lounge_team_members ltm ON ltm.user_id = lrs.user_id
           JOIN lounge_teams lt ON lt.id = ltm.team_id AND lt.session_id = ?
           WHERE lrr.session_id = ? AND lrr.is_void = FALSE AND lrs.status = 'approved'
           GROUP BY lt.id, lt.tag
           ORDER BY team_points DESC"#
    )
    .bind(session_id).bind(session_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| serde_json::json!({
        "tag": r.get::<String, _>("tag"),
        "team_points": r.get::<Option<i64>, _>("team_points").unwrap_or(0),
    })).collect())
}

// ============================================================
// lounge_teams
// ============================================================

pub async fn create_team(pool: &MySqlPool, session_id: i64, tag: &str) -> BridgeResult<i64> {
    let result = sqlx::query(
        "INSERT INTO lounge_teams (session_id, tag) VALUES (?, ?)"
    )
    .bind(session_id).bind(tag)
    .execute(pool)
    .await?;
    Ok(result.last_insert_id() as i64)
}

pub async fn add_team_member(pool: &MySqlPool, team_id: i64, user_id: i64) -> BridgeResult<()> {
    sqlx::query(
        "INSERT IGNORE INTO lounge_team_members (team_id, user_id) VALUES (?, ?)"
    )
    .bind(team_id).bind(user_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_teams(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let teams = sqlx::query_as::<_, LoungeTeam>(
        "SELECT id, session_id, tag FROM lounge_teams WHERE session_id = ?"
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;

    let mut result = vec![];
    for team in teams {
        let members: Vec<i64> = sqlx::query_scalar(
            "SELECT user_id FROM lounge_team_members WHERE team_id = ?"
        )
        .bind(team.id)
        .fetch_all(pool)
        .await?;

        result.push(serde_json::json!({
            "id": team.id,
            "tag": team.tag,
            "member_ids": members,
        }));
    }
    Ok(result)
}
