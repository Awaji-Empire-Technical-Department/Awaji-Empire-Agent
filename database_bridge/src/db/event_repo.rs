// db/event_repo.rs
// イベント参加フォーム機能の DB 操作を集約する。

use serde_json;
use sqlx::{mysql::MySqlPool, Row};
use tracing::error;

use super::models::{BridgeError, BridgeResult, Event, EventParticipant, EventSession};

// ============================================================
// events
// ============================================================

pub async fn insert_event(
    pool: &MySqlPool,
    survey_id: i32,
    title: &str,
    fee: Option<i32>,
    notes: Option<&str>,
    location: Option<&str>,
    event_date: Option<&str>,
    end_date: Option<&str>,
    application_deadline: Option<&str>,
) -> BridgeResult<i32> {
    let result = sqlx::query(
        "INSERT INTO events \
         (survey_id, title, fee, notes, location, status, event_date, end_date, application_deadline, created_at) \
         VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, NOW())",
    )
    .bind(survey_id)
    .bind(title)
    .bind(fee)
    .bind(notes)
    .bind(location)
    .bind(event_date)
    .bind(end_date)
    .bind(application_deadline)
    .execute(pool)
    .await
    .map_err(|e| {
        error!("event_repo::insert_event failed: {e}");
        BridgeError::Sqlx(e)
    })?;

    Ok(result.last_insert_id() as i32)
}

const EVENT_SELECT: &str =
    "SELECT id, survey_id, title, fee, notes, location, status, \
     CAST(event_date AS CHAR) as event_date, \
     CAST(end_date AS CHAR) as end_date, \
     CAST(application_deadline AS CHAR) as application_deadline, \
     CAST(created_at AS CHAR) as created_at \
     FROM events";

pub async fn find_event_by_id(pool: &MySqlPool, event_id: i32) -> BridgeResult<Event> {
    sqlx::query_as::<_, Event>(&format!("{EVENT_SELECT} WHERE id = ?"))
        .bind(event_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| BridgeError::NotFound(format!("event_id={event_id}")))
}

pub async fn find_event_by_survey(pool: &MySqlPool, survey_id: i32) -> BridgeResult<Option<Event>> {
    Ok(
        sqlx::query_as::<_, Event>(&format!("{EVENT_SELECT} WHERE survey_id = ?"))
            .bind(survey_id)
            .fetch_optional(pool)
            .await?,
    )
}

pub async fn update_event_status(pool: &MySqlPool, event_id: i32, status: &str) -> BridgeResult<()> {
    sqlx::query("UPDATE events SET status = ? WHERE id = ?")
        .bind(status)
        .bind(event_id)
        .execute(pool)
        .await?;
    Ok(())
}

// ============================================================
// event_sessions
// ============================================================

pub async fn insert_session(
    pool: &MySqlPool,
    event_id: i32,
    name: &str,
    event_date: Option<&str>,
    end_date: Option<&str>,
    location: Option<&str>,
    capacity: Option<i32>,
) -> BridgeResult<i32> {
    let result = sqlx::query(
        "INSERT INTO event_sessions (event_id, name, event_date, end_date, location, capacity) \
         VALUES (?, ?, ?, ?, ?, ?)",
    )
    .bind(event_id)
    .bind(name)
    .bind(event_date)
    .bind(end_date)
    .bind(location)
    .bind(capacity)
    .execute(pool)
    .await?;

    Ok(result.last_insert_id() as i32)
}

pub async fn find_sessions_by_event(
    pool: &MySqlPool,
    event_id: i32,
) -> BridgeResult<Vec<EventSession>> {
    Ok(sqlx::query_as::<_, EventSession>(
        "SELECT id, event_id, name, \
         CAST(event_date AS CHAR) as event_date, \
         CAST(end_date AS CHAR) as end_date, \
         location, capacity \
         FROM event_sessions WHERE event_id = ? ORDER BY id",
    )
    .bind(event_id)
    .fetch_all(pool)
    .await?)
}

