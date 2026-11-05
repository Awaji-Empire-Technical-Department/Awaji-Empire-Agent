# 監視設計: 何を見るか、なぜ見るか、どうなったらアラートにするか

- **ステータス**: 下書き（未導入。しきい値は初期値で、導入後の実測で見直す）
- **作成日**: 2026-11-05
- **関連**: [構成案](zabbix-architecture.md) / [セットアップ手順](zabbix-setup.md) / [学んだこと](zabbix-lessons.md) / [INC-001](../incidents/INC-001-ubuntu26-venv-broken.md)

---

## 1. 考え方

テンプレートを当てれば数百のアイテムとトリガーが一度に入る。
しかし「それが鳴ったら何をするか」が決まっていないアラートは、何回か鳴ったあと無視されるようになる。
そこで、この設計では次の順に考える。

1. **何が起きたら困るか**（利用者に見える停止・データの漏えい・気づかないうちの劣化）
2. **それは何が崩れたときに起きるか**（前提）
3. **その前提を、何で見られるか**（アイテム）
4. **どうなったら人が動くべきか**（トリガー）。**動かなくてよいものは通知しない**

監視項目を次の 8 つに分ける。**C（前提の崩れ）** がこの設計の中心である。

| 区分 | 見るもの | 主な問い |
|---|---|---|
| A | Proxmox ホスト | 土台は生きているか、資源は足りているか |
| B | 各ゲスト（LXC / VM） | 各ゲストの OS は健康か |
| **C** | **前提の崩れ** | **動いている前提が、今も成り立っているか。変わっていないか** |
| D | アプリのサービス | 3 つのプロセスは動き続けているか |
| E | MariaDB | DB は応答しているか、異常な接続はないか |
| F | 外から見た死活 | 利用者から見て使えるか |
| G | セキュリティの前提 | 不審なアクセス・証明書・意図しない待ち受けはないか |
| H | 監視自身 | 監視と通知は動いているか |

---

## 2. 重要度と通知の決まり（アラートを無視させない工夫の中心）

| 重要度（Zabbix） | 意味 | 通知 | 受けたら何をするか |
|---|---|---|---|
| **Disaster** | 利用者に見える停止が**いま**起きている | Discord の通知チャンネル + **メンション** | すぐ対応する |
| **High** | 放っておくと**近いうちに**停止する、またはセキュリティ上の異常 | Discord の通知チャンネル + **メンション** | その日のうちに対応する |
| **Average** | 劣化している。止まってはいない | Discord の通知チャンネル（メンションなし） | 次に作業するときに見る |
| **Warning** | 傾向として気にしておくもの | Discord の通知チャンネル（メンションなし） | 週 1 回の見直しで見る |
| **Information** | **前提が変わった**という記録 | Discord の**変更記録チャンネル**（メンションなし） | 「意図した変更か」を確かめ、確認済み（Acknowledge）にコメントを書いて閉じる |

決まりごと:

1. **「受けたら何をするか」が書けないトリガーは、通知しない**（Information にするか、無効にする）。
2. **一度の失敗では鳴らさない**。デプロイ（`master` への push のたびに 3 サービスを `systemctl restart`、`.github/workflows/deploy.yml`）で数秒止まるのは正常なので、しきい値は「N 分続いたら」で書く。デプロイの時刻は決まっていないので、メンテナンス期間では吸収できない。
3. **依存関係を張る**。Proxmox ホストが落ちたら、その上のゲストのアラートは出さない。アプリ層ゲストのエージェントに届かないときは、そのゲストのサービスのアラートは出さない。1 つの原因で通知が 10 通来ると、肝心の 1 通が埋もれる。
4. **変化の検知（C 区分）は Information**。変化そのものは異常ではない。しかし INC-001 は「OS が変わった」ことに誰も気づかなかったことが始まりだった。変化を**記録して、人が意図した変化かどうかを確かめる**ところまでを仕組みにする（手動クローズ + 確認済みのコメント）。
5. **計画した作業（OS 更新など）の前にはメンテナンス期間を設定する**。その間に鳴る C 区分の変化は、作業の記録として残る。
6. **週 1 回の見直し**（[zabbix-lessons.md](zabbix-lessons.md) の「アラートの見直し記録」に書く）:
   - 先週鳴ったトリガーの一覧（*Reports → Top 100 triggers*）
   - **鳴ったが何もしなかった**ものは、しきい値を直すか、通知をやめるか、消す
   - 鳴るべきだったのに鳴らなかったもの（障害に気づいた経路が Zabbix 以外だったもの）は、項目を足す
