# 🤖 Awaji Empire Agent

淡路帝国のコミュニティ運営を支える、多機能 Discord Bot & 管理ダッシュボードプラットフォーム。

## 🌟 プロジェクトの概要

本プロジェクトは、Discord Bot (`discord.py`) と Web ダッシュボード (`Quart`) を MariaDB で統合した、コミュニティ管理システムです。
単なる Bot ではなく、インフラ（Proxmox / Cloudflare Tunnel）からフロントエンドまでを一貫して内製しており、高度な柔軟性とセキュリティを両立しています。

## 💡 設計思想 — なぜ Web アプリにこだわるのか

Discord Bot 単体では、機能のすべてが Discord の API 制限・仕様変更に縛られ、「API がサポートしていない＝実装不可能」という壁に常にぶつかります。
本プロジェクトは **Discord を「入口」、Web アプリを「本体」** と位置づけ、自由度が必要な処理を自前インフラ側へ逃がすことで、その壁を「不可能」ではなく「設計の問題」に置き換えています。つまり **自由度＝主導権** をこちら側に保つことが中核の方針です。

> [!IMPORTANT]
> 設計の背景と Discord・Web アプリ・ユーザーの関係図は [DESIGN_PHILOSOPHY_WEBAPP.md](./docs/DESIGN_PHILOSOPHY_WEBAPP.md) を参照してください。

## 🚀 主要機能

本システムは主に 6 つのコア機能を提供します。

| 機能 | 概要 | 詳細ドキュメント |
| :--- | :--- | :--- |
| **通知マスミュート** | 大規模サーバーの通知騒音を防ぐ権限自動管理 | [詳細はこちら](./docs/features/FEATURE_MASS_MUTE.md) |
| **内製アンケート** | Webで作成しDiscordで答える、完全独自のフォームシステム + イベント管理システム | [詳細はこちら](./docs/features/FEATURE_SURVEY.md) |
| **寝落ち切断** | 特定ユーザーがVCから退出して一定時間経過しても、まだVCに残っているユーザーを「寝落ち」と判定し、自動的に切断（Kick）する機能。また、切断した人数を集計し、テキストチャンネルに報告する。 | [詳細はこちら](./docs/features/FEATURE_VOICE_KEEPER.md) |
| **セキュアロビー(東方憑依華専用)** | Cloudflare WARP を利用した安全なオンライン対戦ロビーシステム。IPアドレスを公開することなく、参加者同士が直接接続できる。 | [詳細はこちら](./docs/features/FEATURE_LOBBY.md) |
| **配信コメントリセット** | `#配信コメント` チャンネルを毎月20日に自動リセット（削除→再作成）。VoiceKeeper 報告検知トリガー・フォールバック cron・Self Heal・管理者スラッシュコマンドの4段構え。 | [詳細はこちら](./docs/features/FEATURE_STREAM_COMMENT_RESET.md) |
| **大会・ラウンジ機能** | マリオカートワールドやアソビ大全、カービィのエアライダーのエアライダーの大会運営をサポートする。 | [詳細はこちら(大会)](./docs/features/FEATURE_GENERAL_TOURNAMENT.md) | [詳細はこちら(ラウンジ)](./docs/features/FEATURE_LOUNGE.md) |

> [!TIP]
> 各機能の詳細仕様は [`docs/features/`](./docs/features/) にまとめています。

> [!NOTE]
> **メッセージフィルタ機能**（特定チャンネルでの不正投稿を自動排除）は、ホストの意向により廃止されました（Phase 2, 2026-02-21）。

## 🏗️ システムアーキテクチャ

物理サーバー上に構築された仮想化環境と、Zero Trust ネットワークを組み合わせた堅牢な構成を採用しています。

### 🖥️ Hardware Spec

- **CPU**: Intel Core i3 9100F
- **GPU**: NVIDIA GeForce GT 710 (**望まれざる客**)
- **RAM**: 16GB
- **SSD**: 500GB

### 🌐 Infrastructure

- **Virtualization**: Proxmox VE 9.1
- **OS**: Ubuntu 24.04 LTS / MariaDB (LXC)
- **Networking**: Cloudflare Tunnel (HTTPS 化 / 固定 IP 不要)

> [!IMPORTANT]
> インフラ構成図および詳細なネットワークフローについては [ARCHITECTURE.md](./docs/ARCHITECTURE.md) を参照してください。

## 🛠️ セットアップ（クイックスタート）

### 1. 環境変数の設定

`.env` ファイルを作成し、必要な情報を設定します。以下のファイルをコピーして環境変数を入力してください。

[./discord_bot/.env.example](./discord_bot/.env.example)

### 2. 依存関係のインストール

```Bash
uv sync 
```

### 3. サービスの起動

```Bash
# Botの起動
uv run bot.py

# Webダッシュボードの起動
uv run webapp.py
```

### 4. Rust DB ブリッジの起動

```bash
cd database_bridge
cargo run
```

## 🐳 Docker Compose での開発環境構築

MariaDB を含めた開発環境一式を Docker Compose で再現できます。

```bash
# 1. .env を作成（未作成の場合）
cp discord_bot/.env.example discord_bot/.env
# DISCORD_TOKEN / SECRET_KEY などを編集

# 2. ビルド & 起動
docker compose up --build

# ダッシュボード: http://localhost:5000
```

- `mariadb`: MariaDB 本体。`discord_bot/.env` の `DB_NAME` / `DB_USER` / `DB_PASS` をそのまま初期認証情報として使う。
- `app`: `database_bridge` (Rust) / `bot.py` / `webapp.py` を同一コンテナ内で起動する（理由は [ADR-028](./docs/adr/021-030/028-docker-compose-dev-environment.md) を参照）。

> [!WARNING]
> `database_bridge/migrations/` は `003_*.sql` から始まっており、`surveys` などのコアテーブルを
> 作成するマイグレーションがリポジトリに含まれていません。まっさらな DB では一部機能がテーブル
> 未作成でエラーになります。詳細と対処法は [infra/db-init/README.md](./infra/db-init/README.md)
> を参照してください。

再作成する場合（DB を初期化してやり直す）:

```bash
docker compose down -v
docker compose up --build
```

## 各ディレクトリの説明

詳細な説明は以下のディレクトリのREADME.mdを参照してください。

- [discord_bot/common/README.md](./discord_bot/common/README.md)
- [discord_bot/services/README.md](./discord_bot/services/README.md)
- [discord_bot/routes/README.md](./discord_bot/routes/README.md)
- [discord_bot/cogs/README.md](./discord_bot/cogs/README.md)

## 更新内容

詳細な更新内容は[CHANGELOG.md](./CHANGELOG.md)を参照してください。

## 📜 ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

© 2026 Awaji Empire Technical Department
