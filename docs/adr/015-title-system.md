# ADR-015: 称号システムのアーキテクチャ方針

- **ステータス**: 採用
- **作成日**: 2026-05-18
- **作成者**: Wanyaldee
- **関連ADR**: [ADR-012](012-general-tournament-system.md), [ADR-013](013-lounge-system.md)

---

## コンテキスト

Phase 1（汎用大会）・Phase 2（ラウンジ）の実装に伴い、プレイヤーの実績を可視化する仕組みが必要となった。  
当初、Discord のロールをそのまま実績バッジとして活用することを検討したが、以下の課題があった。

- ロールが複数付与されても Discord 上では見え方に差がなく、視覚的な意味が薄い
- ゲーム内のティア管理・チャンネルアクセス制御と「称号（栄誉）」の役割が混在する
- 太鼓の達人のドンだーひろばのように「獲得済みの中から1つ選んで表示する」体験が望ましい

---

## 決定

**称号システムを共通インフラとして実装し、Webアプリ側を主体に管理する。Discord ロールは装備中の称号1つにのみ紐づけ、アクセス制御には使用しない。**

### 設計の核心

| 観点 | 決定内容 |
|------|------|
| 主管 | Webアプリ（`titles` / `player_titles` / `player_active_title` テーブル） |
| 装備可能数 | 1人につき常に1つのみ（`player_active_title` の UPSERT で保証） |
| Discord ロール | 装備称号に対応する1ロールのみ付与。装備切替時に旧ロール削除→新ロール付与 |
| Discord ロールの用途 | 称号・栄誉の表示のみ。チャンネルアクセス制御には使わない |
| 称号マスタ管理 | Staff が dashboard.html から CRUD操作（外部 JS: `dashboard_titles.js`） |

### 解除条件の種別

| `unlock_type` | 解除トリガー |
|------|------|
| `lounge_rank` | ラウンジセッション終了時に `auto_grant_lounge_rank_title` が MMR を確認して自動付与 |
| `tournament_win` | 大会finalMatch承認後に `auto_grant_tournament_titles` が優勝回数を確認して自動付与 |
| `manual` | Staff が dashboard から手動付与 |

---

## 検討した代替案

### 案A: Discord ロールを主体に管理（Webアプリ側は何も持たない）
- **メリット**: 実装コストが低い
- **デメリット**: 複数ロール付与時の見え方の問題が解決されない。称号図鑑など将来的な表示機能が作れない
- **判断**: 否決

### 案B: Webアプリ側で複数の称号を同時表示し、Discord はすべてのロールを付与
- **メリット**: 全実績を Discord 上でも見られる
- **デメリット**: 複数ロール付与で Discord 側の見え方に意味がなくなる（ユーザーの指摘通り）。ロール数が増えて管理が煩雑になる
- **判断**: 否決

### 案C（採用）: Webアプリ主体 + Discord は装備中の1ロールのみ
- **判断**: 採用。「どうせ複数のロールが設定されたところで見えはせん」という運営判断と一致する

---

## 結果

### メリット
- 装備称号の切替が Webアプリ完結で行え、Discord API 呼び出しは最小限（ロール付け替えのみ）
- 称号マスタを Staff が自由に追加・編集でき、ゲームタイトルや季節イベントに合わせた称号拡張が容易
- 汎用大会・ラウンジどちらの実績でも同一の称号テーブルに統一できる

### デメリット・リスク
- Discord ロールIDの管理は Staff が手動で入力する必要がある（ロールIDの調達フローが別途必要）
- MMR 計算式が変わった場合、既付与の lounge_rank 称号は剥奪されない（実績の永続性はメリットとも言える）

### 実装ファイル
| ファイル | 役割 |
|------|------|
| `database_bridge/migrations/006_general_tournament.sql` | `titles` / `player_titles` / `player_active_title` テーブル定義 |
| `database_bridge/src/db/tournament_repo.rs` | 称号CRUD・自動付与ロジック |
| `database_bridge/src/api/handlers/tournament.rs` | `/titles/*` エンドポイント |
| `discord_bot/routes/tournament.py` | 称号CRUD・装備切替 API・Discord ロール同期 |
| `discord_bot/static/js/dashboard_titles.js` | 称号管理UI（dashboard.html から分離） |
| `discord_bot/templates/dashboard.html` | 称号管理カード・装備切替パネル |