7. しきい値は**公式テンプレートの既定値から始め**、変えたら理由を lessons に残す。

---

## 3. 監視項目

表の「取り方」の列:
- **[T: テンプレート名]** は Zabbix 公式テンプレート（出典は 5 章）。
- **[K: キー]** はエージェントの標準キー。
- **[U: キー]** は自作の UserParameter（定義は 4 章）。

トリガー式は Zabbix 7.0 の書式で、ホスト名は `HOST` と書いた。導入時に Web UI で作るときの下書きであり、**式は Web UI の「Test」で確かめてから保存する**。

### A. Proxmox ホスト

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| A-1 | Proxmox API が応答するか | 全ゲストの土台。API が落ちると A の他の項目も取れない | [T: Proxmox VE by HTTP] `proxmox.api.available` | 応答コードが 200 以外（テンプレート既定） | High |
| A-2 | ホストのメモリ使用率 | 16GB にゲストを詰めているので、Zabbix CT の追加を含めて余裕がなくなるとゲストが OOM で落ちる | [T: Proxmox VE by HTTP] ノードのメモリ | 90% 超が 15 分続く（`{$PVE.MEMORY.PUSE.MAX.WARN}` 既定 90） | Average |
| A-3 | ホストの swap 使用率 | メモリ不足は swap の増加として先に表れる | [T: Proxmox VE by HTTP] | 90% 超（`{$PVE.SWAP.PUSE.MAX.WARN}` 既定 90）。**実測後に下げることを検討**（swap を使い始めた時点で気づきたい） | Average |
| A-4 | ストレージ使用率 | SSD 500GB が埋まると、全ゲストの書き込みが止まる（DB も止まる） | [T: Proxmox VE by HTTP] `{$PVE.STORAGE.PUSE.MAX.WARN}` | 90% 超 | High |
| A-5 | ルートファイルシステムの使用率 | ホストの `/` が埋まると Proxmox 自身が不安定になる | [T: Proxmox VE by HTTP] `{$PVE.ROOT.PUSE.MAX.WARN}` | 90% 超 | High |
| A-6 | ゲストの稼働状態 | 本番のアプリ層・DB のゲストが止まっていないか | [T: Proxmox VE by HTTP] LXC / QEMU の discovery | 本番ゲストが `running` 以外【要確認: テンプレートのトリガー名と、停止中のテスト用ゲストを除外する方法】 | Disaster |
| A-7 | ホストの CPU 使用率 | i3 9100F（4C/4T）は余裕が小さい。継続的な高負荷は Rust のビルド（CI）と重なると応答遅延になる | [T: Proxmox VE by HTTP] `{$PVE.CPU.PUSE.MAX.WARN}` | 90% 超が 15 分続く | Warning |

ディスクの SMART（寿命）は **今回は見ない**。エージェント 2 の SMART プラグインは `smartctl` を root 権限で動かす必要があり、「監視のために sudo を与えない」（[構成案](zabbix-architecture.md) 3.3）と衝突する。代わりに Proxmox の GUI（*Disks*）で月 1 回目視する（lessons のチェックリストに入れる）。

