# ADR-033: Zabbix による監視基盤の導入（構成・DB・公開方法）

- **ステータス**: 提案中（下書き。導入前）
- **作成日**: 2026-11-05
- **更新日**: 2026-11-06（Zabbix のバージョンを 8.0 LTS に決定。OpenTelemetry との役割分担を [ADR-034](034-opentelemetry-introduction.md) に分けた）
- **作成者**: Wanyaldee
- **ブランチ**: `Wanyaldee/zabbix-setup-doc`

---

## 背景 (Context)

いまは Grafana などでコンテナや VM の状態を**眺めている**だけで、異常を判断して知らせる仕組みがない
（Grafana の構成はリポジトリに記録がない【要確認】）。

[INC-001](../../incidents/INC-001-ubuntu26-venv-broken.md) では、テスト環境の OS を Ubuntu 26.04 に上げたあと、
システム Python のパスが変わって `.venv/bin/python3` のリンク先がなくなり、`discord_webapp.service` が再起動を繰り返して 502 になった。
この障害から、次のことが分かった。

- **動いているプロセスは、ファイルが壊れても止まらない。止まるのは次の再起動のとき**。壊れた瞬間と止まった瞬間の間に、気づける時間があった。
- しかし「venv の Python の実体がある」「OS のバージョンが変わっていない」という**前提は、誰も見ていなかった**。

[ADR-029](../021-030/029-production-kernel-update-cve-2026-99999.md) でも、更新前のカーネルのバージョンを記録しておらず、何が変わったかを後から追えなかった。

想定と違う事態（サービスが止まる、DB の情報を盗まれる）は、前提が崩れたときに起こる。前提は日々変わるので、それに追いつき続ける仕組みが要る。
あわせて、機器の監視に広く使われている Zabbix を、自分の手で入れて運用した経験を作りたい。

決めることは 4 つあった。

1. Zabbix を入れるか（いまの Grafana のままにしないか）
2. どこに置くか（16GB のホストで、既存のサービスに影響しない形）
3. DB を何にして、どこに置くか
4. Web UI をどう見るか（自宅の IP を公開しない方針を守る）

## 決定事項 (Decision)

1. **Zabbix を入れる**。Grafana は残し、**判断と通知は Zabbix、傾向を眺めるのは Grafana** と役割を分ける。通知は Zabbix からだけ出す。
2. **Proxmox 上に Zabbix 専用の非特権 LXC**（Ubuntu 24.04、2 vCPU、メモリ 2048 MiB、swap 512 MiB、ディスク 16 GiB）を作る。
3. **DB はその LXC の中に専用の MariaDB**（Ubuntu 24.04 の apt 版 10.11）を入れる。本番の MariaDB CT には相乗りしない。
4. **Web UI は LAN 内からのみ**（`:8080`、Proxmox ファイアウォールで LAN のセグメントだけ許可）。外から見たくなったら、Cloudflare Tunnel + Cloudflare Access を別の ADR で決める。
5. エージェントは**エージェント 2 をパッシブで**使い、**ホストごとに別の PSK で暗号化**する。Proxmox ホストにはエージェントを入れず、読み取り専用の API トークンで見る。
6. 監視項目は「前提の崩れ」（INC-001 型）を独立した区分として持つ（[監視設計](../../monitoring/monitoring-design.md) の C 区分）。
7. Zabbix のバージョンは **8.0 LTS** にする（2026-11-06 に本人が決定）。
8. OpenTelemetry も並行して入れる。役割の分け方は [ADR-034](034-opentelemetry-introduction.md) で決める。

詳しい内容は次のドキュメントにある。

- [構成案・セキュリティ方針・Grafana との関係](../../monitoring/zabbix-architecture.md)
- [監視設計](../../monitoring/monitoring-design.md)
- [セットアップ手順とロールバック](../../monitoring/zabbix-setup.md)

### 未決（本人が決める）

