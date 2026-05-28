# Stripe事前決済システム 実装マニュアル（将来実装用リファレンス）

**ステータス:** 未実装（アイデア記録）  
**作成日:** 2026-05-26  
**対象:** オフ会・イベントの事前決済機能

---

## 目次

1. [アーキテクチャ概要](#1-アーキテクチャ概要)
2. [前提・技術選定の理由](#2-前提技術選定の理由)
3. [運用モデルの選択：パターンA vs B](#3-運用モデルの選択パターンa-vs-b)
4. [決済フロー詳細](#4-決済フロー詳細)
5. [Python側の実装イメージ](#5-python側の実装イメージ)
6. [Frontend側の実装イメージ](#6-frontend側の実装イメージ)
7. [Webhook実装（最重要）](#7-webhook実装最重要)
8. [Rust Bridge側の実装イメージ](#8-rust-bridge側の実装イメージ)
9. [既存システムへの統合ポイント](#9-既存システムへの統合ポイント)
10. [環境変数・Stripe設定](#10-環境変数stripe設定)
11. [テスト方法](#11-テスト方法)
12. [注意事項・落とし穴](#12-注意事項落とし穴)

---

## 1. アーキテクチャ概要

本プロジェクトは **Python（Discord Bot / Webapp） ↔ Rust Bridge（HTTP IPC） ↔ MariaDB** という3層構成をとっている（ADR-003参照）。  
Stripe決済の**DB書き込みはすべてRust Bridgeを経由する**ことがアーキテクチャの一貫性につながる。

```
[参加者]
   |
   | フォーム送信
   ↓
[Python Backend (Quart/FastAPI)]
   |
   | stripe.PaymentIntent.create()
   ↓
[Stripe API]
   |
   | client_secret を返す
   ↓
[Frontend (HTML + Stripe.js)]
   |
   | カード情報入力 → stripe.confirmPayment()
   ↓
[Stripe] ─── Webhook ───→ [Python Backend]
                                 |
                                 | httpx → Rust Bridge (HTTP IPC)
                                 ↓
                          [Rust Bridge: axum]
                                 |
                                 | sqlx → MariaDB
                                 ↓
                          [payment_status を "paid" に更新]
                                 |
                          Python が結果を受け取り
                                 ↓
                          [Discord DM: 参加確定通知]
```

---

## 2. 前提・技術選定の理由



### なぜ Frontend 主体はダメか

| 方式 | 問題点 |
|---|---|
| JS側で金額を決めてStripeに送る | 改ざん可能。DevToolsで金額を1円にできる |
| `/payment/complete` リダイレクトで完了判定 | ブラウザを閉じると検知できない。二重申請の危険 |

### 正しい分担

- **Python:** 金額計算・PaymentIntent生成・Webhook受信・BridgeClient経由でDB更新・Discord通知
- **Rust Bridge:** DB書き込み（payment_status更新・paid_at記録）
- **JavaScript:** カード入力UIの描画のみ（Stripe Elementsを表示する）

PCI DSS準拠のため、カード番号はStripeのサーバーに直接送信される。PythonにもRustにもカード情報は一切届かない。

---

## 3. 運用モデルの選択：パターンA vs B

Stripeを組み込む際、**「誰のStripeアカウントに入金するか」** によって2つのモデルがある。

### パターンA：プラットフォーム集約型（シンプル）

```
参加者 → Stripe（あなたのアカウント） → 後日 主催者へ手動振込
```

| 項目 | 内容 |
|---|---|
| 主催者のStripe登録 | **不要** |
| 実装難易度 | 低い（本マニュアルの他章がそのまま使える） |
| 環境変数 | `STRIPE_SECRET_KEY` 1本のみ |
| デメリット | あなたが一時的に資金を預かる形になる |

**主催者の操作はゼロ。** 管理者権限を持つ人がダッシュボードでイベントに `price` を設定するだけ。

---

### パターンB：Stripe Connect（主催者に直接入金）

複数の主催者が自分のStripeアカウントで売上を管理したい場合の方式。  
「BASE」「STORES」のような決済プラットフォームと同じ仕組み。

```
参加者
   ↓ 決済
Stripe Connect（あなたがプラットフォーム）
   ├── 主催者Aのアカウントへ入金（手数料差し引き後）
   └── あなたへプラットフォーム手数料
```

#### 主催者の連携フロー（OAuth）

```
主催者がダッシュボードで「Stripeアカウントを連携する」ボタンを押す
   ↓
stripe.com/oauth/authorize へリダイレクト
   ↓
主催者がStripeにログイン・アクセスを承認
   ↓
あなたのサーバーにコールバック（?code=xxxxx）が届く
   ↓
Python: stripe.OAuth.token(code=code) で access_token を取得
   ↓
取得した stripe_account_id をDBの organizers テーブルに保存
   ↓
以降そのイベントはその主催者のStripeに直接入金
```

#### Python側の連携処理イメージ

```python
import stripe

# Step 1: 主催者をStripe連携ページへリダイレクト
@app.get("/connect/stripe/authorize")
async def stripe_authorize():
    url = stripe.OAuth.authorize_url(
        scope="read_write",
        state=current_user_id,  # CSRF対策のステートトークン
    )
    return redirect(url)

# Step 2: OAuthコールバック受信
@app.get("/connect/stripe/callback")
async def stripe_callback():
    code  = request.args.get("code")
    state = request.args.get("state")  # ステート検証（省略せずに行うこと）

    response = stripe.OAuth.token(
        grant_type="authorization_code",
        code=code,
    )
    connected_account_id = response["stripe_user_id"]  # 例: acct_xxxxxxxxxx

    # Rust Bridge 経由でDBに保存
    await bridge_client.save_stripe_account(
        discord_user_id=state,
        stripe_account_id=connected_account_id,
    )
    return redirect("/dashboard")
```

#### Connect使用時のPaymentIntent生成（差分のみ）

```python
# 通常のPaymentIntentとの違いは stripe_account と application_fee_amount だけ
intent = stripe.PaymentIntent.create(
    amount=event["price"],
    currency="jpy",
    application_fee_amount=int(event["price"] * 0.05),  # プラットフォーム手数料5%
    stripe_account=organizer["stripe_account_id"],       # 主催者のアカウントID
    metadata={
        "discord_user_id": discord_user_id,
        "event_id": str(event_id),
    },
)
```

#### DBへの追加カラム（パターンBのみ必要）

```sql
-- organizersテーブル（または eventsテーブル）への追加
ALTER TABLE organizers
  ADD COLUMN stripe_account_id VARCHAR(100) NULL COMMENT 'Stripe ConnectのアカウントID (acct_xxx)';
```

#### パターンB固有の注意点

- **Stripeの審査が必要：** Connect利用にはStripeプラットフォーム審査がある（個人利用は通りにくい場合も）
- **Webhook受信が複雑になる：** 各Connectedアカウントのイベントを受け取るには `connect=True` を指定する必要がある
- **主催者がStripeアカウントを持っていない場合：** 連携前にStripeアカウント作成が必要（ハードルになる）

```python
# Connect用Webhookの署名検証（通常版との違い）
event = stripe.Webhook.construct_event(
    payload, sig_header, WEBHOOK_SECRET,
    # stripe_account=xxx は不要（プラットフォーム側のWebhookで受け取る）
)
# event["account"] で どの主催者のイベントか判別できる
organizer_account = event.get("account")  # "acct_xxxxxxxxxx"
```

---

### どちらを選ぶか

| 観点 | パターンA | パターンB |
|---|---|---|
| 主催者の手間 | なし | Stripeアカウント作成・連携が必要 |
| 実装コスト | 低い | 高い（OAuth + Connect対応） |
| 資金管理 | あなたが一時預かり | 主催者に直接入金 |
| 手数料設定 | 不要 | `application_fee_amount` で柔軟に設定可 |
| 向いている規模 | 身内・小規模オフ会 | 複数主催者・マネタイズ目的 |

**学習目的であれば、まずパターンAで動かしてからパターンBに拡張する順番が理解しやすい。**

---

## 4. 決済フロー詳細

> パターンA・Bどちらも Step 1〜7 の基本フローは同じ。パターンBはPaymentIntent生成時に `stripe_account` を追加するだけ。

### Step 1: 参加者がフォームを送信

既存のイベント参加フォームの「送信」ボタン押下。

### Step 2: Python が PaymentIntent を作成

`stripe.PaymentIntent.create()` を呼び出す。  
`metadata` に `discord_user_id` と `event_id` を埋め込む（Webhook受信後の特定に使う）。  
`client_secret` を取得してフロントに返す。

### Step 3: フロントが決済UIを表示

Stripe.js の `stripe.confirmPayment()` でカード入力フォームを表示。  
参加者がカード情報を入力して決済実行。

### Step 4: Stripe が Webhook を飛ばす

決済成功時に `payment_intent.succeeded` イベントをPythonサーバーに通知。  
失敗時は `payment_intent.payment_failed`。

### Step 5: Python が Rust Bridge 経由でDB更新

Webhookの署名を検証（改ざん防止）後、  
`bridge_client.py` 経由で Rust Bridge の `/event-responses/payment` エンドポイントを呼び出す。

### Step 6: Rust Bridge が MariaDB を更新

`sqlx` で `event_responses` テーブルの `payment_status` を `paid` に更新し、`paid_at` を記録。

### Step 7: Python が Discord DM 送信

Bridge からの成功レスポンスを受け取り、既存の通知基盤で参加確定DMを送信。

---

## 5. Python側の実装イメージ

### インストール

```bash
uv add stripe
```

### PaymentIntent生成エンドポイント

```python
import stripe
from quart import Blueprint, request, jsonify

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

payment_bp = Blueprint("payment", __name__)

@payment_bp.post("/api/payment/create-intent")
async def create_payment_intent():
    data = await request.get_json()
    event_id = data["event_id"]
    discord_user_id = data["discord_user_id"]

    # 金額はDBから取得（フロントから受け取らない）
    event = await bridge_client.get_event(event_id)
    if not event or not event.get("price"):
        return jsonify({"error": "このイベントは有料設定されていません"}), 400

    intent = stripe.PaymentIntent.create(
        amount=event["price"],   # 円単位（例: 3000 = 3,000円）
        currency="jpy",
        metadata={
            "discord_user_id": discord_user_id,
            "event_id": str(event_id),
        },
    )

    return jsonify({"client_secret": intent.client_secret})
```

### bridge_client.py への追加メソッドイメージ

```python
# discord_bot/bridge_client.py に追加するメソッド

async def confirm_payment(
    self,
    discord_user_id: str,
    event_id: int,
    payment_intent_id: str,
) -> dict:
    """決済完了をRust Bridgeに通知してDBを更新する"""
    return await self._post("/event-responses/payment", {
        "discord_user_id": discord_user_id,
        "event_id": event_id,
        "payment_intent_id": payment_intent_id,
        "payment_status": "paid",
    })
```

---

## 6. Frontend側の実装イメージ

### HTMLへの追加（最小構成）

```html
<!-- Stripe.jsの読み込み -->
<script src="https://js.stripe.com/v3/"></script>

<!-- カード入力エリア -->
<div id="payment-element"></div>
<button id="pay-button">決済して参加確定する</button>

<script>
const stripe = Stripe("pk_live_xxxxx"); // 公開可能キー（秘密キーではない）

// バックエンドから client_secret を取得
const res = await fetch("/api/payment/create-intent", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ event_id: EVENT_ID, discord_user_id: DISCORD_USER_ID })
});
const { client_secret } = await res.json();

// Stripe Elements でカード入力UIを描画
const elements = stripe.elements({ clientSecret: client_secret });
const paymentElement = elements.create("payment");
paymentElement.mount("#payment-element");

// 決済実行
document.getElementById("pay-button").addEventListener("click", async () => {
    const { error } = await stripe.confirmPayment({
        elements,
        confirmParams: {
            return_url: "https://yoursite.com/payment/complete",
        },
    });
    if (error) {
        alert(error.message);
    }
});
</script>
```

---

## 7. Webhook実装（最重要）

Webhookは決済完了を**確実に検知する唯一の手段**。絶対に省略しないこと。

### エンドポイント実装

```python
# discord_bot/webapp.py に追加

WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

@app.post("/webhook/stripe")
async def stripe_webhook():
    payload = await request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        # 署名不正 = 偽リクエスト
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        discord_user_id = intent["metadata"]["discord_user_id"]
        event_id = int(intent["metadata"]["event_id"])
        payment_intent_id = intent["id"]

        # Rust Bridge 経由でDB更新
        await bridge_client.confirm_payment(
            discord_user_id=discord_user_id,
            event_id=event_id,
            payment_intent_id=payment_intent_id,
        )

        # 既存の通知基盤でDiscord DM送信
        await send_payment_confirmed_dm(discord_user_id, event_id)

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        discord_user_id = intent["metadata"]["discord_user_id"]
        await send_payment_failed_dm(discord_user_id)

    # Stripeには必ず200を返す（200以外だとリトライし続ける）
    return jsonify({"status": "ok"})
```

### StripeダッシュボードでのWebhook設定

1. Stripe Dashboard → 「開発者」→「Webhook」→「エンドポイントを追加」
2. URL: `https://yourdomain.com/webhook/stripe`
3. 受信イベント: `payment_intent.succeeded`, `payment_intent.payment_failed`
4. 表示される「署名シークレット」を `STRIPE_WEBHOOK_SECRET` に設定

---

## 8. Rust Bridge側の実装イメージ

Rust側は `axum` でエンドポイントを追加し、`sqlx` でDBを更新する（ADR-003のアーキテクチャに従う）。

### DBマイグレーション

```sql
-- migrations/XXXX_add_payment_fields.sql

ALTER TABLE event_responses
  ADD COLUMN price           INT          NULL     COMMENT '参加費（円）',
  ADD COLUMN payment_status  VARCHAR(20)  NOT NULL DEFAULT 'unpaid'
                             COMMENT 'unpaid / pending / paid / refunded',
  ADD COLUMN payment_intent_id VARCHAR(100) NULL,
  ADD COLUMN paid_at         DATETIME     NULL;

-- eventsテーブルへの参加費追加
ALTER TABLE events
  ADD COLUMN price INT NULL COMMENT '参加費（円）。NULLなら無料';
```

### Rustの型定義（database_bridge/src/models.rs への追加）

```rust
#[derive(Debug, Serialize, Deserialize, sqlx::FromRow)]
pub struct EventResponse {
    pub id: i64,
    pub event_id: i64,
    pub discord_user_id: String,
    // ... 既存フィールド ...
    pub price: Option<i32>,
    pub payment_status: String,          // "unpaid" | "pending" | "paid" | "refunded"
    pub payment_intent_id: Option<String>,
    pub paid_at: Option<chrono::DateTime<chrono::Utc>>,
}

#[derive(Debug, Deserialize)]
pub struct ConfirmPaymentRequest {
    pub discord_user_id: String,
    pub event_id: i64,
    pub payment_intent_id: String,
    pub payment_status: String,
}
```

### Rustのエンドポイント（database_bridge/src/routes/event_response.rs への追加）

```rust
// POST /event-responses/payment
pub async fn confirm_payment(
    State(pool): State<MySqlPool>,
    Json(req): Json<ConfirmPaymentRequest>,
) -> Result<Json<serde_json::Value>, AppError> {
    let now = chrono::Utc::now();

    sqlx::query!(
        r#"
        UPDATE event_responses
        SET
            payment_status     = ?,
            payment_intent_id  = ?,
            paid_at            = ?
        WHERE
            discord_user_id = ?
            AND event_id    = ?
        "#,
        req.payment_status,
        req.payment_intent_id,
        now,
        req.discord_user_id,
        req.event_id,
    )
    .execute(&pool)
    .await?;

    Ok(Json(serde_json::json!({ "status": "ok" })))
}

// ルーター登録（src/router.rs）
// .route("/event-responses/payment", post(confirm_payment))
```

### 返金処理の場合（将来対応）

```rust
// POST /event-responses/refund
pub async fn refund_payment(
    State(pool): State<MySqlPool>,
    Json(req): Json<RefundRequest>,
) -> Result<Json<serde_json::Value>, AppError> {
    sqlx::query!(
        "UPDATE event_responses SET payment_status = 'refunded' WHERE payment_intent_id = ?",
        req.payment_intent_id,
    )
    .execute(&pool)
    .await?;

    Ok(Json(serde_json::json!({ "status": "ok" })))
}
```

Python側では `stripe.Refund.create(payment_intent=intent_id)` を呼び出し、その後BridgeにREFUND通知を送る。

---

## 9. 既存システムへの統合ポイント

| 既存コンポーネント | 変更内容 |
|---|---|
| `events` テーブル | `price` カラム追加（NULL = 無料） |
| `event_responses` テーブル | `payment_status`, `payment_intent_id`, `paid_at` 追加 |
| `Rust Bridge` | `POST /event-responses/payment` エンドポイント追加 |
| `bridge_client.py` | `confirm_payment()` メソッド追加 |
| イベント作成フォーム | 「参加費」入力欄追加（0 or 未入力なら無料） |
| 参加フォーム送信処理 | 有料イベントの場合、決済フローへ分岐 |
| Discord通知 | 既存の `send_dm()` を再利用して「参加確定」DM送信 |
| 管理ダッシュボード | 参加者の `payment_status` 表示・CSVエクスポートに追加 |

---

## 10. 環境変数・Stripe設定

```env
# .env に追加する項目
STRIPE_SECRET_KEY=sk_live_xxxxx        # 秘密キー（絶対に公開しない）
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxx   # 公開可能キー（フロントで使う）
STRIPE_WEBHOOK_SECRET=whsec_xxxxx      # Webhook署名シークレット
```

### テスト用キーと本番用キーの切り替え

- テスト時: `sk_test_xxxxx` / `pk_test_xxxxx`
- 本番時: `sk_live_xxxxx` / `pk_live_xxxxx`
- テストカード番号: `4242 4242 4242 4242`（有効期限・CVCは任意の未来日）

---

## 11. テスト方法

### ローカルでWebhookをテストする

Stripe CLIを使うことでローカルにWebhookを転送できる。

```bash
# Stripe CLIインストール後
stripe login
stripe listen --forward-to localhost:8000/webhook/stripe

# 別ターミナルでテスト決済を発火
stripe trigger payment_intent.succeeded
```

### テストシナリオ

| シナリオ | テストカード番号 |
|---|---|
| 決済成功 | `4242 4242 4242 4242` |
| カード拒否 | `4000 0000 0000 0002` |
| 残高不足 | `4000 0000 0000 9995` |
| 3Dセキュア要求 | `4000 0025 0000 3155` |

---

## 12. 注意事項・落とし穴

### やってはいけないこと

- **フロントから金額を受け取ってPaymentIntentを作らない** → 改ざん可能
- **`/payment/complete` リダイレクト到達で完了判定しない** → 通信断で検知漏れ
- **Webhookの署名検証を省略しない** → 偽のWebhookで不正参加確定が可能
- **`sk_live_` キーをコードにハードコードしない** → 必ず環境変数経由

### 日本円（JPY）の注意

JPYは**少数を持たない通貨（ゼロデシマル）** なので、Stripeに渡す `amount` はそのまま円単位でよい。

```python
# 正しい
amount=3000   # → 3,000円

# USDなら cents単位（参考）
# amount=300  → 3.00ドル
```

### Rustの `sqlx` の型注意

`chrono::DateTime<chrono::Utc>` を MariaDB の `DATETIME` に保存する場合は  
`Cargo.toml` に `chrono` feature を有効化しておくこと。

```toml
# Cargo.toml
sqlx = { version = "0.7", features = ["runtime-tokio", "mysql", "chrono"] }
```

---

## 参考リンク

- [Stripe Payment Intents API 公式](https://stripe.com/docs/payments/payment-intents)
- [Stripe Webhooks 公式](https://stripe.com/docs/webhooks)
- [Stripe.js / Elements 公式](https://stripe.com/docs/js)
- [Stripe テストカード一覧](https://stripe.com/docs/testing#cards)
- [Stripe CLI](https://stripe.com/docs/stripe-cli)
- [ADR-003: Python ↔ Rust HTTP IPC方式](./adr/003-phase3b-python-rust-ipc-method.md)
- [環境変数・シークレット管理マニュアル](./ENV_SECRETS_MANAGEMENT.md)（Stripe導入時は必読）
