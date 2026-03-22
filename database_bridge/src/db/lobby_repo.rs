// db/lobby_repo.rs
// Why: ロビー関連テーブルへのCRUD操作をカプセル化する。
use sqlx::MySqlPool;
use crate::db::models::{BridgeResult, BridgeError, LobbyRoom, LobbyMember};

pub async fn ensure_user_exists(pool: &MySqlPool, discord_id: i64) -> BridgeResult<()> {
    let query = r#"
        INSERT IGNORE INTO user_networks (discord_id, email, username)
        VALUES (?, '', NULL)
    "#;
    sqlx::query(query)
        .bind(discord_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn sync_user_network(pool: &MySqlPool, discord_id: i64, email: &str, username: Option<&str>, virtual_ip: Option<&str>) -> BridgeResult<()> {
    let query = r#"
        INSERT INTO user_networks (discord_id, email, username, virtual_ip)
        VALUES (?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
        email = VALUES(email),
        username = VALUES(username),
        virtual_ip = VALUES(virtual_ip),
        updated_at = CURRENT_TIMESTAMP
    "#;
    sqlx::query(query)
        .bind(discord_id)
        .bind(email)
        .bind(username)
        .bind(virtual_ip)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn cleanup_expired_rooms(pool: &MySqlPool) -> BridgeResult<()> {
    let query = "DELETE FROM matchmaking_rooms WHERE expires_at <= NOW()";
    let _ = sqlx::query(query).execute(pool).await; // Ignore errors in lazy deletion
    Ok(())
}

pub async fn find_active_rooms(pool: &MySqlPool) -> BridgeResult<Vec<LobbyRoom>> {
    let _ = cleanup_expired_rooms(pool).await;
    let query = r#"
        SELECT m.passcode, m.host_id, m.mode, m.title, m.description, CAST(m.tournament_start_at AS CHAR) as tournament_start_at, m.is_approved, CAST(m.expires_at AS CHAR) as expires_at, u.virtual_ip
        FROM matchmaking_rooms m
        LEFT JOIN user_networks u ON m.host_id = u.discord_id
        WHERE m.expires_at > NOW()
    "#;
    let rooms = sqlx::query_as::<_, LobbyRoom>(query).fetch_all(pool).await?;
    Ok(rooms)
}

pub async fn find_room_by_passcode(pool: &MySqlPool, passcode: &str) -> BridgeResult<LobbyRoom> {
     let query = r#"
        SELECT m.passcode, m.host_id, m.mode, m.title, m.description, CAST(m.tournament_start_at AS CHAR) as tournament_start_at, m.is_approved, CAST(m.expires_at AS CHAR) as expires_at, u.virtual_ip
        FROM matchmaking_rooms m
        LEFT JOIN user_networks u ON m.host_id = u.discord_id
        WHERE m.passcode = ? AND m.expires_at > NOW()
    "#;
    let room = sqlx::query_as::<_, LobbyRoom>(query)
        .bind(passcode)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| BridgeError::NotFound(format!("Room '{}' not found", passcode)))?;
    Ok(room)
}

pub async fn insert_room(
    pool: &MySqlPool, 
    passcode: &str, 
    host_id: i64, 
    mode: &str, 
    title: &str,
    description: Option<&str>,
    expires_in_hours: u32
) -> BridgeResult<()> {
    ensure_user_exists(pool, host_id).await?;

    let query = r#"
        INSERT INTO matchmaking_rooms (passcode, host_id, mode, title, description, expires_at)
        VALUES (?, ?, ?, ?, ?, DATE_ADD(NOW(), INTERVAL ? HOUR))
    "#;
    sqlx::query(query)
        .bind(passcode)
        .bind(host_id)
        .bind(mode)
        .bind(title)
        .bind(description)
        .bind(expires_in_hours)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn delete_room(pool: &MySqlPool, passcode: &str) -> BridgeResult<()> {
    // ON DELETE CASCADE なしでも動くように手動で依存関係を削除
    sqlx::query("DELETE FROM tournament_matches WHERE room_passcode = ?")
        .bind(passcode)
        .execute(pool)
        .await?;
        
    sqlx::query("DELETE FROM lobby_members WHERE room_passcode = ?")
        .bind(passcode)
        .execute(pool)
        .await?;

    let query = "DELETE FROM matchmaking_rooms WHERE passcode = ?";
    sqlx::query(query).bind(passcode).execute(pool).await?;
    Ok(())
}

pub async fn update_room_approval(pool: &MySqlPool, passcode: &str, is_approved: bool) -> BridgeResult<()> {
    let query = "UPDATE matchmaking_rooms SET is_approved = ? WHERE passcode = ?";
    sqlx::query(query)
        .bind(is_approved)
        .bind(passcode)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn start_tournament(pool: &MySqlPool, passcode: &str) -> BridgeResult<()> {
    let query = "UPDATE matchmaking_rooms SET tournament_start_at = NOW() WHERE passcode = ? AND mode = 'tournament'";
    sqlx::query(query)
        .bind(passcode)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn transfer_host(pool: &MySqlPool, passcode: &str, new_host_id: i64) -> BridgeResult<()> {
    ensure_user_exists(pool, new_host_id).await?;
    let query = "UPDATE matchmaking_rooms SET host_id = ? WHERE passcode = ?";
    sqlx::query(query)
        .bind(new_host_id)
        .bind(passcode)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn find_members(pool: &MySqlPool, passcode: &str) -> BridgeResult<Vec<LobbyMember>> {
    let query = r#"
        SELECT l.room_passcode, l.user_id, u.username, u.virtual_ip, l.role, l.status
        FROM lobby_members l
        LEFT JOIN user_networks u ON l.user_id = u.discord_id
        WHERE l.room_passcode = ?
    "#;
    let members = sqlx::query_as::<_, LobbyMember>(query)
        .bind(passcode)
        .fetch_all(pool)
        .await?;
    Ok(members)
}

pub async fn upsert_member(pool: &MySqlPool, passcode: &str, user_id: i64, role: &str) -> BridgeResult<()> {
    ensure_user_exists(pool, user_id).await?;
    let query = r#"
        INSERT INTO lobby_members (room_passcode, user_id, role)
        VALUES (?, ?, ?)
        ON DUPLICATE KEY UPDATE role = VALUES(role)
    "#;
    sqlx::query(query)
        .bind(passcode)
        .bind(user_id)
        .bind(role)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn remove_member(pool: &MySqlPool, passcode: &str, user_id: i64) -> BridgeResult<()> {
    let query = "DELETE FROM lobby_members WHERE room_passcode = ? AND user_id = ?";
    sqlx::query(query)
        .bind(passcode)
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn update_member_status(pool: &MySqlPool, passcode: &str, user_id: i64, status: &str) -> BridgeResult<()> {
    let query = "UPDATE lobby_members SET status = ? WHERE room_passcode = ? AND user_id = ?";
    sqlx::query(query)
        .bind(status)
        .bind(passcode)
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn get_tournament_matches(pool: &MySqlPool, passcode: &str) -> BridgeResult<Vec<crate::db::models::TournamentMatch>> {
    let query = r#"
        SELECT * FROM tournament_matches WHERE room_passcode = ? ORDER BY round_num ASC, match_index ASC
    "#;
    let matches = sqlx::query_as::<_, crate::db::models::TournamentMatch>(query)
        .bind(passcode)
        .fetch_all(pool)
        .await?;
    Ok(matches)
}

pub async fn insert_tournament_match(
    pool: &MySqlPool, 
    passcode: &str, 
    player1_id: Option<i64>, 
    player2_id: Option<i64>,
    round_num: i32,
    match_index: i32,
    win_condition: i32
) -> BridgeResult<i32> {
    let query = r#"
        INSERT INTO tournament_matches (room_passcode, player1_id, player2_id, round_num, match_index, win_condition)
        VALUES (?, ?, ?, ?, ?, ?)
    "#;
    let result = sqlx::query(query)
        .bind(passcode)
        .bind(player1_id)
        .bind(player2_id)
        .bind(round_num)
        .bind(match_index)
        .bind(win_condition)
        .execute(pool)
        .await?;
    Ok(result.last_insert_id() as i32)
}

pub async fn report_match_winner(pool: &MySqlPool, match_id: i32, winner_id: i64, score1: i32, score2: i32) -> BridgeResult<()> {
    // NOTE: Simplified logic. For full validation, we'd check if max(score1, score2) >= win_condition.
    let query = "UPDATE tournament_matches SET winner_id = ?, status = 'finished', score1 = ?, score2 = ? WHERE match_id = ?";
    sqlx::query(query)
        .bind(winner_id)
        .bind(score1)
        .bind(score2)
        .bind(match_id)
        .execute(pool)
        .await?;
    Ok(())
}
