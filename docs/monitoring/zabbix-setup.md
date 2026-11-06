# Zabbix セットアップ手順（Proxmox VE 9.1 / Ubuntu 24.04 LXC / Zabbix 8.0 LTS）

- **ステータス**: 下書き。**この手順はまだ誰も実機で通していない**。最初に通した人が、つまずいた点を [zabbix-lessons.md](zabbix-lessons.md) に書き、この手順を直す。
- **作成日**: 2026-11-05
- **前提の決定**: [構成案](zabbix-architecture.md)（専用の非特権 LXC / 専用 MariaDB / Web UI は LAN のみ / 8.0 LTS で開始）
- **監視項目**: [監視設計](monitoring-design.md)

---

## この手順の使い方

- 各ステップに **確認方法** がある。確認が通るまで次に進まない。
- `<...>` はプレースホルダ。**秘密の値（パスワード・PSK・トークン・Webhook URL）は、このファイルにも、コミットにも、チャットにも書かない。**
- `【要確認】` は、リポジトリや公式ドキュメントから確かめきれなかった点。手順 0 か、そのステップの実行前に埋める。
- 手順の区切りで `pct snapshot` を取る。失敗したら最後のスナップショットに戻る（最後の「ロールバック」の章）。
- コマンドの出典:
  - リポジトリ設定パッケージの URL・パッケージ名・ファイルの置き場所・既定の設定値: `repo.zabbix.com` の 8.0 のパッケージ（`zabbix-release` `1:8.0-0.5+ubuntu24.04`、各コンポーネント `8.0.0-1+ubuntu24.04`）の中身を `dpkg -c` / `dpkg-deb` で確認した（2026-11-06）。
  - DB の作り方: <https://www.zabbix.com/documentation/8.0/en/manual/appendix/install/db_scripts>
  - 公式のダウンロードページ（<https://www.zabbix.com/download?zabbix=8.0&os_distribution=ubuntu&os_version=24.04&components=server_frontend_agent&db=mysql&ws=nginx>）は JavaScript で手順を生成するため、この文書の作成時には本文を取得できなかった。**実行前に、このページの手順と見比べる。** 食い違ったら公式に従い、この文書を直す。

### プレースホルダの一覧（手順 0 で決める）

| プレースホルダ | 意味 | 例の形（実際の値ではない） |
|---|---|---|
| `<CTID>` | Zabbix CT の VMID | 3 桁の数字【要確認: 空いている番号】 |
| `<STORAGE>` | CT のルートディスクを置くストレージ | `local-lvm` など【要確認: `pvesm status`】 |
| `<BRIDGE>` | ネットワークブリッジ | `vmbr0` など【要確認】 |
| `<ZBX_IP>` / `<GW_IP>` / `<PREFIX>` | Zabbix CT の固定 IP・ゲートウェイ・プレフィックス長 | LAN のセグメント【要確認】 |
| `<LAN_CIDR>` | Web UI を見てよい LAN の範囲 | 【要確認】 |
| `<APP_HOST>` / `<DB_HOST>` | アプリ層ゲスト・MariaDB CT の名前（Zabbix 上のホスト名） | `awaji-app` / `awaji-db` |
| `<ZABBIX_DB_PASSWORD>` | Zabbix 専用 DB の `zabbix` ユーザーのパスワード | 秘密 |
| `<ZBX_MONITOR_PASSWORD>` | 本番 MariaDB の監視用ユーザーのパスワード | 秘密 |

---

## 手順 0: 事前確認（読み取りのみ。何も変えない）

Proxmox ホストのシェルで:

```bash
pveversion
pct list
qm list
pvesm status
free -h
pveam update
pveam available --section system | grep -i ubuntu-24.04
```

やること:

1. [構成案](zabbix-architecture.md) 1.1 の Q1〜Q8 を埋める（アプリ層が VM か LXC か、各ゲストの IP とメモリ、`cloudflared` の場所など）。
2. メモリの余裕を計算する（構成案 2.5）。2.5 GiB 以上残らなければ、手順 1 のメモリを 1536 にし、手順 3 のバッファプールを 256M にする。
3. 上のプレースホルダを決め、パスワードマネージャーに Zabbix 用の項目を作る。

**確認方法**: 構成案 1.1 の表の【要確認】が、全部実際の値か「不要」に置き換わっている。

---

## 手順 1: Zabbix 用の非特権 LXC を作る

```bash
# Proxmox ホストで。テンプレートを取得する（ファイル名は pveam available の出力からコピーする）
pveam download local <ubuntu-24.04 のテンプレートのファイル名>

# CT を作る（非特権・自動起動・nesting 有効）
pct create <CTID> local:vztmpl/<ubuntu-24.04 のテンプレートのファイル名> \
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

pct start <CTID>
pct enter <CTID>
```

オプションの理由:

