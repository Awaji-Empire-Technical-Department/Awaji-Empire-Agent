# 環境変数・シークレット管理マニュアル

**ステータス:** 運用推奨（Stripe導入時は必須）  
**作成日:** 2026-05-26  
**参考:** [dotenvxの使い方 (Zenn)](https://zenn.dev/cocomina/articles/how-to-use-dotenvx)

---

## なぜこのドキュメントが必要か

`STRIPE_SECRET_KEY` のような本番キーが `.env` に平文で存在する状態でGitに誤ってコミットすると、  
第三者に悪用されStripeアカウントが不正利用される。  
**dotenvx** を使って `.env` を暗号化しつつGit管理することで、このリスクをゼロにする。

---

## 目次

1. [現状の問題点](#1-現状の問題点)
2. [dotenvxとは](#2-dotenvxとは)
3. [インストール](#3-インストール)
4. [基本的な使い方](#4-基本的な使い方)
5. [環境別ファイル管理（development / production）](#5-環境別ファイル管理development--production)
6. [.gitignoreのルール](#6-gitignoreのルール)
7. [復号して実行する（アプリ起動）](#7-復号して実行するアプリ起動)
8. [チームメンバーへの鍵の共有方法](#8-チームメンバーへの鍵の共有方法)
9. [systemdでの本番運用](#9-systemdでの本番運用)
10. [Stripe導入時の追加ルール](#10-stripe導入時の追加ルール)
11. [よくあるミスと対処](#11-よくあるミスと対処)

---

## 1. 現状の問題点

```
# 現在の .env（平文）
DISCORD_TOKEN=xxxxxxxxxxx
DATABASE_URL=mysql://...

# Stripe導入後に追加される機密度の高いキー
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxx   ← 漏洩すると即座に不正課金被害
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxx
```

平文の `.env` を `.gitignore` で除外するだけでは：
- うっかり `git add .` で含めてしまうリスクが残る
- サーバーに `.env` を手動でコピーする作業が属人化する
- チームメンバーへの鍵配布が口頭・DM頼りになる

---

## 2. dotenvxとは

- `.env` ファイルを **公開鍵暗号（ECC）で暗号化** してGitに安全にコミットできるツール
- 暗号化された `.env` は復号鍵（`.env.keys`）がないと読めない
- 復号鍵は `.env.keys` 1ファイルに集約され、これだけ厳重に管理すればよい
- `dotenvx run -- <コマンド>` で起動時に自動復号し、プロセスに環境変数を注入する

```
.env（暗号化済み） → Gitに含めてOK
.env.keys          → Gitに含めてはいけない（これだけ守ればよい）
```

---

## 3. インストール

本プロジェクトはPython + uvを使用しているため、dotenvxは **スタンドアロンバイナリ** として導入する。  
npmに依存しないインストール方法が公式から提供されている。

### Linux / macOS（本番サーバー・開発環境）

```bash
# 公式インストールスクリプト
curl -sfS https://dotenvx.sh/install.sh | sh

# バージョン確認
dotenvx --version
```

### Windows（開発環境）

```powershell
# winget経由
winget install dotenvx

# または scoop経由
scoop install dotenvx
```

### インストール確認

```bash
dotenvx --version
# dotenvx/1.x.x
```

---

## 4. 基本的な使い方

### 4-1. 既存の .env を暗号化する

```bash
dotenvx encrypt
```

実行後、`.env` の内容が以下のように変わる：

```bash
# Before（平文）
DISCORD_TOKEN=xxxxxxxxxxx
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxx

# After（暗号化済み）
#/-------------------[DOTENV_PUBLIC_KEY]--------------------/
#/         public-key encryption for .env files            /
#/  [how it works](https://dotenvx.com/encryption)        /
#/----------------------------------------------------------/
DOTENV_PUBLIC_KEY="0x04abc123..."

DISCORD_TOKEN="encrypted:BDDGy8vYNJ..."
STRIPE_SECRET_KEY="encrypted:BDEHJ7kLmP..."
```

同時に **`.env.keys`** が生成される：

```bash
# .env.keys（復号マスターキー）
DOTENV_PRIVATE_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 4-2. 特定の変数だけ追加・更新する

```bash
# 暗号化しながら変数を追加
dotenvx set STRIPE_SECRET_KEY "sk_live_xxxxxxxx"

# 確認（復号して表示）
dotenvx get STRIPE_SECRET_KEY
```

---

## 5. 環境別ファイル管理（development / production）

本番と開発で別キーを使うことで、開発者が本番Stripeにアクセスできない状態を作れる。

```bash
# 開発用
dotenvx encrypt -f .env.development

# 本番用
dotenvx encrypt -f .env.production
```

`.env.keys` には両環境の鍵がまとめて記録される：

```bash
# .env.keys
DOTENV_PRIVATE_KEY_DEVELOPMENT="dev用の秘密鍵..."
DOTENV_PRIVATE_KEY_PRODUCTION="prod用の秘密鍵..."
```

### ファイル構成

```
プロジェクトルート/
├── .env.development       # 暗号化済み → Gitにコミットしてよい
├── .env.production        # 暗号化済み → Gitにコミットしてよい
├── .env.keys              # 復号マスターキー → 絶対にGitにコミットしない
└── .gitignore
```

---

## 6. .gitignoreのルール

```gitignore
# .gitignore に追加・確認する項目

# 復号マスターキー（絶対に含めない）
.env.keys

# 平文の .env（万が一作成してしまった場合）
.env
.env.local

# 暗号化済みファイルはコミットしてよい（以下はコメントアウト不要）
# .env.development
# .env.production
```

> **チェック方法：**  
> `git ls-files .env.keys` の出力が空であることを必ず確認すること。

---

## 7. 復号して実行する（アプリ起動）

### 開発時

```bash
# .env.development を復号してBotを起動
dotenvx run -f .env.development -- python -m discord_bot.bot

# uvと組み合わせる場合
dotenvx run -f .env.development -- uv run python -m discord_bot.bot
```

### 本番時（手動起動の場合）

```bash
# DOTENV_PRIVATE_KEY_PRODUCTION を環境変数に渡して実行
DOTENV_PRIVATE_KEY_PRODUCTION="xxxx..." dotenvx run -f .env.production -- uv run python -m discord_bot.bot
```

---

## 8. チームメンバーへの鍵の共有方法

`.env.keys` は **Gitに含めず** 、以下の方法で共有する：

| 方法 | 用途 |
|---|---|
| Discordの管理者専用チャンネル（DMPを使用） | 開発者間での一時共有 |
| サーバーの環境変数（`/etc/environment` や systemdの `EnvironmentFile`） | 本番サーバーへの設定 |
| パスワードマネージャー（Bitwarden等）への保存 | 長期管理 |

> **口頭・平文テキストでの共有は禁止。**  
> 必ず暗号化された通信経路（DM・パスワードマネージャー）を使うこと。

---

## 9. systemdでの本番運用

本プロジェクトはsystemdでRust BridgeとBot/Webappを管理している（ARCHITECTURE.md参照）。  
dotenvxをsystemdと組み合わせる場合、復号鍵を `EnvironmentFile` か `Environment` で渡す。

### 方法A: systemdのEnvironmentに直接記述

```ini
# /etc/systemd/system/awaji-bot.service

[Unit]
Description=Awaji Empire Discord Bot
After=network.target awaji-bridge.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Awaji_Empire_Agent
Environment="DOTENV_PRIVATE_KEY_PRODUCTION=xxxxxxxxxxxxxxxx"
ExecStart=dotenvx run -f .env.production -- uv run python -m discord_bot.bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 方法B: 鍵ファイルを別途配置

```ini
# /etc/systemd/system/awaji-bot.service
[Service]
EnvironmentFile=/etc/awaji/secrets   # サーバーローカルの鍵ファイル
ExecStart=dotenvx run -f .env.production -- uv run python -m discord_bot.bot
```

```bash
# /etc/awaji/secrets（サーバー上にのみ存在・Gitには含めない）
DOTENV_PRIVATE_KEY_PRODUCTION=xxxxxxxxxxxxxxxx
```

```bash
# パーミッション設定（rootのみ読み取り可能）
sudo chmod 600 /etc/awaji/secrets
sudo chown root:root /etc/awaji/secrets
```

---

## 10. Stripe導入時の追加ルール

Stripe導入後は以下の変数が `.env.production` に追加される。  
これらは漏洩した瞬間に不正課金被害が発生するため、特に厳重に扱うこと。

```bash
# .env.production に追加（dotenvx set コマンドで暗号化しながら追記）
dotenvx set STRIPE_SECRET_KEY "sk_live_xxxxxxxxxx" -f .env.production
dotenvx set STRIPE_PUBLISHABLE_KEY "pk_live_xxxxxxxxxx" -f .env.production
dotenvx set STRIPE_WEBHOOK_SECRET "whsec_xxxxxxxxxx" -f .env.production

# パターンB（Stripe Connect）の場合は追加で
dotenvx set STRIPE_CLIENT_ID "ca_xxxxxxxxxx" -f .env.production
```

### テスト用キーと本番用キーの分離

```bash
# .env.development にはテスト用キーのみ設定する
dotenvx set STRIPE_SECRET_KEY "sk_test_xxxxxxxxxx" -f .env.development
dotenvx set STRIPE_PUBLISHABLE_KEY "pk_test_xxxxxxxxxx" -f .env.development
dotenvx set STRIPE_WEBHOOK_SECRET "whsec_test_xxxxxxxxxx" -f .env.development
```

> **`sk_live_` を `.env.development` に書かない。**  
> 開発環境から本番Stripeに誤ってアクセスできる状態は作らない。

---

## 11. よくあるミスと対処

### `.env.keys` をうっかりコミットしてしまった

```bash
# 即座に鍵をローテーション（再生成）
dotenvx rotate

# Gitの履歴から完全削除（git-filter-repoを使用）
pip install git-filter-repo
git filter-repo --path .env.keys --invert-paths

# その後、Stripeダッシュボードで旧キーを即座に無効化・新キーを発行
```

### 暗号化された .env を平文に戻したい（緊急時のみ）

```bash
dotenvx decrypt
# → .env が平文に戻る（作業後は必ず再暗号化すること）
```

### 復号できない（鍵が見つからない）

```bash
# DOTENV_PRIVATE_KEY が環境変数に設定されているか確認
echo $DOTENV_PRIVATE_KEY_PRODUCTION

# 明示的に鍵を指定して実行
DOTENV_PRIVATE_KEY_PRODUCTION="xxxx" dotenvx run -f .env.production -- python -c "import os; print(os.environ['STRIPE_SECRET_KEY'])"
```

---

## 参考リンク

- [dotenvx公式ドキュメント](https://dotenvx.com/docs)
- [dotenvxの使い方 (Zenn)](https://zenn.dev/cocomina/articles/how-to-use-dotenvx)
- [Stripe導入マニュアル](./STRIPE_PAYMENT_MANUAL.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)（systemdサービス管理の詳細）
