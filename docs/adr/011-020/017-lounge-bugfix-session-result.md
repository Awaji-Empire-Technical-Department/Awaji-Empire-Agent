# ADR-017: ラウンジシステム バグ修正・セッション結果表示の実装

- **ステータス**: 採用
- **作成日**: 2026-05-22
- **作成者**: Wanyaldee
- **関連ADR**: [ADR-013](013-lounge-system.md), [ADR-016](016-lounge-ux-realtime-improvements.md)

---

## コンテキスト

ADR-016 実装後のテスト中に以下の不具合と課題が判明した。

1. **Rust Bridge クラッシュ**: `GET /lounge/sessions/{id}/standings` を呼ぶとサーバーが "disconnected without sending a response" で落ちる
2. **順位申告がリアルタイムで他プレイヤーに反映されない**: WS受信後にHTTPフェッチを挟む設計のため遅延・不確実性がある。またWS切断後の再接続ロジックがなく、サーバー再起動後に更新が永久に止まる
3. **12レース上限を超えてセッションが継続**: `next_race` がDB上でセッションをfinishedにしても誰にも通知されず、ホストが無限にレースを作成できる
4. **提出状況でDiscord IDとユーザーネームが別エントリとして重複表示**: JSのIEEE 754浮動小数点精度損失によるキー不一致
5. **モーダルから抜け出せない**: WS経由のイベント受信だけがモーダルを閉じる唯一の経路であり、WS断絶・イベント取りこぼし時に永久にハマる
6. **セッション終了後の結果が貧弱**: MMRのみ表示でセッション内順位・ポイントが確認できない。10秒カウントダウンもなかった

---

## 決定した設計

### 1. Rust Bridge クラッシュの修正（SUM型パニック）

**原因**: `get_session_standings` / `get_team_standings` クエリで `SUM(points)` を使用していたが、MySQLの `SUM(INT)` は DECIMAL 型を返す。sqlx の `Row::get::<Option<i64>>()` は型不一致時に `panic!()` を呼ぶため、Tokio タスクが異常終了しコネクションが切断された。

**修正**: SQL側で `CAST(COALESCE(SUM(...), 0) AS SIGNED)` に変更し、DECIMAL→SIGNED INTEGER に明示的にキャストすることでデコードエラーを回避した。

```sql
-- 変更前
SUM(lrs.points) as total_points

-- 変更後
CAST(COALESCE(SUM(lrs.points), 0) AS SIGNED) as total_points
```

同様の修正を `COUNT(CASE WHEN ...)` にも適用した（MySQLのCOUNT戻り値はBIGINTだが、CAST統一で将来の型変更に対応）。

**採用しなかった案**:
- `Row::try_get()` でエラーを捕捉 → パニックを抑制できるが、型不一致の根本原因を残す
- `sqlx::types::Decimal` で受け取る → 依存クレートが増え、単純な整数演算に不要

---

### 2. 順位申告のWS即時反映・自動再接続

**変更前の問題**:
- `lounge.score_reported` 受信 → `loadSubmissions(raceId)` でHTTPフェッチ → DB読み取り → 描画という3ホップ
- WS接続が切れた場合の `close` ハンドラが未実装のため、サーバー再起動後に更新が完全に停止する

**変更後の設計**:

Rust側のWS発火メッセージに申告データを含める:
```json
{
  "type": "lounge.score_reported",
  "race_id": 42,
  "user_id": "123456789012345678",
  "position": 3,
  "is_disconnect": false
}
```

JS側はWS受信時にHTTPフェッチなしで直接 `submissionState` を更新して再描画:
```js
submissionState[String(msg.user_id)] = {
    submitted: true,
    position: msg.position ?? null,
    is_disconnect: msg.is_disconnect ?? false,
};
renderSubmissions();
```

WS自動再接続:
```js
ws.addEventListener('close', () => {
    wsReconnectTimer = setTimeout(connectWs, 3000);
});
```

**採用しなかった案**:
- HTTPポーリング（1秒間隔）→ サーバー負荷増加・即時性が劣る
- SSE（Server-Sent Events）→ 双方向通信が不要なこの文脈では過剰。既存WSインフラを活用する方が一貫性が高い

---

### 3. Discord user_id の精度損失バグ

**原因**: Discord Snowflake ID は最大18桁の整数。JSON数値としてJSが受け取ると `Number()` でIEEE 754 の仮数部53ビットを超え精度が落ちる（例: `123456789012345678` → `123456789012345680`）。Jinja2テンプレートで文字列として埋め込まれた `MEMBERS` 辞書のキーと不一致になり、同一ユーザーが「ID番号」と「ユーザーネーム」の2エントリとして表示された。

**修正**: Rust側の全WS発火メッセージおよびAPI応答で `user_id` を `i64.to_string()` で文字列化。JS側の `String(msg.user_id)` は文字列→文字列変換になり精度損失が発生しない。

対象:
- `lounge.score_reported` / `lounge.disconnect_reported` WS メッセージ
- `list_race_scores_named` / `list_session_members` / `get_session_standings` API レスポンス

---

### 4. 12レース上限の自動セッション終了

**問題**: `advance_session_race` はDBのステータスを `finished` に更新するが、そのことを誰にも通知しない。ホストのボタンUI（「レース開始」）はセッションステータスを見ておらず、上限後も無限にレースを作成できた。

**修正の二層構成**:

**層1 - ガード（Rust `create_race` ハンドラ）**:
```rust
if session.current_race >= session.total_races {
    return (StatusCode::FORBIDDEN, Json(json!({
        "status": "error",
        "message": "レース上限に達しています"
    })));
}
```

