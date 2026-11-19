# ADR 031–040: 保守・セキュリティ整備

このディレクトリには、リポジトリの保守・セキュリティ整備に関する Architecture Decision Record が収録されています。

## 一覧

| No. | タイトル | ステータス | 日付 |
|-----|---------|-----------|------|
| [ADR-031](031-remove-token-txt-and-unused-files.md) | token.txt フォールバックの全廃と不要ファイルの削除 | 採用 | 2026-11-01 |
| [ADR-032](032-webapp-oauth-state-ws-auth-cors-bridge-user.md) | Webapp の OAuth state 検証・WebSocket 認証・CORS 撤去と database_bridge の非 root 化 | 採用 | 2026-11-01 |
| [ADR-033](033-production-nginx-update-1-30.md) | 本番 VM の nginx 更新（nginx 1.30.x の脆弱性修正への追随） | 採用 | 2026-11-19 |

## 概要

- **ADR-031**: `routes/lobby.py`・`routes/tournament.py` が `token.txt` のみを読んでいた ADR-023 の移行漏れを修正し、Bot トークンの取得元を `DISCORD_TOKEN` に統一。未使用の `config.py.example`・`main.py`・`db_repair.py` 等を削除し、`.env.example` のギルド ID キーを `DISCORD_GUILD_ID` に修正。
- **ADR-032**: ログイン CSRF 対策として OAuth2 `state` を検証。`/ws/hyouibana` を未ログインなら 401 で拒否。不要な `cors(allow_origin="*")` と `quart-cors` 依存を削除。`database_bridge.service` を `User=devuser` に変更。
- **ADR-033**: nginx 1.30.x の脆弱性修正（1.30.7 など）を受けて本番 VM の nginx を更新した。更新後は nginx.org の `conf.d/` しか読まず、リポジトリの設定（`sites-enabled` 前提）が読み込まれておらず、本番の nginx は経路外だった可能性が高いことが判明（`deploy.sh` との食い違いは未解決）。1.24.0（Ubuntu 標準）から 1.30.7（nginx.org stable）へ配布元ごと切り替えた。