### B. 各ゲスト（アプリ層・DB・Zabbix 自身）

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| B-1 | エージェントに届くか | 届かないと、そのゲストの他の項目は全部「データなし」になる | [T: Linux by Zabbix agent] `agent.ping` | 5 分間データなし（`nodata(/HOST/agent.ping,5m)=1`） | High。**A-6 に依存**させる |
| B-2 | ファイルシステムの使用率・inode | ログや venv の再作成でディスクが埋まると、サービスは「起動できない」形で止まる | [T: Linux by Zabbix agent] FS discovery | テンプレート既定（使用率と inode） | Average |
| B-3 | 使えるメモリ | OOM Killer がアプリのプロセスを殺すと、systemd の再起動で一見直ったように見える | [T: Linux by Zabbix agent] `{$MEMORY.AVAILABLE.MIN}` 既定 20M / `{$MEMORY.UTIL.MAX}` 既定 90 | テンプレート既定 | Average |
| B-4 | 時刻のずれ | Discord OAuth・Cookie・TLS は時刻に依存する。ずれるとログインが失敗する | [T: Linux by Zabbix agent] `system.localtime`（`{$SYSTEM.FUZZYTIME.MIN}` 既定 10s） | テンプレート既定 | Warning |
| B-5 | 再起動された | 意図しない再起動（OOM・カーネルパニック・ホストの再起動）に気づく | [T: Linux by Zabbix agent] `system.uptime` | テンプレート既定（稼働時間が短い）。**Information に下げる**。計画した再起動のたびに鳴るため | Information |

### C. 前提の崩れ（この設計の中心）

INC-001 では、`.venv/bin/python3 → python → （実体なし）` となっていた。
**動いている Python のプロセスはメモリに載っているので、ファイルが壊れても止まらない。止まるのは次に再起動したとき**である。
そしてデプロイのたびに再起動するので、「壊れた瞬間」と「止まった瞬間」の間に、気づける時間がある。C 区分はその時間を使うための項目である。

| ID | 何を見るか（前提） | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| C-1 | **venv の `python3` の実体があり、実行できる** | INC-001 の直接の原因。壊れていても、いま動いているプロセスは止まらない。**次の再起動で止まる**ことを先に知る | [U: `awaji.venv.python.exec`]（5 分ごと） | 0（実行できない）になった。1 回で鳴らす（壊れたら自然には直らないため） | **High** |
| C-2 | **venv から主要なモジュールが import できる** | INC-001 では `ModuleNotFoundError: No module named 'hypercorn'` で落ちた。`python3` があっても、パッケージが揃っていなければ同じ | [U: `awaji.venv.import_ok`]（10 分ごと） | 0 が 2 回続く（`max(/HOST/awaji.venv.import_ok,#2)=0`。`uv sync` の途中を拾わないため） | **High** |
| C-3 | venv の `python3` が指している**実体のパス** | INC-001 では、OS 更新でシステム Python のパスが変わったことが壊れた理由だった。パスが変わったこと自体を、壊れる前に記録する | [U: `awaji.venv.python.realpath`]（1 時間ごと、テキスト） | 前回の値と違う（`last(/HOST/awaji.venv.python.realpath)<>last(/HOST/awaji.venv.python.realpath,#2)`） | Information（手動クローズ） |
| C-4 | システムの Python のバージョン | `uv venv --python /usr/bin/python3`（INC-001 の解決策）は、`/usr/bin/python3` の中身が変わると前提が変わる。`pyproject.toml` は `requires-python = ">=3.12"` | [U: `awaji.system.python.version`]（1 時間ごと） | 前回の値と違う | Information（手動クローズ） |
| C-5 | **OS のバージョン・カーネル** | INC-001 は 24.04 → 26.04 の更新が引き金だった。ADR-029 では「更新前のカーネルを記録していない」ことが問題になった。Zabbix に履歴が残れば、いつ変わったかを後から追える | [K: `system.sw.os[short]`]（1 時間ごと） / [K: `system.uname`]（1 時間ごと） | 前回の値と違う | Information（手動クローズ） |
| C-6 | **再起動待ち**（`/var/run/reboot-required` がある） | ADR-029 の教訓。「カーネルは入れただけでは差し替わらず、再起動するまで古いカーネルが動き続ける。更新済みに見えてしまう」 | [K: `vfs.file.exists[/var/run/reboot-required]`]（1 時間ごと） | 1 が 7 日続く（`min(/HOST/vfs.file.exists[/var/run/reboot-required],7d)=1`） | Warning |
| C-7 | 未適用のセキュリティ更新の数 | 「パッチが当たっている」という前提。ADR-029 のように CVE が出たとき、未適用の更新がどれだけあるかを即答できるようにする | [U: `awaji.apt.security`]（6 時間ごと） | 1 以上が 7 日続く | Warning |
| C-8 | **待ち受けているポートの一覧** | 「外から届くのは Tunnel だけ、DB は 3306 だけ」という前提。意図しないサービスが待ち受けを始めたら気づく（構成案 3.5 の `0.0.0.0:5000` の件もここで見える） | [U: `awaji.listen.ports`]（1 時間ごと、テキスト） | 前回の値と違う | Information（手動クローズ） |
| C-9 | systemd ユニットファイルの中身 | `infra/*.service` は CI が `/etc/systemd/system/` に上書きする（`scripts/setup-systemd.sh`）。`ExecStart` の Python のパスが変わると INC-001 の再発条件が変わる | [K: `vfs.file.cksum[/etc/systemd/system/discord_webapp.service,sha256]`] ほか 2 ユニット（1 時間ごと） | 前回の値と違う | Information（手動クローズ） |
| C-10 | インストール済みパッケージの変化 | 障害が起きたとき「直前に何が変わったか」を Zabbix の履歴から引けるようにする | [K: `vfs.file.cksum[/var/lib/dpkg/status,sha256]`]（1 時間ごと） | **通知しない**（トリガーを作らず、履歴だけ残す）。apt を使うたびに変わるため | — |
| C-11 | Zabbix・MariaDB・OS のサポート期限 | 「サポートされている版を使っている」という前提。Zabbix 7.0 のフルサポートは 2027-06-30 まで。8.0 は MariaDB の下限が 10.11 | 自動化しない。[zabbix-lessons.md](zabbix-lessons.md) の「期限の一覧」に日付を書き、カレンダーに入れる | 期限の 90 日前に作業を始める | — |

