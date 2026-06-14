# ADR-023: Discord Bot トークン管理を token.txt から .env へ移行

- **ステータス**: 採用
- **作成日**: 2026-05-28
- **作成者**: Wanyaldee

---

## コンテキスト

`bot.py` は起動時および締切スケジューラー内の DM 送信処理で、Discord Bot トークンを `token.txt` ファイルから直接読み込んでいた。

```python
# 旧実装（2箇所存在）
with open('token.txt', 'r') as f:
    token = f.read().strip()
```

この設計には以下の問題があった。

1. **平文ファイルの管理が属人的**: `token.txt` はどこに置くか、誰が管理するかが暗黙知になっていた。
2. **他のシークレットと管理方式が分断**: DB 認証情報・Cloudflare トークン等はすでに `.env` で管理しているのに、Discord トークンだけ別方式だった。
3. **systemd との連携漏れ**: `discord_bot.service` に `EnvironmentFile=` が設定されておらず、`.env` の値がプロセスに渡っていなかった。
4. **`load_dotenv()` 呼び出し順バグ**: `load_dotenv()` より前に `os.getenv('DASHBOARD_URL')` が呼ばれており、`.env` が読まれる前にデフォルト値が確定していた。

また、`setup-systemd.sh` が `database_bridge.service` のみを対象としており、`discord_bot.service` と `discord_webapp.service` はリポジトリ外で手動管理されていた。

---

## 決定内容

### 1. bot.py: `DISCORD_TOKEN` 環境変数から取得

`python-dotenv` はすでに `requirements.txt` に含まれているため、追加依存なし。

```python
# load_dotenv() を全 os.getenv() より先頭に移動
load_dotenv()

# トークン取得を一本化
def get_token() -> str | None:
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token:
        print("Error: DISCORD_TOKEN が設定されていません。", file=sys.stderr)
        return None
    return token
```

締切スケジューラー内の `open('token.txt')` も `os.getenv('DISCORD_TOKEN')` に統一した。

### 2. discord_bot.service に `EnvironmentFile=` を追加

```ini
EnvironmentFile=/Awaji-Empire-Agent/discord_bot/.env
```

これにより、systemd が Bot プロセスを起動する際に `.env` の全変数が自動的に環境変数として渡される。

### 3. 全サービスファイルを `infra/` で一元管理

| ファイル | 用途 |
|---|---|
| `infra/database_bridge.service` | 既存（変更なし） |
| `infra/discord_bot.service` | 新規追加（`EnvironmentFile=` 含む） |
| `infra/discord_webapp.service` | 新規追加（既存設定をリポジトリに収録） |

### 4. `setup-systemd.sh` を汎用化

`infra/*.service` を全てループしてインストールする形に変更。以後、サービスファイルを追加するだけで CI/CD が自動適用する。

```bash
for SOURCE_PATH in "${INFRA_DIR}"/*.service; do
    cp "${SOURCE_PATH}" "${SYSTEMD_DIR}/$(basename "${SOURCE_PATH}")"
    systemctl enable "$(basename "${SOURCE_PATH}")"
done
systemctl daemon-reload
```

### 5. `.env` への `DISCORD_TOKEN` キー追加

`.env` および `.env.example` に `DISCORD_TOKEN=` を明示。実値はサーバー上の `.env` に手動で設定済み。

---

## 検討した代替案

### token.txt を継続し .env に追記しない

- **却下理由**: 同じプロセスが `DB_PASS` を `.env` から読み、`DISCORD_TOKEN` だけ別ファイルから読む二重管理は保守コストが高い。

### dotenvx を導入して暗号化管理

- **却下理由**: 現時点では物理サーバー上の `.env` はファイルシステム権限（root 所有 / devuser 読み取り不可）で保護されており、暗号化の優先度は低い。将来的なオプションとして保留。

### GitHub Actions Secrets から直接 systemd に注入

- **却下理由**: self-hosted runner 環境では `.env` ファイルを直接サーバーに置く方が設定が単純。Secrets 経由にするとデプロイ時の上書きロジックが複雑になる。

---

## 影響範囲

| 対象 | 変更内容 |
|---|---|
| `discord_bot/bot.py` | `load_dotenv()` 順序修正・`get_token_from_file()` 廃止・`DISCORD_TOKEN` 環境変数で統一 |
| `discord_bot/.env` | `DISCORD_TOKEN` キー追加 |
| `discord_bot/.env.example` | `DISCORD_TOKEN` キー追加（説明コメント付き） |
| `infra/discord_bot.service` | 新規追加（`EnvironmentFile=` 含む） |
| `infra/discord_webapp.service` | 新規追加（既存設定をリポジトリに収録） |
| `scripts/setup-systemd.sh` | `infra/*.service` 全件ループに汎用化 |
| `infra/sudoers_deploy` | `discord_bot.service` の enable/restart/status 権限を追加 |
