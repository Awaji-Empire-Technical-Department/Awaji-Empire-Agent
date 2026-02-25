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

### 何が起きたか

`form.html` にインラインで `<script>` ブロックが埋め込まれていた。
バグ調査・修正の際にHTMLとロジックが混在していて可読性が低かった。

### ルール

> テンプレートファイル内の `<script>` ブロックが**3関数以上 or 30行以上**になったら、
> `static/js/<page_name>.js` として分離すること。
> HTML には `<script src="...">` のみを残す。

---

## LESSON-003: sqlx で nullable カラムは必ず `Option<T>` で受ける

- **発見日**: 2026-02-25
- **ADR**: `docs/adr/005-phase3d-survey-response-fix.md § Phase 3-E`

### 何が起きたか

`survey_responses.user_id` (BIGINT) を Rust 側で `i64` として定義していた。  
本番 DB に `user_id = NULL` のレコードが混入した際、sqlx がデコードに失敗して  
`GET /surveys/{id}/responses` が 500 エラーを返し、テキスト型回答が全件「回答なし」になった。

```text
error occurred while decoding column "user_id": unexpected null;
try decoding as an 'Option'
```

### ルール

> **DB スキーマで `NOT NULL` 制約が明示されていないカラムは、  
> Rust 側のモデル型を必ず `Option<T>` で定義すること。**  
> `NOT NULL` が確実なカラムのみ non-Option で受けてよい。