C-1〜C-3 はアプリ層のゲストだけに入れる。C-4〜C-8・C-10 は Linux のゲスト全部、C-9 はアプリ層だけに入れる。

**sudoers の構文**（INC-001 の「sudoers の警告も要対応」）は Zabbix では見ない。`/etc/sudoers.d/*` は root しか読めず、`visudo -c` も root が要る。Zabbix に root を渡すほうが危ない。代わりに、OS 更新後のチェックリスト（INC-001 の再発防止策）に残す。

### D. アプリのサービス

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| D-1 | 3 サービスが `active` か | Bot・Web・bridge のどれかが止まると、機能が止まる | [T: Systemd by Zabbix agent 2] `systemd.service.active_state[...]`。対象を `{$SYSTEMD.NAME.SERVICE.MATCHES}` で絞る（下記） | `active` 以外が 3 分続く（デプロイの再起動を拾わないため。テンプレート既定の「1 回で鳴る」から変える） | **Disaster** |
| D-2 | **再起動を繰り返していないか** | INC-001 の症状は「起動直後にクラッシュを繰り返す（Restart ループ）」。`Restart=always` + `RestartSec=5` なので、D-1 は `activating` と `active` を行き来し、取得のタイミングによっては `active` に見える | [U: `awaji.systemd.nrestarts[discord_webapp.service]`] ほか 2 サービス（1 分ごと）。アイテムの前処理に **Simple change**（前回との差）を入れ、「1 分あたりに増えた回数」として保存する | 10 分間の合計が 3 以上（`sum(/HOST/awaji.systemd.nrestarts[discord_webapp.service],10m)>=3`） | **High** |
| D-3 | bridge の `/health` | bridge が動いていても DB に繋がっていなければ、DB を使う機能が全部失敗する。`/health` は DB への問い合わせまで含む（`database_bridge/src/api/handlers/mod.rs:56-58`） | [K: `web.page.get[127.0.0.1,/health,7878]`]（1 分ごと）+ 前処理で HTTP のステータス行を取り出す。bridge は `127.0.0.1` だけで待ち受けているので、Zabbix サーバーからの HTTP ではなく、同じゲストのエージェントから取る | 200 以外が 3 分続く | High。**E-1 に依存**させる（DB が落ちているなら原因は DB） |
| D-4 | webapp（`:5000`）と nginx（`:80`）が TCP で応答するか | プロセスがいても待ち受けていない状態を拾う | [K: `net.tcp.service[tcp,127.0.0.1,5000]`] / [K: `net.tcp.service[http,127.0.0.1,80]`] | 0 が 3 分続く | High。**D-1 に依存** |
| D-5 | `cloudflared` が動いているか | 外部公開の唯一の経路 | [T: Systemd by Zabbix agent 2]【要確認: `cloudflared` がどのゲストで、どのユニット名で動いているか（構成案 Q5）】 | `active` 以外が 3 分続く | Disaster |

