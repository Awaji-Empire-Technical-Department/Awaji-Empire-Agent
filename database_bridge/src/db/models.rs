// db/models.rs
// Why: すべての DB テーブル対応 Struct をここに集約する。
//
// [重要] MariaDB の LONGTEXT / MEDIUMTEXT 型は sqlx が内部的に BLOB として扱うため、
//        Rust 側は Vec<u8> で受け取る必要がある。String を指定すると実行時デコードエラーになる。
//        シリアライズ時は serde_bytes_to_string モジュールで UTF-8 String に変換して出力する。
//
// [重要] MariaDB の DATETIME 型はタイムゾーン情報を持たないため、sqlx の OffsetDateTime は
//        使用不可。CAST(... AS CHAR) で SQL 側で文字列化したものを String で受け取る。

use serde::{Deserialize, Serialize};
use sqlx::FromRow;

// ============================================================
// surveys テーブル
// ============================================================

/// surveys テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Survey {
    pub id: i64,
    pub owner_id: String,
    pub title: String,
    /// DB側が LONGTEXT (sqlx는 BLOB 扱い) のため Vec<u8> で受け取る。
    /// JSON Serialize 時は serde_bytes_to_string で String に変換。
    #[serde(with = "serde_bytes_to_string")]
    pub questions: Vec<u8>,
    pub is_active: bool,
    /// CAST(created_at AS CHAR) で SQL 側で文字列化した値を String で受け取る。
    pub created_at: String,
}

impl Survey {
    /// `questions` JSON フィールドを型安全にパースする。
    pub fn parse_questions(&self) -> Result<Vec<Question>, serde_json::Error> {
        serde_json::from_slice(&self.questions)
    }

    /// 質問数をゼロコスト（エラー時は 0）で返す。
    pub fn question_count(&self) -> usize {
        self.parse_questions().map(|q| q.len()).unwrap_or(0)
    }
}

/// questions フィールド内の個々の質問。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Question {
    pub id: String,
    pub text: String,
    #[serde(rename = "type")]
    pub question_type: QuestionType,
    pub options: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum QuestionType {
    Text,
    Radio,
    Checkbox,
}

// ============================================================
// survey_responses テーブル
// ============================================================

/// survey_responses テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct SurveyResponse {
    pub id: i64,
    pub survey_id: i64,
    /// DB が bigint(20) のため i64。
    pub user_id: i64,
    pub user_name: String,
    /// DB側が LONGTEXT (sqlx は BLOB 扱い) のため Vec<u8> で受け取る。
    #[serde(with = "serde_bytes_to_string")]
    pub answers: Vec<u8>,
    /// CAST(submitted_at AS CHAR) で SQL 側で文字列化した値を String で受け取る。
    pub submitted_at: String,
    pub dm_sent: bool,
}

impl SurveyResponse {
    /// `answers` JSON フィールドをパースする。
    pub fn parse_answers(
        &self,
    ) -> Result<std::collections::HashMap<String, AnswerValue>, serde_json::Error> {
        serde_json::from_slice(&self.answers)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum AnswerValue {
    Text(String),
    Choices(Vec<String>),
}

// ============================================================
// operation_logs テーブル
// ============================================================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct OperationLog {
    pub id: i64,
    pub user_id: String,
    pub user_name: String,
    pub command: String,
    pub detail: String,
    /// CAST(created_at AS CHAR) で SQL 側で文字列化した値を String で受け取る。
    pub created_at: String,
}

// ============================================================
// Serde helpers for Vec<u8> (BLOB/LONGTEXT) <-> String
// ============================================================

mod serde_bytes_to_string {
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S>(bytes: &Vec<u8>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let s = String::from_utf8_lossy(bytes);
        serializer.serialize_str(&s)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Vec<u8>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        Ok(s.into_bytes())
    }
}

// ============================================================
// セキュア対戦ロビーシステム (user_networks, matchmaking_rooms, lobby_members, etc)
// ============================================================

/// user_networks テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct UserNetwork {
    pub discord_id: i64,
    pub email: String,
    pub username: Option<String>,
    pub virtual_ip: Option<String>,
    pub is_active: Option<bool>,
    pub is_staff: Option<bool>,
    /// CAST(agreed_at AS CHAR) で取得
    pub agreed_at: Option<String>,
    /// CAST(updated_at AS CHAR) で取得
    pub updated_at: Option<String>,
}

/// matchmaking_rooms テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LobbyRoom {
    pub passcode: String,
    pub host_id: i64,
    /// 'free' または 'tournament'
    pub mode: Option<String>, 
    pub title: Option<String>,
    pub description: Option<String>,
    /// CAST(tournament_start_at AS CHAR) で取得
    pub tournament_start_at: Option<String>,
    pub is_approved: Option<bool>,
    /// CAST(expires_at AS CHAR) で取得
    pub expires_at: String,
    pub virtual_ip: Option<String>,
    #[sqlx(default)]
    pub gamelink: Option<String>,
}

/// lobby_members テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LobbyMember {
    pub room_passcode: String,
    pub user_id: i64,
    pub username: Option<String>,
    pub virtual_ip: Option<String>,
    #[sqlx(default)]
    pub gamelink: Option<String>,
    pub role: Option<String>,
    pub status: Option<String>,
}

/// tournament_matches テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct TournamentMatch {
    pub match_id: i32,
    pub room_passcode: Option<String>,
    pub player1_id: Option<i64>,
    pub player2_id: Option<i64>,
    pub winner_id: Option<i64>,
    pub status: Option<String>,
    pub round_num: Option<i32>,
    pub match_index: Option<i32>,
    pub next_match_id: Option<i32>,
    pub score1: Option<i32>,
    pub score2: Option<i32>,
    pub win_condition: Option<i32>,
}

