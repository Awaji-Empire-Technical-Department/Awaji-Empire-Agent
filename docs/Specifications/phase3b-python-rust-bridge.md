# Phase 3-B: Python ↔ Rust ブリッジ方式 設計仕様書

- **ブランチ**: `feature/phase3-rust-bridge`
- **ステータス**: 🔴 精査中（実装未着手）
- **作成日**: 2026-02-23
- **前提**: Phase 3-A（Rust クレートスケルトン）が完了していること
- **関連 ADR**: [ADR-002](../adr/002-phase3-rust-database-bridge.md)（Phase 3-B の方式は別途 ADR-003 で記録予定）

---

## 1. 概要と目的

Phase 3-A で Rust 側の `database_bridge` クレートに DB 操作ロジックのスケルトンを用意した。
Phase 3-B では、**Python（Bot / Webapp）が実際に Rust の関数を呼び出せる状態にする**ことが目的。

### 前提となるプロセス構成

```
現在
┌─────────────────────────────────────────┐
│  discord_bot/ (単一プロセス)             │
│  ├── bot.py (discord.py)                │
│  └── webapp.py (Quart / Hypercorn)      │
│       ↓ いずれも aiomysql で直接 MariaDB接続 │
└─────────────────────────────────────────┘

Phase 3-B 以降
┌─────────────────┐     ブリッジ     ┌──────────────────────┐
│ discord_bot/    │ ←─────────────→ │ database_bridge      │
│ (Python プロセス) │   方式は未定    │ (Rust クレート)       │
└─────────────────┘                  └──────────────────────┘
                                             ↓
                                         MariaDB
```

---

## 2. ブリッジ方式の候補

### 候補 A: PyO3（Rust → Python 拡張モジュール）

Python から `import database_bridge` として直接呼び出す FFI 方式。

```python
# Python 側のイメージ
import database_bridge  # Rust で build した .pyd / .so

async def save():
    response_id = await database_bridge.upsert_response(
        survey_id=1, user_id="123", user_name="foo", answers={...}
    )
```

```rust
// Rust 側（pyo3 使用イメージ）
#[pyfunction]
async fn upsert_response(
    survey_id: i64,
    user_id: &str,
    ...
) -> PyResult<i64> {
    bot::survey_handler::upsert_response(...).await
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
}
```

**メリット**:

- 追加プロセスが不要。Bot / Webapp と同一プロセスで動作
- 関数呼び出しのオーバーヘッドが最小（IPC なし）
- 既存の Python コードの変更量が最小（`from services.survey_service import SurveyService` → `import database_bridge` に差し替えるだけ）

**デメリット**:

- **`async` の扱いが複雑**: PyO3 の async サポートは `pyo3-asyncio` が必要。`asyncio`（Python）と `tokio`（Rust）のランタイム橋渡しに注意が必要
- **ビルド環境の整備が必要**: `maturin` でビルドし、`.pyd`（Windows）/ `.so`（Linux）を生成する CI/CD の追加が必要
- **デプロイパッケージの変更**: バイナリ成果物を `discord_bot/` に配置する仕組みが必要

**主要ライブラリ**:

- `pyo3 = { version = "0.23", features = ["extension-module"] }`
- `pyo3-asyncio` または `pyo3-async-runtimes`
- Python 側: `maturin`（ビルドツール）

---

### 候補 B: Unix Domain Socket / TCP ソケット（IPC）

Rust を独立したバックグラウンドプロセスとして起動し、Python から HTTP または独自バイナリプロトコルで通信する方式。

```
Python (Bot/Webapp)
    ↓ HTTP POST / Unix Socket
Rust database_bridge プロセス（ローカル 127.0.0.1:PORT）
    ↓
MariaDB
```

**メリット**:

