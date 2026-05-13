# マリオカートワールド ラウンジシステム

- **ブランチ**: `feature/general-tournament`（インフラ共通）
- **ステータス**: 設計中
- **作成日**: 2026-05-07
- **ADR**: [ADR-013](./adr/013-lounge-system.md)
- **運営サーバ**: 社畜天狗Discord サーバ「淡路帝国」

---

## 1. プロジェクト概要

マリオカートワールドのラウンジ運営を支援するシステム。  
汎用ゲーム大会システム（`FEATURE_GENERAL_TOURNAMENT.md`）とインフラを共有しつつ、ラウンジ固有のルール・ロジックを独立したモジュールとして実装する。

### インフラ共通・ロジック別の原則

```
[共通層]  プレイヤー管理 / DB基盤 / API基盤 / WebSocket / Discord連携
              ↑                              ↑
[大会モジュール]                    [ラウンジモジュール]
  単発イベント管理                    継続セッション管理
  シンプルなスコア計算                 ラウンジ独自配点
  ブラケット進行                      コース重複ペナルティ
                                      回線落ち仲裁・CPU点数
                                      チームtag・レート管理
```

---

## 2. 責任分界点

システムをゲーム側とWebアプリ側に明確に分ける。ゲーム側の情報はすべてプレイヤーの手動申告を経てWebアプリ側に取り込む。

> [!IMPORTANT]
> **自己申告方式を採用する理由**  
> Webアプリからマリオカートワールドのレースデータをリアルタイムに自動取得する公式手段は存在しない。  
> 強制的に取得しようとすると、通信の傍受・メモリ読み取り・非公開APIの不正利用といったハック的手法が必要となる。  
> これらはNintendo / マリオカートワールドの利用規約への違反、および不正競争防止法・著作権法等の法令に抵触する可能性が高い。  
> **本システムはいかなる形でもゲームの自動データ取得を行わない。プレイヤーの自己申告を唯一の入力経路とする。**

### ゲーム側の責任（マリオカートワールド本体）

| 責務 | 内容 |
|------|------|
| ルーム設定 | CPU強さ・アイテム設定・インターバル・人数 |
| レース実行 | コース選択・レース進行・順位決定 |
| 結果表示 | レース終了後の全プレイヤー順位画面 |
| 回線落ち検知 | 誰がいつ落ちたかをゲーム内で把握 |
| チームtag適用 | プレイヤー名へのtag付与（ゲーム内での名前変更） |

> [!NOTE]
> ゲーム側はWebアプリに何も送信しない。結果はすべてプレイヤーが目視してWebアプリに申告する。

### Webアプリ側の責任

| 責務 | 内容 |
|------|------|
| スコア計算 | 申告された順位 → 配点テーブルでポイント変換 |
| 累計ランキング管理 | 12レース分の合計ポイントを集計・表示 |
| コース重複ペナルティ判定 | 申告コース名の正規化・重複検出・通知 |
| 回線落ち仲裁 | 報告受付・CPU点数付与・5人以上でレース無効判定 |
| チーム管理 | 2v/3v時のチーム編成・tag登録・チームスコア合算 |
| プレイヤー管理 | Discord IDベースの参加者・レート管理 |
| セッション管理 | ラウンジセッションの開始・進行・終了 |

### 申告フロー（責任の受け渡し）

```
[ゲーム内でレース終了]
      ↓ プレイヤーが結果画面を目視
[各自がWebアプリに順位を入力・送信]
      ↓
[Webアプリがスコア計算・重複検知・ランキング更新]
      ↓
[Staff/Hostが承認 → 次レースへ]
```

---

## 3. ラウンジ基本ルール（FFA / 個人戦）

### 2.1 セッション設定

| 項目 | 値 |
|------|------|
| CPU強さ | 強い |
| レース数 | 12レース |
| アイテム | ノーマル |
| インターバル | 10秒 |
| キャラクター | 自由 |
| 最大参加人数 | 24人 |

### 2.2 コース管理

- ラウンジ内でのコース重複はペナルティ対象
- 単品レインボーロードと「ピーチスタジアム〜レインボーロード」は同一コースとして扱う

