# ADR-020: ラウンジ 覇者称号未付与・結果モーダル未表示の修正

- **ステータス**: 採用
- **作成日**: 2026-05-23
- **作成者**: Wanyaldee
- **関連ADR**: [ADR-018](018-lounge-final-score-reporting.md), [ADR-019](019-lounge-mobile-ui.md)

---

## コンテキスト

Phase 3 のリリース後、2つのバグが報告された。

### バグ1: 1位でも覇者称号が付与されない

`_do_finish_session` が `TitleService.grant_rank(uid, new_mmr)` のみを呼んでいた。
`grant_rank` は `lounge_rank` タイプの称号（MMR閾値到達）を対象とするため、
`tournament_win` タイプの称号（大会・セッション優勝回数）は一切付与されなかった。
「覇者」は `tournament_win` タイプで登録されているため、1位でも付与されなかった。

### バグ2: 非ホストの結果モーダルが自動表示されない

ホストが終了確定を押すと Rust が `lounge.session_finished` WS イベントをブロードキャストする。
非ホスト側はこの WS イベントで `showResultModal()` を呼ぶ設計だったが、
WS メッセージの受信タイミングがずれた場合（接続直後・輻輳時）に確実に発火しなかった。
結果として手動リロードしなければモーダルが表示されないケースが発生した。

---

## 決定内容

### バグ1の修正

`_do_finish_session` 内でセッション1位のプレイヤー（`final_rank == 1`）を特定し、
`TitleService.grant_tournament_win(winner_uid)` を追加呼び出しする。

```python
winner_uid = next(
    (e.get("user_id") for e in results if e.get("final_rank") == 1),
    None,
)
# ...
if uid == winner_uid:
    win_ids = await TitleService.grant_tournament_win(uid)
    newly_granted_ids = list(set(newly_granted_ids + win_ids))
```

`grant_rank` と `grant_tournament_win` は独立した閾値テーブルを参照するため、
両方呼んでも副作用はなく、いずれかの条件を満たす称号のみが付与される。

### バグ2の修正

WS 単一経路への依存をやめ、**3つの独立した経路**で結果モーダルを表示する。

| 経路 | 発動条件 |
|-----|---------|
| WS `lounge.session_finished` | 正常ケース（即時） |
| ホスト: API レスポンス成功時 | WS より先に届く場合も確実に表示 |
| ポーリング `pollTick()` | WS 未着・切断時の補完（最大10秒） |

`resultModalShown` フラグで二重表示を防止。
`pollTick` 内で `/api/sessions/{id}/status` を呼び `finished` ならモーダルを開く。

---

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `discord_bot/routes/lounge.py` | `_do_finish_session` に `grant_tournament_win` 追加・`/api/sessions/{id}/status` エンドポイント追加 |
| `discord_bot/static/js/lounge.js` | `resultModalShown` フラグ・`pollTick` でのステータス確認追加 |

---

## トレードオフ

| 観点 | 内容 |
|-----|------|
| ポーリングの追加通信 | WS 切断中のみ発動・通常は 0 オーバーヘッド |
| `grant_tournament_win` の追加呼び出し | 副作用なし・既存称号テーブルの設計通り |
| `/status` エンドポイントの追加 | 軽量な GET のみ・DB 負荷は最小 |