Systemd テンプレートの調整:

- `{$SYSTEMD.NAME.SERVICE.MATCHES}` を `^(database_bridge|discord_bot|discord_webapp|nginx|ssh|cloudflared)\.service$` のように**見るものだけに絞る**（既定の `.+` だと、OS の enabled なサービス全部が対象になってアラートが増える）【要確認: 各ゲストで実際に動いているユニット名】。
- テンプレートのトリガー「`{#UNIT.NAME} has been restarted`」（稼働時間 10 分未満で Info）は**無効にする**。デプロイのたびに 3 サービスとも鳴るので、すぐに無視するようになる。再起動の繰り返しは D-2 で見る。

**見えていないもの**: Bot のプロセスは動いているが Discord の Gateway から切れている状態は、いまの仕組みでは検知できない。Bot 側に「最後にイベントを受けた時刻」をファイルに書く仕組みなどを足せば `vfs.file.time` で見られるが、アプリのコード変更になるので今回は入れない（lessons の「次にやること」に置く）。

### E. MariaDB（本番 DB の CT）

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| E-1 | DB が応答するか | 全機能の土台 | [T: MySQL by Zabbix agent 2] `mysql.ping` | テンプレート既定 | **Disaster** |
| E-2 | DB が再起動された | 意図しない再起動（OOM など） | [T: MySQL by Zabbix agent 2] uptime | テンプレート既定。Information に下げる | Information |
| E-3 | 接続の失敗（Aborted connects） | **「DB の情報を盗まれる」前提の崩れ**。認証の失敗が増えるのは、パスワードの総当たりか、設定の不整合（アプリのパスワードが変わった）のどちらか。どちらも人が見るべき | [T: MySQL by Zabbix agent 2] `{$MYSQL.ABORTED_CONN.MAX.WARN}` 既定 3 | テンプレート既定。実測で見直す | **High** に上げる |
| E-4 | 接続数・スロークエリ・バッファプール | 性能の劣化 | [T: MySQL by Zabbix agent 2] 既定のマクロ | テンプレート既定 | Warning |
| E-5 | DB の CT のディスク | B-2 と同じ。DB は書けなくなると止まる | [T: Linux by Zabbix agent] | テンプレート既定 | High に上げる |

監視用の DB ユーザーは、テンプレートの README の例では `'zbx_monitor'@'%'` だが、**`'zbx_monitor'@'localhost'` にする**。エージェント 2 は DB と同じ CT で動くので、ネットワーク越しに許す必要がない。

DB のユーザー一覧（`mysql.user`）の変化を見る案もあるが、**今回は入れない**。監視用ユーザーに `mysql.user` の SELECT 権限を足す必要があり、監視用ユーザーが漏れたときに見られる範囲が広がる。

### F. 外から見た死活

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| F-1 | `https://dashboard.awajiempire.net/` が期待どおりに応答するか | 利用者から見た「使えるか」。D 区分が全部正常でも、Tunnel・DNS・Cloudflare 側の設定で届かないことがある | Zabbix の **Web シナリオ**（Zabbix CT から実行）。リダイレクトを**追わない**設定で `/` を GET し、ステータス 302 を期待する（`discord_bot/webapp.py:269-273` の挙動）。`Location` が `/login` を含むかの確認は【要確認: Web シナリオでレスポンスヘッダーを検査する方法】 | 3 回続けて失敗（1 分間隔） | **Disaster** |
| F-2 | 応答時間 | 劣化に先に気づく | F-1 の Web シナリオの応答時間 | 5 秒超が 10 分続く（初期値。実測で見直す） | Warning |