- `--unprivileged 1`: CT の root がホストの root にならない。Zabbix CT が乗っ取られたときにホストまで取られにくくする。
- `--features nesting=1`: 新しめの Ubuntu の systemd を非特権 CT で動かすときに有効にすることが多い【要確認: Proxmox の GUI で CT を作ると既定で有効になるか、無効だと何が起きるか】。
- `firewall=1`: 手順 12 で Proxmox ファイアウォールのルールを当てられるようにしておく（ルールを有効にするまでは何も変わらない）。
- `--password`: 対話でパスワードを聞かれる（コマンドラインに書かない）。
- メモリ 2048 / ディスク 16G の根拠は構成案 2.5。

出典: <https://pve.proxmox.com/pve-docs/pct.1.html>

CT の中で（以後、`# zabbix#` と書いたものは Zabbix CT の中で実行する）:

```bash
# zabbix#
apt update && apt full-upgrade -y
timedatectl set-timezone Asia/Tokyo
```

**確認方法**:

```bash
# Proxmox ホストで
pct status <CTID>            # status: running
pct config <CTID>            # unprivileged: 1 / memory: 2048 / onboot: 1
# zabbix#
grep VERSION_ID /etc/os-release          # "24.04"
ip -4 addr show eth0                     # <ZBX_IP> が付いている
ping -c 3 repo.zabbix.com                # 外に出られる
timedatectl                              # Time zone: Asia/Tokyo、System clock synchronized: yes
```

**スナップショット**（Proxmox ホストで）:

```bash
pct snapshot <CTID> s1-base --description "Ubuntu 24.04 + full-upgrade"
```

---

## 手順 2: Zabbix の公式リポジトリを追加する

```bash
# zabbix#
cd /tmp
wget https://repo.zabbix.com/zabbix/8.0/release/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_8.0+ubuntu24.04_all.deb

# 入れる前に、中身の .sources がどこを指しているかを見る（構成案 2.3）
dpkg-deb -f zabbix-release_latest_8.0+ubuntu24.04_all.deb Version
dpkg-deb --fsys-tarfile zabbix-release_latest_8.0+ubuntu24.04_all.deb | tar -xO --wildcards '*.sources'

dpkg -i zabbix-release_latest_8.0+ubuntu24.04_all.deb
apt update
```

- 7.0 と違い、URL のパスに **`release/`** が入る。
- このパッケージは `/etc/apt/sources.list.d/` に `.sources` を、`/usr/share/keyrings/zabbix.gpg` に署名鍵を置く。2026-11-06 に確かめた中身（`1:8.0-0.5+ubuntu24.04`）は、次の 4 つを指していた:
  - `https://repo.zabbix.com/zabbix/8.0/stable/ubuntu`（**正式版はここから来る**）
  - `https://repo.zabbix.com/zabbix/8.0/release/ubuntu`（`zabbix-release` 自身の更新用。`Architectures: all`）
  - `https://repo.zabbix.com/zabbix/8.0/unstable/ubuntu`（`Enabled: no`。**有効になっていたら入れない**）
  - `https://repo.zabbix.com/zabbix-tools/debian-ubuntu`（周辺ツール用。`Architectures: all`）
- 前日（2026-11-05）の同じパッケージは `1:8.0-0.4` で、`stable` を指さず `unstable` が有効だった。**`Version` が `0.5` より古いか、`unstable` が `Enabled: no` になっていなければ、入れずに止まる。**
- Ubuntu 標準のリポジトリにも Zabbix のパッケージはあるが、公式ドキュメントは「OS のリポジトリのパッケージは古いことがあり、サポート対象外」としている（<https://www.zabbix.com/documentation/8.0/en/manual/installation/install_from_packages/debian_ubuntu>）。

**確認方法**:

```bash
# zabbix#
cat /etc/apt/sources.list.d/zabbix*.sources         # 8.0/stable がある。unstable は Enabled: no
apt-cache policy zabbix-server-mysql                  # Candidate が 1:8.0.x で、repo.zabbix.com/zabbix/8.0/stable から来ている
```

---

## 手順 3: Zabbix 専用の MariaDB を入れる

```bash
# zabbix#
apt install -y mariadb-server
systemctl enable --now mariadb
```

メモリを絞る設定を、Ubuntu の設定ファイルを直接いじらずに別ファイルで足す:

```bash
# zabbix#
cat > /etc/mysql/mariadb.conf.d/60-zabbix.cnf <<'EOF'
# Zabbix 専用 CT の MariaDB。CT のメモリが 2 GiB なので、バッファプールを絞る。
# 根拠: docs/monitoring/zabbix-architecture.md 2.5
[mysqld]
innodb_buffer_pool_size = 512M
EOF
systemctl restart mariadb
```

**確認方法**:

```bash
# zabbix#
mariadb --version                                   # 10.11.x（Zabbix 8.0 の対応範囲 10.11〜12.3 の中。下限ちょうど）
ss -tlnp | grep 3306                                # 127.0.0.1:3306 だけで待ち受けている（0.0.0.0 ではない）
mariadb -e "SELECT @@innodb_buffer_pool_size/1024/1024 AS MiB;"   # 512
```