| 論点 | 案 | 推奨 |
|---|---|---|
| Zabbix・自宅回線が死んだことに誰が気づくか | 外部の死活監視サービス / デッドマンスイッチ / 当面は受け入れる | 未定（監視設計 H-3） |
| テスト環境にもエージェントを入れるか | 入れる / 入れない | 入れる（アラートの試験をテスト環境でできるため。手順書の手順 11） |

## 根拠 (Reason)

### 置き場所: 専用の非特権 LXC

```bash
pct create <CTID> local:vztmpl/<ubuntu-24.04 のテンプレート> \
  --hostname zabbix \
  --cores 2 \
  --memory 2048 \
  --swap 512 \
  --rootfs <STORAGE>:16 \
  --net0 name=eth0,bridge=<BRIDGE>,ip=<ZBX_IP>/<PREFIX>,gw=<GW_IP>,firewall=1 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --password
```

- **アプリ層のゲストに同居させない**: INC-001 のように OS 更新でアプリ層のゲストが壊れたとき、監視も一緒に壊れる。監視する側と監視される側は、同じ理由で一緒に落ちない場所に置く。
- **VM ではなく LXC**: VM はゲストのカーネル分だけメモリを余計に使う。16GB のホストで、既存のサービスへの影響を小さくしたい。
- **`--unprivileged 1`**: Zabbix は全ホストに話しかけられる立場になる。CT が乗っ取られても、CT の root がホストの root にならないようにする。
- **`--memory 2048`**: 公式の要件ページの Small の例は「メトリクス 1,000 件で 8 GiB」だが、これは専用サーバー 1 台の目安で、この構成は数百アイテムを見込む。MariaDB のバッファプールを 512 MiB に絞り、Zabbix 本体・nginx・php-fpm を足して 2 GiB とした。**見込みであって実測ではない**ので、導入 1 週間後に見直す（構成案 2.5）。
- **`--rootfs <STORAGE>:16`**: 公式の計算式（数値 1 値あたり約 90 バイト）で、300 アイテム × 60 秒間隔 × 履歴 7 日 ≒ 約 270 MB。余裕を大きく取っても 16 GiB に収まる。
- **`firewall=1`**: LAN の中でも、Web UI（8080）を見られる範囲と、エージェント（10050）に話しかけられる相手（Zabbix CT だけ）を絞るため。

### DB: Zabbix 専用の MariaDB を同じ CT に

```ini
# /etc/mysql/mariadb.conf.d/60-zabbix.cnf
[mysqld]
innodb_buffer_pool_size = 512M
```

- **本番の MariaDB に相乗りしない**: 「本番 DB が落ちた」ことを、落ちた DB に書こうとすることになる。また Zabbix は書き込みが多く、本番 DB と I/O やバッファプールを食い合う。
- **PostgreSQL ではなく MariaDB**: このリポジトリの運用経験は MariaDB だけ。数百アイテムでは性能の差が出ないので、新しく覚えるものを Zabbix 本体に絞った。
- **Ubuntu 24.04 の apt 版（10.11）**: Zabbix 8.0 のサポート範囲（10.11〜12.3）に入る。ただし**下限ちょうど**なので、Ubuntu を上げずに Zabbix だけ次の版へ上げると下限を割るおそれがある（監視設計 C-11）。
- **設定は別ファイル（`60-zabbix.cnf`）**: Ubuntu のパッケージの設定ファイルを直接書き換えると、パッケージ更新のときに差分の確認を求められる。別ファイルなら、消せば元に戻る。

### 公開方法: LAN のみ

- 自宅の IP を公開しない方針（ARCHITECTURE §6.2、ADR-029）を守る。ルーターのポートは開けない。
- Cloudflare Tunnel で出すことはできるが、**Access を付けずに出すと Zabbix のログイン画面がインターネットに直接さらされる**。Access を付けるなら「誰を通すか」というポリシーの判断が増えるので、外から見る必要が出てから別の ADR で決める。
- どの方法でも、Zabbix 側で初期の `Admin` のパスワードの変更と無効化、MFA（TOTP。7.0 から使え、8.0 にもある）を必須にする。

