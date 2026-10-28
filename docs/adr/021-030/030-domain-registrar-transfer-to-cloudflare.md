# ADR-030: awajiempire.net のレジストラをお名前.com から Cloudflare Registrar へ移管

- **ステータス**: 採用
- **作成日**: 2026-10-28
- **作成者**: Wanyaldee
- **ブランチ**: —（ドメイン管理の運用作業のため、対応するコード変更なし）

---

## 背景 (Context)

`awajiempire.net` は次のように分かれて管理されていた。

| 役割 | 提供元 |
|------|--------|
| レジストラ（ドメイン登録・更新） | GMO インターネット「お名前.com」 |
| 権威 DNS | Cloudflare |
| 外部公開（`dashboard.awajiempire.net`） | Cloudflare Tunnel |
| 対戦ロビーの仮想 IP 管理 | Cloudflare WARP / Zero Trust |

2026-10-20、GMO インターネットの「お名前.com デスクトップクラウド」で、
第三者による不正なプログラムの設置が確認された。翌 21 日には全プランのサーバが停止された
（[Impress Watch](https://www.watch.impress.co.jp/docs/news/2150663.html)、
[熊本日日新聞](https://kumanichi.com/articles/2050148)）。

淡路帝国はこのサービスを利用しておらず、レジストラ部分に直接の被害もなかった。
ただ、同じ事業者の別サービスで侵害が起きている以上、レジストラのアカウントが
巻き込まれるのも時間の問題と判断した。
レジストラのアカウントを奪われると、NS レコードの書き換えやドメインの移管によって、
ドメインそのものを乗っ取られる。

## 決定事項 (Decision)

2026-10-28 に、レジストラを Cloudflare Registrar へ移管した（申請・完了とも同日）。
移管後、お名前.com のアカウントは削除した。

手順:

1. お名前.com で Whois 情報公開代行を解除
2. お名前.com で AuthCode（認証コード）を取得
3. Cloudflare ダッシュボードから移管を申請
4. お名前.com のアカウントを削除

## 根拠 (Reason)

### 移管先に Cloudflare を選んだ理由

もともと DNS・Tunnel・WARP を Cloudflare で運用していた。レジストラも Cloudflare にすれば、
ドメインに関わるものを 1 か所にまとめられる。他のレジストラとは比較していない
（目的が「Cloudflare に統一すること」だったため）。

この構成には、移管作業の上でも利点があった。

- Cloudflare Registrar では、Cloudflare DNS を使っていることが移管の前提条件になる。
  今回はすでに NS が Cloudflare を向いていた。
  そのため、移管の前後でネームサーバの切り替えが発生しない。
- レジストラが変わっても権威 DNS は変わらないので、名前解決やサイトの公開は
  移管中も止まらない。

移管後の NS（2026-10-28 に確認）:

```
$ dig +short NS awajiempire.net
leia.ns.cloudflare.com.
boyd.ns.cloudflare.com.
```

### 各手順の理由

- **Whois 情報公開代行の解除**: 公開代行中は、登録者の連絡先がお名前.com の代理情報に
  置き換わっている。解除しておかないと、移管手続きに関する連絡を登録者本人が受け取れない。
- **AuthCode の取得**: 移管先レジストラに対して、ドメインの正当な保有者であることを示すコード。
  移管元のアカウントに入れる人だけが取得できる。
- **お名前.com アカウントの削除**: 移管後もアカウントを残しておくと、侵害のあった事業者の側に
  個人情報や支払い情報が残り続ける。管理するドメインがなくなったアカウントを残す理由はないので、
  削除して攻撃対象そのものをなくした。

## 選択肢 (Alternatives Considered)

| 選択肢 | 理由 |
|--------|------|
| お名前.com に残す（パスワード変更・2 段階認証の強化のみ） | 同じ事業者でインシデントが起きている以上、アカウント側の対策だけでは事業者側の侵害を防げない |
| Cloudflare 以外のレジストラへ移管 | 検討していない。目的が既存の Cloudflare 環境への統一だったため |

## 影響 (Consequences)

### ポジティブ

- ドメインに関わる管理（登録・DNS・Tunnel・WARP）が Cloudflare の 1 アカウントにまとまった。
- 移管直後から `client transfer prohibited`（移管ロック）が有効になっている。

### ネガティブ・トレードオフ

- **単一障害点が増えた**: Cloudflare アカウントを乗っ取られると、ドメイン・DNS・公開経路を
  まとめて失う。Cloudflare アカウントの保護（2 段階認証、API トークンの権限の最小化）の重要度が
  上がった。
- Cloudflare Registrar で登録したドメインは、Cloudflare 以外のネームサーバに向けられない。
  DNS だけを他社に移したくなった場合は、レジストラごと移管し直す必要がある。
- ICANN のルールにより、移管完了から 60 日間は別のレジストラへ再移管できない。

## 検証 (Verification)

- 移管後の状態確認（2026-10-28、移管完了後）
  - `whois` で表示されるレジストラが Cloudflare になっていること
  - DNS の名前解決ができていること
  - サイトが停止していないこと

  Verified-by: Wanyaldee (human)、2026-10-28

- 上の内容を再確認した（`whois` コマンドが入っていないため RDAP で代用）。
  Checked-by: Claude Opus 5.5 (AI agent)、2026-10-28

  ```
  $ curl -sS https://rdap.verisign.com/net/v1/domain/awajiempire.net  # 抜粋
  registrar: Cloudflare, Inc.
  events:
    registration:  2025-12-22T02:06:36Z
    expiration:    2030-12-22T02:06:36Z
    last changed:  2026-10-28T12:12:02Z
  status: ['client transfer prohibited']

  $ dig +short NS awajiempire.net
  leia.ns.cloudflare.com.
  boyd.ns.cloudflare.com.

  $ dig +short dashboard.awajiempire.net
  104.21.69.219
  172.67.213.129

  $ curl -sS -o /dev/null -w "%{http_code}\n" https://dashboard.awajiempire.net/
  302
  ```

  `302` はログイン画面へのリダイレクトで、オリジンまで到達していることを示している。

### 未検証

- お名前.com アカウントの削除が完了したこと（削除完了の通知や画面は記録していない）
- DNSSEC の設定状況（移管の前後で確認していない）
- Cloudflare アカウントの 2 段階認証の設定状況（この ADR の範囲外として確認していない）

## 関連ドキュメント

- [ADR-008: セキュア対戦ロビーシステム](../001-010/008-secure-lobby-system.md) — Cloudflare WARP の利用
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Cloudflare Tunnel による公開構成
- お名前.com デスクトップクラウドのインシデント報道:
  - <https://www.watch.impress.co.jp/docs/news/2150663.html>
  - <https://kumanichi.com/articles/2050148>
