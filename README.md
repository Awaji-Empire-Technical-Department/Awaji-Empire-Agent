# 🤖 Awaji Empire Agent

淡路帝国のコミュニティ運営を支える、多機能 Discord Bot & 管理ダッシュボードプラットフォーム。

## 🌟 プロジェクトの概要

本プロジェクトは、Discord Bot (`discord.py`) と Web ダッシュボード (`Quart`) を MariaDB で統合した、コミュニティ管理システムです。
単なる Bot ではなく、インフラ（Proxmox / Cloudflare Tunnel）からフロントエンドまでを一貫して内製しており、高度な柔軟性とセキュリティを両立しています。

## 🚀 主要機能

本システムは主に 6 つのコア機能を提供します。

| 機能 | 概要 | 詳細ドキュメント |
| :--- | :--- | :--- |
| **通知マスミュート** | 大規模サーバーの通知騒音を防ぐ権限自動管理 | [詳細はこちら](./docs/FEATURE_MASS_MUTE.md) |
| **内製アンケート** | Webで作成しDiscordで答える、完全独自のフォームシステム + イベント管理システム | [詳細はこちら](./docs/FEATURE_SURVEY.md) |
| **寝落ち切断** | 特定ユーザーがVCから退出して一定時間経過しても、まだVCに残っているユーザーを「寝落ち」と判定し、自動的に切断（Kick）する機能。また、切断した人数を集計し、テキストチャンネルに報告する。 | [詳細はこちら](./docs/FEATURE_VOICE_KEEPER.md) |
| **セキュアロビー(東方憑依華専用)** | Cloudflare WARP を利用した安全なオンライン対戦ロビーシステム。IPアドレスを公開することなく、参加者同士が直接接続できる。 | [詳細はこちら](./docs/FEATURE_LOBBY.md) |
| **配信コメントリセット** | `#配信コメント` チャンネルを毎月20日に自動リセット（削除→再作成）。VoiceKeeper 報告検知トリガー・フォールバック cron・Self Heal・管理者スラッシュコマンドの4段構え。 | [詳細はこちら](./docs/FEATURE_STREAM_COMMENT_RESET.md) |
| **大会・ラウンジ機能** | マリオカートワールドやアソビ大全、カービィのエアライダーのエアライダーの大会運営をサポートする。 | [詳細はこちら(大会)](./docs/FEATURE_GENERAL_TOURNAMENT.md) | [詳細はこちら(ラウンジ)](./docs/FEATURE_LOUNGE.md) |

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
