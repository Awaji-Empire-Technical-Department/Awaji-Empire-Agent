# 本番環境（Master）移行・再構築ガイド

リポジトリのモノレポ化および `uv` / `Rust` 導入に伴い、本番サーバー側で必要となる初回セットアップ手順をまとめます。

## 1. 事前準備 (Antigravity 側での作業)

本番マージ前に、以下のファイルが正しく設定されているか確認してください。

- [ ] **GitHub Actions の更新**: `.github/workflows/` 内の YAML で `working-directory` が指定されていること。
- [ ] **依存関係の確定**: `discord_bot/pyproject.toml` と `uv.lock` が最新であること。
- [ ] **Rust 構成**: `database_bridge/Cargo.toml` に必要な依存関係が記述されていること。

## 2. 本番サーバー（01sv-production等）での初回作業

### A. インフラ環境の導入

本番サーバーに SSH で入り、新しいツールチェーンをインストールします。

1. **uv のインストール**

   ```bash
   curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
   source $HOME/.local/bin/env

2. **Rust (Cargo) のインストール**

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf [https://sh.rustup.rs](https://sh.rustup.rs) | sh
   source $HOME/.cargo/env
   ```

### B. リポジトリのクローンと環境設定

1. **リポジトリの取得**

   ```bash
   cd /home/awaji-bot
   git clone <Your-Repo-URL> awaji-empire-agent
   cd awaji-empire-agent
   ```

2. **環境変数の配置**

   ```bash
   cp .env.example .env
   # .env を開き、実際のトークンや設定値を入力する
   ```

3. **Python 仮想環境の作成と依存関係のインストール**

   ```bash
   # 仮想環境の作成
   uv venv
   source .venv/bin/activate

   # 依存関係のインストール
   uv sync
   ```

4. **Rust 依存関係のビルド**

   ```bash
   cd database_bridge
   cargo build --release
   cd ..
   ```

### C. サービスの再構築

1. **既存サービスの停止**

   ```bash
   sudo systemctl stop discord_bot.service
   sudo systemctl stop discord_webapp.service
   ```

2. **ファイルの配置**

   ```bash
   # 既存のファイルを削除またはバックアップ
   sudo rm -rf /discord_bot/*
   sudo rm -rf /discord_webapp/*

   # 新しいコードを配置
   sudo rsync -av --exclude='.git' ./ /discord_bot/
   sudo rsync -av --exclude='.git' ./webapp/ /discord_webapp/
   ```

3. **権限の調整**

   ```bash
   sudo chown -R devuser:devuser /discord_bot
   sudo chown -R devuser:devuser /discord_webapp
   ```

4. **サービスの反映**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start discord_bot.service
   sudo systemctl start discord_webapp.service
   ```

### D. 一括セットアップスクリプト

サーバーに SSH で入った後、以下のスクリプトを `setup_env.sh` として保存し実行することで、環境構築を自動化できます。
>> [!IMPORTANT]
>> 必ず `discord_bot` ディレクトリで実行するようにすること！

```bash
#!/bin/bash
set -e

echo "🚀 本番環境の再構築を開始します..."

# 1. インフラ導入 (uv)
if ! command -v uv &> /dev/null; then
    echo "📦 uv をインストールしています..."
    curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
    source $HOME/.local/bin/env
fi

# 2. リポジトリの最新化
cd /Awaji-Empire-Agent
git fetch origin
git checkout master
git pull origin master

# 3. Python環境構築
echo "🐍 Python 仮想環境を構築しています..."
cd /Awaji-Empire-Agent/discord_bot
uv sync

# 4. Service ファイルのパス自動修正
echo "⚙️  systemd サービスファイルをモノレポ構造に更新しています..."
SERVICE_FILE="/etc/systemd/system/discord_bot.service"

# WorkingDirectory と ExecStart のパスを修正
sudo sed -i "s|^WorkingDirectory=.*|WorkingDirectory=/Awaji-Empire-Agent/discord_bot|" $SERVICE_FILE
sudo sed -i "s|^ExecStart=.*|ExecStart=/Awaji-Empire-Agent/discord_bot/.venv/bin/python3 bot.py|" $SERVICE_FILE

# 5. 反映と再起動
sudo systemctl daemon-reload
sudo systemctl restart discord_bot.service

echo "✅ セットアップが完了しました！"
systemctl status discord_bot.service --no-pager
```

## 3. GitHub Actions による自動デプロイ設定

モノレポ化に伴い、GitHub Actions の設定を更新する必要があります。

- **`working-directory` の設定**: 各ジョブ（`deploy` など）内で `working-directory: discord_bot` を指定し、正しいディレクトリでコマンドが実行されるようにします。
- **`uv` の利用**: `pip` の代わりに `uv` コマンド（`uv sync`, `uv run`）を使用するように変更します。

## 4. 確認事項

デプロイ後、以下の点を確認してください。

- [ ] Bot が起動し、チャンネルに接続しているか。
- [ ] Web アプリケーションが正常に動作しているか。
- [ ] `database_bridge` が正常にコンパイルされ、Bot から呼び出されているか。
