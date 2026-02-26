# 教訓集 (Lessons Learned)

開発中に発生したミス・問題とその対策を記録する。二度と同じ過ちを繰り返さないために。

---

## LESSON-001: Jinja2 ネストループでの `loop` 変数スコープ上書き

- **発見日**: 2026-02-23
- **仕様書**: `docs/Specifications/bugfix-form-radio-name.md`
- **修正ブランチ**: `fix/form-radio-name-conflict`

### 何が起きたか

`form.html` のラジオボタンで、外側ループ（質問）の `loop.index0` を
内側ループ（選択肢）の中でそのまま使用していた。
Jinja2 ではネストした `{% for %}` の内側で `loop` 変数が**上書きされる**ため、
内側ループ内の `loop.index0` は「選択肢の番号」を指していた。

```jinja2
{% for q in questions %}          {# loop.index0 = 質問番号 (0,1,2...) #}
  {% for opt in q.options %}      {# loop が上書きされる！ #}
    <input name="q_{{loop.index0}}">  {# ← 実際は選択肢番号 (0,1,2...) #}
  {% endfor %}
{% endfor %}
```

### 影響

- 同じ質問の選択肢が異なる `name` グループに入り、複数同時選択が可能になる
- `checkLogic()` の質問インデックスマッピングが全崩壊 → 条件分岐が一切動かない
- 他の質問を選択すると、別の質問の選択状態が干渉される

### 正しい対処法

**外側ループで変数に保存してから使う**。`{% set %}` は内側ループで上書きされない。

```jinja2
{% for q in questions %}
  {% set q_idx = loop.index0 | string %}   {# ← 外側ループで保存 #}
  {% for opt in q.options %}
    <input name="q_{{q_idx}}">  {# ← q_idx は安全 ✅ #}
  {% endfor %}
{% endfor %}
```

### ルール

> **Jinja2 テンプレートで `{% for %}` をネストするとき、外側ループの `loop.*` は
> 必ず `{% set %}` で変数に保存してから内側ループ内で使用すること。
> `loop.index0` / `loop.index` / `loop.last` 等すべてに該当する。**

---

## LESSON-002: インライン JS/CSS は早期に外部ファイル化する

- **発見日**: 2026-02-23

#### 何が起きたか

`form.html` にインラインで `<script>` ブロックが埋め込まれていた。
バグ調査・修正の際にHTMLとロジックが混在していて可読性が低かった。

#### ルール

> テンプレートファイル内の `<script>` ブロックが**3関数以上 or 30行以上**になったら、
> `static/js/<page_name>.js` として分離すること。
> HTML には `<script src="...">` のみを残す。

---

## LESSON-003: sqlx で nullable カラムは必ず `Option<T>` で受ける

- **発見日**: 2026-02-25
- **ADR**: `docs/adr/005-phase3d-survey-response-fix.md § Phase 3-E`

#### 何が起きたか

`survey_responses.user_id` (BIGINT) を Rust 側で `i64` として定義していた。  
本番 DB に `user_id = NULL` のレコードが混入した際、sqlx がデコードに失敗して  
`GET /surveys/{id}/responses` が 500 エラーを返し、テキスト型回答が全件「回答なし」になった。

```text
error occurred while decoding column "user_id": unexpected null;
try decoding as an 'Option'
```

#### ルール

> **DB スキーマで `NOT NULL` 制約が明示されていないカラムは、  
> Rust 側のモデル型を必ず `Option<T>` で定義すること。**  
> `NOT NULL` が確実なカラムのみ non-Option で受けてよい。

---

## LESSON-004: 外部キー制約(FK Constraints)とデータ同期の不一致

- **発見日**: 2026-02-26
- **ADR**: `docs/adr/008-secure-lobby-system.md`

### 何が起きたか

Rust側で生成する `matchmaking_rooms` テーブルの `host_id` には、`user_networks(discord_id)` への外部キー制約が設定されていた。しかし、Python(Quart)での Discord OAuth ログイン時、DBへのユーザー登録が省略されていたため、初めてアクセスしたユーザーがロビーを作成しようとすると「外部キー制約違反（Error 1452）」で落ちる問題が起きた。

### 正しい対処法

Rustフロント側でロビー作成（`insert_room`）、参加（`upsert_member`）、権限譲渡（`transfer_host`）を行う直前に、`INSERT IGNORE INTO user_networks` で未登録ユーザーの暗黙的追加を行うヘルパー関数 `ensure_user_exists` を呼び出し解決した。

### ルール

> **外部キー制約がかかる処理を実装する場合、元のテーブルへの参照レコードが存在することを保証するライフサイクルを必ず設計・実装すること。事前に暗黙的登録（UPSERTやIGNORE等）で補うのが有効なパターンの一つ。**

---

## LESSON-005: Jinja2 内での Python 組み込み関数の使用不可

- **発見日**: 2026-02-26
- **ブランチ**: `feature/secure-lobby`

#### 何が起きたか

HTMLのJinja2テンプレートで型の厳密な比較を行うため `{% if str(m.get('user_id')) == str(user['id']) %}` と記述した結果、`UndefinedError: 'str' is undefined` が発生し `500 Internal Server Error` になった。Jinja2はPythonそのものではなく、組み込みの `str()` は利用できない。

#### 正しい対処法

Jinja2 の組み込みフィルター `|string` を用いて文字列変換を行う。

```jinja2
{% if m.get('user_id')|string == user['id']|string %}
```

#### ルール

> **Jinja2 テンプレートエンジン内で Python 組み込み関数 (`str()`, `int()`, `len()` 等) は使えないと認識せよ。必ずマニュアルで提供される Jinja Filters (`|string`, `|int`, `|length`) を使用すること。**