/// admin_logs テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct AdminLog {
    pub id: i64,
    pub staff_id: i64,
    pub action: String,
    pub target_id: Option<i64>,
    pub detail: Option<String>,
    /// CAST(created_at AS CHAR) で取得
    pub created_at: Option<String>,
}

// ============================================================
// 汎用大会システム (game_titles, match_scores, point_tables)
// ============================================================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct GameTitle {
    pub id: i32,
    pub name: String,
    pub match_type: String,
    pub max_players: i8,
    pub score_type: String,
    pub is_active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct MatchScore {
    pub id: i64,
    pub match_id: i32,
    pub user_id: i64,
    pub position: i8,
    pub points: i32,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct PointTable {
    pub game_title_id: i32,
    pub position: i8,
    pub points: i32,
}

// ============================================================
// 称号システム (titles, player_titles, player_active_title)
// ============================================================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Title {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub unlock_type: String,
    pub unlock_threshold: Option<i32>,
    pub discord_role_id: Option<String>,
    pub is_active: bool,
    pub display_order: i32,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct PlayerTitle {
    pub id: i64,
    pub user_id: i64,
    pub title_id: i32,
    pub earned_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct PlayerActiveTitle {
    pub user_id: i64,
    pub title_id: i32,
    pub updated_at: String,
}

/// 称号一覧取得用（称号情報 + 獲得済みフラグ）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TitleWithStatus {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub unlock_type: String,
    pub unlock_threshold: Option<i32>,
    pub discord_role_id: Option<String>,
    pub is_active: bool,
    pub display_order: i32,
    pub earned: bool,
    pub is_active_title: bool,
}

// ============================================================
// ラウンジシステム (lounge_*)
// ============================================================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LoungePlayer {
    pub user_id: i64,
    pub mmr: i32,
    pub peak_mmr: i32,
    pub total_races: i32,
    pub total_sessions: i32,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LoungeSession {
    pub id: i64,
    pub room_id: String,
    pub mode: String,
    pub total_races: i8,
    pub current_race: i8,
    pub status: String,
    pub host_id: i64,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LoungeSessionFinalScore {
    pub id: i64,
    pub session_id: i64,
    pub user_id: i64,
    pub final_rank: i8,
    pub mmr_delta: i32,
    pub submitted_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct LoungeTeam {
    pub id: i64,
    pub session_id: i64,
    pub tag: String,
}

// ============================================================
// stream_comment_reset_log テーブル
// ============================================================

/// stream_comment_reset_log テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct ResetLog {
    pub id: u64,
    /// CAST(executed_at AS CHAR) で取得
    pub executed_at: String,
    pub triggered_by: String,
    pub event_type: String,
    pub status: String,
    pub error_message: Option<String>,
}

// ============================================================
// 共通エラー型
// ============================================================

#[derive(Debug, thiserror::Error)]
pub enum BridgeError {
    #[error("Database error: {0}")]
    Sqlx(#[from] sqlx::Error),

    #[error("Record not found: {0}")]
    NotFound(String),

    #[error("Permission denied: owner mismatch")]
    PermissionDenied,

    #[error("JSON parse error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type BridgeResult<T> = Result<T, BridgeError>;

#[cfg(test)]
mod tests {
    use super::*;

    fn make_survey(questions_json: &str) -> Survey {
        Survey {
            id: 1,
            owner_id: "user1".to_string(),
            title: "Test Survey".to_string(),
            questions: questions_json.as_bytes().to_vec(),
            is_active: true,
            created_at: "2026-01-01 00:00:00".to_string(),
        }
    }

    #[test]
    fn test_question_count_valid() {
        let json = r#"[
            {"id":"q1","text":"Q1","type":"text","options":null},
            {"id":"q2","text":"Q2","type":"radio","options":["A","B"]}
        ]"#;
        let survey = make_survey(json);
        assert_eq!(survey.question_count(), 2);
    }

    #[test]
    fn test_question_count_empty() {
        let survey = make_survey("[]");
        assert_eq!(survey.question_count(), 0);
    }

    #[test]
    fn test_question_count_invalid_json_returns_zero() {
        let survey = make_survey("not json");
        assert_eq!(survey.question_count(), 0);
    }

    #[test]
    fn test_parse_questions_types() {
        let json = r#"[
            {"id":"q1","text":"自由記述","type":"text","options":null},
            {"id":"q2","text":"単一選択","type":"radio","options":["A","B"]},
            {"id":"q3","text":"複数選択","type":"checkbox","options":["X","Y"]}
        ]"#;
        let survey = make_survey(json);
        let questions = survey.parse_questions().unwrap();
        assert_eq!(questions[0].question_type, QuestionType::Text);
        assert_eq!(questions[1].question_type, QuestionType::Radio);
        assert_eq!(questions[2].question_type, QuestionType::Checkbox);
    }

    #[test]
    fn test_survey_response_parse_answers() {
        let answers_json = r#"{"q1":"回答テキスト","q2":["選択肢A","選択肢B"]}"#;
        let response = SurveyResponse {
            id: 1,
            survey_id: 1,
            user_id: 123456789,
            user_name: "tester".to_string(),
            answers: answers_json.as_bytes().to_vec(),
            submitted_at: "2026-01-01 00:00:00".to_string(),
            dm_sent: false,
        };
        let answers = response.parse_answers().unwrap();
        assert!(answers.contains_key("q1"));
        assert!(answers.contains_key("q2"));
        match &answers["q2"] {
            AnswerValue::Choices(v) => assert_eq!(v.len(), 2),
            _ => panic!("q2 should be Choices"),
        }
    }
}
