# 🏆 汎用ゲーム大会システム

- **ブランチ**: `feature/general-tournament`
- **ステータス**: 設計中
- **作成日**: 2026-04-26
- **ADR**: [ADR-011](../docs/adr/011-general-tournament-system.md)

---

## 1. プロジェクト概要

遊び大全・マリオカートをはじめとする任意のゲームタイトルで大会を開催できる汎用トーナメントシステム。  
東方憑依華専用ロビーシステム（`feature/secure-lobby`）の大会運営コアを流用しつつ、ゲーム固有のIP接続管理を排除し、スコア制・多人数マッチに対応した汎用設計とする。

### 核心設計原則

| 原則 | 実現方法 |
| :--- | :--- |
| ゲーム内完結 | スコア計算・勝敗判定はゲーム本体に任せる。システムはゲームが表示した結果を受け取るだけ |
| 最小申告 | 申告は「ゲームの結果画面に表示された数字を入力するだけ」。計算・判断をプレイヤーに求めない |
| ダッシュボード専念 | Webダッシュボードはトーナメントの進行管理（申告受取・承認・ブラケット更新）に特化する |
| 汎用性 | ゲームタイトルをDBに登録し、任意タイトルで大会作成可能 |
| 多人数マッチ対応 | 1対1〜最大24人のマッチフォーマットをサポート |
| IP非依存 | Cloudflare WARP不要。Discord IDのみで参加者管理 |
| 流用コア | ブラケット進行・Discord優勝ロール付与・Staff権限体系は既存実装を再利用 |

### 流用・非流用の整理

| コンポーネント | 流用 | 備考 |
| :--- | :---: | :--- |
| `matchmaking_rooms` テーブル構造 | ✅ | ゲーム種別カラムを追加 |
| `tournament_matches` テーブル | ✅ | スコア記録カラムを追加 |
| `lobby_members` テーブル | ✅ | そのまま流用 |
| `admin_logs` テーブル | ✅ | そのまま流用 |
| ブラケット進行ロジック | ✅ | 多人数マッチ対応に拡張 |
| Discord優勝ロール付与 | ✅ | そのまま流用 |
| Staff/Host権限体系 | ✅ | そのまま流用 |
| Bracketryブラケット可視化 | ✅ | そのまま流用 |
| Cloudflare WARP / 仮想IP管理 | ❌ | 不要。削除 |
| GameLinkFormatter | ❌ | 東方憑依華専用。不使用 |
| `user_networks`のWARP関連カラム | ❌ | メール照合・IP管理列は不要 |
| WebSocket IP変更監視 | ❌ | 不要。参加者状態管理のみに変更 |

---

## 2. 対応ゲームタイトルと試合形式

### 2.1 試合形式の分類

| 形式 | 対応ゲーム例 | 勝利条件 |
| :--- | :--- | :--- |
| `1v1` | 遊び大全（囲碁・将棋・オセロ等） | 勝敗（n本先取） |
| `multiplayer` | マリオカート（最大12人） | ポイント合計（レース順位積算） |

### 2.2 トーナメント形式

| 形式 | 説明 |
| :--- | :--- |
| `single_elimination` | シングルイリミネーション（負けたら終了） |
| `round_robin` | 総当たり戦 |
| `swiss` | スイス式（将来実装候補） |

---

## 3. データベース設計

既存テーブルを流用・拡張する。新規テーブルのみ追加。

### 3.1 `game_titles`（対応ゲームマスタ） ★新規

```sql
CREATE TABLE game_titles (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,           -- 例: 'マリオカート8DX', '遊び大全'
    match_type      ENUM('1v1', 'multiplayer') NOT NULL,
    max_players     TINYINT NOT NULL DEFAULT 2,     -- マリカなら12、1v1なら2
    score_type      ENUM('win_loss', 'point_sum') NOT NULL,
    -- win_loss: n本先取勝敗制 / point_sum: 順位ポイント積算制
    is_active       BOOLEAN DEFAULT TRUE
);

-- 初期データ
INSERT INTO game_titles (name, match_type, max_players, score_type) VALUES
    ('マリオカート8 デラックス', 'multiplayer', 12, 'point_sum'),
    ('遊び大全',                '1v1',          2, 'win_loss'),
    ('その他',                  '1v1',          2, 'win_loss');
```

### 3.2 `matchmaking_rooms` 拡張（既存テーブルに追加）

```sql
ALTER TABLE matchmaking_rooms
    ADD COLUMN game_title_id    INT NULL AFTER mode,
    ADD COLUMN bracket_format   ENUM('single_elimination', 'round_robin') DEFAULT 'single_elimination' AFTER game_title_id,
    ADD COLUMN wins_required    TINYINT DEFAULT 1 AFTER bracket_format,
    -- point_sum 形式では「何レース行うか」として解釈
    ADD FOREIGN KEY (game_title_id) REFERENCES game_titles(id);
```

