# ADR 031–040: 保守・セキュリティ整備

このディレクトリには、リポジトリの保守・セキュリティ整備に関する Architecture Decision Record が収録されています。

## 一覧

| No. | タイトル | ステータス | 日付 |
|-----|---------|-----------|------|
| [ADR-031](031-remove-token-txt-and-unused-files.md) | token.txt フォールバックの全廃と不要ファイルの削除 | 採用 | 2026-11-01 |
| [ADR-032](032-webapp-oauth-state-ws-auth-cors-bridge-user.md) | Webapp の OAuth state 検証・WebSocket 認証・CORS 撤去と database_bridge の非 root 化 | 採用 | 2026-11-01 |
| [ADR-033](033-zabbix-monitoring-introduction.md) | Zabbix による監視基盤の導入（構成・DB・公開方法） | 提案中 | 2026-11-05 |

## 概要

- **ADR-031**: `routes/lobby.py`・`routes/tournament.py` が `token.txt` のみを読んでいた ADR-023 の移行漏れを修正し、Bot トークンの取得元を `DISCORD_TOKEN` に統一。未使用の `config.py.example`・`main.py`・`db_repair.py` 等を削除し、`.env.example` のギルド ID キーを `DISCORD_GUILD_ID` に修正。
- **ADR-032**: ログイン CSRF 対策として OAuth2 `state` を検証。`/ws/hyouibana` を未ログインなら 401 で拒否。不要な `cors(allow_origin="*")` と `quart-cors` 依存を削除。`database_bridge.service` を `User=devuser` に変更。
- **ADR-033**（下書き）: INC-001 を受け、「前提の崩れ」を監視するために Zabbix を導入する。Proxmox 上の専用の非特権 LXC に、Zabbix 専用の MariaDB を同居させる。Web UI は LAN 内のみ。エージェントは PSK で暗号化。Grafana は残し、通知は Zabbix に一本化。Zabbix のバージョン（7.0 / 8.0 LTS）は未決。詳細は [docs/monitoring/](../../monitoring/README.md)。