### 2.3 配点テーブル

| 順位 | 点数 |
|------|------|
| 1位 | 15点 |
| 2位 | 12点 |
| 3位 | 10点 |
| 4〜5位 | 9点 |
| 6〜7位 | 8点 |
| 8〜9位 | 7点 |
| 10〜12位 | 6点 |
| 13〜15位 | 5点 |
| 16〜18位 | 4点 |
| 19〜21位 | 3点 |
| 22〜23位 | 2点 |
| 24位 | 1点 |

### 2.4 回線落ち処理

- 落ちた際は**即時報告**が必要（報告遅延で誰が落ちたか不明になる）
- 基本処理: 使用していたCPUキャラクターの取得点数を付与
- **同一キャラクターで複数人が落ちた場合**: 先に報告した人に高い点数を付与
- **24人レースで5人以上落ちた場合**: そのレースは無効（ノーカウント）

---

## 4. チーム戦ルール（2v / 3v）

FFAルールに加え、以下を適用する。

### 3.1 チーム識別

- チームの代表者1名がtagを指定する
- 全チームメンバーはゲーム内の名前先頭にtagを付けて参加（例: `[ABC] プレイヤー名`）

### 3.2 スコア集計

- チームメンバーの個人スコアを合算してチームスコアとする
- チームスコアで順位を決定

### 3.3 チーム編成

- ラウンジ形式の場合はランダム編成が基本
- レートを申告してもらい、高レートと低レートを組み合わせる均等編成も可

### 3.4 ボイスチャット

本システムは社畜天狗Discordサーバ「淡路帝国」での運営を想定している。同サーバでは一般ユーザのボイスチャンネル利用が基本的に許可されていないため、ラウンジ中のボイスチャットは原則行わない。

希望者がボイスチャットを使用する場合は、淡路帝国とは別のDiscordサーバ（参加者間で調整）で行うこととする。本システムはボイスチャットの管理・連携を担わない。

---

## 5. データベース設計（ラウンジ固有テーブル）

共通インフラのテーブルは `FEATURE_GENERAL_TOURNAMENT.md` §3 を参照。  
以下はラウンジモジュールが追加・管理するテーブル。

### 4.1 `lounge_sessions`（ラウンジセッション）

```sql
CREATE TABLE lounge_sessions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    room_id         INT NOT NULL,                       -- matchmaking_rooms.id（共通インフラ）
    mode            ENUM('ffa', '2v', '3v') NOT NULL DEFAULT 'ffa',
    total_races     TINYINT NOT NULL DEFAULT 12,
    current_race    TINYINT NOT NULL DEFAULT 0,
    status          ENUM('waiting', 'in_progress', 'finished') DEFAULT 'waiting',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES matchmaking_rooms(id)
);
```

### 4.2 `lounge_race_results`（レース結果）

```sql
CREATE TABLE lounge_race_results (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT NOT NULL,
    race_number     TINYINT NOT NULL,                   -- 第何レースか（1〜12）
    course_name     VARCHAR(128) NOT NULL,
    is_void         BOOLEAN DEFAULT FALSE,              -- 5人以上落ちで無効
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id)
);
```

### 4.3 `lounge_race_scores`（個人スコア）

```sql
CREATE TABLE lounge_race_scores (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    race_result_id  BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    position        TINYINT,                            -- NULL = 回線落ち
    points          INT NOT NULL DEFAULT 0,
    is_disconnect   BOOLEAN DEFAULT FALSE,
    disconnect_reported_at DATETIME NULL,               -- 報告タイムスタンプ（同キャラ落ち仲裁用）
    FOREIGN KEY (race_result_id) REFERENCES lounge_race_results(id)
);
```

### 4.4 `lounge_teams`（チーム編成 / 2v・3v用）

```sql
CREATE TABLE lounge_teams (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT NOT NULL,
    tag             VARCHAR(16) NOT NULL,
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id)
);

CREATE TABLE lounge_team_members (
    team_id         BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES lounge_teams(id)
);
```

### 4.5 `lounge_course_history`（コース使用履歴 / 重複ペナルティ用）

