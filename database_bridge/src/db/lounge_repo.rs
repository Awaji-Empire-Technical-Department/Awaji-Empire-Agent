// db/lounge_repo.rs
// Phase 3: セッション最終順位申告方式。レースごとの申告フローは廃止。
use sqlx::MySqlPool;
use crate::db::models::{
    BridgeResult, BridgeError,
    LoungeSession, LoungeTeam, LoungePlayer,
};

// 順位 1〜24 に対する MMR 増加量（index 0 は未使用）
// 月1開催想定。初期MMR 1000 から1セッションで各ランク閾値に到達するよう設計。
// 閾値: Iron≥0, Bronze≥2000, Silver≥4000, Gold≥6000, Platinum≥8000, Diamond≥10000
const MMR_DELTA: [i32; 25] = [
    0,    // 未使用
    9500, // 1位  → 10500 (Diamond ≥10000)
    8500, // 2位  → 9500  (Platinum)
    8000, // 3位  → 9000  (Platinum)
    7500, // 4位  → 8500  (Platinum)
    7000, // 5位  → 8000  (Platinum ≥8000)
    6500, // 6位  → 7500  (Gold)
    6200, // 7位  → 7200  (Gold)
    5500, // 8位  → 6500  (Gold)
    5000, // 9位  → 6000  (Gold ≥6000)
    4500, // 10位 → 5500  (Silver)
    4200, // 11位 → 5200  (Silver)
    4000, // 12位 → 5000  (Silver)
    3600, // 13位 → 4600  (Silver)
    3300, // 14位 → 4300  (Silver)
    3000, // 15位 → 4000  (Silver ≥4000)
    2500, // 16位 → 3500  (Bronze)
    2200, // 17位 → 3200  (Bronze)
    2000, // 18位 → 3000  (Bronze)
    1000, // 19位 → 2000  (Bronze ≥2000)
    800,  // 20位 → 1800  (Iron <2000)
    600,  // 21位 → 1600  (Iron)
    400,  // 22位 → 1400  (Iron)
    200,  // 23位 → 1200  (Iron)
    100,  // 24位 → 1100  (Iron)
];

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
        "INSERT INTO lounge_sessions (room_id, mode, total_races, host_id, status) VALUES (?, ?, ?, ?, 'in_progress')"
    )
    .bind(room_id).bind(mode).bind(total_races).bind(host_id)
    .execute(pool)
    .await?;
    Ok(result.last_insert_id() as i64)
}

pub async fn list_active_sessions(pool: &MySqlPool) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT ls.id, ls.room_id, ls.mode, ls.total_races, ls.status,
                  ls.host_id, u.username as host_name,
                  CAST(ls.created_at AS CHAR) as created_at,
                  COUNT(lsm.user_id) as member_count
           FROM lounge_sessions ls
           LEFT JOIN user_networks u ON u.discord_id = ls.host_id
           LEFT JOIN lounge_session_members lsm ON lsm.session_id = ls.id
           WHERE ls.status = 'in_progress'
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

