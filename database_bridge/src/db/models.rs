// db/models.rs
// Why: すべての DB テーブル対応 Struct をここに集約する。
//      bot/ も webapp/ もこのファイルだけを参照すれば型定義を得られる設計。

use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use time::OffsetDateTime;

// ============================================================
// surveys テーブル
// ============================================================

/// surveys テーブルの 1 行に対応する Struct。
///
/// Why: Python 側では `Dict[str, Any]` として扱っていたが、
///      Rust の型システムを活かしてフィールドを静的に検証する。
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Survey {
    pub id: i64,
    /// Discord User ID。u64 だが DB では VARCHAR 保持のため String で管理。
    pub owner_id: String,
    pub title: String,
    /// JSON 文字列。`parse_questions()` で `Vec<Question>` に変換する。
    pub questions: String,
    pub is_active: bool,
    pub created_at: OffsetDateTime,
}

impl Survey {
    /// `questions` JSON フィールドを型安全にパースする。
    ///
    /// Why: Python では `json.loads()` のエラーを `"?"` で握りつぶしていたが、
    ///      Rust では `Result` で明示的に伝播し、呼び出し側で制御できる。
    pub fn parse_questions(&self) -> Result<Vec<Question>, serde_json::Error> {
        serde_json::from_str(&self.questions)
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
    /// ラジオ・チェックボックスの選択肢。テキスト系は None。
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
    /// JSON 文字列。`parse_answers()` で `HashMap<String, AnswerValue>` に変換する。
    pub answers: String,
    pub submitted_at: OffsetDateTime,
    pub dm_sent: bool,
}

impl SurveyResponse {
    /// `answers` JSON フィールドをパースする。
    pub fn parse_answers(
        &self,
    ) -> Result<std::collections::HashMap<String, AnswerValue>, serde_json::Error> {
        serde_json::from_str(&self.answers)
    }
}

/// answers フィールドの値型。
///
/// Why: Python 側では `str` と `list` が混在していたため、
///      `#[serde(untagged)]` で両方を受け付ける。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum AnswerValue {
    Text(String),
    Choices(Vec<String>),
}

// ============================================================
// operation_logs テーブル
// ============================================================

/// operation_logs テーブルの 1 行に対応する Struct。
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
// 共通エラー型
// ============================================================

/// `database_bridge` 全体で使う統一エラー型。
///
/// Why: Python 側では `try/except + None 返し` だったが、
///      Rust では `Result<T, BridgeError>` で呼び出し元に
///      どのエラーが起きたかを型レベルで伝播する。
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
