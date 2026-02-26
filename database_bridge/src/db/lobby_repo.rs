// db/lobby_repo.rs
// Why: ロビー関連テーブルへのCRUD操作をカプセル化する。
use sqlx::MySqlPool;
use crate::db::models::{BridgeResult, BridgeError, LobbyRoom, LobbyMember};

pub async fn ensure_user_exists(pool: &MySqlPool, discord_id: i64) -> BridgeResult<()> {
    let query = r#"
        INSERT IGNORE INTO user_networks (discord_id, email)
        VALUES (?, '')
    "#;
    sqlx::query(query)
        .bind(discord_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn find_active_rooms(pool: &MySqlPool) -> BridgeResult<Vec<LobbyRoom>> {
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
        WHERE m.passcode = ?
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
    let query = "SELECT room_passcode, user_id, role FROM lobby_members WHERE room_passcode = ?";
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
