# Phase 3: Rust Database Bridge 設計仕様書

- **ブランチ**: `feature/phase3-rust-bridge`
- **ステータス**: 🟡 設計中
- **作成日**: 2026-02-23
- **対象クレート**: `database_bridge/`

---

## 1. 概要

### 1.1 目的

現行の Python（aiomysql / mysql-connector）による DB 操作ロジックを、`database_bridge` Rust クレートへ段階的に移譲する。

| 観点 | 現状（Python） | 目標（Rust） |
|------|---------------|-------------|
| 型安全性 | 辞書型（`Dict[str, Any]`）が主流。実行時エラーのリスクあり | `struct` による静的型付け。コンパイル時に構造の誤りを検出 |
| パフォーマンス | GIL の影響。非同期だが CPython 依存 | tokio による真のノンブロッキング I/O、GIL なし |
| 接続管理 | `SurveyLogic` や `webapp.py` がそれぞれ個別にプールを生成 | `sqlx::Pool` を一元管理し、Bot・Webapp の両方から参照 |
| エラー処理 | `try/except` + `logger.error` + `None` 返し | `Result<T, E>` による明示的なエラー伝播、パニック不使用 |

### 1.2 移行の対象ファイル（Python 側）

| ファイル | 現在の役割 | Rust 移譲先 |
|---------|-----------|------------|
| `services/database.py` | SQLAlchemy engine 生成（現在は未使用に近い） | `db/connection.rs` |
| `services/survey_service.py` | アンケート CRUD | `db/survey_repo.rs` + `bot/survey_handler.rs` |
| `services/log_service.py` | 操作ログ INSERT | `db/log_repo.rs` |
| `webapp.py` (index route) | ダッシュボード用 SELECT | `webapp/dashboard_query.rs` |
| `cogs/survey/logic.py` (pool管理部) | DB プール初期化・終了 | `db/connection.rs` に統合 |
| `bot.py` (get_db_connection) | 同期 mysql.connector（起動時テストのみ） | `db/connection.rs` の `health_check()` |

---

## 2. ターゲット構造（`database_bridge/src/`）

```
database_bridge/
├── Cargo.toml
└── src/
    ├── main.rs              # CLI エントリ（将来的な管理ツール用）
    ├── lib.rs               # crate root（PyO3 or FFI エクスポート用）
    │
    ├── db/                  ★ Core Data Access Layer
    │   ├── mod.rs
    │   ├── connection.rs    # Pool 生成・管理・ヘルスチェック
    │   ├── models.rs        # すべての Struct 定義（テーブル対応）
    │   ├── survey_repo.rs   # surveys テーブル CRUD
    │   ├── response_repo.rs # survey_responses テーブル CRUD
    │   └── log_repo.rs      # operation_logs テーブル INSERT
    │
    ├── bot/                 ★ Bot Logic Layer
    │   ├── mod.rs
    │   └── survey_handler.rs # Bot 固有ロジック（UPSERT、DM フラグ等）
    │
    └── webapp/              ★ Webapp Logic Layer
        ├── mod.rs
        └── dashboard_query.rs # ダッシュボード集計・権限照合クエリ
```

---

## 3. A. 関数の振り分け（Python → Rust マッピング）

### 3.1 `db/` へ移譲（アプリ非依存の純粋な CRUD）

| Python 関数 (survey_service.py) | Rust 関数 | 備考 |
|---------------------------------|-----------|------|
| `SurveyService.create_survey()` | `survey_repo::insert()` | |
| `SurveyService.get_survey()` | `survey_repo::find_by_id()` | |
| `SurveyService.get_surveys_by_owner()` | `survey_repo::find_by_owner()` | `active_only` は `Option<bool>` |
| `SurveyService.get_active_surveys()` | `survey_repo::find_active()` | |
| `SurveyService.update_survey()` | `survey_repo::update()` | |
| `SurveyService.delete_survey()` | `survey_repo::delete()` | owner 照合は Rust 層で実施 |
| `SurveyService.get_owner_id()` | `survey_repo::get_owner_id()` | |
| `SurveyService.get_responses()` | `response_repo::find_by_survey()` | |
| `SurveyService.get_existing_answers()` | `response_repo::find_answers_by_user()` | |
| `SurveyService.mark_dm_sent()` | `response_repo::mark_dm_sent()` | |
| `LogService.log_operation()` | `log_repo::insert()` | |
| `database.py::_build_database_url()` | `connection::build_url()` (private fn) | |
| `database.py::get_engine()` | `connection::get_pool()` | |
| `bot.py::get_db_connection()` | `connection::health_check()` | 同期→非同期へ変換 |

### 3.2 `bot/` へ移譲（Bot 固有ロジック）

| Python 関数 | Rust 関数 | 備考 |
|------------|-----------|------|
| `SurveyService.save_response()` | `bot::survey_handler::upsert_response()` | SELECT→分岐→INSERT/UPDATE の複合ロジックを含む Bot 特有処理 |
| `SurveyService.toggle_status()` | `bot::survey_handler::toggle_status()` | owner_id 照合付きステータス切替 |