- Python / Rust のランタイムが完全分離。`asyncio` と `tokio` のコンフリクトがゼロ
- Rust プロセスのクラッシュが Python プロセスに波及しない（プロセス境界による安全性）
- REST API として設計すれば、将来的に他言語からも呼び出せる

**デメリット**:

- **ネットワーク RTT の追加**: 現在 aiomysql → MariaDB の 1 RTT が、Python → Rust → MariaDB の 2 RTT に増える。ただしその差は通常 < 1ms（ローカル通信）
- **Rust 側に HTTP サーバーが必要**: `axum` や `actix-web` の追加が必要
- **デプロイの複雑化**: Rust バイナリと Python プロセスを別々に起動・管理する必要がある（`systemd` unit を 2 つ用意、または `supervisord`）
- **エラーハンドリングの複雑化**: ネットワークエラーとビジネスロジックエラーを区別する必要がある

**主要ライブラリ（Rust 側への追加）**:

- `axum = "0.8"`
- `tower = "0.5"`

**Python 側の呼び出しイメージ**:

```python
# services/survey_service.py を Bridge 経由の shim に変える
import httpx

BRIDGE_URL = "http://127.0.0.1:7878"  # Rust プロセスのローカルポート

class SurveyService:
    @staticmethod
    async def save_response(pool, survey_id, user_id, user_name, answers):
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BRIDGE_URL}/responses/upsert", json={...})
            return r.json().get("id")
```

---

### 候補 C: gRPC（`tonic`）

Protocol Buffers でインターフェースを定義し、gRPC で通信する方式。

```
Python (Bot/Webapp) → grpc → Rust database_bridge
```

**メリット**:

- `.proto` ファイルがインターフェースの単一の真実（型安全な API 定義）
- Python 側は自動生成されたスタブを使うだけで型補完が効く
- 将来的にマイクロサービス化する際の標準的なアーキテクチャ

**デメリット**:

- **導入コストが最大**: `.proto` ファイルの管理、Python stub 生成（`grpcio-tools`）、Rust 側の `tonic` ビルドと、習得・設定コストが最も高い
- **現スケールには過剰**: Bot + Webapp の DB アクセスという小規模な用途に対してオーバーエンジニアリングの懸念
- **依存が増える**: `grpcio`, `grpcio-tools`, `tonic`, `prost` の追加が必要

**主要ライブラリ**:

- Rust: `tonic`, `prost`
- Python: `grpcio`, `grpcio-tools`

---

## 3. 方式比較表

| 観点 | A: PyO3（FFI） | B: IPC（HTTP） | C: gRPC |
|------|--------------|---------------|---------|
| **導入コスト** | 中（maturin セットアップ） | 低〜中 | 高 |
| **呼び出しオーバーヘッド** | ◎ 最小（同一プロセス） | ○ 小（ローカル） | ○ 小（ローカル） |
| **asyncio / tokio 統合** | △ 要 pyo3-asyncio | ◎ 完全分離 | ◎ 完全分離 |
| **デプロイの変化** | 中（.pyd 配置） | 中（Rust プロセス追加） | 大（proto 管理） |
| **Python コードの変化量** | 少（import 差し替え） | 中（HTTP 呼び出しに変更） | 中（stub 呼び出しに変更） |
| **プロセス分離（安全性）** | ✗ 同一プロセス | ✓ 別プロセス | ✓ 別プロセス |
| **将来の拡張性** | 低（Python 限定） | 中（REST なら汎用） | 高（多言語対応） |
| **現スケールへの適合** | ◎ | ○ | △ 過剰 |

---

## 4. 現環境への影響分析

### Python の変更が必要なファイル（方式共通）

| ファイル | 変更内容 |
|---------|---------|
| `services/survey_service.py` | Rust Bridge 経由の shim（呼び出し先を切り替え） |
| `services/log_service.py` | 同上 |
| `cogs/survey/logic.py` | `initialize_pool` / `close_pool` を削除 |
| `webapp.py` | DB プール生成コードを削除 |
| `pyproject.toml` | `aiomysql`, `mysql-connector-python` を削除（Phase 3-E） |

