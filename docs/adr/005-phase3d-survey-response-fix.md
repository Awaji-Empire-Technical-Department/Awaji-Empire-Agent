# ADR-005: Phase 3-D — Rust Bridge 型不一致の修正と survey_responses UNIQUE KEY 追加

- **日付**: 2026-02-25（更新: 2026-02-25）
- **ステータス**: 承認済み (Phase 3-E 追加修正済み)
- **ブランチ**: `feature/phase3d-hotfix`
- **関連仕様書**: [phase3d-hotfix-survey-and-massmute.md](../Specifications/phase3d-hotfix-survey-and-massmute.md)

---

## 1. 背景

Phase 3-C 完了後のテスト環境稼働中に、以下の 3 つの不具合が発覚した。

1. **アンケート一覧が空になる**: 管理画面でアンケートが「まだありません」と表示される。
2. **回答取得で 500 エラー**: `GET /surveys/{id}/responses` が `Internal Server Error` を返す。
3. **再回答が上書きされずに追加される**: 同一ユーザーが回答し直すと、既存レコードが更新されず新規追加される。

SSH でテスト環境に入り調査した結果、以下の 3 つの根本原因が特定された。

---

## 2. 根本原因

### 原因 A — MariaDB LONGTEXT を String で受け取ろうとした

`sqlx` は MariaDB の `LONGTEXT` / `MEDIUMTEXT` を内部的に **BLOB** として扱う。
フィールドの型を `String` で定義すると、実行時に以下のエラーが発生し行全体がデコードされない。

```
error occurred while decoding column "questions":
mismatched types; Rust type 'alloc::string::String' (as SQL type 'VARCHAR')
is not compatible with SQL type 'BLOB'
```

### 原因 B — MariaDB DATETIME を OffsetDateTime で受け取ろうとした

MariaDB の `DATETIME` 型はタイムゾーン情報を持たない。`sqlx` の `OffsetDateTime`（タイムゾーン必須）にマッピングしようとすると実行時デコードエラーになる。

### 原因 C — survey_responses に UNIQUE KEY が存在しなかった

`ON DUPLICATE KEY UPDATE` 文は `(survey_id, user_id)` の UNIQUE KEY がなければ機能しない。
スキーマ設計時に UNIQUE KEY が定義されておらず、同一ユーザーの再回答が常に新規 INSERT されていた。

---

## 3. 決定事項

### 3.1 LONGTEXT カラムの受け取り型

| 選択肢 | 採否 | 理由 |
|---|---|---|
| `String` のまま | ❌ | BLOB として扱われるためデコードエラー |
| `Vec<u8>` + serde_bytes_to_string ヘルパー | ✅ 採用 | BLOB を正しく受け取り、JSON 出力時は UTF-8 文字列に変換 |

#### 採用理由

- `Vec<u8>` は `sqlx` の BLOB マッピングと完全に互換。
- `serde_bytes_to_string` モジュールにより、JSON レスポンスでは `String` として出力できる。
- Python 側への影響なし（JSON 文字列として透過的に渡される）。

#### 実装

```rust
// models.rs
#[serde(with = "serde_bytes_to_string")]
pub questions: Vec<u8>,
```

### 3.2 DATETIME カラムの受け取り型

| 選択肢 | 採否 | 理由 |
|---|---|---|
| `OffsetDateTime` + `time::serde::rfc3339` | ❌ | TZ なし DATETIME と非互換、実行時エラー |
| `time::PrimitiveDateTime` | △ | デコードは可能だが serde 連携が複雑 |
| SQL 側で `CAST(created_at AS CHAR)` + Rust 側で `String` | ✅ 採用 | 確実・シンプル・Python 側への影響なし |

#### 採用理由

1. **確実性**: SQL の `CAST` は DB レベルで保証されるため、`sqlx` の型マッパーに依存しない。
2. **シンプルさ**: Rust 側で型変換ロジックが不要。
3. **後方互換**: Python 側は日時を文字列として受け取っており、フォーマット変更は不要。

#### 実装

```rust
// survey_repo.rs — SELECT * の廃止と CAST の導入
const SELECT_COLUMNS: &str =
    "id, owner_id, title, questions, is_active, CAST(created_at AS CHAR) as created_at";
```

