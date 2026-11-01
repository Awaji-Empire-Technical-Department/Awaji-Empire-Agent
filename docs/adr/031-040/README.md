# ADR 031–040: 保守・セキュリティ整備

このディレクトリには、リポジトリの保守・セキュリティ整備に関する Architecture Decision Record が収録されています。

## 一覧

| No. | タイトル | ステータス | 日付 |
|-----|---------|-----------|------|
| [ADR-031](031-remove-token-txt-and-unused-files.md) | token.txt フォールバックの全廃と不要ファイルの削除 | 採用 | 2026-11-01 |

## 概要

- **ADR-031**: `routes/lobby.py`・`routes/tournament.py` が `token.txt` のみを読んでいた ADR-023 の移行漏れを修正し、Bot トークンの取得元を `DISCORD_TOKEN` に統一。未使用の `config.py.example`・`main.py`・`db_repair.py` 等を削除し、`.env.example` のギルド ID キーを `DISCORD_GUILD_ID` に修正。
