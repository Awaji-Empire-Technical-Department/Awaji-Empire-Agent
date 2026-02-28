# 🎮 東方憑依華専用：セキュア対戦ロビーシステム

- **ブランチ**: `feature/secure-lobby`
- **ステータス**: 設計中
- **作成日**: 2026-02-26
- **ADR**: [ADR-008](../adr/008-secure-lobby-system.md)

---

## 1. プロジェクト概要

対戦格闘ゲーム『東方憑依華 〜 Antinomy of Common Flowers.』における P2P 通信の安全性を高め、合言葉によるマッチングおよび大会運営を自動化するシステム。

### 核心設計原則

| 原則 | 実現方法 |
| :--- | :--- |
| 東方憑依華専用 | 12桁0埋めIP形式 + Cキー（Pad 3）入力に完全準拠 |
| 物理IP非露出 | Cloudflare WARP 仮想IP を Rust 側でフォーマット後のみ提供 |
| モード選択可能 | 自由対戦 / 大会モードを選択可能 |
| プライバシーポリシー | プライバシーポリシー同意を必須。同意履歴を `user_networks` に記録 |
| ダッシュボード無破壊 | 「📜 アンケート管理」カード直下に追加。既存CSS不変 |
| 運営兼プレイヤーモデル | Staff/Moderator は選手または運営補助として参加可能 |
| ホスト権限委譲 | 部屋作成者（Host）は他ユーザーに権限を譲渡可能 |

---

## 2. インフラ・アーキテクチャ

### 2.1 仮想ネットワーク

- **基盤**: Cloudflare WARP（Zero Trust）
- **IPレンジ**: `100.64.0.0/10`
- **UPnP**: 完全無効化。外部からのポート開放は不要

### 2.2 Cloudflare WebDashboard での手動設定作業

> [!IMPORTANT]
> 以下の設定はコードで自動化できない。Cloudflare ダッシュボード上での手動作業が必要。

| 作業 | 場所 | 詳細 | 該当環境変数 |
| :--- | :--- | :--- | :--- |
| WARP 有効化 | Zero Trust > Settings > Network | Split Tunnel から除外し全トラフィックをルーティング | - |
| Access Application 作成 | Zero Trust > Access > Applications | `dashboard.awajiempire.net` を Discord OAuth2 で保護 | - |
| Service Token 発行 | Zero Trust > Access > Service Auth | Rust Bridge がAPIを叩く際の認証トークン | `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` |
| API Token 発行 | My Profile > API Tokens | Zero Trust Read スコープ | `CLOUDFLARE_API_TOKEN` |
| アカウントID確認 | Dashboard 概要 | 32桁の英数字 | `CLOUDFLARE_ACCOUNT_ID` |

### 2.3 セキュリティ設計

- Discord OAuth2 スコープ `email` でユーザーのメールアドレスを取得し、Cloudflare API で照合して WARP 仮想 IP を引き当てる（ドメイン制限なし）
- フロントエンドへは `virtual_ip` を渡さず、フォーマット済み `gamelink` 文字列のみ渡す
- 運営者の権限操作はすべて `admin_logs` テーブルに記録

---

## 3. データベース設計

### 3.1 `user_networks`（ユーザー情報・WARPキャッシュ）

```sql
CREATE TABLE user_networks (
    discord_id  BIGINT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,       -- CF照合用
    virtual_ip  VARCHAR(15),                 -- 生の仮想IP (100.x.x.x)
    is_active   BOOLEAN DEFAULT FALSE,       -- WARP接続状態
    is_staff    BOOLEAN DEFAULT FALSE,       -- 運営権限フラグ
    agreed_at   TIMESTAMP NULL,             -- プライバシーポリシー同意日時
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.2 `matchmaking_rooms`（動的ロビー）

```sql
CREATE TABLE matchmaking_rooms (
    passcode            VARCHAR(32) PRIMARY KEY,
    host_id             BIGINT NOT NULL,
    mode                ENUM('free', 'tournament') DEFAULT 'free',
    title               VARCHAR(255) DEFAULT '新対戦ロビー', -- ロール名に使用
    description         TEXT NULL,                      -- 大会やロビーの任意の説明
    tournament_start_at TIMESTAMP NULL,
    is_approved         BOOLEAN DEFAULT FALSE,          -- ホストによる最終承認
    expires_at          TIMESTAMP NOT NULL,
    FOREIGN KEY (host_id) REFERENCES user_networks(discord_id)
);