### バージョン: 8.0 LTS

```bash
wget https://repo.zabbix.com/zabbix/8.0/release/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_8.0+ubuntu24.04_all.deb
dpkg-deb --fsys-tarfile zabbix-release_latest_8.0+ubuntu24.04_all.deb | tar -xO --wildcards '*.sources'
```

- **7.0 で始めて後から上げる案をやめた**: 7.0 のフルサポートは 2027-06-30 まで。8.0 で始めれば 2029-11-30 まで上げ直しが要らない。
- **前日に懸念していた点が解消していた**: 2026-11-05 の時点では、リポジトリ設定パッケージ（`1:8.0-0.4`）が `stable` を指さず `unstable` が有効だった。2026-11-06 に取り直すと `1:8.0-0.5` になり、`stable` を指して `unstable` は `Enabled: no` だった。手順書では、入れる前に `.sources` を表示して確かめる手順を残した。この値は日によって変わりうるため。
- **OpenTelemetry と比べられる**: 8.0 から、OpenTelemetry のデータを Zabbix で扱う機能（APM）が入った。ADR-034 で入れる OpenTelemetry と比べる材料になる。ただし APM には proxy と ClickHouse が要るので、この ADR の範囲では入れない（ADR-034 の段階 4）。

### 前提の崩れを見る UserParameter（INC-001 への直接の答え）

```ini
UserParameter=awaji.venv.python.exec,test -x /Awaji-Empire-Agent/discord_bot/.venv/bin/python3 && echo 1 || echo 0
UserParameter=awaji.venv.import_ok,/Awaji-Empire-Agent/discord_bot/.venv/bin/python3 -c "import quart, discord, hypercorn" >/dev/null 2>&1 && echo 1 || echo 0
UserParameter=awaji.systemd.nrestarts[*],systemctl show -p NRestarts --value "$1"
```

- **`test -x` を使い、Zabbix 標準の `vfs.file.exists` を使わない**: INC-001 の壊れ方は「リンクはあるがリンク先がない」。`test -x` はリンクを最後までたどる。`vfs.file.exists` は公式ドキュメントにリンクをたどるかどうかが書かれていないので、この壊れ方を確実に拾えるとは言えない。
- **import するのは `quart`・`discord`・`hypercorn` の 3 つだけ**: `hypercorn` は INC-001 で実際に見つからなかったモジュール。全依存を import するとエージェントのタイムアウト（既定 3 秒）を超えるおそれがある。
- **再起動の繰り返しは `NRestarts` で数える**: `infra/discord_webapp.service` は `Restart=always` / `RestartSec=5` なので、`active_state` だけを見ると、取得のタイミングによっては `active` に見えて見逃す。自動で再起動した回数を数えれば、取得のタイミングに関係なく拾える。
- 残りの UserParameter と、それぞれのしきい値の理由は [監視設計](../../monitoring/monitoring-design.md) 4 章。

### Grafana を残して役割を分ける

- いまの Grafana で何を見ているかの棚卸し【要確認】をする前に消すと、見ていたものが見えなくなる。
- 通知を両方から出すと、同じ障害で 2 通来て「どちらを見ればいいか」が曖昧になり、通知を無視する癖がつく。だから**通知は Zabbix だけ**にする。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| Zabbix を入れず Grafana のアラートで済ませる | 判断（トリガー）・依存関係・確認済み（Acknowledge）・メンテナンス期間といった運用の仕組みが Zabbix のほうが揃っている。学習の目的（Zabbix の運用経験）も満たせない |
| Prometheus + Alertmanager | 学習の目的が Zabbix の運用経験なので不採用。技術的に劣るという判断ではない |
| 専用の VM に置く | ゲストのカーネル分だけメモリを余計に使う。16GB のホストでは割に合わない |
| アプリ層のゲストに同居 | 監視する側とされる側が同じ理由で一緒に落ちる |
| Proxmox ホストに直接インストール | ハイパーバイザに Web サーバーと DB を足すことになり、PVE の更新と Zabbix の依存関係が絡む |
| 本番の MariaDB に `zabbix` DB を相乗り | 本番 DB が落ちると監視の記録も止まる。I/O とバッファプールを食い合う |
| PostgreSQL（+ TimescaleDB） | 数百アイテムでは差が出ず、運用経験のない DB を増やすことになる |
| Web UI を Cloudflare Tunnel だけで公開（Access なし） | Zabbix のログイン画面がインターネットに直接さらされる |
| Web UI を Cloudflare Tunnel + Access で公開 | 今は不要。必要になったら別の ADR で決める |
| エージェントを暗号化しない | 監視データ（プロセス名・待ち受けポート・パッケージ）は偵察情報になる。LAN 内でも PSK で暗号化する |
| エージェントで `system.run` を有効にする | Zabbix CT を乗っ取られると全ホストで任意のコマンドが実行できてしまう |

