# Technical Lessons Learned (Phase 3-C)

Rust Bridge の開発および MariaDB/CI 連携において得られた重要な知見を記録します。

## 1. Axum 0.8 のルーティング構文変更
Axum 0.8 以降、パスパラメータの指定方法が変更されました。旧来の構文を使用すると、**コンパイルは通るが実行直後にパニック**します。

- **NG**: `.route("/surveys/:id", get(handler))`
- **OK**: `.route("/surveys/{id}", get(handler))`
- **症状**: `thread 'main' panicked at ... Path segments must not start with ':'`

## 2. MariaDB JSON カラムの型不一致 (BLOB 問題)
MariaDB の `JSON` 型は内部的に `LONGTEXT` のエイリアスですが、Rust の `sqlx` 経由では `BLOB` 型として返される場合があります。これを直接 `String` としてデコードしようとするとエラーになります。

- **症状**: `error occurred while decoding column "xxx": mismatched types; Rust type 'alloc::string::String' is not compatible with SQL type 'BLOB'`
- **対策**:
  1. 構造体定義で `Vec<u8>` として受け取る。
  2. `serde` のカスタムシリアライザを使用して、API 出力時に `String` に変換する。
  3. `serde_json::from_slice` を使用してバイナリから直接パースする。

## 3. CI/CD 環境における所有権管理
セルフホストランナー（Proxmox VM等）でデプロイを行う際、過去の手動操作や異なる Job で作成された `.venv` 等が `root` 所有になっていると、デプロイユーザー（`devuser`等）がファイルを上書きできず、`Permission denied` (os error 13) が発生します。

- **対策**: `sudo rm -rf` は環境消滅のリスクがあるため避け、`sudo chown -R $(whoami):$(whoami) .venv` で所有権をデプロイユーザーに移譲する。

## 4. SQLx マクロと CI 環境の疎結合化
`sqlx::query!` などのマクロはコンパイル時に DB 接続（`DATABASE_URL`）を要求するため、CI 環境のセットアップが複雑になります。

- **対策**: `sqlx::query()` などのランタイム API を使用する。
  - コンパイル時に DB が不要になり、CI/CD パイプラインが安定する。
  - 開発時のビルド速度も向上する。
  - 型安全性は、別途結合テスト層で担保する設計に倒す。

## 5. OffsetDateTime の Serde 実装
`sqlx` の `time` フィーチャーを有効にするだけでは、`OffsetDateTime` の `Serialize`/`Deserialize` は実装されません。

- **対策**: `Cargo.toml` に直接 `time = { version = "0.3", features = ["serde"] }` を追加する必要がある。

## 6. sudoers のパス・引数指定の罠
`visudo` でコマンドを許可する際、引数を細かく指定しすぎると（例: `systemctl restart service_name`）、フラグが一つ増えただけで弾かれます。

- **教訓**: CI のように頻繁にコマンド構成が変わる場合は、コマンドパス（`/usr/bin/systemctl` 等）のみを許可し、ユーザー名が `whoami` と一致しているか、および実行コマンドの絶対パスが `sudoers` の記述と 1 文字も違わないかを厳格に確認する。

## 7. Windows/Linux 改行コード (CRLF/LF) の罠
Windows で作成したシェルスクリプトを `rsync` 等で Linux に転送して実行すると、末尾の `\r` (CR) が原因で `#!/bin/bash\r` となり、Linux が「そんなシェル（コマンド）はない」というエラー (`command not found`) を出します。

- **対策**: デプロイフローの中で `sed -i 's/\r$//' script.sh` を実行してから `chmod +x` し実行する。ファイルが存在するのに「見つからない」と言われる場合は、ほぼこれが原因。

## 8. OffsetDateTime のシリアライズ形式 (RFC3339)
`time::serde::rfc3339` を明示的に指定しないと、`OffsetDateTime` は数値の配列（`[2026, 55, ...]`）としてシリアライズされることがあります。

- **対策**: 構造体フィールドに `#[serde(with = "time::serde::rfc3339")]` を付与し、API レスポンスが標準的な ISO-8601 文字列になるよう強制する。