pub async fn finish_session(pool: &MySqlPool, session_id: i64) -> BridgeResult<()> {
    sqlx::query("UPDATE lounge_sessions SET status = 'finished' WHERE id = ?")
        .bind(session_id)
        .execute(pool)
        .await?;
    // 除外されていないメンバーの total_sessions をインクリメント
    sqlx::query(
        r#"UPDATE lounge_players lp
           JOIN lounge_session_members lsm ON lsm.user_id = lp.user_id
           SET lp.total_sessions = lp.total_sessions + 1
           WHERE lsm.session_id = ? AND lsm.excluded = FALSE"#
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
        r#"SELECT lsm.user_id, lsm.excluded, u.username, lp.mmr
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
    Ok(rows.iter().map(|r| {
        let uid: i64 = r.get("user_id");
        serde_json::json!({
            "user_id":  uid.to_string(),
            "username": r.get::<Option<String>, _>("username"),
            "mmr":      r.get::<Option<i32>, _>("mmr").unwrap_or(1000),
            "excluded": r.get::<bool, _>("excluded"),
        })
    }).collect())
}

// ============================================================
// 除外操作（ホストのみ）
// ============================================================

/// player の excluded フラグをトグルする。
pub async fn toggle_exclude_player(pool: &MySqlPool, session_id: i64, user_id: i64) -> BridgeResult<bool> {
    sqlx::query(
        r#"UPDATE lounge_session_members
           SET excluded = NOT excluded
           WHERE session_id = ? AND user_id = ?"#
    )
    .bind(session_id).bind(user_id)
    .execute(pool)
    .await?;

    let excluded: bool = sqlx::query_scalar(
        "SELECT excluded FROM lounge_session_members WHERE session_id = ? AND user_id = ?"
    )
    .bind(session_id).bind(user_id)
    .fetch_one(pool)
    .await?;
    Ok(excluded)
}

// ============================================================
// lounge_session_final_scores
// ============================================================

pub async fn report_final_score(
    pool: &MySqlPool,
    session_id: i64,
    user_id: i64,
    final_rank: i8,
) -> BridgeResult<()> {
    if final_rank < 1 || final_rank > 24 {
        return Err(BridgeError::NotFound("final_rank は 1〜24 で指定してください".into()));
    }
    sqlx::query(
        r#"INSERT INTO lounge_session_final_scores (session_id, user_id, final_rank)
           VALUES (?, ?, ?)
           ON DUPLICATE KEY UPDATE final_rank = VALUES(final_rank), submitted_at = NOW()"#
    )
    .bind(session_id).bind(user_id).bind(final_rank)
    .execute(pool)
    .await?;
    Ok(())
}

/// 全メンバーの申告状況を返す（未申告者も含む）。
pub async fn get_final_scores(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    let rows = sqlx::query(
        r#"SELECT lsm.user_id, lsm.excluded, u.username,
                  lsf.final_rank, lsf.mmr_delta,
                  CASE WHEN lsf.user_id IS NOT NULL THEN TRUE ELSE FALSE END as submitted
           FROM lounge_session_members lsm
           LEFT JOIN user_networks u ON u.discord_id = lsm.user_id
           LEFT JOIN lounge_session_final_scores lsf
               ON lsf.session_id = lsm.session_id AND lsf.user_id = lsm.user_id
           WHERE lsm.session_id = ?
           ORDER BY COALESCE(lsf.final_rank, 999), lsm.joined_at"#
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    Ok(rows.iter().map(|r| {
        let uid: i64 = r.get("user_id");
        let submitted: bool = r.get("submitted");
        serde_json::json!({
            "user_id":    uid.to_string(),
            "username":   r.get::<Option<String>, _>("username"),
            "excluded":   r.get::<bool, _>("excluded"),
            "submitted":  submitted,
            "final_rank": r.get::<Option<i8>, _>("final_rank"),
            "mmr_delta":  r.get::<Option<i32>, _>("mmr_delta"),
        })
    }).collect())
}

/// 申告済み・非除外プレイヤーの MMR を計算・更新し、結果を返す。
/// トランザクションで一括処理する。
pub async fn calc_and_apply_mmr(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    // 申告済み・非除外プレイヤーを取得
    let rows = sqlx::query(
        r#"SELECT lsf.user_id, lsf.final_rank
           FROM lounge_session_final_scores lsf
           JOIN lounge_session_members lsm
               ON lsm.session_id = lsf.session_id AND lsm.user_id = lsf.user_id
           WHERE lsf.session_id = ? AND lsm.excluded = FALSE
           ORDER BY lsf.final_rank"#
    )
    .bind(session_id)
    .fetch_all(pool)
    .await?;

    use sqlx::Row;
    let mut results = vec![];

    let mut tx = pool.begin().await?;

    for row in &rows {
        let user_id: i64 = row.get("user_id");
        let final_rank: i8 = row.get("final_rank");
        let rank_idx = final_rank.clamp(1, 24) as usize;
        let delta = MMR_DELTA[rank_idx];

        // MMR 更新
        sqlx::query(
            r#"UPDATE lounge_players
               SET mmr = GREATEST(0, mmr + ?),
                   peak_mmr = GREATEST(peak_mmr, GREATEST(0, mmr + ?))
               WHERE user_id = ?"#
        )
        .bind(delta).bind(delta).bind(user_id)
        .execute(&mut *tx)
        .await?;

        // final_scores に mmr_delta を記録
        sqlx::query(
            "UPDATE lounge_session_final_scores SET mmr_delta = ? WHERE session_id = ? AND user_id = ?"
        )
        .bind(delta).bind(session_id).bind(user_id)
        .execute(&mut *tx)
        .await?;

        results.push((user_id, final_rank, delta));
    }

    tx.commit().await?;

    // 新 MMR を取得して返却
    let mut output = vec![];
    for (user_id, final_rank, delta) in results {
        let new_mmr: i32 = sqlx::query_scalar(
            "SELECT mmr FROM lounge_players WHERE user_id = ?"
        )
        .bind(user_id)
        .fetch_one(pool)
        .await
        .unwrap_or(1000);

        output.push(serde_json::json!({
            "user_id":    user_id.to_string(),
            "final_rank": final_rank,
            "mmr_delta":  delta,
            "new_mmr":    new_mmr,
        }));
    }
    Ok(output)
}

/// セッション最終順位一覧（result_modal / standings 表示用）。
pub async fn get_session_standings(pool: &MySqlPool, session_id: i64) -> BridgeResult<Vec<serde_json::Value>> {
    get_final_scores(pool, session_id).await
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
            "id":         team.id,
            "tag":        team.tag,
            "member_ids": members,
        }));
    }
    Ok(result)
}