pub async fn delete_sessions_by_event(pool: &MySqlPool, event_id: i32) -> BridgeResult<()> {
    sqlx::query("DELETE FROM event_sessions WHERE event_id = ?")
        .bind(event_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// 部ごとの承認済み参加者数を返す。
pub async fn count_accepted_per_session(
    pool: &MySqlPool,
    event_id: i32,
) -> BridgeResult<std::collections::HashMap<i32, i32>> {
    let rows = sqlx::query(
        "SELECT session_id, COUNT(*) as cnt \
         FROM event_participants \
         WHERE event_id = ? AND approval = 'accepted' AND session_id IS NOT NULL \
         GROUP BY session_id",
    )
    .bind(event_id)
    .fetch_all(pool)
    .await?;

    let mut map = std::collections::HashMap::new();
    for row in rows {
        let sid: i32 = row.try_get("session_id").unwrap_or(0);
        let cnt: i64 = row.try_get("cnt").unwrap_or(0);
        map.insert(sid, cnt as i32);
    }
    Ok(map)
}

// ============================================================
// event_participants
// ============================================================

pub async fn upsert_participant(
    pool: &MySqlPool,
    event_id: i32,
    user_id: i64,
    response_id: Option<i32>,
    preferred_session_ids: Option<&str>,
    access_token: &str,
) -> BridgeResult<i32> {
    let result = sqlx::query(
        "INSERT INTO event_participants \
         (event_id, user_id, response_id, preferred_session_ids, approval, access_token) \
         VALUES (?, ?, ?, ?, 'pending', ?) \
         ON DUPLICATE KEY UPDATE \
         response_id = VALUES(response_id), \
         preferred_session_ids = VALUES(preferred_session_ids)",
    )
    .bind(event_id)
    .bind(user_id)
    .bind(response_id)
    .bind(preferred_session_ids)
    .bind(access_token)
    .execute(pool)
    .await?;

    Ok(result.last_insert_id() as i32)
}

pub async fn find_participants_by_event(
    pool: &MySqlPool,
    event_id: i32,
) -> BridgeResult<Vec<EventParticipant>> {
    Ok(sqlx::query_as::<_, EventParticipant>(
        "SELECT id, event_id, user_id, response_id, session_id, \
         preferred_session_ids, approval, personal_note, access_token, \
         CAST(notified_at AS CHAR) as notified_at \
         FROM event_participants WHERE event_id = ? ORDER BY id",
    )
    .bind(event_id)
    .fetch_all(pool)
    .await?)
}

pub async fn find_participant_by_token(
    pool: &MySqlPool,
    token: &str,
) -> BridgeResult<EventParticipant> {
    sqlx::query_as::<_, EventParticipant>(
        "SELECT id, event_id, user_id, response_id, session_id, \
         preferred_session_ids, approval, personal_note, access_token, \
         CAST(notified_at AS CHAR) as notified_at \
         FROM event_participants WHERE access_token = ?",
    )
    .bind(token)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| BridgeError::NotFound(format!("token={token}")))
}

pub async fn update_participant_approval(
    pool: &MySqlPool,
    participant_id: i32,
    approval: &str,
    session_id: Option<i32>,
    personal_note: Option<&str>,
) -> BridgeResult<()> {
    sqlx::query(
        "UPDATE event_participants \
         SET approval = ?, session_id = ?, personal_note = COALESCE(?, personal_note) \
         WHERE id = ?",
    )
    .bind(approval)
    .bind(session_id)
    .bind(personal_note)
    .bind(participant_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn mark_notified(pool: &MySqlPool, participant_id: i32) -> BridgeResult<()> {
    sqlx::query(
        "UPDATE event_participants SET notified_at = NOW() WHERE id = ?",
    )
    .bind(participant_id)
    .execute(pool)
    .await?;
    Ok(())
}

// ============================================================
// 自動割り当てロジック
// ============================================================

/// 応募者を希望部優先で自動割り当てする。
/// 1. 「不参加」(preferred_session_ids が null or "[]") → スキップ
/// 2. 第一希望の部に空きあり → accepted
/// 3. 第一希望が満席 → 空きのある別の部へ
/// 4. 全部満席 → waitlist
pub async fn auto_assign(pool: &MySqlPool, event_id: i32) -> BridgeResult<()> {
    let sessions = find_sessions_by_event(pool, event_id).await?;
    let participants = find_participants_by_event(pool, event_id).await?;
    let mut counts = count_accepted_per_session(pool, event_id).await?;

    for p in participants {
        // 既に確定済みはスキップ
        if p.approval == "accepted" || p.approval == "rejected" {
            continue;
        }

        let preferred: Vec<i32> = p
            .preferred_session_ids
            .as_deref()
            .and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default();

        // 不参加（希望なし）
        if preferred.is_empty() {
            continue;
        }

        let mut assigned: Option<i32> = None;

        // 希望順に空き確認
        'outer: for sid in &preferred {
            if let Some(sess) = sessions.iter().find(|s| s.id == *sid) {
                let used = *counts.get(sid).unwrap_or(&0);
                let has_space = sess.capacity.map_or(true, |cap| used < cap);
                if has_space {
                    assigned = Some(*sid);
                    *counts.entry(*sid).or_insert(0) += 1;
                    break 'outer;
                }
            }
        }

        // 希望部が全滅なら空き部を探す（部制あり）
        if assigned.is_none() && !sessions.is_empty() {
            for sess in &sessions {
                let used = *counts.get(&sess.id).unwrap_or(&0);
                let has_space = sess.capacity.map_or(true, |cap| used < cap);
                if has_space {
                    assigned = Some(sess.id);
                    *counts.entry(sess.id).or_insert(0) += 1;
                    break;
                }
            }
        }

        let (approval, sid) = match assigned {
            Some(s) => ("accepted", Some(s)),
            None => ("waitlist", None),
        };

        update_participant_approval(pool, p.id, approval, sid, None).await?;
    }

    Ok(())
}
