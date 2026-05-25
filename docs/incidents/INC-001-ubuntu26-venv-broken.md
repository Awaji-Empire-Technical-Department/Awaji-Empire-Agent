# INC-001: Ubuntu 26.04 アップグレード後の venv 破損による 502 Bad Gateway

- **発生日**: 2026-05-24
- **影響範囲**: dashboard.awajiempire.net（テスト環境）
- **深刻度**: High（Web ダッシュボード全停止）
- **解決時間**: 約 30 分
- **環境**: テスト環境（本番影響なし）

---

## 症状

- `dashboard.awajiempire.net` にアクセスすると 502 Bad Gateway
- `discord_webapp.service` が起動直後にクラッシュを繰り返す（Restart ループ）

```
hypercorn[79491]: ModuleNotFoundError: No module named 'hypercorn'
discord_webapp.service: Failed with result 'exit-code'.
```

---

## 根本原因

Ubuntu 26.04 へのアップグレードに伴い、**システム Python のパスが変わり、`.venv` 内のシンボリックリンクが破損**した。

`.venv/bin/python3` → `python` → （実体が存在しない）という状態になっており、venv 全体が機能していなかった。

```bash
# 破損状態の例
lrwxrwxrwx ... python3 -> python   # python の実体が見つからない
sudo: '/Awaji-Empire-Agent/discord_bot/.venv/bin/python3': command not found
```

---

## 対応手順（時系列）

| # | 操作 | 結果 |
|---|---|---|
| 1 | `uv sync` | パッケージは入るが `.venv/bin/` にバイナリが生成されない |
| 2 | `uv cache clean` → `rm -rf .venv` → `uv venv` → `uv sync` | `.venv/bin/hypercorn` は作成されたが実行できず |
| 3 | `chown -R devuser .venv` | 権限問題を解消するも依然 `status=203/EXEC` |
| 4 | `python3 -m hypercorn` に ExecStart を変更 | `python3` 自体が見つからず失敗 |
| 5 | `which python3` でシステム Python パスを確認し、`uv venv --python /usr/bin/python3` で再作成 | **解決** |

---

## 解決策

```bash
cd /Awaji-Empire-Agent/discord_bot
rm -rf .venv
uv venv --python /usr/bin/python3   # システム Python を明示指定
uv sync
systemctl restart discord_webapp
```

---

## 再発防止策

### 1. デプロイスクリプトで Python パスを明示する

`uv venv` 単体ではなく、Python パスを固定する：

```bash
uv venv --python /usr/bin/python3
```

### 2. OS アップグレード後のチェックリストに追加

- [ ] `python3 --version` でバージョン確認
- [ ] `.venv` を削除して `uv venv --python $(which python3)` で再作成
- [ ] `uv sync` 後に `.venv/bin/` のバイナリ存在を確認
- [ ] `systemctl status` で各サービスの起動を確認

### 3. sudoers の警告も要対応

`/etc/sudoers.d/awaji_deploy` に構文エラーがある（`garbage at end of line`）。
Ubuntu 26.04 アップグレード時に書式が変わった可能性あり。別途修正が必要。

```bash
visudo -c -f /etc/sudoers.d/awaji_deploy
```

---

## 教訓

- **OS メジャーアップグレード後は venv を必ず再作成する**。Python のシンボリックリンクはアップグレードで無効になりうる。
- `uv venv` は `--python` を省略するとシステムの `python3` を自動検出するが、アップグレード後は検出先が変わることがある。
- テスト環境で先行してアップグレードしたことで本番への影響を防げた。テスト環境先行の有効性が確認された。
