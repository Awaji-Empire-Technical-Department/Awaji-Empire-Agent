# ADR-016: ラウンジ UX 改善・リアルタイム化・セキュリティ強化

- **ステータス**: 採用
- **作成日**: 2026-05-22
- **作成者**: Wanyaldee
- **関連ADR**: [ADR-013](013-lounge-system.md), [ADR-015](015-title-system.md)

---

## コンテキスト

ADR-013 で実装したラウンジシステムには以下の課題が残存していた。

1. **セキュリティ**: ゲストがホスト専用操作（レース開始・結果承認・セッション終了）をUIおよびAPIから実行できた
2. **UX**: 順位申告フォームがページ内の静的UIとして存在しており、レースタイミングとの連動がなかった
3. **リアルタイム性**: 参加者の申告状況がリアルタイムで把握できず、ホストが全員の完了を確認しにくかった
4. **セッション終了**: 終了後にMMRやランクが確認できなかった
5. **モバイル対応**: PC向けレイアウトのみで、スマホからの操作が困難だった
6. **ルームID**: 「合言葉」という曖昧な表現で、MKWのルームIDの書式（6桁英数字大文字）が明示されていなかった
7. **WebSocket疎通**: `/ws/hyouibana` がPython appで処理されておらず、ブラウザからRust bridgeに到達できなかった

---

## 決定した設計

### 1. ホスト権限の二重チェック（UI + API）

**UI層**（Jinja2テンプレート）:
- `is_host = str(user["id"]) == str(session_data.get("host_id", ""))` をサーバー側で算出
- Staff操作パネルを `{% if is_host %}` で囲み、非ホストには一切表示しない

**API層**（Python routes）:
- `create_race` / `approve_race` / `next_race` / `finish_session` の4エンドポイントで `session_data.get("host_id")` と照合し、不一致は403を返す
- `approve_race` のURLを `/api/sessions/<sid>/races/<rid>/approve` に変更し、session_idを直接検証できるようにした

**採用しなかった案**:
- Discordロール（例: Staff）でのロールベース認可 → セッションごとに異なるホストを扱うには不向き

---

### 2. 順位申告モーダルの設計

**フロー（ホスト）**:
```
「レース開始」クリック
  → モーダル（セットアップフェーズ）が即座に開く
    → コース名を入力
      → 「このコースでレースを開始する」クリック
        → POST /api/sessions/<sid>/races
          → 成功: モーダルが申告フェーズに移行（WS不要）
```

**フロー（ゲスト）**:
```
ホストがレースを開始
  → Rust Bridge が lounge.race_created をブロードキャスト
    → WebSocket経由でブラウザに届く
      → 申告フェーズのモーダルが自動で開く
```

**モーダルの2フェーズ構成**:
- `modal-phase-setup`: コース名入力（ホストのみ `{% if is_host %}` でレンダリング）
- `modal-phase-report`: 順位申告フォーム + 提出状況一覧（全員）

**ホストのモーダルがWSに依存しない理由**:
- 当初はWS `lounge.race_created` イベント受信でモーダルを開く実装だったが、WSの疎通問題（後述）により確実性がなかった
- HTTP APIレスポンスで直接 `openReportPhase()` を呼ぶことでWS不達時でもホストは確実に操作できる

**採用しなかった案**:
- Staffパネルにコース名入力を残す → 「申告モーダル内でコース名と順位を入力したい」というユーザー要望と乖離

---

### 3. リアルタイム提出状況

提出状況は `MEMBERS` マップ（`user_id → username`、Jinja2でJSに渡す）と `submissionState` オブジェクト（JSのメモリ上）で管理する。

- WS `lounge.score_reported` 受信 → `loadSubmissions(raceId)` を呼び、APIから最新スコアを取得してリスト再描画
- ページリロード時は `GET /lounge/api/sessions/<sid>/active-race` で最新レースを取得し、申告フェーズのモーダルを復元

**新規追加エンドポイント（Rust Bridge）**:
| エンドポイント | 用途 |
|---|---|
| `GET /lounge/sessions/{id}/active-race` | 最新レース取得（ページリロード復元） |
| `GET /lounge/races/{id}/scores/named` | ユーザー名付きスコア一覧 |
| `GET /lounge/players/{user_id}` | プレイヤーMMR取得 |