-- ロビー参加者・役割管理
CREATE TABLE lobby_members (
    room_passcode VARCHAR(32),
    user_id       BIGINT,
    role          ENUM('player', 'staff') DEFAULT 'player',
    PRIMARY KEY (room_passcode, user_id),
    FOREIGN KEY (room_passcode) REFERENCES matchmaking_rooms(passcode) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user_networks(discord_id) ON DELETE CASCADE
);
```

### 3.3 `tournament_matches`（大会ブラケット）

```sql
CREATE TABLE tournament_matches (
    match_id     INT AUTO_INCREMENT PRIMARY KEY,
    room_passcode VARCHAR(32),
    player1_id   BIGINT,
    player2_id   BIGINT,
    winner_id    BIGINT NULL,
    status       ENUM('waiting', 'playing', 'finished') DEFAULT 'waiting',
    FOREIGN KEY (room_passcode) REFERENCES matchmaking_rooms(passcode) ON DELETE CASCADE
);
```

### 3.4 `admin_logs`（管理操作監査ログ）

```sql
CREATE TABLE admin_logs (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id   BIGINT NOT NULL,
    action     VARCHAR(64) NOT NULL,
    target_id  BIGINT,
    detail     TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. コア実装

### 4.1 GameLinkFormatter（東方憑依華専用）

`database_bridge/src/lobby/game_link.rs` に実装。

| 項目 | 値 |
|:---|:---|
| 入力 | `100.96.18.5`（CF仮想IP） |
| 出力 | `100.096.018.005:10800` |
| ロジック | 各セグメントを3桁ゼロ埋め + `:10800` を末尾付与 |
| ポート | `10800`（憑依華のデフォルト通信ポート） |

ゲーム内でCキー（Pad 3）を押した際に、この形式のみが正しく認識される（仮想IPを憑依華が認識可能な「12桁0埋め」形式に整形）。

### 4.2 Rust Bridge API エンドポイント

```text
GET    /lobby/rooms            ロビー一覧（gamelink のみ返す）
POST   /lobby/rooms            ロビー作成（mode, title, passcode, description）
DELETE /lobby/rooms/{passcode} ロビー削除
PATCH  /lobby/rooms/{passcode} ロビー更新（host_id 譲渡、is_approved 承認）
POST   /lobby/join             ロビー参加（role 指定）
GET    /lobby/members          参加者一覧
POST   /lobby/winner           勝者記録（Staff/Host only）
GET    /lobby/export           大会結果CSV出力（Staff/Host only）
GET    /admin/logs             監査ログ（Staff only）
```

> [!WARNING]
> `GET /lobby/rooms` は **絶対に** `virtual_ip` フィールドをレスポンスに含めてはならない。  
> Rust の `LobbyRoomResponse` struct に `virtual_ip` フィールドを持たせないことで型レベルで保証する。

### 4.3 非干渉 WebSocket 通信 (`/ws/hyouibana`)

既存のREST APIとは独立した `/ws/hyouibana` エンドポイントを新設。
ロビー内のステータス、対戦カード、観戦状況をリアルタイムでブロードキャストする。

- **通信方式:** WebSocket によるサーバープッシュ通知。
- **監視項目:**
  - Cloudflare WARP の接続ステータス（Active/Inactive）。
  - 仮想IPアドレスの変更検知。
- **UX:** ユーザーがページをリロードすることなく、最新の「対戦可能IP」を常に表示する。
- **プレイヤーの状態定義:**
  - `[⚪️ オフライン]`: アプリ未接続。まずはWARPをONにするよう促す。
  - `[🔵 オンライン]`: 準備完了。ロビーを眺めている状態。
  - `[🟢 受付中]`: ホスト待機中。「憑依する」ボタンが光る。
  - `[🔴 対戦中]`: 試合中。「観戦（IPコピー）」が可能。

---

## 5. モード別挙動

### 5.1 自由対戦モード (Free Battle)

- **ホスト宣言:** ユーザーが自ら「ホスト待機」を選択。
- **受付:** ホスト待機中のユーザーに対してのみIPコピーを許可。
- **観戦:** 対戦中であってもIPコピー（観戦）を制限せず、誰と誰が対戦中かを可視化。
- **完了報告:** 自由対戦時は勝敗報告の代わりに、ホストが「対戦終了」をシステムに通知することで、ロビーの空き状況をリアルタイム更新する。

### 5.2 大会モード (Tournament)

- **練習時間:** 開始時刻までは自由対戦モードとして動作。
- **本番開始:** 自動的にブラケット進行へ移行。システムが「Host(待機)」と「Client(参加)」を強制的かつ自動で指定。
  - ホストに指定された人が勝敗を報告し、その試合はクローズして次に進む。
- **可視化:** 本番時はトーナメント表（ブラケット）をわかりやすく可視化する。
  - ダッシュボードにアクセスできる人（淡路帝国サーバー加入者）は、途中参加はできないが、トーナメント表をダッシュボードから閲覧可能（フロントエンドは軽量JSライブラリ `Bracketry` 等を採用）。
- **Discord連携:** 最終勝者確定時、Botが自動で「優勝ロール」を付与。
- **Win Condition (自動変更):** 大会ごとに「n本先取」を設定可能。トーナメントの進行度（例：Finalのみ）に応じて勝利条件を自動変更する機能を保持。
- **バリデーション:** 設定された本数に満たない不正な報告をブロックし、運営の修正コストを最小化する。

---

## 6. フロントエンド UI/UX

### 6.1 配置方針とコンポーネント

- `discord_bot/templates/dashboard.html` の「📜 アンケート管理」カード直下に追加
- 既存の `.card`, `.btn`, `.badge`, `.table` クラスを完全に流用し、デザインの統一性を維持
- **独立設計**: 既存の `form.js` とは別の `possession_lobby.js` を作成し、WebSocketロジックや状態描画を独立させて動作させる。
- **WARPの接続案内**: 初めてアクセスする人には「Cloudflare WARPをインストールして、環境設定からZeroTrustで "awaji-empire" と入力してログインする」よう促す表示を追加。
- **ビジュアルガイド (インライン表示)**:
  - ホスト時: 「東方憑依華のNETWORKにて "対戦相手の接続を待つ" を選択してください。」
  - クライアント時: 「東方憑依華のNETWORKにて "接続先を指定して対戦相手の接続" を選択し、クリップボードのアドレスを入力 (Key C/Pad 3) を押してください。」
- **配信連携の推奨**: 「一人が観戦し、Discordで画面共有する」運用を、モーダル等ではなくインラインでしれっと推奨・表示する。

### 6.2 ロビー作成フォーム内容

- **ロビー名**: テキスト入力（デフォルト: {ユーザー名}のロビー）
- **合言葉**: テキスト入力（必須・半角英数字）
- **説明書き (任意)**: テキストエリア（大会のルールや概要などを自由に記述可能）
- **対戦モード**: ラジオボタン選択
  - `自由対戦`: 通常のP2P対戦用
  - `大会モード`: 進行管理・結果集計・承認フローが有効化
- **参加時オプション（大会モードのみ）**:
  - チェックボックスで役割を選択
    - `[ ] 選手として参加` (デフォルトON)
    - `[ ] スタッフとして参加` (モデレーター権限)
    - ※ 選手OFF/スタッフON で運営専念が可能
    - 両方ONで選手兼スタッフ

### 6.3 初回利用時：同意モーダル

`agreed_at IS NULL` のユーザーには、画面全体を覆うオーバーレイで同意を強制する。

**記載内容**:

- メールアドレスの利用目的（Cloudflare APIとの照合のみ）
- 同意しない場合はロビー機能を利用できない旨

### 6.3 特権操作オーバーレイ（Staff / Host 用）

`is_staff = TRUE` モジュールまたはロビー内の `Staff` 権限保持者には、以下を統合表示する。

- **勝敗操作**: 参加者の自己申告を修正・上書き
- **参加者管理**: 迷惑ユーザーの追放
- **大会結果のCSV出力**: 全試合の組み合わせと勝敗をCSV形式で取得可能
- **ホスト権限の譲渡**: 別の参加者にHost（承認者）の座を譲る
- **最終承認実行（Hostのみ）**:
  - 全ての決勝戦終了後、内容を確認して承認。実行時に優勝者にロールを付与し、結果を確定させる。
  - 優勝ロール名はデフォルトで `{ロビー名} 優勝` とするが、承認時に任意の名前に変更可能。

---

## 7. プライバシーと透明性

- **用途の限定**: メールアドレスは Cloudflare API との照合のみに使用。第三者への提供、マーケティング利用は行わない
- **技術ガイダンス**: 配信にてパワーポイントを用いたシステム解説を実施し、参加者が安心して利用できるよう周知する
- **監査**: 運営者による権限操作はすべて `admin_logs` に記録し、検証可能にする

---

## 8. ファイル追加・変更一覧

| 操作 | ファイル | 説明 |
| :--- | :--- | :--- |
| **新規** | `database_bridge/migrations/003_lobby_tables.sql` | 5テーブル追加（members追加） |
| **新規** | `database_bridge/src/lobby/game_link.rs` | GameLinkFormatter |
| **新規** | `database_bridge/src/db/lobby_repo.rs` | ロビーCRUD・権限操作 |
| **変更** | `database_bridge/src/db/models.rs` | 新struct追加 |
| **変更** | `database_bridge/src/main.rs` | ロビーエンドポイント追加 |
| **新規** | `discord_bot/routes/lobby.py` | Quart Blueprint（CSV出力対応） |
| **新規** | `discord_bot/services/lobby_service.py` | Rust Bridge APIラッパー |
| **新規** | `discord_bot/templates/lobby.html` | ロビーUI（役割選択・承認ボタン） |
| **新規** | `discord_bot/cogs/lobby/tournament.py` | 優勝ロール動的付与 |
| **変更** | `discord_bot/webapp.py` | `lobby_bp` 登録追加 |
| **変更** | `discord_bot/templates/dashboard.html` | ロビーカード挿入 |
