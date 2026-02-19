# [Phase 2] アーキテクチャ刷新・モジュール分離仕様書

## 1. 概要

本リファクタリングの目的は、肥大化したコードを解体し、将来的な Rust への移行を容易にするための「境界線」を定義することです。

## 2. ディレクトリ再配置方針

| 元のファイル | 配置先 | 理由 |
| :--- | :--- | :--- |
| `database.py` | `services/database.py` | DB操作は副作用の塊であり、Rust移行の最優先箇所。 |
| `utils.py` (DB操作有) | `services/utils.py` | `log_operation` 等は I/O を伴うため。 |
| `utils.py` (純粋関数) | `common/utils.py` | 依存関係をクリーンに保つため。 |
| `filter.py` | **削除** | 不要な機能の整理。 |
| `survey.py` | `routes/` & `services/` | 400行のロジックを Web 側から分離。 |

## 3. 実装のモデルケース

`cogs/voice_keeper` の構成をベースとしますが、内部の DB 操作や API 通信については `services/` の関数を呼び出す形にリファクタリングしてください。

## 4. 依存ルール

1. `Interface (cogs/routes)` -> `Services` -> `Common` の順で依存する。
2. `Services` 層は `discord.ext.commands.Context` を受け取らない。
