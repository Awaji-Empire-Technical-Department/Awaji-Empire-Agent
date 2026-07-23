# ADR-027: Webダッシュボードの格納型XSS修正とセッション署名鍵の必須化

- **ステータス**: 採用
- **作成日**: 2026-07-23
- **作成者**: Wanyaldee
- **ブランチ**: `security/xss-and-secret-key-hardening`

---

## 背景 (Context)

コードベース全体のセキュリティレビューで、Webダッシュボードに2件の脆弱性を確認した。

1. **格納型XSS（High）**: 順位表・称号表を描画する際、`fetch()` で受け取った
   生JSON中の `username` / 称号名をエスケープせずテンプレートリテラルへ埋め込み、
   `element.innerHTML` に代入していた。`username` は Discord の表示名
   (`global_name` / `username`) 由来で、`/callback` から `LobbyService.sync_user`
   経由で `user_networks.username` に格納されるユーザー制御値。攻撃者は表示名に
   `<img src=x onerror=...>` を仕込むだけで、順位表を開いた他の参加者・ホストの
   ブラウザで任意スクリプトを実行できた（lounge.js は5秒間隔で自動ポーリング）。
   対象: `static/js/tournament.js`, `static/js/lounge.js`, `static/js/dashboard_titles.js`。

   なお `lounge.html` の `MEMBERS` 経由の描画は Jinja オートエスケープ済みの値を
   使うため対象外（二重エスケープを避けるため触っていない）。脆弱なのは
   fetch の生JSONを描画する経路に限られる。

2. **セッション署名鍵の危険なデフォルト（Medium）**: `webapp.py` の
   `SECRET_KEY = os.getenv('SECRET_KEY', 'default_insecure_key')` は、環境変数が
   未設定の場合に公開ソース上の既知固定値へフォールバックしていた。設定漏れがあると
   攻撃者が既知の鍵でセッションCookieを偽造でき、`session['discord_user']['id']` を
   `ADMIN_USER_ID` に一致させて管理者になりすませる（認証・認可の完全バイパス）。

SQLインジェクションは確認範囲では問題なし（Rust側 `sqlx` は全て `?` バインド、
`format!` は定数カラム名の連結のみ）。

## 決定事項 (Decision)

1. **XSS**: 影響を受ける各 JS ファイルの IIFE 内にローカルの `escapeHtml()` を追加し
   （既存の `staff_collaborators.js` と同一実装・同一スタイル）、fetch 由来の
   `username` / 称号名 / 称号説明を出力する `innerHTML` 経路すべてに適用した。
   `dashboard_titles.js` の削除ボタンは、壊れやすい
   `onclick="deleteTitle(id, '${name.replace(/'/g,...)}')"` の文字列埋め込みを廃し、
   `deleteTitle(id)` に変更して名前は `allTitles` から引く形にした（属性コンテキストへの
   ユーザー値埋め込み自体を排除）。

2. **SECRET_KEY**: フォールバックを廃し `os.environ['SECRET_KEY']` とした。未設定なら
   起動時に `KeyError` で停止する（fail-closed）。あわせて `discord_bot/.env.example` に
   `SECRET_KEY` を必須項目として追記した。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| 共有 `util.js` に `escapeHtml` を集約しベーステンプレートで読み込む | 全ページの `<script>` 配線とファイル追加が必要で差分が広がる。既存は各 IIFE がローカル定義する方式なので、それに合わせた（ceiling: 3ファイルに小さな重複。数が増えたら共有utilへ集約する） |
| DOM API (`textContent` / `createElement`) へ全面書き換え | 順位表の描画ロジックを大きく作り直すことになり、修正としては過剰。エスケープ適用で根本原因（未エスケープ埋め込み）は塞げる |
| SECRET_KEY を起動時に自動生成 | プロセス再起動ごとに全セッションが無効化され、複数ワーカー間で鍵が不一致になる。運用者が明示設定すべき値なので fail-closed を選択 |

## 影響 (Consequences)

### ポジティブ

- 表示名・称号名を経路とした格納型XSSを塞いだ。fetch 由来値を描画する全経路で
  エスケープが効く。
- SECRET_KEY 設定漏れによる管理者なりすましを構造的に不可能にした（起動失敗で気づける）。

### ネガティブ・トレードオフ

- `SECRET_KEY` 未設定の既存デプロイは、この変更後 webapp が起動しなくなる。
  デプロイ手順で環境変数の設定が必須（`.env.example` に追記済み）。
- `escapeHtml` が3ファイルに重複（`ponytail:` 上の既知の天井）。利用箇所が増えたら
  共有ユーティリティへ集約する。

## 関連ドキュメント

- 関連 ADR: [ADR-023](023-discord-token-dotenv-migration.md)（シークレットの .env 管理）
- 環境変数運用: `docs/ENV_SECRETS_MANAGEMENT.md`
