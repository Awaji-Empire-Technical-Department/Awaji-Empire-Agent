// db/models.rs
// Why: すべての DB テーブル対応 Struct をここに集約する。
//      MariaDB の JSON 型が BLOB として返される場合があるため、
//      questions/answers カラムを Vec<u8> で受け取り、
//      アプリケーション層で String に変換する設計に変更。

use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use sqlx::types::time::OffsetDateTime;

// ============================================================
// Helper functions for BLOB to String conversion
// ============================================================

fn blob_to_string(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

// ============================================================
// surveys テーブル
// ============================================================

/// surveys テーブルの 1 行に対応する Struct。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Survey {
    pub id: i64,
    pub owner_id: String,
    pub title: String,
    /// JSON 文字列。DB側が BLOB(LONGBLOB) のため Vec<u8> で受け取る。
    /// Serialize 時には String に変換して出力する。
    #[serde(with = "serde_bytes_to_string")]
    pub questions: Vec<u8>,
    pub is_active: bool,
    pub created_at: OffsetDateTime,
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
    pub user_id: String,
    pub user_name: String,
    /// JSON 文字列。DB側が BLOB のため Vec<u8> で受け取る。
    #[serde(with = "serde_bytes_to_string")]
    pub answers: Vec<u8>,
    pub submitted_at: OffsetDateTime,
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
    pub created_at: OffsetDateTime,
}

// ============================================================
// Serde helpers for Vec<u8> (BLOB) <-> String
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
