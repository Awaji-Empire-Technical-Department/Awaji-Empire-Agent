# ADR-004: Phase 3-C — BridgeUnavailableError の導入と CSS 分割リファクタリング

- **日付**: 2026-02-24
- **ステータス**: 承認済み (実装完了)
- **ブランチ**: `feature/phase3-rust-bridge`
- **関連仕様書**: [phase3c-deployment-and-verification.md](../Specifications/phase3c-deployment-and-verification.md)

---

## 1. 背景

Phase 3-B にて Python ↔ Rust Bridge (IPC) の通信方式を HTTP-based IPC に決定し、`bridge_client.py` を実装した（ADR-003 参照）。

Phase 3-C では以下 2 点の設計決定が必要となった。

1. **Bridge 停止時のエラー通知方式**: Rust Bridge プロセスが停止した際に、ユーザーがどのようなフィードバックを受けるか。
2. **CSS 管理方式**: `static/style.css` が 452 行に達し、単一ファイル管理の保守コストが問題となってきた。

---

## 2. 決定事項 A — BridgeUnavailableError の導入

### 2.1 検討した選択肢

| 選択肢 | 概要 | 問題点 |
|---|---|---|
| **A-1: `return None` のまま維持** | 既存通り `httpx.RequestError` を捕捉して `None` を返す | route 層が「Bridge 停止」と「API エラー (4xx/5xx)」を区別できない |
| **A-2: グローバルエラーハンドラ** | `@app.errorhandler(503)` で一括対応 | 個別ルートの細かいハンドリングが困難、Quart の制限あり |
| **A-3: 専用例外 `BridgeUnavailableError`** | `httpx.RequestError` 発生時に専用例外を raise し route 層でキャッチ | — |

### 2.2 決定

**A-3: 専用例外 `BridgeUnavailableError`** を採用した。

```python
# services/bridge_client.py
class BridgeUnavailableError(Exception):
    """Bridge プロセスへの接続失敗を示す専用例外"""
    pass

# except 節で raise
except httpx.RequestError as e:
    raise BridgeUnavailableError(...) from e
```

### 2.3 採用理由

1. **判別の明確化**: `None` が「Bridge 停止」を意味するのか「API エラー」を意味するのかが曖昧だった。例外により両者を deterministic に区別できる。
2. **一貫したユーザー体験**: 各 route が `except BridgeUnavailableError` → `maintenance.html` (503) という統一パターンで応答できる。
3. **テスト容易性**: `httpx.RequestError` をモックして `BridgeUnavailableError` の raise を単体テストで確認できる（pytest 7件全 PASS 確認済み）。
4. **`httpx` への依存を service 層に封じ込め**: route 層が `httpx` を直接 import せずに済む。

### 2.4 影響

- `routes/survey.py` の 5 ルートおよび `webapp.py` の `index()` に `except BridgeUnavailableError` を追加。
- `templates/maintenance.html` を新規作成（専用メンテナンスページ）。

---

## 3. 決定事項 B — CSS 分割リファクタリング

### 3.1 問題

`static/style.css` が 452 行の単一ファイルとなり、以下の問題が顕在化した。

- 保守時に関係のないスタイルの把握コストが高い
- `maintenance.html` 専用スタイルをインラインで記述しており、`style.css` との役割が混在

### 3.2 検討した選択肢

| 選択肢 | 概要 | 判断 |
|---|---|---|
| **B-1: 単一ファイル維持** | 現状維持 | 保守性の問題が解決しない |
| **B-2: CSS @import 分割** | `style.css` を @import ファサードにし、`css/` 配下に責任分離 | ✅ 採用 |
| **B-3: CSS Modules / PostCSS** | ビルドツール導入 | 本プロジェクトの規模にはオーバーエンジニアリング |

### 3.3 決定

**B-2: CSS @import 分割** を採用した。

```
static/
├── style.css           ← @import ファサード (テンプレートのリンク先は変更なし)
└── css/
    ├── base.css        — CSS変数・リセット
    ├── layout.css      — ナビバー・コンテナ・カード
    ├── buttons.css     — ボタン系全般
    ├── forms.css       — フォームコントロール
    ├── components.css  — テーブル・バッジ・アラート・チャート
    ├── pages.css       — 認証ページ・送信完了・ユーティリティ
    └── maintenance.css — メンテナンスページ専用
```

### 3.4 採用理由

1. **後方互換性の維持**: テンプレートの `<link rel="stylesheet" href="style.css">` は変更不要。
2. **単一責任の原則**: 各 CSS ファイルが 1 つの役割に対応し、変更箇所がすぐに特定できる。
3. **`maintenance.css` の独立管理**: メンテナンスページ固有の CSS（アニメーション・管理者セクション等）が他のスタイルと混在しなくなった。
4. **ビルドツール不要**: 開発サーバーレベルでは `@import` の実装コストが最小。

### 3.5 影響

- `templates/maintenance.html` のインラインスタイルブロックを削除し、`css/maintenance.css` に移行。
- HTML テンプレート 7 ファイルの変更は**不要**。

---

---

## 4. 決定事項 C — 非対話型デプロイと sudoers 設定

### 4.1 背景
GitHub Actions による自動デプロイ中、`sudo` コマンドがパスワード入力を要求し、CI パイプラインがハングアップする問題が発生した。非対話環境で `sudo` を安全に、且つ確実に実行するための設計が必要となった。

### 4.2 決定
1. **GitHub Runner ユーザー用の sudoers 設定**: `/etc/sudoers.d/deploy` を作成し、デプロイに必要な特定コマンド（`rsync`, `systemctl`, `chown`, `chmod`, `cp`, `env`, `setup-systemd.sh`）を `NOPASSWD` で許可する。
2. **非対話フラグの活用**: `deploy.yml` 内の `sudo` に `-n` (`--non-interactive`) を付与し、パスワードが必要な場合は待機せず即座にエラーを出させることでデバッグ性を向上。
3. **改行コード修正の自動化**: Windows 環境からのデプロイに備え、スクリプト実行前に `sed -i 's/\r$//'` による CRLF → LF 変換を行うステップを導入。

### 4.3 採用理由
1. **セキュリティの最小権限原則**: `ALL=(ALL) ALL` を避け、デプロイに必要なコマンドのみに限定することでリスクを最小化。
2. **実行パスの完全一致**: `sudoers` には `/usr/bin/systemctl` 等の絶対パスを記述し、実行時もパスを意識することで不一致によるブロックを回避。
3. **環境耐性**: 改行コード修正をパイプラインに組み込むことで、開発者の OS 環境に依存しない堅牢なデプロイを実現。

---

## 5. 結論

Phase 3-C では「エラー通知の明確化」「CSS の保守性向上」に加え、「完全自動化された非対話デプロイフロー」を確立した。これにより、Phase 4 以降の頻繁な Rust コード更新に対しても、手動介入なしで安全に本番・テスト環境を最新化できる基盤が整った。