## 影響 (Consequences)

### ポジティブ

- INC-001 型の「前提の崩れ」に、サービスが止まる前に気づける（venv の Python が壊れた時点で High が鳴る）。
- OS・カーネル・Python のバージョン・ユニットファイル・待ち受けポートの**変化の履歴**が Zabbix に残る。ADR-029 のように「更新前に何だったか」が分からなくなることを防ぐ。
- Zabbix CT を消せば元に戻る。本番のアプリ（`infra/*.service`・`.env`・コード）には手を入れない。

### ネガティブ・トレードオフ

- Proxmox ホストのメモリを約 2 GiB 使う。いま各ゲストに割り当てているメモリの合計が分からないので、余裕があるかは導入前に確かめる必要がある【要確認】。
- **本番に手を入れるのは 2 か所**: アプリ層ゲストと DB の CT にエージェント 2 を入れること、本番 MariaDB に読み取り専用の監視ユーザー（`zbx_monitor`）を作ること。
- 守るべき秘密が増える（Zabbix の DB パスワード、各ホストの PSK、Proxmox API トークン、MariaDB の監視ユーザーのパスワード、Discord Webhook URL）。どれもアプリの `.env` とは分けて管理する。
- **Zabbix 自体や自宅の回線が止まったときには、Zabbix からの通知も止まる**。外部の見張りをどうするかは未決（監視設計 H-3）。
- 8.0.0（x.0.0）で始めるので、初期の不具合を踏む可能性がある。手順の区切りで `pct snapshot` を取って戻れるようにしてある。
- Bot が Discord の Gateway から切れている状態は、この構成では検知できない（アプリのコード変更が要る）。

## 検証 (Verification)

この ADR はドキュメントの下書きであり、**サーバーには何もインストール・設定していない**。
以下はドキュメントを書くために行った調査で、いずれも実機の動作確認ではない。

- **調査:** Zabbix の公式ライフサイクルのページで LTS の版とサポート期限を確認（8.0 LTS: 2026-11-05 リリース、7.0 LTS: フルサポート 2027-06-30 まで）。
- **調査:** `repo.zabbix.com` から次のパッケージを取得し、`dpkg -c` / `dpkg-deb` で中身を確認した。
  - `zabbix-release_latest_7.0+ubuntu24.04_all.deb`（`1:7.0-5+ubuntu24.04`）: `https://repo.zabbix.com/zabbix/7.0/ubuntu` を指す
  - `zabbix-release_latest_8.0+ubuntu24.04_all.deb`（`1:8.0-0.4+ubuntu24.04`）: `.../8.0/release/ubuntu` と `.../8.0/unstable/ubuntu` を指し、`stable` を指していない（翌日に解消。下記）
  - `zabbix-sql-scripts` 7.0.32: `/usr/share/zabbix-sql-scripts/mysql/server.sql.gz`、8.0.0: `/usr/share/zabbix/sql-scripts/mysql/server.sql.gz`
  - `zabbix-agent2` 7.0.32: 既定値 `Server=127.0.0.1` / `ServerActive=127.0.0.1` / `Hostname=Zabbix server`、`Include=/etc/zabbix/zabbix_agent2.d/*.conf`
  - `zabbix-nginx-conf` 7.0.32: `listen 8080` と `server_name` がコメント、`postinst` が `/etc/nginx/conf.d/zabbix.conf` にリンクを作る
  - `zabbix-server-mysql` 7.0.32: `/etc/zabbix/zabbix_server.conf` は `-rw------- root/root`