**新規追加エンドポイント（Python routes）**:
| エンドポイント | 用途 |
|---|---|
| `GET /lounge/api/sessions/<sid>/active-race` | ブリッジへのプロキシ |
| `GET /lounge/api/sessions/<sid>/races/<rid>/scores` | スコア一覧（named） |
| `POST /lounge/api/sessions/<sid>/races/<rid>/finalize` | 承認 + 次レースを一括処理 |
| `GET /lounge/api/me` | 自分のMMR・ランク称号を取得 |

**finalize エンドポイントの理由**:
- 旧来は「承認」「次のレースへ」が別々のボタンだった
- ホストの操作ステップを削減するため1ボタンで統合
- 内部では `approve_race(race_id)` → `next_race(session_id)` を順次実行

---

### 4. セッション終了時のMMR結果表示

`lounge.session_finished` WS受信 or セッション終了ボタン押下後:
1. 順位申告モーダルを閉じる
2. 結果モーダル（`result-modal-overlay`）を表示
3. `GET /lounge/api/me` を呼びMMR・ランク称号を取得して表示
4. 15秒後に `/`（ダッシュボード）へ自動リダイレクト

表示内容:
- 現在のMMR数値
- `unlock_type = 'lounge_rank'` の称号のうち最高閾値のものをランク名として表示
- Discordロールとして称号が付与されることの案内

---

### 5. WebSocket プロキシ

**問題**: ブラウザは `ws://192.168.50.69/ws/hyouibana`（Python app）に接続するが、Rust bridgeは `127.0.0.1:7878` にあり、サーバーローカルからしか到達できない。

**解決策**: Quart に `/ws/hyouibana` WebSocket エンドポイントを追加し、`aiohttp.ClientSession.ws_connect()` でRust bridgeへ双方向中継するプロキシを実装。

```
Browser ←── WS ──→ Quart(:port)/ws/hyouibana
                          ↑↓ aiohttp WS
                   Rust Bridge(127.0.0.1:7878)/ws/hyouibana
```

**採用しなかった案**:
- ブラウザから直接 `ws://127.0.0.1:7878` に接続 → サーバーサイドのポートをブラウザに公開する必要があり、ファイアウォール・セキュリティ上不適
- nginx/traefik でのリバースプロキシ設定 → インフラ変更コストが高く、Quartアプリ内で完結する方が変更箇所が少ない

**使用ライブラリ**: `aiohttp==3.13.2`（requirements.txtに既存、discord.pyの依存としても引き込まれている）

---

### 6. ルームID仕様の明確化

MKWのルームIDは6桁の大文字英数字（例: `ABC123`）。

- フロントエンド: `input` イベントで自動大文字変換 + `[^A-Z0-9]` 除去
- 送信時バリデーション: `/^[A-Z0-9]{6}$/` で拒否
- UIの `placeholder` を「合言葉」→「例: ABC123」に変更
- ダッシュボードのラウンジバナーにゲーム内ルームIDを表示

---

### 7. モバイル対応（lounge.css）

| ブレークポイント | 変更内容 |
|---|---|
| ≤640px | `lounge-grid` を1カラム化、Staffパネルボタンをフル幅、作成フォームを縦並び、ナビバーのユーザー名を非表示、カードパディング縮小 |
| 641px〜900px | 左カラムを280px→220pxに縮小 |
| 全体 | `lounge-table` クラスで `min-width: 600px` をリセット |

---

## 結果

- ゲストがStaff操作を実行できなくなった（UI・API両層でブロック）
- ホストが「レース開始」→モーダルでコース名入力→申告フェーズという一連の操作を直感的に行えるようになった
- 全参加者が誰の申告が完了しているかをリアルタイムで把握できるようになった
- セッション終了後にMMRとランクが即座に確認できるようになった
- WebSocket疎通問題がプロキシ追加で解決された
- スマホからの操作が可能になった

## トレードオフ・既知の制限

- `active-race` エンドポイントは「最新レース」を返すため、全レースが終了したセッションでも最後のレースのモーダルが復元される可能性がある（ページリロード時の誤検知）。現状は許容範囲として残す
- WSプロキシはQuartプロセスごとに接続を持つため、複数Quartワーカー構成では各ワーカーが独立したWS接続を持つ。現状シングルワーカー運用のため問題なし