### 残存する Python 側の責任（方式問わず変わらない）

- Discord API 呼び出し（`discord.py`）
- OAuth2 フロー（`httpx` による Discord API 通信）
- HTML テンプレートレンダリング（Quart / Jinja2）
- セッション管理

---

## 5. 懸念事項・前提確認事項

### 5.1 `asyncio` と `tokio` のランタイム競合（候補 A の場合）

- `discord.py` は `asyncio` ベース、`database_bridge` は `tokio` ベース
- `pyo3-asyncio`（または後継の `pyo3-async-runtimes`）でブリッジ可能だが、バージョン互換に注意
- **確認事項**: `pyo3-asyncio` が Python 3.12 + discord.py 2.x の組み合わせで安定して動作するか

### 5.2 `UNIQUE KEY (survey_id, user_id)` の実在確認

- `bot/survey_handler.rs` の `upsert_response()` は DB に `UNIQUE KEY (survey_id, user_id)` があることを前提とする
- **確認事項**: 現行の MariaDB インスタンスにこのキーが存在するか確認し、なければ migration が必要

### 5.3 `questions` JSON スキーマの確定

- `db/models.rs` の `Question` struct は現在の `form.js` / `form.html` の実装に基づく推測
- **確認事項**: 実際に送受信される JSON の構造を確かめ、enum `QuestionType` の値（`text` / `radio` / `checkbox`）が合っているか

### 5.4 デプロイスクリプトへの影響

- `docs/setup-production.md` に Rust バイナリのビルド・配置ステップを追記する必要がある
- **確認事項**: 本番サーバーに `rustup` / `cargo` がインストール済みか、またはクロスコンパイルで対応するか

---

## 6. 推奨案（未確定・精査待ち）

> ⚠️ この節は Wanyaldee の確認・承認を得てから確定する。

現時点での推奨は **候補 B（IPC / HTTP）**。

**理由**:

1. `asyncio` と `tokio` のランタイム競合を完全回避できる
2. `pyo3-asyncio` の複雑なバージョン管理が不要
3. Python 側のコードは `httpx` という既存依存だけで呼び出せる（`pyproject.toml` に新規ライブラリ追加不要）
4. Rust プロセスのクラッシュが Bot / Webapp に波及しない安全性
5. 将来的に管理 API として外部からアクセスする拡張の余地がある

ただし以下の点を Wanyaldee と確認したい:

- **デプロイの複雑さ許容度**: Rust プロセスを `systemd` 等で別途管理することへの抵抗感
- **レイテンシへの許容度**: ローカル HTTP の追加 RTT（推定 < 1ms）が問題にならないか

---

## 7. 次フェーズの実装スコープ（方式確定後）

### 候補 B（IPC）で進める場合の作業

**Rust 側**:

- `Cargo.toml` に `axum` を追加
- `src/main.rs` を HTTP サーバーとして実装
- 各 handler（`/surveys/...`, `/responses/...`, `/logs/...`）を実装
- エラーレスポンスの JSON 形式を定義

**Python 側**:

- `services/bridge_client.py`（新規）: Rust プロセスへの HTTP クライアント
- `services/survey_service.py`: `bridge_client` 経由の shim に書き換え
- `services/log_service.py`: 同上
- `cogs/survey/logic.py`: `initialize_pool` / `close_pool` を削除

**インフラ**:

- `database_bridge` の `systemd` unit ファイルを作成
- `setup-production.md` を更新

---

## 8. 関連ドキュメント

- [Phase 3-A 仕様書](./phase3-rust-database-bridge.md)
- [ADR-002](../adr/002-phase3-rust-database-bridge.md)
- ADR-003（Phase 3-B 方式確定後に作成予定）
- `tasks/todo.md` — Phase 3-B チェックリスト