- **調査:** Zabbix 公式テンプレート（GitHub ミラー `release/7.0`）の README で、Proxmox VE by HTTP の必要権限とマクロ、Systemd by Zabbix agent 2 のマクロとトリガー、MySQL by Zabbix agent 2 の監視ユーザーの権限、Website certificate by Zabbix agent 2 のトリガーを確認。
- **調査:** Zabbix 7.0 / 8.0 の要件ページ（MariaDB の対応範囲、Small の目安、既定のポート、DB サイズの計算式）、PSK・MFA のページ、Proxmox の `pct`・`pveum` のマニュアル、Cloudflare Access のドキュメントを参照。

  Checked-by: Claude Opus 5.5 (AI agent)、2026-11-05
- **調査（2026-11-06）:** 8.0 に決めたことを受けて、次を取り直した。
  - `zabbix-release_latest_8.0+ubuntu24.04_all.deb`（`1:8.0-0.5+ubuntu24.04`）: `8.0/stable` と `8.0/release` を有効にし、`8.0/unstable` は `Enabled: no`。ほかに `zabbix-tools/debian-ubuntu` を追加する
  - `8.0/stable` の `noble` に `8.0.0-1+ubuntu24.04` がある。`zabbix-agent2` 8.0.0 の既定値は 7.0 と同じ（`Server=127.0.0.1` / `ServerActive=127.0.0.1` / `Hostname=Zabbix server`）
  - `zabbix-nginx-conf` 8.0.0: `listen 8080` と `server_name` がコメントのまま。`postinst` が `/etc/nginx/conf.d/zabbix.conf` にリンクを作る
  - `zabbix-server-mysql` 8.0.0: `/etc/zabbix/zabbix_server.conf` は `-rw-------`。`TelemetryProvider`（ClickHouse のみ）と `StartTelemetryQueryPollers` が増えている
  - 公式テンプレート（Proxmox VE、Linux、Systemd、MySQL agent 2、Website certificate agent 2、Discord）が GitHub ミラーの `release/8.0` にあること
  - Debian 13・Ubuntu 26.04 向けの `zabbix-release_latest_8.0` があること

  Checked-by: Claude Opus 5.5 (AI agent)、2026-11-06

### 未検証

- 手順書のすべてのコマンド（実機で一度も通していない）
- メモリ 2048 MiB で足りるか（実測なし）
- 自作 UserParameter が `zabbix` ユーザーの権限で期待どおりの値を返すか（とくに venv の読み取り権限と、import のタイムアウト）
- `NRestarts` が手動の `systemctl restart` で 0 に戻るか、前処理 Simple change が値の減少をどう扱うか
- Zabbix 公式のダウンロードページの手順との突き合わせ（ページが JavaScript で生成されるため取得できなかった）
- 構成案 1.1 の Q1〜Q8（アプリ層が VM か LXC か、本番の OS バージョンなど）

## 関連ドキュメント

- 関連 ADR: [ADR-029](../021-030/029-production-kernel-update-cve-2026-99999.md)（更新前のバージョンを記録していなかった）, [ADR-030](../021-030/030-domain-registrar-transfer-to-cloudflare.md)（Cloudflare への集約）, [ADR-028](../021-030/028-docker-compose-dev-environment.md)（本番の構成の記述）
- インシデント: [INC-001](../../incidents/INC-001-ubuntu26-venv-broken.md)
- 監視ドキュメント: [docs/monitoring/](../../monitoring/README.md)
- Zabbix ライフサイクル: <https://www.zabbix.com/life_cycle_and_release_policy>
- Zabbix 8.0 要件: <https://www.zabbix.com/documentation/8.0/en/manual/installation/requirements>
