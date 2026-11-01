# ADR-031: token.txt フォールバックの全廃と不要ファイルの削除

- **ステータス**: 採用
- **作成日**: 2026-11-01
- **作成者**: Wanyaldee
- **ブランチ**: `chore/cleanup-unused-files-and-token-txt`

---

## 背景 (Context)

公開リポジトリの監査（2026-11-01）で、次の 3 点が見つかった。

1. **ADR-023 の移行漏れ（バグ）**: ADR-023 で Bot トークンを `token.txt` から `.env` の
   `DISCORD_TOKEN` に移したが、`routes/lobby.py` と `routes/tournament.py` は **`token.txt` しか読んでいなかった**。
   `token.txt` が無い環境ではトークンが空になり、大会の優勝ロール付与・称号ロール付与/削除が
   無言でスキップされる（LESSON-008 と同じ型の不具合）。
   `routes/survey.py` / `routes/event.py` は `.env` 優先だが、`token.txt` へのフォールバックが残っていた。
2. **不要ファイル**: 現行コードから参照されないファイルが残っていた。
   - `config.py.example`（ルート）と `discord_bot/config.py.example`: 同一内容。`config.py` はもうどこからも import されていない（設定は `.env`）。
   - `discord_bot/cogs/voice_keeper.py.example`: `cogs/voice_keeper/` へ移行済みの旧実装。
   - `discord_bot/main.py`: 起動処理が `TODO` のままのスタブで、トークン末尾 4 文字を標準出力に出し、存在しない `scripts/migrate_token.py` を案内していた。実際の起動は `bot.py`。
   - `db_repair.py`: migration 006/100 衝突時の一度きりの修復スクリプト。実行すると `_sqlx_migrations` の行削除と `ALTER TABLE ... DROP COLUMN` を行うため、誤実行するとデータを失う。
3. **`.env.example` の誤り**: ギルド ID のキーが `GUILD_ID` だったが、コード（`webapp.py` / `bot.py` / `routes/tournament.py` / `cogs/stream_comment_reset`）が読むのは `DISCORD_GUILD_ID`。
   例のとおりに設定すると `Config.TARGET_GUILD_ID` が `None` になり、**ダッシュボードのギルドメンバー判定（ADR-026）が黙って無効になる**。
   また `DISCORD_REDIRECT_URI` が Markdown リンク記法 `[url](url)` で壊れていた。

## 決定事項 (Decision)

- Discord Bot トークンの取得元を **環境変数 `DISCORD_TOKEN` のみ** に統一し、`token.txt` の読み込みをコードから全廃する。
- 上記の不要ファイル 5 つを削除する（必要なら Git 履歴から参照できる）。
- `.env.example` のキーを `DISCORD_GUILD_ID` に直し、`DISCORD_REDIRECT_URI` を正しい URL にする。

## 根拠 (Reason)

`token.txt` フォールバックを残さない理由: 本番の 3 サービスは同じ `EnvironmentFile=/Awaji-Empire-Agent/discord_bot/.env` を読み（`infra/*.service`）、
`bot.py` は `DISCORD_TOKEN` が無いと起動しない。Bot が動いている時点で webapp にも `DISCORD_TOKEN` は渡っているため、
フォールバックは「取得経路が 2 つあるせいで移行漏れが見えなくなる」害しかない。LESSON-008 の再発防止
（「`token.txt` 依存を残さない」）をコードで強制する。

変更後のコード（4 ファイルとも同じ取得経路）:

```python
# routes/lobby.py
def get_bot_token():
    # ADR-023 / ADR-031: トークンは環境変数 DISCORD_TOKEN のみから読む。
    return os.getenv('DISCORD_TOKEN', '').strip() or None

# routes/tournament.py （呼び出し側は空文字を falsy として扱うため戻り値型 str を維持）
def _get_bot_token() -> str:
    # ADR-023 / ADR-031: トークンは環境変数 DISCORD_TOKEN のみから読む。
    return os.getenv("DISCORD_TOKEN", "").strip()

# routes/survey.py, routes/event.py （モジュール読込時に確定。webapp.py が routes import 前に load_dotenv する）
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN', '').strip() or None
```

共通ヘルパーに切り出さなかったのは、1 行の `os.getenv` のために新モジュールを足すより、各ファイルの既存の関数名・戻り値型を保ったほうが呼び出し側を一切触らずに済むため。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| `lobby.py` / `tournament.py` に `.env` 優先 + `token.txt` フォールバックを足す（survey/event と揃える） | 取得経路が 2 つ残り、次の移行漏れを隠す。本番では `.env` が必ずある（上記）ので利点がない |
| `common/` にトークン取得ヘルパーを新設 | 1 行のために層を増やす。既存の関数名・型を変えずに済む今回の形で十分 |
| `.env.example` の `DB_USER=root` も変更 | `infra/mariadb/docker-entrypoint.sh` が `DB_USER=root` を前提にしている（ADR-028）。変えると開発用 Docker 環境が壊れるため対象外 |

## 影響 (Consequences)

### ポジティブ

- 大会・称号のロール操作が `.env` 運用で動くようになる。
- Bot トークンの取得経路が 1 つになり、`grep -rn "token.txt" --include=*.py` が 0 件になる。
- `.env.example` どおりに設定すればギルドメンバー判定が有効になる。

### ネガティブ・トレードオフ

- サーバーに `token.txt` だけを置き、`.env` に `DISCORD_TOKEN` を書いていない環境では webapp のロール操作・DM が動かない。
  ただしその環境では `bot.py` 自体が起動しないため、気付かないまま運用される状況は起きない。
- 既存のサーバーの `.env` が `GUILD_ID` のままなら、`DISCORD_GUILD_ID` を追記する必要がある（コード側の変更ではなく、従来から必要だった設定）。

## 検証 (Verification)

- **操作:** `cd discord_bot && uv run pytest -q`
  **結果:** `35 passed`（exit 0）
- **操作:** `uv run --with flake8 flake8 . --exclude .venv --count --select=E9,F63,F7,F82`
  **結果:** `0`（exit 0）
- **操作:** `uv run python -m py_compile bot.py webapp.py routes/*.py`
  **結果:** exit 0
- **操作:** `grep -rn "token\.txt" --include=*.py discord_bot`
  **結果:** 0 件

  Checked-by: Claude (AI agent)、2026-11-01

### 未検証

- 本番/テスト環境での大会ロール付与・称号ロール操作の実機確認（Discord API を叩く経路で、テストが無い）
- 本番 `.env` に `DISCORD_GUILD_ID` が設定されているか（サーバー側の状態のため確認不可）

## 関連ドキュメント

- 関連 ADR: [ADR-023](../021-030/023-discord-token-dotenv-migration.md), [ADR-026](../021-030/026-event-form-guild-nonmember-dashboard-block.md), [ADR-028](../021-030/028-docker-compose-dev-environment.md)
- 教訓: `tasks/lessons.md` LESSON-008