`ss` の結果が `0.0.0.0:3306` や `*:3306` なら、Zabbix の DB が LAN に開いている。`/etc/mysql/mariadb.conf.d/50-server.cnf` の `bind-address` を確かめる【要確認: Ubuntu 24.04 の既定値】。

---

## 手順 4: Zabbix のパッケージを入れ、DB を初期化する

```bash
# zabbix#
apt install -y zabbix-server-mysql zabbix-frontend-php zabbix-nginx-conf zabbix-sql-scripts zabbix-agent2
```

- パッケージ名は `repo.zabbix.com` の 8.0 / `noble`（`stable`）の一覧で確認した。`zabbix-nginx-conf` は `nginx` と `php-fpm` を依存として連れてくる（パッケージの `Depends` で確認）。
- エージェントは `zabbix-agent` ではなく **`zabbix-agent2`** にする（Systemd・MySQL・証明書のテンプレートがエージェント 2 前提のため）。

DB とユーザーを作る。パスワードはプロンプトで打つ（シェルのコマンドラインに書かない）:

```bash
# zabbix#
mariadb
```

```sql
-- MariaDB のプロンプトで。<ZABBIX_DB_PASSWORD> はその場で打つ
CREATE DATABASE zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER zabbix@localhost IDENTIFIED BY '<ZABBIX_DB_PASSWORD>';
GRANT ALL PRIVILEGES ON zabbix.* TO zabbix@localhost;
SET GLOBAL log_bin_trust_function_creators = 1;
QUIT;
```

- `utf8mb4` / `utf8mb4_bin`・ユーザーを `localhost` に限る・`log_bin_trust_function_creators` を一時的に 1 にして取り込み後に 0 に戻す、はいずれも公式の DB 作成手順のとおり（<https://www.zabbix.com/documentation/8.0/en/manual/appendix/install/db_scripts>）。
- MariaDB のプロンプトで打った文は履歴ファイルに残る。この手順の最後で消す。

スキーマとデータを取り込む（数分かかる。パスワードを聞かれる）:

```bash
# zabbix#
zcat /usr/share/zabbix/sql-scripts/mysql/server.sql.gz | mariadb --default-character-set=utf8mb4 -uzabbix -p zabbix
```

> **7.0 から場所が変わった**: 7.0 は `/usr/share/zabbix-sql-scripts/...`、8.0 は `/usr/share/zabbix/sql-scripts/...`（8.0.0 のパッケージの中身で確認）。7.0 向けの記事のコマンドをそのまま使うと「ファイルがない」で失敗する。

取り込みが終わったら戻す:

```bash
# zabbix#
mariadb -e "SET GLOBAL log_bin_trust_function_creators = 0;"
rm -f ~/.mariadb_history ~/.mysql_history
```

**確認方法**:

```bash
# zabbix#
mariadb -e "SELECT COUNT(*) AS tables FROM information_schema.tables WHERE table_schema='zabbix';"   # 数百（0 や数個なら取り込み失敗）
mariadb -e "SELECT @@GLOBAL.log_bin_trust_function_creators;"                                     # 0
mariadb -e "SELECT user, host FROM mysql.user WHERE user='zabbix';"                                # zabbix / localhost の 1 行だけ
```

**スナップショット**:

```bash
pct snapshot <CTID> s2-db-imported --description "Zabbix 8.0 packages + DB schema"
```

---

## 手順 5: サーバーと Web の設定をして起動する

### 5.1 Zabbix サーバーの DB パスワード

```bash
# zabbix#
ls -l /etc/zabbix/zabbix_server.conf      # パッケージの既定は -rw------- root root（root しか読めない）
editor /etc/zabbix/zabbix_server.conf
```

`# DBPassword=` の行を見つけ、その下に `DBPassword=<ZABBIX_DB_PASSWORD>` を書く。`DBName=zabbix`・`DBUser=zabbix` はパッケージの既定のまま。

- 設定ファイルは `0600 root:root` のままにする。`zabbix_server` は root で起動して設定を読んでから `zabbix` ユーザーに切り替わる、と理解している【要確認: 起動後に `ps -o user,cmd -C zabbix_server` が `zabbix` になっていること】。

### 5.2 nginx

`/etc/zabbix/nginx.conf` の先頭 2 行がコメントになっている（パッケージの中身で確認）:

```nginx
#        listen          8080;
#        server_name     example.com;
```

```bash
# zabbix#
editor /etc/zabbix/nginx.conf
```

次のように変える:

```nginx
        listen          8080;
        server_name     <ZBX_IP>;
```

- `zabbix-nginx-conf` のインストール時に `/etc/nginx/conf.d/zabbix.conf → /etc/zabbix/nginx.conf` のシンボリックリンクが作られる（パッケージの `postinst` で確認）。
- `:80` は Ubuntu の nginx の既定サイトが使っているので、Zabbix は `:8080` にする。

