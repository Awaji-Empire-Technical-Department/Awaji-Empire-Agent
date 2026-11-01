# ADR-032: Webapp の OAuth state 検証・WebSocket 認証・CORS 撤去と database_bridge の非 root 化

- **ステータス**: 採用
- **作成日**: 2026-11-01
- **作成者**: Wanyaldee
- **ブランチ**: `security/webapp-oauth-state-ws-auth`

---

## 背景 (Context)

公開リポジトリの監査（2026-11-01）で、次の 4 点が見つかった。

1. **OAuth2 の `state` が無い**: `/login` が Discord 認可 URL に `state` を付けず、`/callback` も検証していなかった。
   攻撃者が自分のアカウントで取得した `code` 付きの `/callback?code=...` を被害者に踏ませると、
   被害者のブラウザが攻撃者のアカウントでログインした状態になる（ログイン CSRF）。
   被害者がその状態でフォーム回答・ロビー参加などを行うと、操作が攻撃者のアカウントに紐づく。
2. **WebSocket `/ws/hyouibana` が未認証**: 接続元のページ（`/lounge`・`/tournament`・ロビー）はすべて
   `_require_login()` でログイン必須なのに、WS プロキシ自体は誰でも接続でき、Rust Bridge のブロードキャスト
   （ラウンジ・大会の進行イベント）を読めた。
3. **`cors(app, allow_origin="*")`**: ダッシュボードはすべて同一オリジンで完結しており（JS は相対パス / `location.host` で fetch・WS 接続）、
   クロスオリジン許可は不要だった。`quart-cors` は既定で credentials を許可しないため直接の悪用経路は無いが、
   将来の設定変更で危険になる不要な許可だった。
4. **`database_bridge.service` が `User=root`**: Bridge は `127.0.0.1:7878` で待ち受けて DB に接続するだけで、
   特権ポートもファイル書き込みも使わない。Bot / Webapp は既に `User=devuser` で動いている。

## 決定事項 (Decision)

- `/login` で `secrets.token_urlsafe(32)` の `state` を発行してセッションに保存し、`/callback` で一致しなければ 400 を返す。state は一度使ったら破棄する。
- `/ws/hyouibana` はセッションに `discord_user` が無ければ accept 前に 401 で拒否する。
- `quart-cors` の利用と依存（`pyproject.toml` / `requirements.txt` / `uv.lock`）を削除する。
- `infra/database_bridge.service` を `User=devuser` にする（他 2 サービスと同じ）。

## 根拠 (Reason)

OAuth state（`discord_bot/webapp.py`）:

```python
@app.route('/login')
async def login():
    ...
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    discord_auth_url = (... f"&state={state}")

@app.route('/callback')
async def callback():
    expected_state = session.pop('oauth_state', None)
    state = request.args.get('state', '')
    # bytes で比較: str の compare_digest は非ASCII入力で TypeError (→500) になるため
    if not expected_state or not secrets.compare_digest(state.encode(), expected_state.encode()):
        return "Error: Invalid OAuth state. Please log in again.", 400
```

- 検証は `code` の確認・トークン交換より前に置く。不正なリクエストでは Discord API を一切呼ばない。
- `session.pop` で一度きりにする。callback の再読み込みは 400 になるが、`/login` からやり直せば済む。
- セッション Cookie は Quart 既定（SameSite 未指定 → ブラウザ既定の Lax）。Discord からのリダイレクトはトップレベル GET なので Cookie は送られ、state を照合できる。

WebSocket 認証:

```python
@app.websocket('/ws/hyouibana')
async def ws_proxy():
    if not session.get('discord_user'):
        abort(401)
    ...
```

- WS ハンドシェイクにもセッション Cookie が付くので、HTTP ルートと同じ `session['discord_user']` で判定できる。
  接続元ページがすべてログイン必須なので、正規の利用者への影響は無い。

`database_bridge.service`:

```ini
[Service]
User=devuser
EnvironmentFile=/Awaji-Empire-Agent/discord_bot/.env
```

- `EnvironmentFile=` は User 切り替え前に systemd（root）が読むため、`.env` が devuser から読めなくても環境変数は渡る。
- `main.rs` の `dotenvy::dotenv().ok()` は読めなくてもエラーを無視する。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| CORS の許可オリジンを `dashboard.awajiempire.net` に絞る | クロスオリジン呼び出し自体が存在しないので、許可を残す理由がない |
| WS で Origin ヘッダも検証する | 未ログイン拒否で今回の問題（未認証でのブロードキャスト閲覧）は解消する。Origin 検証はクロスサイト WS 乗っ取り対策として別途検討 |
| Bridge 専用のシステムユーザーを新設 | サーバー側で useradd が必要になり、デプロイ（`setup-systemd.sh`）だけで完結しない。既存の `devuser` で root を外すことを優先 |
| `requests-oauthlib` で OAuth フローを書き直す | 既存の手書きフローに state を足すだけで足りる |

## 影響 (Consequences)

### ポジティブ

- ログイン CSRF を防げる。
- 未ログインのクライアントは WS のブロードキャストを読めない。
- Bridge が侵害されても root 権限は取られない。
- 依存が 1 つ減る（`quart-cors`）。

### ネガティブ・トレードオフ

- `/callback` を直接再読み込みすると 400 になる（`/login` からやり直す必要がある）。
- **デプロイ時のリスク**: `/Awaji-Empire-Agent/database_bridge/target/release/database_bridge` が devuser から実行できない権限になっていると、Bridge が起動せず Bot / Webapp も機能しなくなる。
  CI は `rsync -av` で runner のワークスペースから所有者ごとコピーするため、通常は実行可能（確度: 中）。
  先に `test` ブランチ（テスト環境）でデプロイして確認すること。戻す場合は `User=root` に戻して再デプロイする。

## 検証 (Verification)

- **操作:** `cd discord_bot && uv run pytest -q`
  **結果:** `42 passed`（exit 0）。新規 `tests/test_webapp_auth.py`（7 件）:
  `/login` が state を発行しセッションに保存する／state 欠落・不一致・非ASCII で 400／`/login` を経ない callback を拒否／state の再利用を拒否／未ログイン WS が 401
- **操作:** 変更前の `webapp.py` に戻して `tests/test_webapp_auth.py -k "not ws"` を実行
  **結果:** `5 failed`（テストが変更前の挙動を検出できることを確認）。WS テストは変更前だと 401 にならず応答待ちで止まる
- **操作:** `uv run --with flake8 flake8 . --exclude .venv --count --select=E9,F63,F7,F82`
  **結果:** `0`

  Checked-by: Claude (AI agent)、2026-11-01

### 未検証

- 実際の Discord OAuth を通したログイン（ブラウザ + 本物の Discord）
- ログイン済みブラウザからのラウンジ / 大会画面の WS リアルタイム更新
- `database_bridge` の `User=devuser` での起動（サーバー上のファイル権限に依存）

## 関連ドキュメント

- 関連 ADR: [ADR-016](../011-020/016-lounge-ux-realtime-improvements.md)（WS プロキシ導入）, [ADR-023](../021-030/023-discord-token-dotenv-migration.md), [ADR-027](../021-030/027-webapp-xss-and-secret-key-hardening.md), [ADR-031](031-remove-token-txt-and-unused-files.md)