```sql
CREATE TABLE lounge_course_history (
    session_id      BIGINT NOT NULL,
    course_key      VARCHAR(64) NOT NULL,               -- 正規化済みコース識別子
    PRIMARY KEY (session_id, course_key),
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id)
);
```

> [!NOTE]
> `course_key` はコース名を正規化した値。単品レインボーロードと「ピーチスタジアム〜レインボーロード」は同一の `course_key = 'rainbow_road'` として登録する。

---

## 6. ラウンジ固有ロジック

### 5.1 配点計算

`FEATURE_GENERAL_TOURNAMENT.md` §3.4 の `point_tables` は汎用配点マスタ。  
ラウンジ独自の配点（§2.3）は `point_tables` に `lounge_ffa` として登録し、ラウンジモジュールのみが参照する。

### 5.2 コース重複ペナルティ判定

```
コース選択時:
  course_key を正規化
  lounge_course_history に同 session_id + course_key が存在する → ペナルティ通知
  存在しない → 登録して続行
```

### 5.3 回線落ち仲裁フロー

```
落ち報告受信:
  disconnect_reported_at を記録
  同レース・同キャラの落ち報告が複数存在するか確認
    単独 → CPUの取得点数をそのまま付与
    複数 → disconnect_reported_at が早い順に高い点数を付与
  is_void 判定: そのレースの落ち人数 >= 5 → is_void = TRUE、スコア全員0
```

### 5.4 チームスコア集計（2v/3v）

```
lounge_race_scores を session_id + race_number でグループ化
  → チームメンバーの points を合算
  → チームスコアで順位決定
```

---

## 7. API エンドポイント（ラウンジ固有）

共通APIは `FEATURE_GENERAL_TOURNAMENT.md` §4 を参照。

```text
# セッション管理
POST   /lounge/sessions                          セッション作成（mode, total_races）
GET    /lounge/sessions/{id}                     セッション状態取得
PATCH  /lounge/sessions/{id}/next-race           次のレースへ進める（Staff/Host）

# レース結果
POST   /lounge/sessions/{id}/races               レース追加（course_name）
POST   /lounge/races/{race_id}/scores/report     個人スコア申告（position）
POST   /lounge/races/{race_id}/disconnect        回線落ち報告

# チーム管理（2v/3v）
POST   /lounge/sessions/{id}/teams               チーム作成（tag, member_ids）
GET    /lounge/sessions/{id}/teams               チーム一覧取得

# ランキング
GET    /lounge/sessions/{id}/standings           累計ポイントランキング（FFA）
GET    /lounge/sessions/{id}/team-standings      チームスコアランキング（2v/3v）
GET    /lounge/sessions/{id}/course-history      コース使用履歴（重複確認用）
```

---

## 8. ファイル追加・変更一覧

| 操作 | ファイル | 説明 |
|------|------|------|
| **新規** | `database_bridge/migrations/005_lounge.sql` | ラウンジ固有テーブル追加 |
| **新規** | `database_bridge/src/lounge/mod.rs` | ラウンジロジック（配点・回線落ち仲裁・コース重複） |
| **新規** | `database_bridge/src/db/lounge_repo.rs` | ラウンジ用DBクエリ |
| **変更** | `database_bridge/src/db/models.rs` | ラウンジ用struct追加 |
| **変更** | `database_bridge/src/main.rs` | `/lounge/*` エンドポイント追加 |
| **新規** | `discord_bot/routes/lounge.py` | ラウンジ Blueprint |
| **新規** | `discord_bot/services/lounge_service.py` | Rust Bridge APIラッパー |
| **新規** | `discord_bot/templates/lounge.html` | ラウンジ進行UI |
| **新規** | `discord_bot/static/js/lounge.js` | スコア入力・ランキング更新 |
| **変更** | `discord_bot/webapp.py` | `lounge_bp` 登録 |

---

## 9. 備考・未決事項

- 回線落ちの「CPUキャラの取得点数」はゲーム内結果から手動申告とするか、CPUキャラ名から自動推定するか
- コース重複ペナルティの具体的な処置内容（警告のみか、スコア減算か）
- 2v/3v時のチーム数上限
- レートシステムの詳細設計（初期レート・上下幅・算出式）