### 3.3 `webapp/` へ移譲（Webapp 固有ロジック）

| Python 関数/ルート | Rust 関数 | 備考 |
|------------------|-----------|------|
| `webapp.py::index()` 内の `SELECT surveys` | `webapp::dashboard_query::fetch_user_surveys()` | OAuth ユーザー ID でフィルタ |
| `webapp.py::index()` 内の `SELECT operation_logs` | `webapp::dashboard_query::fetch_recent_logs()` | LIMIT 付き |
| `webapp.py::callback()` のギルド照合ロジック | `webapp::dashboard_query::verify_guild_membership()` | Discord API 呼び出しは Python 側残留、DB 権限照合のみ移譲 |

---

## 4. B. Rust Struct 定義案

```rust
// db/models.rs

use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use time::OffsetDateTime;

/// surveys テーブル対応
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Survey {
    pub id: i64,
    pub owner_id: String,        // Discord User ID（u64 だが文字列で保持）
    pub title: String,
    pub questions: String,       // JSON 文字列（Vec<Question> にデシリアライズ可能）
    pub is_active: bool,
    pub created_at: OffsetDateTime,
}

/// questions フィールドの内側の構造体（JSON デシリアライズ用）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Question {
    pub id: String,              // "q1", "q2" 等
    pub text: String,
    pub question_type: QuestionType,
    pub options: Option<Vec<String>>,  // 選択肢（ラジオ等）
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum QuestionType {
    Text,
    Radio,
    Checkbox,
}

/// survey_responses テーブル対応
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct SurveyResponse {
    pub id: i64,
    pub survey_id: i64,
    pub user_id: String,
    pub user_name: String,
    pub answers: String,         // JSON 文字列（HashMap<String, AnswerValue> にデシリアライズ可能）
    pub submitted_at: OffsetDateTime,
    pub dm_sent: bool,
}

/// answers フィールドの値型
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum AnswerValue {
    Text(String),
    Choices(Vec<String>),
}

/// operation_logs テーブル対応
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct OperationLog {
    pub id: i64,
    pub user_id: String,
    pub user_name: String,
    pub command: String,
    pub detail: String,
    pub created_at: OffsetDateTime,
}

/// DB 操作の汎用エラー型
#[derive(Debug, thiserror::Error)]
pub enum BridgeError {
    #[error("Database error: {0}")]
    Sqlx(#[from] sqlx::Error),
    #[error("Not found: {0}")]
    NotFound(String),
    #[error("Permission denied: owner mismatch")]
    PermissionDenied,
    #[error("JSON parse error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type BridgeResult<T> = Result<T, BridgeError>;
```

---

## 5. C. ロジック最適化案

### 5.1 `save_response()` → `upsert_response()` の改善

**現行 Python の問題点**:

```python
# SELECT → fetchone → if 分岐 → UPDATE/INSERT の 2 RTT
await cur.execute("SELECT id FROM survey_responses WHERE ...")
existing_row = await cur.fetchone()
if existing_row:
    await cur.execute("UPDATE ...")
else:
    await cur.execute("INSERT ...")
```

**Rust での改善案（1 RTT に削減）**:

```rust
// MariaDB の INSERT ... ON DUPLICATE KEY UPDATE を活用
// UNIQUE KEY (survey_id, user_id) が前提
pub async fn upsert_response(
    pool: &Pool<MySql>,
    req: &UpsertResponseRequest,
) -> BridgeResult<i64> {
    let answers_json = serde_json::to_string(&req.answers)?;
    
    let result = sqlx::query!(
        r#"
        INSERT INTO survey_responses
            (survey_id, user_id, user_name, answers, submitted_at, dm_sent)
        VALUES (?, ?, ?, ?, NOW(), FALSE)
        ON DUPLICATE KEY UPDATE
            answers = VALUES(answers),
            submitted_at = NOW(),
            dm_sent = FALSE
        "#,
        req.survey_id,
        req.user_id,
        req.user_name,
        answers_json,
    )
    .execute(pool)
    .await?;
    
    Ok(result.last_insert_id() as i64)
}
```

### 5.2 `fetch_recent_logs()` の並列集計

**webapp.py のダッシュボードクエリ（現行：直列 2 クエリ）**:

```python
await cur.execute("SELECT * FROM surveys WHERE owner_id = %s ...")
surveys = await cur.fetchall()
await cur.execute("SELECT * FROM operation_logs ORDER BY ... LIMIT 30")
logs = await cur.fetchall()
```

**Rust での改善案（`tokio::try_join!` による並列実行）**:

```rust
pub async fn fetch_dashboard_data(
    pool: &Pool<MySql>,
    owner_id: &str,
) -> BridgeResult<DashboardData> {
    // 2 クエリを同時発行 → 合計レイテンシを最大クエリの時間まで短縮
    let (surveys, logs) = tokio::try_join!(
        survey_repo::find_by_owner(pool, owner_id, None),
        log_repo::find_recent(pool, 30),
    )?;
    
    Ok(DashboardData { surveys, logs })
}
```

