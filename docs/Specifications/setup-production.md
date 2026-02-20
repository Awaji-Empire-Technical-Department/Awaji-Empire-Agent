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
> [!IMPORTANT]
> 必ず `discord_bot` ディレクトリで実行するようにすること！

```bash
#!/bin/bash

# =================================================================
# 淡路帝国エージェント：モノレポ移行 & systemd 自動更新スクリプト
# 役割: ディレクトリ整理、Rust/uv初期化、サービスパスの一括修正
# =================================================================

set -e # エラーが発生したら即座に停止

# --- 設定項目 ---
PARENT_DIR="/Awaji-Empire-Agent"
PYTHON_DIR="$PARENT_DIR/discord_bot"
RUST_DIR="$PARENT_DIR/database_bridge"
SERVICES=("discord_bot.service" "discord_webapp.service")

echo "🚀 モノレポ構成への移行を開始します..."

# 1. 親ディレクトリの作成とファイル移動
if [ ! -d "$PARENT_DIR" ]; then
    echo "📂 親ディレクトリ $PARENT_DIR を作成中..."
    sudo mkdir -p "$PYTHON_DIR"

    echo "🚚 既存ファイルを $PYTHON_DIR へ移動中..."
    # 隠しファイルを含め、このスクリプト自身以外の全ファイルを移動
    sudo find . -maxdepth 1 ! -name "." ! -name "$(basename "$0")" -exec mv {} "$PYTHON_DIR/" \;

    # 所有権を自分（現在のユーザー）に変更
    sudo chown -R $USER:$USER "$PARENT_DIR"
else
    echo "⚠️ すでに $PARENT_DIR が存在します。移動をスキップします。"
fi

cd "$PARENT_DIR"

# 2. Rust ブリッジの初期化 (Rust採用に向けた第一歩)
if [ ! -d "$RUST_DIR" ]; then
    echo "🦀 Rust プロジェクトを初期化中..."
    mkdir -p "$RUST_DIR"
    cd "$RUST_DIR"
    cargo init --bin
    cd ..
fi

# 3. uv (Rust製パッケージマネージャー) の導入
echo "⚡ uv をセットアップ中..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # パスを即時反映（インストーラーの指示に従う）
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    fi
    #念のため、PATHにも直接追加しておく
    export PATH="$HOME/.local/bin:$PATH"
fi

# Python環境の初期化
cd "$PYTHON_DIR"
uv init
# 既存の依存関係を pyproject.toml ベースへ
if [ -f "requirements.txt" ]; then
    echo "📦 requirements.txt から依存関係をインポート中..."
    uv pip compile requirements.txt -o requirements.txt
fi
cd ..

# 4. systemd サービスのパス自動書き換え
echo "⚙️ systemd サービスを更新中..."
for SERVICE in "${SERVICES[@]}"; do
    SYSTEMD_PATH="/etc/systemd/system/$SERVICE"

    if [ -f "$SYSTEMD_PATH" ]; then
        echo "🔄 $SERVICE のパスを置換中..."
        # バックアップ作成
        sudo cp "$SYSTEMD_PATH" "${SYSTEMD_PATH}.bak"

        # WorkingDirectory と ExecStart 内のディレクトリパスを置換
        sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PYTHON_DIR|g" "$SYSTEMD_PATH"
        sudo sed -i "s|/discord_bot/|/Awaji-Empire-Agent/discord_bot/|g" "$SYSTEMD_PATH"

        echo "✅ $SERVICE の更新完了（バックアップ: ${SERVICE}.bak）"
    else
        echo "❌ エラー: $SYSTEMD_PATH が見つかりません。"
    fi
done

# 5. systemd 設定の反映と再起動
echo "🔄 サービスを再起動中..."
sudo systemctl daemon-reload
for SERVICE in "${SERVICES[@]}"; do
    sudo systemctl restart "$SERVICE"
    echo "🚀 $SERVICE が再起動しました。"
done

# 6. Git ブランチ設定
echo "🌿 Git ブランチを 'test' に切り替え中..." # <- これはtest環境の話,本番環境であればいらない
if [ ! -d ".git" ]; then
    git init
fi
# masterに影響を与えないよう test ブランチを作成 <- これはtest環境の話
# 本番環境はmaster
git checkout test

echo "✨ 全ての工程が完了しました！"
echo "現在のディレクトリ構造:"
ls -R | grep ":$" | sed -e 's/:$//' -e 's/[^-][^\/]*\//--/g' -e 's/^/   /
```

## 3. GitHub Actions による自動デプロイ設定

モノレポ化に伴い、GitHub Actions の設定を更新する必要があります。

- **`working-directory` の設定**: 各ジョブ（`deploy` など）内で `working-directory: discord_bot` を指定し、正しいディレクトリでコマンドが実行されるようにします。
- **`uv` の利用**: `pip` の代わりに `uv` コマンド（`uv sync`, `uv run`）を使用するように変更します。

`rsync` コマンドと `systemctl` コマンドをパスワード無しで使えるようにします。
これをしなければ、GitHub Actions からデプロイする際にパスワードを入力する必要があります。

1. 設定ファイルを開く

```bash
sudo visudo -f /etc/sudoers.d/github-actions
```

※ `/etc/sudoers.d/` 配下に新しいファイルを作るのが、システムを汚さない最も安全な方法です。

1. 以下を追加

```bash
your_github_actions_user ALL=(ALL) NOPASSWD: /usr/bin/rsync, /bin/systemctl
```

※ YAML で `sudo` を使っているのは `rsync` と `systemctl` だけなので、これらだけを指定するのがセキュリティ上望ましいです。

## 4. 確認事項

デプロイ後、以下の点を確認してください。

- [ ] Bot が起動し、チャンネルに接続しているか。
- [ ] Web アプリケーションが正常に動作しているか。
- [ ] `database_bridge` が正常にコンパイルされ、Bot から呼び出されているか。
