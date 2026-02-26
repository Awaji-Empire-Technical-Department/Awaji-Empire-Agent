# ADR-008: セキュア対戦ロビーシステムのアーキテクチャ選定

- **日付**: 2026-02-26
- **ステータス**: 承認済み
- **ブランチ**: `feature/secure-lobby`
- **関連仕様書**: [FEATURE_LOBBY.md](../FEATURE_LOBBY.md)

---

## 1. 背景

東方憑依華 〜Antinomy of Common Flowers.〜 のコミュニティにおいて、P2P対戦時に「物理IPアドレスの交換」が発生していた。これはセキュリティリスク（IPの特定・DDoS等）であると同時に、ゲーム固有の入力形式（12桁0埋め）への対応が毎回手動となり、接続ミスの原因となっていた。

また、大会運営が Discord DM による手動のブラケット管理で行われており、進行ミスや集計ミスが発生していた。

これらを解消するため、Cloudflare WARP を基盤とした仮想プライベートネットワーク上でのロビーシステムを構築する。

---

## 2. 決定事項

### 2.1 ネットワーク基盤：Cloudflare WARP（Zero Trust）

**採用**: Cloudflare WARP `100.64.0.0/10` レンジの仮想IPを使用したP2P通信

**不採用案**:

| 案 | 不採用理由 |
|:---|:---|
| UPnP（ポート開放） | 参加者のルーター設定を変更させるリスクがあり、セキュリティポリシーに反する |
| VPN（WireGuard自前運用） | サーバーへの負荷と鍵管理コストが高い。Cloudflare WARP で代替可能 |
| 物理IPの直接交換 | IPの露出リスクがある。本システムの解決すべき根本問題そのもの |

**採用理由**:

- 参加者はCloudflare WARPクライアントをインストールするだけで仮想NWに参加できる（低導入コスト）
- 仮想IP（`100.x`）は外部に露出しないため、物理IPは完全に隠蔽される
- 既存インフラ（Cloudflare Tunnel）との親和性が高い

### 2.2 物理IP非露出の担保：GameLinkFormatter（Rust）

**採用**: Rust Bridge 側で `GameLinkFormatter` を実装し、仮想IPをゲームが認識できる形式に変換してからフロントエンドに渡す

```text
入力 (仮想IP):  100.96.18.5
出力 (GameLink): 100.096.018.005:10800
```

**取り決め**:

- フロントエンド（HTML/JS）は `virtual_ip` を受け取らない。`gamelink` 文字列のみを受け取る
- API `/lobby/rooms` のレスポンスJSONに `virtual_ip` フィールドを含めない
- これにより、ブラウザの開発者ツールを使ってもIPを逆引きできない

**不採用案（Python側で変換）**: 型安全性がなく、フォーマットミスによる接続失敗を実行時まで検出できない。Rustのコンパイル時テストで保証するほうが確実。

### 2.3 ロビー識別子：合言葉（パスコード）方式

**採用**: ロビーをパスコード（合言葉）で識別し、知っている者だけが参加できる仕組み

**不採用案（ランダムマッチング）**: 東方憑依華コミュニティでは「知っている相手とだけ対戦する」という文化が根付いており、見ず知らずのプレイヤーとのマッチングはニーズに合致しない。

### 2.4 アクセス制御：Cloudflare Access（Discord OAuth2）

**採用**: `dashboard.awajiempire.net` へのアクセスを Cloudflare Access + Discord OAuth2 で保護し、コードで実装しない

**メール照合**:  Discord OAuth2 スコープに `email` を追加し、取得したメアドを Cloudflare API に渡してデバイスの WARP 仮想 IP を引き当てる。ドメイン制限は行わない。

**理由**: ドメイン制限を配信者全員に誰に課すのは追加コストが大きい。Discord が居る者の誤ったメアドを使う可能性も低い。認証レイヤーをコードに持ち込まずインフラ側（Cloudflare）に委ねることで、認証バイパスの実装ミスリスクを根絶できる。既存のダッシュボード保護方式と統一できる。

### 2.5 UI統合：「アンケート管理」カード直下への追加

**採用**: 既存 `dashboard.html` の `.card` コンポーネントを流用し、「📜 アンケート管理」カードの直下にロビーカードを追加

**取り決め**:

- 新しいCSSクラスの定義は行わない
- `style.css` へのセレクタ追加もしない
- 既存の `.card`, `.btn`, `.badge`, `.table` で完結する

**理由**: 既存ダッシュボードのデザイン一貫性を完全に維持するため。新機能追加でUIが崩れると利用者に混乱を与える。

---

## 3. 採用しなかった設計（明示的な却下記録）

| 設計案 | 却下理由 |
|:---|:---|
| WebRTC P2P | 東方憑依華は独自プロトコルを使用しており、WebRTC は適用不可 |
| ロビー情報をDiscord DMで配布 | 自動化・集約管理というシステムの趣旨に反する |
| 管理者用UIを別ページに分離 | Staff が「選手としても参加」するモデルに合わず、画面を行き来する手間が増える |

---

## 4. 影響

### Cloudflare WebDashboard（手動設定）

- Zero Trust > Settings > Network: WARP有効化
- Zero Trust > Settings > WARP Client: デバイス登録ポリシー設定
- Zero Trust > Access > Applications: Access Application作成
- Zero Trust > Access > Service Auth: Service Token発行
- My Profile > API Tokens: Zero Trust Read スコープのAPIトークン発行

### コード（このリポジトリ）

| 追加ファイル | 役割 |
|:---|:---|
| `database_bridge/migrations/003_lobby_tables.sql` | 4テーブル追加（user_networks, matchmaking_rooms, tournament_matches, admin_logs） |
| `database_bridge/src/lobby/game_link.rs` | GameLinkFormatter 実装 |
| `database_bridge/src/db/lobby_repo.rs` | ロビーCRUD・IP照合 |
| `discord_bot/routes/lobby.py` | Quart Blueprint |
| `discord_bot/services/lobby_service.py` | Rust Bridge API ラッパー |
| `discord_bot/templates/lobby.html` | ロビーUI（同意モーダル・大会表示） |
| `discord_bot/cogs/lobby/tournament.py` | 優勝ロール自動付与 |