F-1 の限界:
- Zabbix CT から自宅の回線 → Cloudflare → Tunnel → 自宅、と回るので、**自宅の回線が切れると F-1 も通知（Discord）も両方届かない**。この場合は H-3 で気づく。
- `/` の 302 は、ログインの先（Discord OAuth）や bridge・DB までは確かめていない。そこは D-3・E-1 で見る。
- `/login` は呼ぶたびに OAuth の `state` を作ってセッションに入れるので、F-1 では `/login` まで追わない（リダイレクトを追わない理由）。

### G. セキュリティの前提

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| G-1 | `dashboard.awajiempire.net` の証明書の期限・有効性 | 利用者の前に出る証明書は Cloudflare のエッジ証明書で、自動で更新される。**それでも期限が近づいたら、Cloudflare 側の設定が崩れたという意味**になる | [T: Website certificate by Zabbix agent 2]（Zabbix CT 自身のエージェント 2 で取る）。`{$CERT.WEBSITE.HOSTNAME}` に `dashboard.awajiempire.net` | 無効（テンプレート既定 High）/ 期限まで 14 日未満（`{$CERT.EXPIRY.WARN}` 既定 7 を 14 に変える） | High / Warning |
| G-2 | 証明書のフィンガープリントの変化 | — | 同テンプレートのトリガー「Fingerprint has changed」 | **無効にする**。Cloudflare のエッジ証明書は自動で入れ替わるので、正常な更新のたびに鳴る（テンプレートの説明にも「複数の正しい証明書がある環境では誤検知になる」とある） | — |
| G-3 | 意図しない待ち受けポート | C-8 と同じ。セキュリティの前提として二重に挙げておく | C-8 | C-8 | Information |
| G-4 | MariaDB の認証失敗 | E-3 と同じ | E-3 | E-3 | High |
| G-5 | SSH のログイン失敗・成功 | 不審なログインの試み。LAN 内のみのはずなので、失敗が続くのは LAN 内の機器が乗っ取られた兆候になる | **第 3 段階**（ログ監視。アクティブチェックが必要）。【要確認: 各ゲストに `/var/log/auth.log` があるか。LXC の Ubuntu では rsyslog がなく journald にしか残らない場合がある】 | 失敗が 10 分で 5 回以上（案） | High |
| G-6 | Proxmox の Web UI のログイン失敗 | ハイパーバイザの管理画面は、乗っ取られると全部が取られる | **第 3 段階**。ホストのログに出る `pvedaemon` の認証失敗【要確認: ログの文言と出力先】 | 失敗が 10 分で 3 回以上（案） | High |
| G-7 | Zabbix 自身のログイン失敗 | Zabbix は全ホストに話しかけられる | **第 3 段階**【要確認: Zabbix の監査ログから検知する方法】 | — | High |

ドメインの期限は見ない。ADR-030 でレジストラを Cloudflare に移した【要確認: 自動更新が有効になっているか】。

### H. 監視自身

| ID | 何を見るか | なぜ見るか | 取り方 | アラート条件（初期値） | 重要度 |
|---|---|---|---|---|---|
| H-1 | Zabbix サーバーの内部の状態（キャッシュ・キュー・プロセスの使用率） | 監視が詰まると、全アラートが遅れるか出なくなる | [T: Zabbix server health]（Zabbix サーバー自身のホストに既定でリンクされている） | テンプレート既定 | High |
| H-2 | 通知の送信に失敗していないか | Discord の Webhook が無効になっていたら、何が起きても気づけない | *Reports → Action log* を週 1 回の見直しで見る（自動化は第 2 段階） | — | — |
| H-3 | **Zabbix 自体・自宅の回線が死んだことに誰が気づくか** | Zabbix が止まると、Zabbix からの「止まった」という通知は来ない | **本人が決める**: 外部の死活監視サービスに `dashboard.awajiempire.net` を見てもらう / Zabbix から外部へ定期的に「生きている」を送り、途切れたら外部が知らせる（デッドマンスイッチ） / 当面は受け入れる | — | — |

