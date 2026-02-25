# 本番環境（Master）移行・再構築ガイド (Phase 3 対応版)

リポジトリの Rust Bridge (database_bridge) 導入に伴い、本番サーバー側で必要となる最新のセットアップ手順をまとめます。

## 1. 事前準備 (Antigravity 側での作業)

本番マージ前に、以下のファイルが正しく設定されているか確認してください。

- [ ] **GitHub Actions の更新**: `.github/workflows/deploy.yml` で `database_bridge.service` の再起動が含まれていること。
- [ ] **DBアクセス方式**: `sqlx::query!` マクロを廃止し、CI環境で `DATABASE_URL` が不要なランタイムAPIに移行済みであること。
- [ ] **型互換性**: MariaDB の JSON (BLOB) カラムに対応した型定義（`Vec<u8>`）になっていること。

## 2. 本番サーバーでの初回作業

### A. ツールチェーンの導入
Rust Bridge のビルドおよび Python 依存関係管理のため、以下をインストールします。

1. **uv (Python パッケージマネージャー)**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
   ```
2. **Rust (Cargo) ツールチェーン**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source $HOME/.cargo/env
   ```

### B. 環境設定とビルド

1. **環境変数の配置**
   `/Awaji-Empire-Agent/discord_bot/.env` に以下の項目が必須です。
   ```env
   DATABASE_URL=mysql://user:pass@localhost/dbname
   # Bridge は 7878 ポートで待ち受ける
   ```

2. **Rust Bridge のビルド**
   ```bash
   cd /Awaji-Empire-Agent/database_bridge
   cargo build --release
   ```

3. **Python 依存関係の同期**
   ```bash
   cd /Awaji-Empire-Agent/discord_bot
   /usr/local/bin/uv sync
   ```

### C. systemd サービスの登録 (重要)

Phase 3 以降、**サービスは3構成**になります。`scripts/setup-systemd.sh` を使用して一括登録します。

1. **セットアップスクリプトの実行**
   ```bash
   cd /Awaji-Empire-Agent
   sudo chmod +x scripts/setup-systemd.sh
   sudo ./scripts/setup-systemd.sh
   ```

2. **登録されるサービス一覧**
   - `database_bridge.service`: Rust 製 DB 通信ブリッジ (Port 7878)
   - `discord_bot.service`: Python 製 Discord Bot 本体
   - `discord_webapp.service`: Python 製 管理画面 Web アプリ

3. **起動確認**
   ```bash
   sudo systemctl status database_bridge.service
   # 疎通確認
   curl http://127.0.0.1:7878/health
   ```

## 3. GitHub Actions による継続的デプロイ (CD)

デプロイ用ユーザーが `sudo` パスワードなしでサービスを制御できるよう、`/etc/sudoers.d/deploy` 等に設定を追加してください。

```text
# 例: /etc/sudoers.d/deploy
devuser ALL=(ALL) NOPASSWD: /usr/bin/rsync, /usr/bin/systemctl, /Awaji-Empire-Agent/scripts/setup-systemd.sh
```

## 4. トラブルシューティング

### 1. `uv sync` で `Permission denied` が出る
過去に root で `.venv` を作成した可能性があります。
```bash
sudo chown -R devuser:devuser /Awaji-Empire-Agent/discord_bot/.venv
```

### 2. Bridge が `mismatched types (BLOB)` で落ちる
DBのカラム型と Rust の構造体が不一致です。`models.rs` で `questions/answers` が `Vec<u8>` で定義されているか確認してください。

### 3. 日時が配列形式 `[2026, ...]` で表示される（旧情報・対応済み）
~~`#[serde(with = "time::serde::rfc3339")]` が付与されている必要があります。~~

> **Phase 3-D 修正済み**: MariaDB の `DATETIME` 型は `OffsetDateTime` に非互換。
> `CAST(created_at AS CHAR)` で SQL 側で文字列化し、Rust 側で `String` で受け取る方式に変更済み。
> `OffsetDateTime` および `time::serde::rfc3339` は **使用禁止**。

### 4. Bridge が `mismatched types ... BLOB` で落ちる
`LONGTEXT` / `MEDIUMTEXT` カラムは `sqlx` が内部的に `BLOB` として扱うため、
Rust の構造体フィールドには `String` ではなく **`Vec<u8>`** を使用すること。
シリアライズ時は `serde_bytes_to_string` モジュールで UTF-8 String に変換する。

---

## 5. 最終確認リスト

- [ ] `curl http://127.0.0.1:7878/health` が `{"status":"ok"}` を返す。
- [ ] 管理画面の「作成日時」が正しく読み取れる形式で表示されている。
- [ ] アンケートを新規作成し、DBに保存される。
- [ ] ログ（`operation_logs`）が Bridge 経由で記録されている。
- [ ] アンケートに回答→再回答した際、レコードが追加されず更新されること。

---

## 6. 本番 DB マイグレーション手順（Phase 3-D 対応）

> **⚠ 重要**: 以下の手順は本番環境への初回デプロイ時または Phase 3-D ブランチのマージ後、
> **必ず手動で実行**してください。コードのデプロイだけでは完結しません。

### 背景

Phase 3-D ホットフィックス（`feature/phase3d-hotfix`）の調査で、
`survey_responses` テーブルに `(survey_id, user_id)` の UNIQUE KEY が存在しないことが判明しました。
UNIQUE KEY がないと `ON DUPLICATE KEY UPDATE` による更新が機能せず、
同一ユーザーが再回答するたびに新しいレコードが追加されてしまいます。

### 実行手順

```sql
-- 【Step 1】UNIQUE KEY が既に存在するか確認（存在する場合はStep 3は不要）
SHOW INDEX FROM survey_responses WHERE Key_name = 'unique_survey_user';

-- 【Step 2】既存の重複行を確認
SELECT survey_id, user_id, COUNT(*) as cnt
FROM survey_responses
GROUP BY survey_id, user_id
HAVING cnt > 1;

-- 【Step 3】重複があれば古いレコードを削除（最新の id を残す）
--   ※ 重複がない場合はスキップ
DELETE sr1 FROM survey_responses sr1
INNER JOIN survey_responses sr2
  ON sr1.survey_id = sr2.survey_id
  AND sr1.user_id = sr2.user_id
  AND sr1.id < sr2.id;

-- 【Step 4】UNIQUE KEY を追加
ALTER TABLE survey_responses
  ADD UNIQUE KEY unique_survey_user (survey_id, user_id);

-- 【Step 5】追加確認
SHOW INDEX FROM survey_responses;
```

### 動作確認

```bash
# 同一アンケートに2回回答し、survey_responses のレコード数が増えないことを確認
SELECT COUNT(*) FROM survey_responses WHERE survey_id = <テスト用ID>;
```