### 3.3 `tournament_matches` 拡張（既存テーブルに追加）

```sql
ALTER TABLE tournament_matches
    ADD COLUMN round            TINYINT NOT NULL DEFAULT 1 AFTER room_passcode,
    ADD COLUMN match_order      TINYINT NOT NULL DEFAULT 1 AFTER round;
    -- ブラケット内の何戦目かを管理

-- 多人数マッチのスコア記録（player2_id/winner_idは1v1専用に留め、multiplayer は本テーブルで管理）
CREATE TABLE match_scores (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    match_id        INT NOT NULL,
    user_id         BIGINT NOT NULL,
    position        TINYINT NOT NULL,               -- 順位（1位=1）
    points          INT NOT NULL DEFAULT 0,         -- ポイント（point_sum形式で使用）
    FOREIGN KEY (match_id) REFERENCES tournament_matches(match_id) ON DELETE CASCADE
);
```

### 3.4 `point_tables`（ポイント配点マスタ） ★新規

```sql
-- マリオカートなど順位ポイント制のゲーム用
CREATE TABLE point_tables (
    game_title_id   INT NOT NULL,
    position        TINYINT NOT NULL,               -- 順位
    points          INT NOT NULL,                   -- 付与ポイント
    PRIMARY KEY (game_title_id, position),
    FOREIGN KEY (game_title_id) REFERENCES game_titles(id)
);

-- マリオカートのデフォルト配点（公式準拠）
INSERT INTO point_tables (game_title_id, position, points)
SELECT id, pos, pts FROM game_titles
CROSS JOIN (VALUES
    (1,15),(2,12),(3,10),(4,9),(5,8),
    (6,7),(7,6),(8,5),(9,4),(10,3),(11,2),(12,1)
) AS v(pos, pts)
WHERE name = 'マリオカート8 デラックス';
```

---

## 4. API エンドポイント

既存ロビーAPIを拡張する形で追加する。

```text
# ゲームタイトルマスタ
GET    /tournament/games                              対応ゲーム一覧

# 大会ルーム（既存 /lobby/rooms を拡張して兼用）
POST   /lobby/rooms                                   game_title_id, bracket_format, wins_required を追加パラメータ化
GET    /lobby/rooms/{passcode}/bracket                ブラケット状態取得（Bracketry用JSON）

# 結果自己申告（プレイヤー操作）
POST   /tournament/matches/{match_id}/report          1v1: 勝者を自己申告
POST   /tournament/matches/{match_id}/scores/report   multiplayer: 自分の順位を申告

# Staff承認操作
PATCH  /tournament/matches/{match_id}/approve         申告内容を承認 → 結果確定・次戦進行（Staff/Host only）
PATCH  /tournament/matches/{match_id}/reject          申告を差し戻し → 再申告を促す（Staff/Host only）
PATCH  /tournament/matches/{match_id}/override        Staff直接修正（申告内容を上書き）（Staff/Host only）

# ランキング
GET    /tournament/rooms/{passcode}/standings         総合ポイントランキング取得（multiplayer用）
```

---

## 5. 自己申告と承認フロー

### 5.1 申告ステータス管理

`tournament_matches.status` を以下に拡張する。

| ステータス | 意味 |
| :--- | :--- |
| `waiting` | 試合未開始 |
| `playing` | 試合中（申告待ち） |
| `pending` | 申告済み・Staff承認待ち |
| `disputed` | 申告内容に矛盾あり・要確認 |
| `finished` | Staff承認済み・確定 |

`match_scores.status` も同様に申告の個別状態を管理する（multiplayer用）。

### 5.2 1v1 モード（遊び大全等）

ゲーム本体が勝者を決定する。プレイヤーはゲームの結果をそのまま申告する。

```
① 試合開始（status: playing）
② 勝者が「自分が勝った」をダッシュボードからワンタップ申告
   ※ ゲーム内ですでに決着しているため、勝者以外の操作は不要
   → status: pending
③ Staffが内容を確認
   - 承認 → status: finished、次戦へ自動進行
   - 差し戻し → status: playing、再申告を促す（申告者に通知）
   - 直接修正 → Staff指定の勝者で確定
④ 全試合終了 → Hostが最終承認 → 優勝ロール自動付与
```

- `wins_required` で n本先取を設定。申告数が規定本数に満たない場合はバリデーションでブロック。
- 申告UIは「自分が勝った」の一択。負け申告UIは設けない（誤操作防止）。

### 5.3 multiplayer モード（マリオカート等）

ゲーム本体がレース結果画面で全員の順位を表示する。プレイヤーはその画面を見て自分の順位を入力するだけ。

