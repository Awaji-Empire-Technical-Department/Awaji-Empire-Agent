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
|:---|:---|
| 東方憑依華専用 | 12桁0埋めIP形式 + Cキー（Pad 3）入力に完全準拠 |
| 物理IP非露出 | Cloudflare WARP 仮想IP を Rust 側でフォーマット後のみ提供 |
| ダッシュボード無破壊 | 「📜 アンケート管理」カード直下に追加。既存CSS不変 |
| 運営兼プレイヤーモデル | Staff は選手として参加しながら管理も行える |

---

## 2. インフラ・アーキテクチャ

### 2.1 仮想ネットワーク

- **基盤**: Cloudflare WARP（Zero Trust）
- **IPレンジ**: `100.64.0.0/10`
- **UPnP**: 完全無効化。外部からのポート開放は不要

### 2.2 Cloudflare WebDashboard での手動設定作業

> [!IMPORTANT]
> 以下の設定はコードで自動化できない。Cloudflare ダッシュボード上での手動作業が必要。

| 作業 | 場所 | 詳細 |
|:---|:---|:---|
| WARP 有効化 | Zero Trust > Settings > Network | Split Tunnel から除外し全トラフィックをルーティング |
| Access Application 作成 | Zero Trust > Access > Applications | `dashboard.awajiempire.net` を Discord OAuth2 で保護 |
| Service Token 発行 | Zero Trust > Access > Service Auth | Rust Bridge がAPIを叩く際の認証トークン |
| CF API Token 発行 | My Profile > API Tokens | Zero Trust Read スコープ。`.env` の `CLOUDFLARE_API_TOKEN` に設定 |

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
    host_id             BIGINT NOT NULL UNIQUE,         -- 1ユーザー1部屋制
    is_tournament       BOOLEAN DEFAULT FALSE,          -- 大会モードフラグ
    tournament_start_at TIMESTAMP NULL,
    expires_at          TIMESTAMP NOT NULL,             -- 動的TTL
    FOREIGN KEY (host_id) REFERENCES user_networks(discord_id) ON DELETE CASCADE
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

ゲーム内でCキー（Pad 3）を押した際に、この形式のみが正しく認識される。

### 4.2 Rust Bridge API エンドポイント

```
GET    /lobby/rooms            ロビー一覧（gamelink のみ返す、virtual_ip は除外）
POST   /lobby/rooms            ロビー作成（合言葉を自動生成 or 指定可）
DELETE /lobby/rooms/{passcode} ロビー削除
POST   /lobby/agree            プライバシーポリシー同意記録
POST   /lobby/winner           勝者記録（Staff only）
GET    /admin/logs             admin_logs 一覧（Staff only）
```

> [!WARNING]
> `GET /lobby/rooms` は **絶対に** `virtual_ip` フィールドをレスポンスに含めてはならない。  
> Rust の `LobbyRoomResponse` struct に `virtual_ip` フィールドを持たせないことで型レベルで保証する。

---

## 5. スケジュール連動型マッチング

| フェーズ | 条件 | 動作 |
|:---|:---|:---|
| **ウォームアップ** | `tournament_start_at` の前 | 全参加者にコピーボタンを表示し、自由対戦を許可 |
| **大会中** | `is_tournament = TRUE` かつ開始後 | 指定カードを最上位に固定。敗退者・待機者同士の並行自由対戦を許可 |
| **大会後** | `winner_id` が確定した時 | Discord Bot が優勝ロールを自動付与 |

---

## 6. フロントエンド & UI/UX

### 6.1 配置方針

- `discord_bot/templates/dashboard.html` の「📜 アンケート管理」カード直下に追加
- 既存の `.card`, `.btn`, `.badge`, `.table` クラスを流用。新CSS定義なし

### 6.2 初回利用時：同意モーダル

`agreed_at IS NULL` のユーザーには、画面全体を覆うオーバーレイで同意を強制する。

**記載内容**:

- メールアドレスの利用目的（Cloudflare APIとの照合のみ）
- 同意しない場合はロビー機能を利用できない旨

### 6.3 Staff 専用オーバーレイ

`is_staff = TRUE` のユーザーには、通常のプレイヤー画面に以下を統合表示する。

- 勝敗の手動修正（`POST /lobby/winner`）
- 参加者の追放（`DELETE /lobby/rooms/{passcode}`）
- `admin_logs` の閲覧

---

## 7. プライバシーと透明性

- **用途の限定**: メールアドレスは Cloudflare API との照合のみに使用。第三者への提供、マーケティング利用は行わない
- **技術ガイダンス**: 配信にてパワーポイントを用いたシステム解説を実施し、参加者が安心して利用できるよう周知する
- **監査**: 運営者による権限操作はすべて `admin_logs` に記録し、検証可能にする

---

## 8. ファイル追加・変更一覧

| 操作 | ファイル | 説明 |
|:---|:---|:---|
| **新規** | `database_bridge/migrations/003_lobby_tables.sql` | 4テーブル追加 |
| **新規** | `database_bridge/src/lobby/game_link.rs` | GameLinkFormatter |
| **新規** | `database_bridge/src/db/lobby_repo.rs` | ロビーCRUD・IP照合 |
| **変更** | `database_bridge/src/db/models.rs` | 新struct追加 |
| **変更** | `database_bridge/src/main.rs` | ロビーエンドポイント追加 |
| **新規** | `discord_bot/routes/lobby.py` | Quart Blueprint |
| **新規** | `discord_bot/services/lobby_service.py` | Rust Bridge APIラッパー |
| **新規** | `discord_bot/templates/lobby.html` | ロビーUI |
| **新規** | `discord_bot/cogs/lobby/tournament.py` | 優勝ロール自動付与 |
| **変更** | `discord_bot/webapp.py` | `lobby_bp` 登録追加 |
| **変更** | `discord_bot/templates/dashboard.html` | ロビーカード挿入 |
