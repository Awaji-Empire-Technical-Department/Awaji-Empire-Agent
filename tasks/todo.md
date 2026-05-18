# Phase 1 / Phase 2 実装計画

## ステータス: 実装完了（コードレビュー・DB適用待ち）

---

## Phase 1: 汎用大会システム + 称号システム

### 完了済み
- [x] `database_bridge/migrations/006_general_tournament.sql` — game_titles, match_scores, point_tables, titles, player_titles, player_active_title
- [x] `database_bridge/src/db/models.rs` — GameTitle, MatchScore, PointTable, Title, TitleWithStatus, Lounge系Struct追加
- [x] `database_bridge/src/db/tournament_repo.rs` — 大会・称号CRUD、自動称号付与ロジック
- [x] `database_bridge/src/api/handlers/tournament.rs` — HTTPハンドラ（スコア申告・承認・称号CRUD）
- [x] `database_bridge/src/api/mod.rs` — /tournament/* /titles/* ルーター登録
- [x] `discord_bot/services/tournament_service.py` — Bridge APIラッパー
- [x] `discord_bot/routes/tournament.py` — Blueprint（大会・称号API）
- [x] `discord_bot/webapp.py` — tournament_bp / lounge_bp 登録
- [x] `discord_bot/templates/tournament.html` — 大会進行UI
- [x] `discord_bot/static/js/tournament.js` — 大会JS（外部ファイル）
- [x] `discord_bot/static/css/tournament.css`
- [x] `discord_bot/templates/dashboard.html` — 称号管理カード追加
- [x] `discord_bot/static/js/dashboard_titles.js` — 称号管理JS（外部ファイル）

## Phase 2: ラウンジシステム

### 完了済み
- [x] `database_bridge/migrations/007_lounge.sql` — lounge_* テーブル
- [x] `database_bridge/src/db/lounge_repo.rs` — ラウンジDBクエリ（MMR・セッション・レース・チーム）
- [x] `database_bridge/src/api/handlers/lounge.rs` — HTTPハンドラ（セッション・レース・申告・承認）
- [x] `database_bridge/src/api/mod.rs` — /lounge/* ルーター登録
- [x] `discord_bot/services/lounge_service.py` — Bridge APIラッパー
- [x] `discord_bot/routes/lounge.py` — Blueprint
- [x] `discord_bot/templates/lounge.html` — ラウンジ進行UI
- [x] `discord_bot/static/js/lounge.js` — ラウンジJS（外部ファイル）
- [x] `discord_bot/static/css/lounge.css`

## 残タスク（未着手）

- [ ] ADR-011 更新（docs/adr/011-general-tournament-system.md）
- [ ] ADR-013 更新（docs/adr/013-lounge-system.md）
- [ ] Discord Cog: 称号ロール自動付与のトリガー統合（Discord Bot側）
- [ ] ラウンジMMR増減計算式の詳細設計（現在は単純スコア加算）
- [ ] tournament.htmlへの Bracketry ブラケット図統合（1v1用）