**層2 - 自動終了（Python `api_finalize_race`）**:
```python
ok2 = await LoungeService.next_race(session_id)
updated = await LoungeService.get_session(session_id)
if updated and updated.get("status") == "finished":
    await _do_finish_session(session_id)  # 称号付与・WS発火を含む完全な終了フロー
```

`_do_finish_session()` は従来の `api_finish_session` のロジックをヘルパー関数に切り出し、手動終了ボタンと自動終了の両方から呼べるように共通化した。

**Rust `next_race` ハンドラに `session_finished` を直接発火させなかった理由**:
- Rust側では称号付与・Discordロール同期が実行できない（Discord API呼び出しはPython側に集約する方針: ADR-013参照）
- Python finishフロー（`_do_finish_session`）の中でRust `POST /lounge/sessions/{id}/finish` を経由してWSが発火するため、二重発火になる

---

### 5. セッション終了時の詳細結果モーダル

**旧実装の問題**:
- `GET /lounge/api/me` でMMRとランク名のみ表示
- セッション内での順位・獲得ポイントが不明
- 15秒後自動遷移のみでカウントダウン表示がなかった

**新エンドポイント `GET /lounge/api/sessions/{id}/my-result`**:

| フィールド | 内容 |
|---|---|
| `rank` | セッション内順位（standings内の自分のインデックス+1） |
| `total_points` | 承認済み合計ポイント |
| `total_players` | セッション参加者数 |
| `mmr` | 現在のMMR |
| `rank_name` | `unlock_type=lounge_rank` の称号のうち最高閾値のもの |
| `is_winner` | `rank == 1` フラグ |

**結果モーダルの表示内容**:
- セッション内順位（大きく表示）
- 合計ポイント / MMR（2カラム）
- 現在のランク称号
- 優勝時: ヘッダーをゴールドに変更、「覇者」「連覇の王」の取得可能性を案内
- 10秒カウントダウン → ダッシュボードへ自動遷移（ボタンでも即時遷移可）

**非ホスト向け「承認待ち」インライン表示**:
全員が提出済みになった時点で `modal-waiting-host` div を表示し、ホストが「結果確定」を押すまで待機していることを明示する。

**MMR変動の「見込み」表示を実装しなかった理由**:
MMR計算式が未定義のため（`update_mmr()` 関数は存在するが呼び出し元なし）、確定値ではなく「見込み」と明示することも精度担保ができない。MMR更新ロジックは別ADRで定義する。

---

### 6. モーダル脱出不能バグの修正

**原因分析**:

モーダルを閉じる経路がWS `lounge.race_advanced` / `lounge.session_finished` イベント受信のみだった。以下の状況でハマる:
- WS切断後に再接続したが、切断中に発生したイベントはリプレイされない
- テスト中のサーバー再起動でWS接続が途切れた状態
- ホストのAPIリクエストは成功しているがWS未到着（ネットワーク遅延）

**修正した3つの脱出経路**:

| 経路 | 対象 | 実装 |
|---|---|---|
| ×ボタン | 全員 | モーダルヘッダー右上に常時表示 |
| オーバーレイクリック | 全員 | `e.target === overlay` 判定でモーダル本体クリックと区別 |
| finalize API成功 | ホストのみ | `data.status === 'ok'` 時点で即座に `hideModal()` を呼ぶ（WS到着を待たない） |

ゲストについては×ボタン・オーバーレイクリックが脱出手段となる。WS経由でのクローズは引き続き動作し、閉じたあとに次のレースのモーダルが自動で開く通常フローは変わらない。

---

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `database_bridge/src/api/handlers/lounge.rs` | 修正・機能追加 | WS user_id文字列化、score_reported/disconnect_reported にposition追加、create_raceガード、next_race後のsession_finished自動発火（削除） |
| `database_bridge/src/db/lounge_repo.rs` | 修正 | SUM/COUNTをCAST修正、user_id文字列化（standings・members・scores） |
| `discord_bot/routes/lounge.py` | 修正・機能追加 | api_finalize_raceに自動finish、_do_finish_sessionヘルパー切り出し、my-resultエンドポイント追加 |
| `discord_bot/templates/lounge.html` | 修正 | 結果モーダルの全面刷新、モーダルに×ボタン追加、承認待ちインライン表示追加 |
| `discord_bot/static/js/lounge.js` | 修正・機能追加 | WS直接state更新、自動再接続、showResultModal刷新、×ボタン/オーバーレイ/finalize即時クローズ |

---

## 結果

- Rust Bridge の standings クラッシュが解消され、WS接続が安定した
- 順位申告がWS経由でHTTPフェッチなしに即時反映されるようになった
- WS断絶後3秒で自動再接続し、リアルタイム性が回復するようになった
- Discord IDの重複表示バグが解消された
- 12レース完了時にセッションが自動終了し、結果モーダルが全員に表示されるようになった
- セッション内順位・ポイント・MMR・優勝演出を含む詳細な結果モーダルが実装された
- 何らかの理由でモーダルに閉じ込められた際の脱出手段が複数確保された

## トレードオフ・既知の制限

- 「覇者」「連覇の王」称号の実際の付与ロジックは未実装。モーダル上のメッセージ表示のみで、実際のタイトル付与はタイトルシステム側への追加が必要
- MMRの変動はセッション終了フローで自動計算されず、現在値をそのまま表示している。MMR計算式の定義と `update_mmr()` の統合は別途対応が必要
- モーダルを×ボタンで閉じた後に `lounge.race_advanced` WS が届くと `hideModal()` が呼ばれるが、既に閉じているため実害はない
