# ADR-033: 本番 VM の nginx 更新（nginx 1.30.x の脆弱性修正への追随）

- **ステータス**: 採用
- **作成日**: 2026-11-19
- **作成者**: Wanyaldee
- **ブランチ**: —（サーバ運用作業のため、対応するコード変更なし）

---

## 背景 (Context)

nginx の 1.30 系は、2026-04-14 の 1.30.0 以降、ほぼ毎月のようにセキュリティ修正のリリースが続いている
（[CHANGES-1.30](https://nginx.org/en/CHANGES-1.30)）。
直近の 1.30.7（2026-11-18）では、HTTP/2・HTTP/3・stream・`resolver` ディレクティブ・
SSL でのリクエストボディ読み取りなど、9 件の脆弱性が修正された。

リポジトリには、Quart（`127.0.0.1:5000`）の前段に置くリバースプロキシの設定
（[`infra/nginx-awaji.conf`](../../../infra/nginx-awaji.conf)）があり、
`scripts/deploy.sh` がそれを `sites-enabled` に配置する。
一方、外部への公開は Cloudflare Tunnel 経由で、インバウンドのポートは開けておらず、
[ARCHITECTURE.md](../../ARCHITECTURE.md) の図では Tunnel は nginx を通らず Web アプリに直接つながっている。
本番 VM で nginx が実際にリクエストの経路に入っているかは、更新の時点では把握していなかった。

同じ時期、さくらインターネットも「[緊急] nginx 脆弱性対応に伴うシステムメンテナンス」を
2026-11-19 に実施していた
（[メンテナンス情報](https://support.sakura.ad.jp/mainte/mainteentry.php?id=40154)。
対象はさくらのレンタルサーバ、メールボックス、マネージドサーバ等）。
大規模な事業者が同じ nginx の更新を緊急で行っているのを見て、自分の VM も更新の対象かどうかを確認した。

## 決定事項 (Decision)

本番 VM の nginx を、Ubuntu 標準のパッケージ（1.24.0）から nginx.org の stable リポジトリ（1.30.7）へ切り替えて更新した。

- 更新後のバージョン: **nginx 1.30.7**（2026-11-18 リリースの最新版。`nginx -v` で確認）
- 更新前のバージョン: **nginx 1.24.0**（Ubuntu 24.04 noble 標準。`1.24.0-2ubuntu7` 系）
- 更新前後の配布元: Ubuntu 標準（noble / noble-updates, noble-security）→ nginx.org の stable（`1.30.7-1~noble`）
- 実施日: 記録なし（2026-11-18〜19 ごろ）

## 根拠 (Reason)

### 実際に読み込まれている設定は、リポジトリの設定ではなかった

更新後の VM で `sudo nginx -T` を確認したところ、読み込まれていたのは次の設定だけだった。

- `/etc/nginx/nginx.conf` が `include /etc/nginx/conf.d/*.conf;` を持つ
- `/etc/nginx/conf.d/default.conf`（nginx.org パッケージが入れる既定の設定）
- `sites-enabled` の読み込みはなく、`infra/nginx-awaji.conf`（`awaji`）も出てこない

つまり、**リポジトリの `nginx-awaji.conf` は、更新後の nginx には読み込まれていない。**
nginx.org のパッケージは `conf.d/` を読む構成で、Ubuntu 標準の `sites-enabled` 方式と違うためである。

この結果から、次のことが言える。

- 更新後の nginx が受けるのは既定の設定だけで、HTTP/2・HTTP/3・stream・`resolver` などを使う構成ではない。
  1.30.7 の CVE のほとんどは、今の設定では直接の攻撃経路にならない。
- 続けて `curl -sI http://127.0.0.1:80/` を実行すると、`HTTP/1.1 200 OK`、`Server: nginx/1.30.7`、
  `Content-Length: 896`（nginx の既定の歓迎ページの大きさ）が返った。80 番は既定ページを返している。
- `/etc/nginx/sites-enabled/` には `default` だけがあり、`awaji-empire` のリンクはなかった。
  `deploy.sh` は `awaji-empire` のリンクを作り、`sites-enabled/default` を削除する
  （[scripts/deploy.sh](../../../scripts/deploy.sh)）。この状態は、**`deploy.sh` の nginx の手順がこの VM では
  実行されていない**ことを示す。更新で消えたのではなく、更新前から nginx はリポジトリの設定で動いていなかった
  可能性が高い（更新前の状態は記録がなく、推論である）。
- したがって、**この VM の nginx は、リクエストの経路に入っていなかった**可能性が高い。
  `ARCHITECTURE.md` の図（Tunnel が Web アプリに直接つながる）とも合う。
  ダッシュボードの動作は、更新後に別途確認する（下の「未検証」）。

それでも更新したのは、次の理由による。

1. **将来の設定変更で効いてくる**。HTTP/2 や TLS 終端を後から足したときに、
   古いバージョンのままだと、そのとき初めて脆弱な状態になる。
2. **バージョンを追随するコストが小さい**。nginx は 1.30.x で毎月のように修正が出ており、
   遅れるほど「どの修正まで入っているか」を調べる手間が増える。
3. **経路に入っていなくても、nginx は 80 番で待ち受けている**。VM 上で動いている以上、
   脆弱なバージョンのまま放置する理由がない。

### 「設定上は影響が小さい」ことと「更新しない」ことは別

ADR-029（カーネル更新）と同じ考え方で、攻撃経路の大きさとは別に、適用のコストを見て決めた。
今回のコストは nginx の再起動またはリロードだけで、停止時間はあっても数秒である。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| 更新を見送る（HTTP/2・stream・TLS 終端を使っていないため） | 直接の影響が小さいのは事実だが、設定を変えたときに脆弱な状態になるリスクが残る。コストが小さい更新を見送る理由が乏しい |
| Ubuntu 標準のまま、noble-security の最新（`1.24.0-2ubuntu7.20`）に上げる | 1.24.0 は 2024 年の安定版で、Ubuntu が修正を個別にバックポートする。今回の 1.30.x の修正がすべて入っているかを、CVE ごとに追う必要がある。upstream の最新に揃えるほうが確認が簡単だと考えた（Ubuntu 側の対応状況は未確認） |
| 脆弱な機能（HTTP/3 等）を設定で無効にして対処する | もともと有効にしていないため、対処として成立しない。修正版への更新のほうが確実 |

## 影響 (Consequences)

### ポジティブ

- 本番 VM の nginx が 1.30.7 になり、CHANGES-1.30 に載っている 1.30.7 までの修正をすべて含む状態になった。
- 実際に読み込まれている設定が既定のものだと分かり、`deploy.sh` と nginx.org パッケージのずれに気づけた。

### ネガティブ・トレードオフ

- **更新前後のバージョンを記録していない。** ADR-029 で「次回以降は作業の前後で記録を残す」と書いたが、
  今回も残せなかった。何から何に上がったかを後から正確にたどれない。
- **配布元が Ubuntu 標準から nginx.org に変わった。** 以後の nginx の更新は `apt` が nginx.org のリポジトリから取る
  ため、Ubuntu のセキュリティ更新（unattended-upgrades など）では nginx が追随されない。
  更新を見る場所が増える（nginx.org の CHANGES を自分で確認する必要がある）。
- **1.24 から 1.30 へ、1.26・1.28 の 2 つの安定版を飛ばして上げた。** 設定の互換性は、
  現在の設定が単純（`proxy_pass`・`alias`・`map` だけ）なので影響は小さいと見ているが、検証していない。
- nginx.org のパッケージは `conf.d/` を読み、Ubuntu 標準の `sites-enabled` を読まない（`nginx -T` で確認済み）。
  `scripts/deploy.sh` は `sites-enabled` 前提なので、**今のまま `deploy.sh` を実行しても、
  `nginx-awaji.conf` は読み込まれない**。`deploy.sh` の修正か、設定の置き場所の変更が必要。
- **「本番の nginx がリポジトリの設定で動いている」という、リポジトリが前提にしている状態と、
  実際の VM が食い違っていた。** 今回の更新は、その食い違いに気づくきっかけになった。
  nginx を使わないなら `deploy.sh` の nginx の手順と `infra/nginx-awaji.conf` の扱いを決める必要がある（別の ADR で扱う）。
- 次回以降は、作業の前後で `nginx -v` と `apt list --installed nginx -a` の出力を残す。

## 検証 (Verification)

- **操作:** nginx のパッケージ更新と、再起動またはリロード
  **意図:** 更新後も Web ダッシュボードと WebSocket（`/ws/`）が通ること
  **対象:** 本番 VM（Proxmox 上、Ubuntu 24.04 LTS）
  **実行者:** Wanyaldee (human)、実施日の記録なし

  ```
  devuser@01sv-ubuntu:~$ nginx -v
  nginx version: nginx/1.30.7
  devuser@01sv-ubuntu:~$ sudo nginx -T | grep -n "sites-enabled\|conf.d\|awaji"
  32:    include /etc/nginx/conf.d/*.conf;
  136:# configuration file /etc/nginx/conf.d/default.conf:
  devuser@01sv-ubuntu:~$ curl -sI http://127.0.0.1:80/
  HTTP/1.1 200 OK
  Server: nginx/1.30.7
  Content-Length: 896
  devuser@01sv-ubuntu:~$ ls /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
  /etc/nginx/conf.d/:     default.conf
  /etc/nginx/sites-enabled/:  default
  ```

  Verified-by: Wanyaldee (human)、2026-11-19 — 更新後のバージョンが 1.30.7 であることをターミナルで確認。
  更新の作業そのもの（コマンドと実施日）の出力は保存されていない。

- 設定の確認（ドキュメント調査）: `infra/nginx-awaji.conf` を読み、HTTP/2・HTTP/3・stream・
  `resolver`・`try_files` を使っていないことを確認した。
  Checked-by: Claude Sonnet 5.5 (AI agent)、2026-11-19
- 修正内容の確認（ドキュメント調査）: nginx の CHANGES-1.30 と、さくらインターネットのメンテナンス情報を参照した。
  Checked-by: Claude Sonnet 5.5 (AI agent)、2026-11-19

### 未検証

- Cloudflare Tunnel の転送先（Quart の `127.0.0.1:5000` と推測しているが、設定は見ていない）
- 更新後の Web ダッシュボードと WebSocket の動作（更新前から nginx が経路外なら、影響はないはず）
- 更新前に `sites-enabled/awaji-empire` が存在していたか（記録なし。推論のみ）
- 更新前の `1.24.0` の正確なパッケージ版（`-2ubuntu7.x` の x）
- Ubuntu 標準（1.24.0-2ubuntu7.20）が 1.30.7 の CVE に対応しているか
- 実際の作業日

## 関連ドキュメント

- 関連 ADR: [ADR-029](../021-030/029-production-kernel-update-cve-2026-99999.md) — 本番カーネル更新（同じ「念のため適用する」判断）
- 設定: [`infra/nginx-awaji.conf`](../../../infra/nginx-awaji.conf)
- nginx: <https://nginx.org/en/CHANGES-1.30>
- さくらインターネット: <https://support.sakura.ad.jp/mainte/mainteentry.php?id=40154>
