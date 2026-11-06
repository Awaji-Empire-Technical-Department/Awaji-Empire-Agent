# ADR-034: OpenTelemetry の導入（Zabbix 8.0 と並行し、役割を分ける）

- **ステータス**: 提案中（下書き。導入前）
- **作成日**: 2026-11-06
- **作成者**: Wanyaldee
- **ブランチ**: `Wanyaldee/zabbix-setup-doc`

---

## 背景 (Context)

[ADR-033](033-zabbix-monitoring-introduction.md) で、「前提の崩れ」を見るために Zabbix を入れると決めた（2026-11-06 にバージョンを 8.0 LTS に決定）。

そのあと、OpenTelemetry（以下 OTel）も入れるかを検討した。きっかけは 2 つ。

- さくらインターネットのクラウド基盤では、機器の監視を Zabbix で続けながら、マイクロサービスのメトリクスを OTel Collector で集め直している（[さくらのIaaS基盤のモニタリングとOpenTelemetry](https://knowledge.sakura.ad.jp/45164/)、OSC 2025 Hokkaido の発表を記事にしたもの、2025-07-30 公開）。旧構成（Prometheus）と並行稼働させながら移している。ネットワーク機器と物理サーバーは今も Zabbix で見ている。
- 「OTel を使い、障害の前ぶれになる状態を何で捉えるかを自宅の Proxmox で試す」と、すでに外部に書いている。小さくてもよいので、実際に動かしておく必要がある。

決めることは 3 つあった。

1. Zabbix を OTel に置き換えるか、両方入れるか
2. OTel で集めたデータをどこに貯め、何で見るか
3. どこまでを最初にやるか（16 GB のホストで、本番にどこまで触れるか）

## 決定事項 (Decision)

1. **Zabbix は置き換えない。両方入れて役割を分ける。** Zabbix は「判断して知らせる」、OTel は「集めて運ぶ」。**通知は Zabbix だけ**から出す（ADR-033 のまま）。
2. **専用の非特権 LXC（OTel CT）**を作り、OTel Collector（コア版 `otelcol` 0.164.0）をゲートウェイとして置く。貯めるのは同じ CT の **Prometheus 2.45（Ubuntu の apt 版）**で、Collector から remote write で送る。見るのは既存の Grafana。
3. **段階 1（最初にやる）**: Proxmox VE 9 の Metric Server（OpenTelemetry）から OTLP/HTTP で Collector に送る。Proxmox ホストにも本番のゲストにも、何も入れない。
4. 段階 2: アプリ層ゲストに Collector をエージェントとして入れ、`host_metrics` で OS の指標を送る。段階 3（アプリの計装）と段階 4（Zabbix 8.0 の APM との比較）は、それぞれ別の ADR で決める。

手順: [docs/monitoring/opentelemetry-setup.md](../../monitoring/opentelemetry-setup.md)

## 根拠 (Reason)

### Zabbix と OTel を両方入れる

- **OTel は「判断して知らせる」部分を持たない**: OTel が決めているのは、データの形式（OTLP）と、集めて運ぶ仕組み（SDK・Collector）まで。アラートの判断は、送り先（Prometheus の Alertmanager・Zabbix・SaaS）の仕事になる。OTel だけにすると、ADR-033 で決めた「前提の崩れ」のトリガーと通知を、別の道具で作り直すことになる。
- **INC-001 型の監視は、OTel の標準の部品では作れない**: ADR-033 の UserParameter（`test -x .venv/bin/python3`、`import quart, discord, hypercorn`、`NRestarts`）にあたる receiver は、コア版 Collector にはない。
- **さくらインターネットも分けている**: 機器は Zabbix、サービスのメトリクスは OTel。自宅で同じように分けて試すことで、両方を触って比べた感触を自分の言葉で話せる。

### 段階 1: Proxmox の Metric Server から送る

```bash
pvesh create /cluster/metrics/server/otel --type opentelemetry --server <OTEL_IP> --port 4318 --otel-protocol http
```

- **エージェントを入れない**: Proxmox VE 9 から、外部の Metric Server の送り先に `opentelemetry` を選べる（API の `type` の選択肢は `graphite`・`influxdb`・`opentelemetry`）。ハイパーバイザに外部のリポジトリとパッケージを足さずに済む。ADR-033 で「Proxmox ホストにはエージェントを入れない」と決めた理由と同じ。
- **`--port 4318`**: 送り方は OTLP/HTTP（API の項目が `otel-protocol` = `http`/`https`、`otel-path` = 既定 `/v1/metrics`）。4318 は OTLP/HTTP の既定のポートで、Collector の `otlp` receiver の HTTP の既定とも合う。
- **`--otel-protocol http`**（既定は `https`）: Collector 側に証明書を用意していない。流れるのは LAN の中だけで、中身は資源の数値だけ。代わりに、OTel CT の 4318 に届く送信元を Proxmox ホストの IP だけに絞る（手順 8）。TLS は後の課題として手順書の 11 章に残した。

### Collector の設定（ゲートウェイ）

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: <OTEL_IP>:4318
      grpc:
        endpoint: <OTEL_IP>:4317
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 200
    spike_limit_mib: 50
  batch: {}
exporters:
  prometheus_remote_write:
    http:
      endpoint: http://<OTEL_IP>:9090/api/v1/write
      tls:
        insecure: true
    max_batch_request_parallelism: 1
    resource_constant_labels:
      included: ["*"]
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus_remote_write]
```

（`extensions`・`telemetry`・`debug` を省いた抜粋。全体は手順書の手順 4）

- **コア版の `otelcol`、`contrib` 版ではない**: 上で使う部品は、すべてコア版の `manifest.yaml`（v0.164.0）に入っている。`contrib` 版は 200 を超える部品を含み、使わない部品の脆弱性の通知まで読むことになる。さくらインターネットは、さらに OCB で必要な部品だけを組み込んでいる。それは手順書の 11 章の課題にした。
- **待ち受けを `<OTEL_IP>` にし、受けるのは `otlp` だけ**: deb の既定の `config.yaml` は、`otlp`・`jaeger`・`zipkin`・`pprof`（1777）・`zpages`（55679）を `0.0.0.0` で待ち受ける。`pprof` と `zpages` はデバッグ用で、外から触れてよいものではない。使わないものは書かず、ポートを開けない。
- **`memory_limiter`、上限 200 MiB**: CT のメモリは 1024 MiB で、Prometheus と同居している。Collector がメモリを使い切ると Prometheus ごと落ちる。上限を超えたら、受け取りを断って送り手に再送させる。急増分 50 MiB は、README の目安（上限の 20%）に近い値。
- **`prometheus_remote_write`（`prometheusremotewrite` ではない）**: v0.164 の `metadata.yaml` で、`type: prometheus_remote_write`、`deprecated_type: prometheusremotewrite` になっている。gRPC 側の `otlp_grpc`、`host_metrics`、`resource_detection` も同じく改名されていた。古い名前でも動くが、非推奨の警告がログに出続ける。
- **`max_batch_request_parallelism: 1`**: 既定は 5 並列。Prometheus 2.45 は既定で、時刻が前後したサンプルを受け付けない。README は、そういう送り先には 1 にするよう書いている。5 のままだと、並列に送ったうちの後着分が拒否されるおそれがある。
- **`resource_constant_labels.included: ["*"]`**: Proxmox が付けてくる「どのノード・どのゲストか」はリソース属性に入る。ラベルにしないと、Prometheus 上でゲストを区別できない。v0.164 の README で非推奨になった `resource_to_telemetry_conversion` は使わない。

### 貯める先: 同じ CT の Prometheus 2.45（apt 版）

```bash
ARGS="--web.listen-address=<OTEL_IP>:9090 --web.enable-remote-write-receiver --storage.tsdb.retention.time=30d"
```

- **apt 版（2.45.3）**: Ubuntu のセキュリティ更新が `apt` で届く。3.x は公式のバイナリを手で置くことになり、更新を自分で追う必要がある。
- **2.45 は OTLP を直接受けられないので、remote write で送る**: OTLP の受け口は 3.x の機能。`--web.enable-remote-write-receiver` があることは、apt 版のバイナリで確かめた。
- **remote write の受け口には認証がない**: このポートに届く相手は誰でも書き込める。だから 9090 に届く相手を Grafana のゲストだけに絞る（手順 8）。
- **`retention.time=30d`**（既定 15 日）: 月 1 回の振り返りで 1 か月分を見る。

### Zabbix CT に同居させない

- 「Zabbix と OTel を比べる」ので、片方を止めても、もう片方に影響しないようにする。メモリの取り合いで、比べた結果がゆがむのも避ける。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|---|---|
| Zabbix をやめて OTel だけにする | OTel は判断と通知を持たない。ADR-033 の「前提の崩れ」の監視を別の道具で作り直すことになる。Zabbix の運用経験という学習の目的も満たせない |
| OTel を入れず Zabbix だけにする | 「OTel を自宅で試す」と外部に書いた内容を実行できない。さくらインターネットが移行している仕組みを触らずに話すことになる |
| Collector から Zabbix 8.0 に直接送る（APM） | Zabbix 8.0 で OTLP を受けるのは proxy で、保存先に ClickHouse が必要（`TelemetryProvider` の選択肢は `clickhouse` だけ）。proxy と ClickHouse の 2 つが増える。トレースがないうちは APM の機能がほとんど活きない。段階 4 として後回しにした |
| Prometheus 3.x を公式のバイナリで入れ、OTLP で受ける | remote write を挟まずに済むが、更新を自分で追う必要がある。手順書の 11 章の課題にした |
| `contrib` 版の Collector | 使わない部品が多く、脆弱性の通知を読む範囲が広がる |
| Proxmox ホストに Collector を入れる | ハイパーバイザにパッケージを足すことになる。Metric Server の機能で足りる |
| Grafana でアラートを出す | 同じ障害で Zabbix と Grafana から 2 通来て、どちらを見ればよいかが曖昧になる（ADR-033） |
| Zabbix CT に Collector と Prometheus を同居 | 比べる対象どうしが互いに影響する |

## 影響 (Consequences)

### ポジティブ

- 段階 1 は、Proxmox ホストにも本番のゲストにも何も入れずにできる。Proxmox の送信先を消して CT を消せば、元に戻る。
- Proxmox ホストと全ゲストの資源の推移が、Grafana で見られるようになる。
- 送り先を変えるときは、Collector の exporter を足すだけで済む（段階 4 で Zabbix にも送る、など）。

### ネガティブ・トレードオフ

- Proxmox ホストのメモリを、さらに約 1 GiB 使う（Zabbix CT と合わせて約 3 GiB）。余裕があるかは、導入前に確かめる必要がある【要確認】。
- Collector には apt リポジトリがない。更新を GitHub のリリースで追う必要がある。
- Proxmox → Collector と、アプリ層 → Collector は平文で流れる。送信元を IP で絞って補っている。
- Prometheus 2.45 の remote write の受け口には認証がない。経路の制限だけで守っている。
- 段階 2 から、本番のゲストに Collector を入れる。
- 「前提の崩れ」は OTel 側では見られない。これは Zabbix の役割のまま。

## 検証 (Verification)

この ADR はドキュメントの下書きであり、**サーバーには何もインストール・設定していない**。
以下はドキュメントを書くために行った調査で、いずれも実機の動作確認ではない。

- **調査:** `otelcol_0.164.0_linux_amd64.deb` を取得し、リリースの `.sha256` と照合した。

  ```
  $ sha256sum -c a.sha256
  sha256sum: a.sha256: チェックサムとして適切な書式の行がありませんでした
  $ echo "$(cat a.sha256 | awk '{print $1}')  otelcol_0.164.0_linux_amd64.deb" | sha256sum -c
  otelcol_0.164.0_linux_amd64.deb: OK
  ```

  `.sha256` はハッシュ値だけのファイルで、`sha256sum -c` に直接渡すと上のエラーになった。手順書のコマンドは、この結果に合わせて組み立てた。
- **調査:** 同じ deb の中身を `dpkg-deb -c` / `-e` / `-x` で確認した。`/etc/otelcol/config.yaml`・`/etc/otelcol/otelcol.conf`・`/lib/systemd/system/otelcol.service`（`User=otel`）があること。`preinst` が `otel` ユーザーを作り、`postinst` が `systemctl enable` と `restart` を実行すること。既定の `config.yaml` が `0.0.0.0` で 4317・4318・14250・6831・6832・14268・9411・1777・55679 を待ち受けること。
- **調査:** コア版の `manifest.yaml`（v0.164.0）に、使う部品がすべて入っていること。各部品の `metadata.yaml` の `type` と `deprecated_type`。`prometheus_remote_write` の README の設定項目（`http.endpoint`・`max_batch_request_parallelism`・`resource_constant_labels`、`resource_to_telemetry_conversion` が非推奨であること）。
- **調査:** Ubuntu noble の `prometheus_2.45.3+ds-2ubuntu0.3_amd64.deb` を取得し、`/etc/default/prometheus`（`ARGS=""`）・ユニットファイル・既定の `prometheus.yml`・バイナリに `web.enable-remote-write-receiver` の文字列があることを確認した。
- **調査:** Proxmox の API 定義で、`/cluster/metrics/server/{id}` の POST の必須項目（`id`・`port`・`server`・`type`）、`type` の選択肢、`otel-*` の各項目と既定値を確認した。
- **調査:** Zabbix 8.0.0 の `zabbix-server-mysql` と `zabbix-proxy-sqlite3` の設定ファイルで、`TelemetryProvider`（ClickHouse のみ）、proxy の `StartAPMCollector`（既定 0）・`APMListenPort`（既定 4317）を確認した。公式の What's new と Package installation notes で、OTLP を受けるのが proxy であること、Ubuntu 24.04 では proxy のパッケージに APM が含まれることを確認した。

  Checked-by: Claude Opus 5.5 (AI agent)、2026-11-06

### 未検証

- **`otelcol validate` を通していない**。取得した `otelcol` のバイナリを手元で動かそうとしたが、実行の許可が出なかった。設定の項目名は README と `metadata.yaml` で確かめたが、検査器にはかけていない。手順書では、実機で必ず `otelcol validate` を通してから起動する手順にした。
- 手順書のすべてのコマンド（実機で一度も通していない）
- `dpkg -i --force-confold` で、先に置いた `/etc/otelcol/config.yaml` が残るか
- Proxmox が送ってくるメトリクスの名前とラベル（公式に一覧がない）
- Prometheus のユニットファイルの防御設定（`PrivateUsers=true` など）が、非特権 LXC で動くか
- OTel CT のメモリ 1024 MiB で足りるか
- 既存の Grafana の場所とデータソース（[Zabbix 構成案](../../monitoring/zabbix-architecture.md) Q6）

## 関連ドキュメント

- 関連 ADR: [ADR-033](033-zabbix-monitoring-introduction.md)（Zabbix の導入。通知は Zabbix に一本化）
- 手順書: [docs/monitoring/opentelemetry-setup.md](../../monitoring/opentelemetry-setup.md)
- さくらインターネットの事例: <https://knowledge.sakura.ad.jp/45164/>、<https://knowledge.sakura.ad.jp/51163/>
- Collector のリリース: <https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.164.0>
- Zabbix 8.0 の APM: <https://www.zabbix.com/documentation/8.0/en/manual/introduction/whatsnew>