#### 禁止事項

> `OffsetDateTime` および `time::serde::rfc3339` は **全ての DB モデルで使用禁止**とする。
> `Cargo.toml` の `time = { features = ["serde"] }` もコメントアウト済み。

### 3.3 survey_responses.user_id の型

| DB 型 | 旧 Rust 型 | 新 Rust 型 | 理由 |
|---|---|---|---|
| `bigint(20)` | `String` | `i64` | 数値型カラムを文字列で受け取ろうとしてデコードエラー |

Python 側から渡される `user_id` は Discord の Snowflake ID（文字列）のため、
`survey_handler.rs` の UPSERT 関数で `parse::<i64>()` によりパースしてから bind する。

### 3.4 survey_responses UNIQUE KEY の追加

`ON DUPLICATE KEY UPDATE` の正しい動作のために `(survey_id, user_id)` への UNIQUE KEY を追加する。

```sql
ALTER TABLE survey_responses
  ADD UNIQUE KEY unique_survey_user (survey_id, user_id);
```

> **この DDL はコードに含まれない手動作業**である。テスト環境・本番環境それぞれで実施が必要。
> 詳細手順は `docs/Specifications/setup-production.md § 6` を参照。

---

## 4. 影響範囲

| ファイル | 変更内容 |
|---|---|
| `database_bridge/src/db/models.rs` | `questions/answers` → `Vec<u8>`、`user_id` → `i64`、datetime → `String` |
| `database_bridge/src/db/survey_repo.rs` | `SELECT *` 廃止、`CAST` 導入、`owner_id="ALL"` 全取得対応 |
| `database_bridge/src/db/response_repo.rs` | `SELECT *` 廃止、`CAST` 導入、`user_id` を `i64` で bind |
| `database_bridge/src/db/log_repo.rs` | `SELECT *` 廃止、`CAST` 導入 |
| `database_bridge/src/db/connection.rs` | 接続 URL に `?charset=utf8mb4` 追加 |
| `database_bridge/src/bot/survey_handler.rs` | `user_id` を `i64` にパースして bind |
| `database_bridge/src/api/handlers.rs` | `get_user_answers` を `s.answers` (Vec<u8>) → `from_slice` に修正 |
| `database_bridge/Cargo.toml` | `time = { features = ["serde"] }` をコメントアウト |

---

## 5. Phase 3-E — 追加修正（2026-02-25）

### 背景

本番環境稼働中に `survey_responses.user_id` が `NULL` のレコードが混入し、
`GET /surveys/{id}/responses` が 500 エラーを返す不具合が発生した。

エラー: `error occurred while decoding column "user_id": unexpected null; try decoding as an 'Option'`

### 対処

1. **即時対応（本番 DB 手動）**: `DELETE FROM survey_responses WHERE user_id IS NULL;` を実行。
2. **防御的コード修正**: `SurveyResponse.user_id` の型を `i64` → `Option<i64>` に変更。
   - 今後 NULL が混入してもデコードエラーにならない。
   - `response_repo.rs` / `survey_handler.rs` の bind は `i64` 直接渡しのため変更不要。
   - JSON レスポンスでは `null` または数値として serde が自動変換。

---

## 6. 学んだ教訓

1. **sqlx の型マッピングは直感と異なる場合がある**: `LONGTEXT` → `BLOB`、`DATETIME` → `OffsetDateTime` 非互換。実際の DB スキーマ (`DESCRIBE`) と sqlx のドキュメントを照合することが必須。
2. **`SELECT *` はデバッグを困難にする**: カラムを明示することで型不一致の特定が容易になる。
3. **UNIQUE KEY などの制約はスキーマ定義時に必ず確認する**: アプリのロジック（`ON DUPLICATE KEY UPDATE`）が制約を前提にしている場合、制約がないと silent に誤動作する。
4. **テスト環境での徹底調査が本番保護になる**: 今回の全不具合がテスト環境で発見・修正されたことで、本番環境への影響ゼロを維持できた。
5. **nullable カラムは常に `Option<T>` で受ける**: DB スキーマで `NOT NULL` が明示されていないカラムは、将来の NULL 混入に備えて `Option` にしておく。
