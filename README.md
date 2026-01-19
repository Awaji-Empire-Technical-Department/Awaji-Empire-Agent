# 🤖 Awaji Empire Agent

淡路帝国のコミュニティ運営を支える、多機能 Discord Bot & 管理ダッシュボードプラットフォーム。

## 🌟 プロジェクトの概要

本プロジェクトは、Discord Bot (`discord.py`) と Web ダッシュボード (`Quart`) を MariaDB で統合した、コミュニティ管理システムです。
単なる Bot ではなく、インフラ（Proxmox / Cloudflare Tunnel）からフロントエンドまでを一貫して内製しており、高度な柔軟性とセキュリティを両立しています。

## 🚀 主要機能

本システムは主に 3 つのコア機能を提供します。

| 機能 | 概要 | 詳細ドキュメント |
| :--- | :--- | :--- |
| **🛡️ メッセージフィルタ** | 特定チャンネルでの不正投稿（コード形式以外）を自動排除 | [詳細はこちら](./docs/FEATURE_FILTER.md) |
| **🔔 通知マスミュート** | 大規模サーバーの通知騒音を防ぐ権限自動管理 | [詳細はこちら](./docs/FEATURE_MASS_MUTE.md) |
| **📝 内製アンケート** | Webで作成しDiscordで答える、完全独自のフォームシステム | [詳細はこちら](./docs/FEATURE_SURVEY.md) |
| **😴 寝落ち切断** | 特定ユーザーがVCから退出して一定時間経過しても、まだVCに残っているユーザーを「寝落ち」と判定し、自動的に切断（Kick）する機能。また、切断した人数を集計し、テキストチャンネルに報告する。 | [詳細はこちら](./docs/voice_keeper.md) |

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

`.env` ファイルを作成し、必要な情報を設定します。

```ini
# Database
DB_HOST=db_ip
DB_NAME=bot_db
DB_USER=bot_user
DB_PASS=your_password

# Discord OAuth2
DISCORD_CLIENT_ID=1446462054423855144
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=[https://dashboard.awajiempire.net/callback](https://dashboard.awajiempire.net/callback)
```

### 2. 依存関係のインストール

```Bash
pip install -r requirements.txt
```

### 3. サービスの起動

```Bash
# Botの起動
python bot.py

# Webダッシュボードの起動
python webapp.py
```

## 更新内容

詳細な更新内容は[CHANGELOG.md](./CHANGELOG.md)

## 📜 ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

© 2025 Awaji Empire Technical Department
