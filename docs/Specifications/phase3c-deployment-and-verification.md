# Phase 3-C: デプロイと最終検証 仕様書

- **ブランチ**: `feature/phase3-rust-bridge`
- **ステータス**: ✅ 実装完了（2026-02-24）
- **作成日**: 2026-02-23
- **前提**: Phase 3-B までのリファクタリングが全て完了（プッシュ済み）していること

---

## 1. 目的

Phase 3-B までに実装した Rust Bridge およびリファクタリング済みの Python コードを本番（またはテスト）環境にデプロイし、安定稼働を確認する。

## 2. デプロイ手順

### 2.1 Rust Bridge のビルドと配置

GitHub Actions (`deploy.yml`) により自動化されるが、手動での確認項目は以下の通り。

1. **バイナリ作成**: `cargo build --release`
2. **配置先**: `/var/www/Awaji-Empire-Agent/database_bridge/target/release/database_bridge`
3. **環境変数**: `.env` ファイルに `DATABASE_URL` が正しく設定されていること。

### 2.2 systemd のセットアップ

`scripts/setup-systemd.sh` を実行し、サービスを起動・有効化する。

```bash
sudo ./scripts/setup-systemd.sh
sudo systemctl status database_bridge
```

### 2.3 Python 側の更新

`uv sync` または `pip install -r requirements.txt` を実行し、`httpx` の導入と `aiomysql` の削除を反映させる。

## 3. 検証項目

### 3.1 接続検証 (Connectivity)

- [ ] `curl http://127.0.0.1:7878/health` で `{"status":"ok"}` が返ること。
- [ ] Bot 起動ログに `✅ Rust Bridge (IPC) connection successful!` が表示されること。

### 3.2 機能検証 (E2E)

- [ ] **アンケート作成**: ダッシュボードから新規作成し、Rust 側の `surveys` テーブルに反映されること。
- [ ] **アンケート回答**: Discord リンクから回答し、DM が送信され、`survey_responses` テーブルに記録されること。
- [ ] **ログ記録**: 全ての操作が `operation_logs` (Rust Bridge 経由) に記録されること。

### 3.3 パフォーマンス監視

- [ ] `journalctl -u database_bridge` でエラーログが出ていないか監視。
- [ ] データベース同時接続数が Rust 側の単一プールに集約されていることを確認。

## 4. 異常系の対応

- **Bridge 停止時**: Python 側で `httpx.ConnectError` が発生する。Service 層で適切にキャッチし、ユーザーにメッセージ（「システムメンテナンス中」等）が表示されるか確認。
- **DB 接続断**: Bridge の `/health` が 503 を返す。Bot の `on_ready` で警告が出る。

---

## 5. 結論

本 Phase の完了をもって、Phase 3 (Rust への DB 操作移譲) は終了となる。以降の Phase 4 では、残りの Python ロジックを順次 Rust へ移行し、最終的に Python 側を薄いラッパー（UI/Gateway）としていく。