---

## 4. 自作の UserParameter

アプリ層のゲストに `/etc/zabbix/zabbix_agent2.d/awaji.conf` として置く（手順は [zabbix-setup.md](zabbix-setup.md) の手順 8）。
`/etc/zabbix/zabbix_agent2.conf` に `Include=/etc/zabbix/zabbix_agent2.d/*.conf` があることは、`zabbix-agent2_7.0.32-2+ubuntu24.04_amd64.deb` の中身で確認した。

```ini
# /etc/zabbix/zabbix_agent2.d/awaji.conf
# Awaji Empire Agent の「前提が成り立っているか」を見るための UserParameter。
# 設計: docs/monitoring/monitoring-design.md の C・D 区分。
# 決め打ちのコマンドだけを置く。外から値を受け取る引数は awaji.systemd.nrestarts のユニット名だけ。

# C-1: venv の python3 の実体があり、実行できるか（1 = OK）
UserParameter=awaji.venv.python.exec,test -x /Awaji-Empire-Agent/discord_bot/.venv/bin/python3 && echo 1 || echo 0

# C-2: venv から主要なモジュールが import できるか（1 = OK）
UserParameter=awaji.venv.import_ok,/Awaji-Empire-Agent/discord_bot/.venv/bin/python3 -c "import quart, discord, hypercorn" >/dev/null 2>&1 && echo 1 || echo 0

# C-3: venv の python3 が最終的に指している実体のパス
UserParameter=awaji.venv.python.realpath,readlink -f /Awaji-Empire-Agent/discord_bot/.venv/bin/python3 || echo MISSING

# C-4: システムの Python のバージョン
UserParameter=awaji.system.python.version,/usr/bin/python3 -c "import sys; print(sys.version.split()[0])" 2>/dev/null || echo MISSING

# C-7: 未適用のセキュリティ更新の数（シミュレーションのみ。root 不要、ロックも取らない）
UserParameter=awaji.apt.security,apt-get -s -o Debug::NoLocking=1 dist-upgrade 2>/dev/null | grep '^Inst' | grep -ci security

# C-8: TCP で待ち受けているアドレス:ポートの一覧
UserParameter=awaji.listen.ports,ss -Htln | awk '{print $4}' | sort -u | tr '\n' ' '

# D-2: systemd が自動で再起動した回数
UserParameter=awaji.systemd.nrestarts[*],systemctl show -p NRestarts --value "$1"
```

コードの選択の理由:

- **C-1 は `test -x` で、Zabbix 標準の `vfs.file.exists` ではない**: INC-001 の壊れ方は「シンボリックリンクはあるが、リンクの先がない」だった。`test -x` はリンクを最後までたどって、実体が実行できるかを見る。`vfs.file.exists` は、公式ドキュメントにリンクをたどるかどうかが書かれていない（種類の指定に `sym` があるだけ）ので、INC-001 の壊れ方を確実に拾えるとは言えない。
- **C-2 で `hypercorn` を入れている**: INC-001 で実際に見つからなかったモジュールだから。`quart` は `webapp.py`、`discord`（`discord-py`）は `bot.py` の土台。全依存を import すると重く、エージェントのタイムアウト（既定 3 秒）を超えるおそれがあるので 3 つに絞った。
- **C-2 の取得間隔を 10 分にしている**: Python を起動して import するので、1 分ごとだと CPU を無駄に使う。壊れてから次のデプロイまでに気づければよいので、10 分で足りる。
- **C-3・C-4 はテキストで、変化だけを見る**: 「正しい値」を決め打ちすると、OS を意図して上げたときに必ず鳴る。変化を記録して人が確かめる、という C 区分の考え方に合わせた。
- **C-7 の `-o Debug::NoLocking=1`**: `apt-get -s` は root でなくても動くが、ロックを取ろうとして警告を出す。シミュレーションなのでロックは要らない。数えられるのは**最後に `apt update`（または `apt-daily.timer`）が取ってきた一覧**に基づく数なので、一覧が古いと 0 に見える【要確認: 各ゲストで `apt-daily.timer` が有効か】。`grep -ci security` は「リポジトリ名に security を含む行」を数える簡易な方法で、Ubuntu の `noble-security` を前提にしている。
- **C-8 の `awk '{print $4}'` は `[*]` のない UserParameter に置いている**: Zabbix は `[*]` 付きの UserParameter では、コマンド中の `$1`〜`$9` を**キーの引数に置き換える**。`[*]` 付きで書くと `awk` の `$4` が空の引数に置き換わって壊れる。
- **D-2 だけ引数（`[*]`）を取る**: ユニットごとに別のキーにすると 3 行が同じ形になるため。`UnsafeUserParameters=0`（既定）のままにして、引数にシェルの特殊文字が入ったら Zabbix 側で拒否させる（拒否される文字の一覧は、導入時に公式マニュアルの `UnsafeUserParameters` の項で確かめる【要確認】）。`"$1"` とクオートしているのは、値を 1 つの引数として渡すため。
- **D-2 の `NRestarts`**: systemd がサービスを自動で再起動した回数（累計のカウンタ）。**手動の `systemctl restart`（デプロイ）や `daemon-reload` で 0 に戻るかどうかは確かめていない**【要確認: `systemctl restart discord_webapp` の前後で `systemctl show -p NRestarts discord_webapp` を比べる】。
  - 累計のまま「10 分間の最大 − 最小」で見ると、窓の途中で 0 に戻ったとき（例: 5 → 0）に差が 5 と出て、再起動していないのに鳴る。
  - そこで前処理の **Simple change** で「前回からの増分」に変えて保存し、10 分間の合計を見る。Simple change は、今回の値が前回より小さいとき（カウンタが戻ったとき）その差を捨てる、と理解している【要確認: 公式マニュアルの前処理の項で、負の差の扱いを確かめる】。この理解が正しければ、0 に戻っても誤って鳴らない。

---

## 5. 使う公式テンプレートと出典

| テンプレート | 対象 | 出典（Zabbix 公式リポジトリの GitHub ミラー、`release/7.0`） |
|---|---|---|
| Proxmox VE by HTTP | Proxmox ホスト（API） | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/app/proxmox> |
| Linux by Zabbix agent | 各ゲストの OS（Proxmox ホストは第 1 段階では API だけで見る。セットアップ手順 7） | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/os/linux> |
| Systemd by Zabbix agent 2 | アプリ層のサービス | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/app/systemd> |
| MySQL by Zabbix agent 2 | 本番 MariaDB | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/db/mysql_agent2> |
| Website certificate by Zabbix agent 2 | `dashboard.awajiempire.net` の証明書 | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/app/certificate_agent2> |
| Zabbix server health | Zabbix 自身 | Zabbix サーバーに既定で入っている |
| Discord（メディアタイプ） | 通知 | <https://github.com/zabbix/zabbix/tree/release/7.0/templates/media/discord> |

エージェントの標準キーの書式（`vfs.file.exists`・`vfs.file.cksum`・`system.sw.os`・`net.tcp.service` など）: <https://www.zabbix.com/documentation/7.0/en/manual/config/items/itemtypes/zabbix_agent>

`web.page.get`・Web シナリオ・トリガー関数（`nodata`・`min`・`max`・`last`）の細かい書式は、導入時に Zabbix 7.0 のマニュアルで確かめ、Web UI の「Test」で動作を確かめる【要確認】。

---

## 6. 段階

| 段階 | 入れるもの | 終わりの条件 |
|---|---|---|
| 第 1 段階 | A・B・D-1・E-1・F-1・H-1、通知（Discord） | Disaster の項目について、わざと止めて通知が届くことを確かめた（手順書の手順 11） |
| 第 2 段階 | C 区分すべて・D-2〜D-5・E-2〜E-5・F-2・G-1・G-2 | 1 週間動かして、鳴ったアラートを全部見直した |
| 第 3 段階 | G-5〜G-7（ログ監視）、H-3、Grafana との連携 | それぞれ別に判断する |