### 5.3 起動

```bash
# zabbix#
nginx -t
ls /etc/php/                               # PHP のバージョンを確かめる（Ubuntu 24.04 なら 8.3 のはず【要確認】。違えば下の php8.3-fpm を読み替える）
systemctl restart zabbix-server zabbix-agent2 nginx php8.3-fpm
systemctl enable zabbix-server zabbix-agent2 nginx php8.3-fpm
```

**確認方法**:

```bash
# zabbix#
systemctl is-active zabbix-server zabbix-agent2 nginx php8.3-fpm mariadb   # すべて active
ss -tlnp | grep -E ':(8080|10050|10051|3306)\b'                            # 8080, 10050, 10051 と 127.0.0.1:3306
tail -n 50 /var/log/zabbix/zabbix_server.log                                # "database is down" や "cannot connect" がない
ps -o user,cmd -C zabbix_server | head -3                                  # user が zabbix
```

LAN 内の PC のブラウザで `http://<ZBX_IP>:8080/` を開き、Zabbix のセットアップ画面が出ること。

---

## 手順 6: Web UI の初期設定とセキュリティ

1. セットアップ画面で:
   - DB: `localhost` / DB 名 `zabbix` / ユーザー `zabbix` / パスワード `<ZABBIX_DB_PASSWORD>`
   - Zabbix server name: `awaji-zabbix`
   - タイムゾーン: `Asia/Tokyo`
2. 初期の管理ユーザー（`Admin`）でログインし、**すぐにパスワードを変える**（*User settings → Profile*）。初期パスワードは公式ドキュメントのクイックスタートで確かめる。
3. 自分用のユーザーを作り、`Super admin role` と `Zabbix administrators` グループに入れる。そのユーザーでログインし直せることを確かめてから、`Admin` を無効にする【要確認: 8.0 の Web UI での無効化の操作】。
4. **MFA（TOTP）を有効にする**（*Users → Authentication* の MFA 設定）。自分のユーザーグループに割り当て、スマホの認証アプリで登録する（出典: <https://www.zabbix.com/documentation/8.0/en/manual/web_interface/frontend_sections/users/authentication/mfa>）。
5. `guest` ユーザーが無効のままであることを確かめる。

**確認方法**:
- ログアウトして、自分のユーザー + TOTP でログインできる。
- `Admin` でログインできない。
- ログアウトした状態で `http://<ZBX_IP>:8080/` を開き、ゲストとして中が見えない。
- *Reports → System information* で「Zabbix server is running: Yes」。

**スナップショット**:

```bash
pct snapshot <CTID> s3-ui-secured --description "Web UI initial setup + MFA"
```

---

## 手順 7: 監視対象にエージェント 2 を入れる（PSK で暗号化）

対象: アプリ層のゲスト（`<APP_HOST>`）、MariaDB CT（`<DB_HOST>`）。

Proxmox ホスト自身には**入れない**（第 1 段階）。ホストは Proxmox API（手順 9.1）で見る。ハイパーバイザに外部のリポジトリとエージェントを足さないため。必要になったら、Debian 13 向けのパッケージ（`https://repo.zabbix.com/zabbix/8.0/release/debian/pool/main/z/zabbix-release/zabbix-release_latest_8.0+debian13_all.deb`、2026-11-06 にリポジトリで存在を確認）で入れる。

各ホストで（ホストごとに繰り返す）:

```bash
# 対象ホストで。OS が Ubuntu 24.04 の場合
cd /tmp
wget https://repo.zabbix.com/zabbix/8.0/release/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_8.0+ubuntu24.04_all.deb
dpkg-deb --fsys-tarfile zabbix-release_latest_8.0+ubuntu24.04_all.deb | tar -xO --wildcards '*.sources'   # 手順 2 と同じ確認
dpkg -i zabbix-release_latest_8.0+ubuntu24.04_all.deb
apt update
apt install -y zabbix-agent2
```

> 対象ホストの OS が Ubuntu 26.04 なら、ファイル名の `ubuntu24.04` を `ubuntu26.04` にする（8.0 の 26.04 向けパッケージ `zabbix-release_latest_8.0+ubuntu26.04_all.deb` の存在を 2026-11-06 に確認）【要確認: 本番の OS バージョン（構成案 Q2）】。

### 7.1 接続先とホスト名

`/etc/zabbix/zabbix_agent2.conf` の既定値は `Server=127.0.0.1` / `ServerActive=127.0.0.1` / `Hostname=Zabbix server`（8.0.0 のパッケージの中身で確認。7.0 と同じ）。この 3 行を書き換える:

```bash
editor /etc/zabbix/zabbix_agent2.conf
```

```ini
Server=<ZBX_IP>
ServerActive=
Hostname=<APP_HOST>
```