### 5.3 `get_active_surveys()` / `build_list_response()` の JSON パース

**現行 Python の問題点**:

```python
# for ループの中で毎回 json.loads()。エラーは "?" に握りつぶし
q_count = len(json.loads(s['questions']))
```

**Rust での改善案**:

```rust
impl Survey {
    /// questions フィールドを型安全にパース
    pub fn parse_questions(&self) -> BridgeResult<Vec<Question>> {
        serde_json::from_str(&self.questions).map_err(BridgeError::Json)
    }
    
    pub fn question_count(&self) -> usize {
        self.parse_questions().map(|q| q.len()).unwrap_or(0)
    }
}
```

---

## 6. D. モジュール依存関係（`mod` 構成）

```
lib.rs
 ├── mod db;          ← 外部から使える公開 API（Repo 関数群）
 │    ├── connection  ← Pool 生成・管理（他モジュールはこれを参照）
 │    ├── models      ← Struct 定義（全モジュールがインポート）
 │    ├── survey_repo
 │    ├── response_repo
 │    └── log_repo
 │
 ├── mod bot;         ← db::* を参照、他への依存なし
 │    └── survey_handler  → db::survey_repo, db::response_repo
 │
 └── mod webapp;      ← db::* を参照、bot には依存しない
      └── dashboard_query → db::survey_repo, db::log_repo
```

**方針**:

- `bot` と `webapp` は **互いに依存しない**（循環依存を防ぐ）。
- 共有したいロジックが生まれた場合は `db/` に落とし込む。
- `db/` は Discord にも Quart にも依存しない純粋な Rust コードのみ。

---

## 7. `Cargo.toml` 更新案

```toml
[package]
name = "database_bridge"
version = "0.3.0"
edition = "2021"

[dependencies]
# 非同期ランタイム
tokio = { version = "1", features = ["full"] }

# DB（MariaDB/MySQL 対応に変更: postgres → mysql）
sqlx = { version = "0.8", features = [
    "runtime-tokio",
    "tls-rustls",
    "mysql",        # ← postgres から変更
    "macros",
    "time",         # ← OffsetDateTime サポート
] }

# シリアライズ
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# 環境変数
dotenvy = "0.15"

# エラー定義
thiserror = "1.0"

# ロギング
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
```

> ⚠️ **重要**: 現行 `Cargo.toml` は `postgres` feature が指定されているが、
> プロジェクトの DB は **MariaDB** のため `mysql` へ変更が必須。

---

## 8. Python 側の段階的移行計画

| フェーズ | 内容 | Python 側の変化 |
|---------|------|----------------|
| **3-A** | `database_bridge` に `db/` 層を実装（Struct + CRUD） | 変化なし（Rust は独立稼働） |
| **3-B** | PyO3 または HTTP/IPC ブリッジ経由で Python から呼び出す | `survey_service.py` が Rust を呼び出す shim に変わる |
| **3-C** | `bot/` 層実装（`upsert_response`, `toggle_status`） | Bot 側の直接 DB 呼び出しを廃止 |
| **3-D** | `webapp/` 層実装（ダッシュボード集計） | `webapp.py` の直 SQL を廃止 |
| **3-E** | Python 側の `aiomysql` 依存を完全削除 | `requirements.txt` から削除 |

---

## 9. 懸念点・注意点

### 9.1 MariaDB 固有の挙動

- `ON DUPLICATE KEY UPDATE` は MariaDB/MySQL 方言。`sqlx` の `query!` マクロはコンパイル時 DB 接続検証が必要なため、CI 環境に MariaDB を立てること。

### 9.2 `questions` フィールドの JSON スキーマ未確定

- 現行 Python は `json.dumps(list)` で格納しているが、リスト内の要素構造がコードから完全に読み取れない。
- **アクション**: `form.html` や `form.js` の実装を確認し、`Question` struct の型を確定させること。

### 9.3 `user_id` の型（String vs u64）

- Discord の User ID は 64 bit 整数だが、Python 側は文字列として扱っている。
- Rust では `String` のまま保持し、必要に応じて `u64::from_str()` で変換する設計を推奨（DB スキーマに合わせる）。

### 9.4 接続プールの共有方法（3-B フェーズ以降）

- Bot（tokio runtime）と Webapp（Quart/uvloop）が同一プロセスではないため、プール共有には **Unix Socket IPC** または **gRPC** が候補。
- Phase 3-A では Rust クレートを **単独バイナリ CLI** として動作させ、IPC 方式は Phase 3-B で決定する。

---

## 10. 関連ドキュメント

- `docs/Specifications/phase2-architecture-refactoring.md`（前フェーズ仕様）
- `database_bridge/Cargo.toml`
- `discord_bot/services/survey_service.py`（移行元）
- `discord_bot/services/log_service.py`（移行元）
- `discord_bot/webapp.py`（移行元）
