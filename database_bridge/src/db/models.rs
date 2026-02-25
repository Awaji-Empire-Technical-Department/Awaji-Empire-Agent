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
    /// DB が bigint(20) のため i64。NULL が紛れ込んでもデコードエラーにならないよう Option で受ける。
    pub user_id: Option<i64>,
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

// ============================================================
// 権限評価 API モデル
// ============================================================

/// `/permissions/evaluate` エンドポイントへのリクエスト。
///
/// Discord のチャンネル名と現在の権限フラグ (allow/deny bitmask) を受け取る。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PermissionEvaluateRequest {
    pub channel_name: String,
    pub current_allow: i64,
    pub current_deny: i64,
}

/// `/permissions/evaluate` エンドポイントからのレスポンス。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PermissionEvaluateResponse {
    pub needs_repair: bool,
    pub target_allow: i64,
    pub target_deny: i64,
    pub reason: Option<String>,
}