- `Hostname=` は Zabbix の Web UI に登録するホスト名と完全に一致させる。
- **`ServerActive=` は空にする**（既定の `127.0.0.1` のままにも、`<ZBX_IP>` にもしない）。この構成はパッシブだけを使う（ADR-033 の決定 5）。`ServerActive` に値があると、エージェントが自分から Zabbix サーバーの 10051 へアクティブチェックの設定を取りに行く。ホストを Web UI に登録する前（手順 7.3 の前）だと、ログに `cannot connect to [<ZBX_IP>:10051]: ... SSL alert number 40`（PSK のハンドシェイクの失敗）と `active check configuration update ... started to fail` が出続ける。2026-11-06 の初回の導入で実際に起きた（[zabbix-lessons.md](zabbix-lessons.md)）。

### 7.2 PSK

```bash
# 対象ホストで。値は画面に出さずにファイルに書く
openssl rand -hex 32 > /etc/zabbix/zabbix_agent2.psk
chown zabbix:zabbix /etc/zabbix/zabbix_agent2.psk
chmod 600 /etc/zabbix/zabbix_agent2.psk

cat > /etc/zabbix/zabbix_agent2.d/10-tls.conf <<'EOF'
# PSK による暗号化。設計: docs/monitoring/zabbix-architecture.md 3.3
TLSConnect=psk
TLSAccept=psk
TLSPSKIdentity=PSK-<APP_HOST>
TLSPSKFile=/etc/zabbix/zabbix_agent2.psk
EOF

systemctl restart zabbix-agent2
systemctl enable zabbix-agent2
```

- PSK の生成方法・パラメータ名・「Zabbix ユーザーだけが読めるように」は公式のとおり（<https://www.zabbix.com/documentation/8.0/en/manual/security/using_pre_shared_keys>）。パラメータ名は `zabbix_agent2.conf` の中のコメント（`# TLSConnect=` など）でも確認した。
- `zabbix_agent2.conf` に `Include=/etc/zabbix/zabbix_agent2.d/*.conf` がある（パッケージの中身で確認）ので、`10-tls.conf` は読み込まれる。
- `TLSAccept=psk` だけにすると、暗号化していない接続は拒否される。
- **PSK の値は、Zabbix の Web UI に貼るときだけ** `cat /etc/zabbix/zabbix_agent2.psk` で表示し、貼ったらターミナルを閉じる。チャットやメモ帳に貼らない。

### 7.3 Zabbix にホストを登録する

Web UI の *Data collection → Hosts → Create host*:

- Host name: `<APP_HOST>`（7.1 の `Hostname=` と一致）
- Interfaces: Agent / `<APP_HOST の IP>` / 10050
- Templates: `Linux by Zabbix agent`、`Systemd by Zabbix agent 2`（`<APP_HOST>` のみ）
- Encryption タブ: Connections to host = PSK、Connections from host = PSK のみ、PSK identity = `PSK-<APP_HOST>`、PSK = ファイルの中身

**確認方法**:

```bash
# 対象ホストで
systemctl is-active zabbix-agent2                 # active
ss -tlnp | grep 10050                             # 待ち受けている
tail -n 20 /var/log/zabbix/zabbix_agent2.log      # 接続の失敗が出続けていない。とくに「cannot connect to [<ZBX_IP>:10051]」がない（出るなら 7.1 の ServerActive が空になっていない）
```

```bash
# zabbix#（暗号化なしでは拒否されること = PSK が効いていることを確かめる）
apt install -y zabbix-get
zabbix_get -s <APP_HOST の IP> -k agent.ping       # 失敗する（暗号化なしは拒否）
```

Web UI の *Monitoring → Hosts* で `<APP_HOST>` の **ZBX アイコンが緑**、*Latest data* に CPU・メモリの値が入ってくる（数分かかる）。

---

## 手順 8: アプリ層に自作の UserParameter を入れる（前提の崩れの監視）

[監視設計](monitoring-design.md) 4 章の内容を、`<APP_HOST>` の `/etc/zabbix/zabbix_agent2.d/awaji.conf` に置く。

```bash
# <APP_HOST> で
editor /etc/zabbix/zabbix_agent2.d/awaji.conf     # monitoring-design.md 4 章の ini をそのまま貼る
chmod 644 /etc/zabbix/zabbix_agent2.d/awaji.conf
systemctl restart zabbix-agent2
```

**確認方法**（エージェントにキーを 1 回だけ試させる。`-t` はテストモード【要確認: `zabbix_agent2 --help` で `-t` があること】）:

```bash
# <APP_HOST> で。zabbix ユーザーとして実行し、権限の問題も同時に確かめる
sudo -u zabbix zabbix_agent2 -t awaji.venv.python.exec            # 1
sudo -u zabbix zabbix_agent2 -t awaji.venv.import_ok              # 1（0 なら venv の読み取り権限か、タイムアウトを疑う）
sudo -u zabbix zabbix_agent2 -t awaji.venv.python.realpath        # /usr/bin/python3.12 のような実体のパス
sudo -u zabbix zabbix_agent2 -t awaji.system.python.version       # 3.12.x など
sudo -u zabbix zabbix_agent2 -t awaji.apt.security                # 数字
sudo -u zabbix zabbix_agent2 -t awaji.listen.ports                # 0.0.0.0:5000 127.0.0.1:7878 ... の並び
sudo -u zabbix zabbix_agent2 -t 'awaji.systemd.nrestarts[discord_webapp.service]'   # 数字
```