```
① レース開始（status: playing）
② 各プレイヤーが結果画面に表示された「自分の順位」を入力して申告
   ※ ゲームがすでに順位を表示しているため、計算は不要
   → 全員申告済みで status: pending
   → 順位の重複検出時は status: disputed（矛盾あり）
③ Staffが内容を確認
   - 申告に矛盾なし → 承認（status: finished）
     → `point_tables` に基づきポイントを自動集計、ランキング更新
   - 矛盾あり（disputed）→ 直接修正して確定、または差し戻して再申告
④ 設定レース数が終了 → 総合ポイントで最終順位確定
⑤ Hostが最終承認 → 優勝ロール自動付与
```

- **レース数設定**: `wins_required` をレース数として解釈（例: 12レース）
- **自動集計**: `point_tables` の配点に基づきポイントを自動加算。プレイヤーが計算する必要はない
- **同点処理**: 同点の場合は最高順位回数が多い方を上位とする（設定で変更可能）
- **ダッシュボード表示**: bracket ビューではなく、レース別順位テーブル＋累計ポイントランキングを表示

---

## 6. フロントエンド UI/UX

### 6.1 大会作成フォーム（既存ロビー作成フォームを拡張）

```
- ゲームタイトル: ドロップダウン選択（game_titles から動的取得）
- ロビー名: テキスト入力
- 合言葉: テキスト入力（必須）
- 説明書き: テキストエリア
- 対戦形式: ラジオ（シングルイリミネーション / 総当たり）
  ※ multiplayer タイトルは総当たりのみ選択可
- n本先取 / レース数: 数値入力（デフォルト: 1）
```

### 6.2 大会進行ビュー

| タイトル種別 | 表示コンポーネント |
| :--- | :--- |
| `1v1` | Bracketry によるブラケット図 |
| `multiplayer` | ポイントランキングテーブル + レース別申告状況一覧 |

### 6.3 自己申告UI（プレイヤー向け）

申告UIはゲームの結果をそのまま転記できるよう、入力項目を最小限に絞る。

**1v1:**
- 担当試合カードに「✅ 自分が勝った」ボタンのみ表示
- 押下後は「📋 承認待ち」バッジに切り替わり、再申告不可
- 差し戻し時のみ再度ボタンが表示される

**multiplayer（マリオカート等）:**
- 担当レースカードに「自分の順位」ドロップダウン（1〜参加人数）のみ表示
- **入力はゲームの結果画面を見て数字を選ぶだけ**。計算・判断は不要
- 送信後は「📋 承認待ち」表示に切り替わり、他プレイヤーの申告状況も表示
- 全員申告完了で自動的に `pending` へ移行
- 重複検出時は即時 `disputed` 表示に切り替わり、Staffへ通知

### 6.4 ダッシュボード進行ビュー

ダッシュボードはトーナメントの「いま何戦目か」と「誰が進んでいるか」の把握に特化する。

**1v1:**
- Bracketry によるブラケット図（承認済み試合は勝者名が入る）
- 現在進行中の試合を上部に強調表示

**multiplayer（マリオカート等）:**
- 累計ポイントランキングテーブル（レースごとに更新）
- レース別順位テーブル（何レース目に誰が何位か）
- 残りレース数カウンター

### 6.5 承認オーバーレイ（Staff/Host 用）

- 申告済み（`pending` / `disputed`）の試合・レース一覧をまとめて表示
- 各エントリに「✅ 承認」「↩️ 差し戻し」「✏️ 直接修正」の3アクション
- `disputed` のエントリは赤くハイライトして最上部に優先表示
- 承認操作はすべて `admin_logs` に記録

---

## 7. ファイル追加・変更一覧

| 操作 | ファイル | 説明 |
| :--- | :--- | :--- |
| **新規** | `database_bridge/migrations/004_general_tournament.sql` | `game_titles`, `match_scores`, `point_tables` テーブル追加 + 既存テーブル拡張 |
| **新規** | `database_bridge/src/tournament/mod.rs` | 汎用トーナメントロジック |
| **新規** | `database_bridge/src/db/tournament_repo.rs` | スコア記録・ランキング集計クエリ |
| **変更** | `database_bridge/src/db/models.rs` | `GameTitle`, `MatchScore`, `PointTable` struct追加 |
| **変更** | `database_bridge/src/main.rs` | `/tournament/*` エンドポイント追加 |
| **新規** | `discord_bot/routes/tournament.py` | 汎用大会 Blueprint |
| **新規** | `discord_bot/services/tournament_service.py` | Rust Bridge APIラッパー（スコア送信・ランキング取得） |
| **新規** | `discord_bot/templates/tournament.html` | 大会進行UI（ブラケット / ランキングビュー切替） |
| **新規** | `discord_bot/static/js/tournament.js` | スコア入力・ランキング更新ロジック |
| **変更** | `discord_bot/webapp.py` | `tournament_bp` 登録 |
| **変更** | `discord_bot/templates/dashboard.html` | 大会管理カード追加 |
