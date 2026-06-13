# ADR-007: 権限エンジンおよびログ統合の Rust 移行

- **日付**: 2026-02-26
- **ステータス**: 承認済み
- **ブランチ**: `feature/phase4-rust-migration`
- **関連仕様書**: [phase4-migration-and-bugfix.md](../Specifications/phase4-migration-and-bugfix.md)
- **前提ADR**: [ADR-005](005-phase3d-survey-response-fix.md), [ADR-006](006-phase3d-mass-mute-self-unblocking.md)

---

## 1. 背景

ADR-005 / ADR-006 にて緊急バグ（アンケート回答取得失敗・権限エラー）を解消した。  
しかし、Python 側にはまだ以下の「DB直接アクセス」が残存していた。

| 残存箇所 | 内容 |
|:---|:---|
| `services/permission_service.py` | 権限チェック結果をDBに書き込んでいた |
| `cogs/*/logic.py` 各所 | ログ記録を `log_service.py` 経由で直接 SQL 実行 |
| 通知メッセージのテンプレート | Python 側でハードコードされていた |

Phase 3 で構築した Rust Bridge（`database_bridge`）が全DB操作の中央ハブとなることが設計目標だったが、上記の箇所がまだ Python から直接 MariaDB に触れていた。

---

## 2. 決定事項

### 2.1 権限エンジンの Rust 移行

**採用案**: Rust Bridge に `permission_repo` を新設し、「期待される権限状態」の定義と差分算出をRust側で一元管理する。Python は HTTP API 経由で差分を受け取り、Discord API の呼び出しのみを担当する。

**不採用案**:

- **Python 内で完結**: DB直接アクセスが残り、Bridge の役割が中途半端になる
- **設定ファイル（TOML/JSON）で外部定義**: 動的な権限変更（大会中の一時制限等）に対応できない

### 2.2 監査ログの完全 Rust 化

**採用案**: Python 側の全 `log_service.py` 呼び出しを、`POST /logs/operation` エンドポイント経由に統一。Python は「何が起きたか」をJSON で Rust に送信し、DB書き込みは Rust が担当する。

**理由**:

- Python コードから SQL 依存をゼロにし、将来の DB 変更影響を Rust 側に閉じ込める
- `log_service.py` が Bridge クライアントの薄いラッパーになることで、テストが容易になる

### 2.3 通知メッセージのテンプレート管理

**採用案**: DM通知の文面テンプレートを `database_bridge` の設定（または DB テーブル）に移動する。Python は API レスポンスで受け取ったテンプレート文字列を Discord に送信するだけとする。

---

## 3. 採用理由（共通）

1. **単一DB窓口**: すべての MariaDB アクセスが Rust Bridge 経由となり、コネクションプールの管理が一箇所に集約される（Proxmox上の物理サーバー負荷軽減）
2. **型安全性**: `sqlx` のコンパイル時クエリ検証により、Python から直書きしていた動的SQLに由来する実行時エラーを根絶
3. **Python コードの純化**: Python は「Discord イベントの受付と API 呼び出し」に専念し、データ操作はすべて Rust に委譲するというアーキテクチャ原則が完成する

---

## 4. 影響

| ファイル | 変更内容 |
|:---|:---|
| `database_bridge/src/db/permission_repo.rs` | 新設。権限定義・差分算出ロジック |
| `database_bridge/src/main.rs` | `GET /permissions/diff`, `POST /logs/operation` エンドポイント追加 |
| `discord_bot/services/permission_service.py` | DB直接呼び出しを Bridge HTTP API 呼び出しに変更 |
| `discord_bot/services/log_service.py` | Bridge HTTP APIラッパーに変更 |

---

## 5. 成功基準

- Python コード内に `aiomysql` / `sqlalchemy` 等のDB直接アクセスが 0 件
- `cargo test` での権限差分算出のユニットテストがパス
- デプロイ後、権限エラーレポートが 0 件で継続