- `awaji.venv.import_ok` が 0 のとき: `ls -ld /Awaji-Empire-Agent /Awaji-Empire-Agent/discord_bot /Awaji-Empire-Agent/discord_bot/.venv` で、`zabbix` ユーザー（others）に読み取りと実行の権限があるか確かめる【要確認】。権限を広げる前に、構成案 3.4 の方針（監視のために権限を広げすぎない）と比べて判断する。

その後、Web UI で `<APP_HOST>` にアイテムとトリガーを作る（監視設計 3 章の C・D の表のとおり。取得間隔・前処理・式も表のとおり）。作ったものは**テンプレート（例: `Template Awaji premises`）にまとめ、エクスポートした YAML をこのリポジトリに置く**ことを検討する（lessons の「次にやること」）。

---

## 手順 9: Proxmox API・MariaDB・証明書・外形監視

### 9.1 Proxmox API（読み取り専用のトークン）

Proxmox ホストで:

```bash
# 監視専用のロールを、テンプレートが求める 3 つの権限だけで作る
pveum role add ZabbixMonitor --privs "Sys.Audit,VM.Audit,Datastore.Audit"
pveum user add zabbix-monitor@pve --comment "Zabbix read-only monitoring"
pveum acl modify / --users zabbix-monitor@pve --roles ZabbixMonitor
pveum user token add zabbix-monitor@pve zabbix --privsep 1 --comment "Zabbix Proxmox VE by HTTP"
pveum acl modify / --tokens 'zabbix-monitor@pve!zabbix' --roles ZabbixMonitor
```

- 権限は、テンプレート `Proxmox VE by HTTP` の README が求める `Sys.Audit`（`/`）・`Datastore.Audit`（`/storage`）・`VM.Audit`（`/vms`）だけ。`/` に付けて下位に引き継がせる（`--propagate` の既定は 1）。
- 組み込みの `PVEAuditor` ロールを使う方法もあるが、中身の権限を確かめていないので【要確認: `pveum role list`】、必要な 3 つだけのロールを作った。`pveum role add` の構文は【要確認: `pveum help role add`】。
- `--privsep 1`: トークンにユーザーとは別に権限を付ける（ユーザーの権限を丸ごと継がない）。
- `pveum user token add` の出力に**シークレットが 1 回だけ表示される**。そのまま Zabbix の Web UI に貼り、パスワードマネージャーに保存し、ターミナルを閉じる。
- 構文の出典: <https://pve.proxmox.com/pve-docs/pveum.1.html>

Zabbix の Web UI でホスト `awaji-pve` を作る:

- Templates: `Proxmox VE by HTTP`
- Macros: `{$PVE.URL.HOST}` = Proxmox ホストの IP、`{$PVE.TOKEN.ID}` = `zabbix-monitor@pve!zabbix`、`{$PVE.TOKEN.SECRET}` = シークレット（**型を `Secret text` にする**）

Proxmox の Web UI は自己署名証明書なので、テンプレートのマクロ `{$HTTP.TLS.VERIFY}` の扱いを決める【要確認: 自己署名のまま `none` にするか、Proxmox ホストの CA を Zabbix CT に入れて検証するか。`none` は経路上のなりすましを検知できない】。

**確認方法**: *Latest data* で `awaji-pve` の API の応答が 200、ノード・LXC・VM のディスカバリ結果が入ってくる。

### 9.2 本番 MariaDB の監視ユーザー

`<DB_HOST>` で（**本番 DB への変更。この手順で本番に手を入れるのはここだけ**）:

```bash
mariadb -e "SELECT @@socket;"          # ソケットのパス（下の DSN に使う）
mariadb
```

```sql
CREATE USER 'zbx_monitor'@'localhost' IDENTIFIED BY '<ZBX_MONITOR_PASSWORD>';
GRANT REPLICATION CLIENT, PROCESS, SHOW DATABASES, SHOW VIEW ON *.* TO 'zbx_monitor'@'localhost';
QUIT;
```

- 権限はテンプレート `MySQL by Zabbix agent 2` の README のとおり。ホストだけ `'%'` から `'localhost'` に狭めた（監視設計 E 章）。
- レプリケーションは使っていないので `SLAVE MONITOR` は付けない（README は、MariaDB 10.5.9 以上でレプリケーションの値を取るときだけ必要としている）。
- 終わったら `rm -f ~/.mariadb_history ~/.mysql_history`。

Zabbix の Web UI で `<DB_HOST>` に:

