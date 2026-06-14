# ADR-026: ギルド未加入者のダッシュボード流入防止

- **ステータス**: 採用
- **作成日**: 2026-06-14
- **作成者**: Wanyaldee
- **関連**: [ADR-024](024-event-form-guild-bypass-share.md)

---

## コンテキスト

ADR-024 で、イベントフォームの回答フロー（`/form/<id>`）に限りギルド加入チェックを
スキップし、ギルド未加入の Discord アカウントでも回答できるようにした。

しかしこの緩和により、未加入者でもログインセッションを獲得できる状態となった。
一方でダッシュボード（`index`）のアクセス制御はログイン有無（`if not user`）しか
見ておらず、加入チェックを行っていなかった。

```python
# discord_bot/webapp.py index（旧実装）
user = session.get('discord_user')
if not user:
    return redirect(url_for('login'))
# ← 加入チェックが無く、未加入者でも素通りできる
```

結果として、**未加入者がフォーム回答後に「ホームへ戻る」ボタンを押す、あるいは
`/` を直接開くと、管理系のダッシュボードへアクセスできてしまう不具合**が判明した。
これは ADR-024 が「回答フローのみ緩和、管理系は加入必須」とした方針に反する。

---

## 決定内容

### 1. ログイン時に加入状態をセッションへ保持

`/callback` で対象ギルドへの加入有無を判定し、`session['is_guild_member']` に保存する。
回答フローでもギルド一覧の取得自体は行い、フラグを残す（未加入でも 403 にはしない）。

```python
# discord_bot/webapp.py /callback（新実装）
is_guild_member = True
if Config.TARGET_GUILD_ID:
    # ギルド一覧を取得して加入状態を判定
    is_guild_member = str(Config.TARGET_GUILD_ID) in guild_ids
    if not is_guild_member and not is_form_answer:
        return await render_template('access_denied.html'), 403
session['is_guild_member'] = is_guild_member
```

### 2. ダッシュボード側で未加入者を拒否（実効的なアクセス制御）

`index` で未加入フラグを確認し、未加入者は `access_denied`（403）を返す。
URL 直打ちでも突破できないサーバー側のガードとする。

```python
# discord_bot/webapp.py index（新実装）
if Config.TARGET_GUILD_ID and not session.get('is_guild_member', True):
    return await render_template('access_denied.html'), 403
```

### 3. 回答完了画面のボタンを無効化（UI）

`submitted.html` の「ホームへ戻る」ボタンを、未加入者に対しては `disabled` 化・
グレーアウトし、案内文を表示する。押せても 403 になるため、UX としても先回りで無効化する。

```
加入者     → 「ホームへ戻る」リンク（index へ）
未加入者   → disabled ボタン + 「このページはギルドメンバー専用です」案内
```

| 層 | 対象 | 役割 |
|---|---|---|
| セッション | `/callback` | 加入状態を `is_guild_member` として記録 |
| サーバーガード | `index` | 未加入者を 403 で拒否（実効的な防御） |
| UI | `submitted.html` | ボタン無効化（先回りの UX） |

---

## 既存セッションの扱い

既存のログイン済みセッションには `is_guild_member` キーが存在しない。
デフォルトを `True`（`session.get('is_guild_member', True)`）とし、次回ログイン時から
正しく判定させる。デフォルトを `False` にすると加入済みメンバーまで巻き込んで弾く
リスクがあるため、安全側に倒した。

---

## 検討した代替案

### UI のボタン無効化のみ

- **却下理由**: 未加入者が `/` を直接開けば素通りでき、根本解決にならない。
  サーバー側ガード（`index` の 403）を主とし、UI 無効化は補助に位置づける。

### ADR-024 のギルドチェック緩和を撤回

- **却下理由**: オフ会集計で未加入参加者を取りこぼさない、という ADR-024 の目的は
  依然有効。回答フローの緩和は維持しつつ、ダッシュボード側で個別に防ぐべき。

---

## 影響範囲

| 対象 | 変更内容 |
|---|---|
| `discord_bot/webapp.py` | `/callback` で `is_guild_member` をセッション保存、`index` で未加入者を 403 |
| `discord_bot/routes/survey.py` | `submit_response` で加入フラグを `submitted.html` へ渡す |
| `discord_bot/templates/submitted.html` | 未加入者向けに「ホームへ戻る」ボタンを無効化 |