- Templates: `Linux by Zabbix agent`、`MySQL by Zabbix agent 2`
- Macros: `{$MYSQL.DSN}` = `unix:<上で確かめたソケットのパス>`、`{$MYSQL.USER}` = `zbx_monitor`、`{$MYSQL.PASSWORD}` = パスワード（**`Secret text`**）

**確認方法**:

```bash
# <DB_HOST> で
mariadb -e "SHOW GRANTS FOR 'zbx_monitor'@'localhost';"     # 上の 4 つの権限だけ
```

*Latest data* で `mysql.ping` が 1。

### 9.3 証明書（Zabbix CT 自身のエージェント 2 で取る）

Zabbix CT のホスト（既定で `Zabbix server` という名前で登録されている）に、テンプレート `Website certificate by Zabbix agent 2` をリンクし、マクロを入れる:

- `{$CERT.WEBSITE.HOSTNAME}` = `dashboard.awajiempire.net`
- `{$CERT.EXPIRY.WARN}` = `14`
- トリガー「Certificate: Fingerprint has changed」は無効にする（監視設計 G-2）

**確認方法**:

```bash
# zabbix#（テンプレートの README の確かめ方）
zabbix_get -s 127.0.0.1 -k 'web.certificate.get[dashboard.awajiempire.net]'
```

JSON が返り、有効期限が入っている。

### 9.4 外形監視（Web シナリオ）

`Zabbix server` ホストに *Web scenarios → Create web scenario*:

- 名前: `dashboard top`、間隔: `1m`、試行回数: 1
- **Follow redirects: オフ**
- Step: URL `https://dashboard.awajiempire.net/`、Required status codes: `302`

トリガー: 監視設計 F-1（3 回続けて失敗で Disaster）。

**確認方法**: *Monitoring → Web* で `dashboard top` が成功、応答コード 302。

---

## 手順 10: 通知（Discord）

1. Discord に**通知用**と**変更記録用**の 2 つのチャンネルを作り、それぞれのチャンネル設定の「連携サービス → ウェブフック」で Webhook を作る。URL は秘密として扱う。
2. Zabbix の *Alerts → Media types* に `Discord` があるか確かめる。なければ公式の定義を取り込む（<https://github.com/zabbix/zabbix/tree/release/8.0/templates/media/discord>）【要確認: 8.0 で既定で入っているか】。
3. グローバルマクロ `{$ZABBIX.URL}` に `http://<ZBX_IP>:8080` を入れる（Discord のメッセージから Zabbix の画面に飛べるようにする。メディアタイプのパラメータ `zabbix_url` がこのマクロを参照している）。
4. 自分のユーザーの *Media* に Discord を 2 つ追加する（Send to にそれぞれの Webhook URL。重要度で分ける）:
   - 通知用: Disaster・High・Average・Warning
   - 変更記録用: Information のみ
5. *Alerts → Actions → Trigger actions* で、問題発生時と回復時に通知するアクションを作る。Disaster・High のメッセージにメンションを入れる【要確認: Discord の Webhook でメンションを効かせる書き方】。

**確認方法**: *Media types → Discord → Test* で、両方のチャンネルにテストメッセージが届く。

---

## 手順 11: アラートの試験（わざと壊して、通知が届くことを確かめる）

**本番ではなくテスト環境（`02sv-testenv`）でやる**【要確認: テスト環境にもエージェントを入れるか（構成案 Q3）】。テスト環境に入れない場合は、本番で D-1 の試験だけを、利用者の少ない時間に行う。

| 試験 | 操作（テスト環境で） | 期待する結果 | 戻し方 |
|---|---|---|---|
| D-1 | `sudo systemctl stop discord_webapp` | 約 3 分で Disaster の通知（メンション付き） | `sudo systemctl start discord_webapp` → 回復の通知 |
| C-1 | `sudo mv /Awaji-Empire-Agent/discord_bot/.venv/bin/python3 /Awaji-Empire-Agent/discord_bot/.venv/bin/python3.zbxtest` | 最大 5 分で High の通知。**このとき `discord_webapp` は止まっていない**（INC-001 の「壊れても次の再起動まで止まらない」の再現） | `sudo mv /Awaji-Empire-Agent/discord_bot/.venv/bin/python3.zbxtest /Awaji-Empire-Agent/discord_bot/.venv/bin/python3`。試験中は `test` ブランチに push しない（デプロイで再起動すると本当に止まる） |

**確認方法**: 上の 2 つで、問題と回復の両方の通知が Discord に届いた。届いた時刻を [zabbix-lessons.md](zabbix-lessons.md) に記録する（「壊してから気づくまで何分か」）。

---

## 手順 12: Proxmox ファイアウォールで経路を絞る

**注意: Proxmox ファイアウォールの設定を誤ると、Proxmox の Web UI（8006）や SSH に入れなくなる。** 作業はホストのコンソール（物理の画面とキーボード）が使えるときに行い、先に 8006 と 22 を LAN から許可するルールを入れてから有効にする。【要確認: いまデータセンター・ホスト・各ゲストのどのレベルでファイアウォールが有効か（構成案 Q7）。CHANGELOG によると、過去に Web VM ↔ DB CT の通信がファイアウォールで遮断されていたことがある】

入れるルール:

| 対象 | 方向 | 許可 | 送信元 |
|---|---|---|---|
| Zabbix CT | IN | TCP 8080 | `<LAN_CIDR>` |
| Zabbix CT | IN | TCP 22 | `<LAN_CIDR>`（SSH を使う場合のみ） |
| Zabbix CT | IN | それ以外 | 拒否（CT の Input Policy を DROP） |
| `<APP_HOST>`・`<DB_HOST>` | IN | TCP 10050 | `<ZBX_IP>` のみ |

出典: <https://pve.proxmox.com/wiki/Firewall>【要確認: 手順を公式で読んでから作業する】

**確認方法**:

```bash
# LAN 内の別の PC から
curl -sS -o /dev/null -w '%{http_code}\n' http://<ZBX_IP>:8080/      # 200（ログイン画面）
# Zabbix CT 以外のゲスト（例: <DB_HOST>）から
timeout 3 bash -c '</dev/tcp/<APP_HOST の IP>/10050' && echo OPEN || echo CLOSED   # CLOSED
```

Web UI の *Monitoring → Hosts* で全ホストの ZBX アイコンが緑のまま（Zabbix CT からは届いている）。

---

## ロールバック（やり直し方）

Zabbix は既存のサービスから独立した CT に入れているので、**Zabbix CT を消せば大部分が元に戻る**。他のホストに足したものだけ個別に消す。

### 途中でやり直す（Zabbix CT の中だけ）

```bash
# Proxmox ホストで
pct listsnapshot <CTID>
pct rollback <CTID> <スナップショット名> --start 1
```

**確認方法**: `pct status <CTID>` が running。戻したスナップショットの時点の手順の「確認方法」が通る。

### 全部やめる

上から順に行う。順番の理由: 先に通知を止め、次にエージェントを消し、最後に Zabbix 本体を消す（逆にすると、消している途中に「エージェントに届かない」通知が飛ぶ）。

| # | 消すもの | コマンド・操作 | 確認方法 |
|---|---|---|---|
| 1 | 通知 | Zabbix の *Actions* を無効にする。Discord の 2 つの Webhook を削除する | Discord のチャンネル設定に Webhook が残っていない |
| 2 | アプリ層・DB のエージェントと自作 UserParameter | 各ホストで `systemctl disable --now zabbix-agent2` → `apt purge -y zabbix-agent2 zabbix-release` → `rm -rf /etc/zabbix` → `apt update` | `dpkg -l \| grep zabbix` が空。`ss -tln \| grep 10050` が空。`ls /etc/apt/sources.list.d/ \| grep zabbix` が空。`ls /etc/zabbix` が存在しない |
| 3 | 本番 MariaDB の監視ユーザー | `<DB_HOST>` で `mariadb -e "DROP USER 'zbx_monitor'@'localhost';"` | `mariadb -e "SELECT user FROM mysql.user WHERE user='zbx_monitor';"` が空 |
| 4 | Proxmox の監視ユーザー・トークン・ロール | `pveum user token delete zabbix-monitor@pve zabbix` → `pveum user delete zabbix-monitor@pve` → `pveum role delete ZabbixMonitor`【要確認: `pveum help role delete`】 | `pveum user list` と `pveum role list` に残っていない |
| 5 | ファイアウォールのルール | 手順 12 で足した 10050 の許可を消す（Zabbix CT のルールは CT ごと消える） | 各ゲストのファイアウォール設定に Zabbix 関連のルールがない |
| 6 | Zabbix CT | `pct stop <CTID>` → `pct destroy <CTID> --purge 1` | `pct list` に出てこない |
| 7 | CT テンプレート | `pveam remove local:vztmpl/<テンプレートのファイル名>`（ほかで使っていなければ） | `pveam list local` に出てこない |

- 本番のアプリ（`infra/*.service`・`.env`・コード）には、この手順のどこでも触れていない。ロールバックでもアプリ側の作業はない。
- Grafana には触れていない（構成案 4 章の第 1 段階）。

---

## 8.0.x のマイナー更新（導入後の作業）

8.0 LTS の中の更新（8.0.0 → 8.0.1 など）は `apt` で上がる。x.0.0 で始めたので、最初の数回の更新は不具合の修正が多いと見込む。

- 更新の前に `pct snapshot <CTID> before-8.0.x` を取り、Zabbix の DB をダンプする。
- 更新したら `journalctl -u zabbix-server` に DB の更新の失敗がないかを見る【要確認: 公式のアップグレード手順にある、マイナー更新での DB の扱い】。
- サポート期限（8.0 LTS: フルサポート 2029-11-30、限定サポート 2031-11-30）は [zabbix-lessons.md](zabbix-lessons.md) の期限の一覧に入れてある。
