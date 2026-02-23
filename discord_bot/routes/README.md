# `routes` ディレクトリ利用ガイド

## 1. 概要

`routes` ディレクトリは、**Webアプリケーション（Dashboardなど）のエンドポイント（ルーティング）** を定義する場所です。
ブラウザからのリクエストを受け取り、適切なロジックへ処理を委譲し、HTMLやJSONなどのレスポンスを返却する役割を持ちます。

Discord Botにおける `cogs` 層が「Discordからの入力」を担当するのに対し、`routes` 層は「Webからの入力」を担当するインターフェース層です。

## 2. ディレクトリの役割分担

Webアプリの肥大化を防ぐため、処理の格納場所を厳格に区別します。

| ディレクトリ | 役割 | 依存関係 |
| :--- | :--- | :--- |
| **`routes/`** | **エンドポイント定義**<br>URLの定義、リクエストのパース、レスポンス返却。 | `Quart` / `Flask`, `services`, `common` |
| **`services/`** | **副作用のある処理**<br>DB保存、Botへの操作依頼、外部API叩き。 | `discord.py`, `database` |
| **`common/`** | **純粋なロジック**<br>計算、バリデーション、定数管理。 | なし（標準ライブラリのみ） |

## 3. 実装ルール

1. **ロジックを直接書かない**
    `routes` 内の関数（ビュー関数）に DB 操作や複雑な計算を直接記述しないでください。それらは `services` または `common` に切り出し、`routes` はそれらを呼び出す「交通整理」に徹します。

2. **依存関係の方向を守る**
    `routes` は `services` や `common` を利用できますが、逆に `services` から `routes` を呼び出してはいけません。

3. **バリデーションの分離**
    フォーム入力値の複雑なチェックは `common` のバリデーターを利用するか、`services` 層で行います。

## 4. 実装例

### ルートの定義 (例: `routes/survey.py`)

```python
from quart import Blueprint, request, render_template, redirect, url_for
from services.survey_service import SurveyService
from common.validators import SurveyValidator

survey_bp = Blueprint('survey', __name__)

@survey_bp.route("/submit", methods=["POST"])
async def handle_submit():
    # 1. 入力の取得
    form_data = await request.form
    
    # 2. バリデーション (common)
    if not SurveyValidator.is_valid(form_data):
        return "入力内容に不備があります", 400
    
    # 3. ビジネスロジックの実行 (services)
    # 400行あったような重い処理はここではなく Service に逃がす
    success = await SurveyService.save_response(form_data)
    
    # 4. レスポンスの返却
    if success:
        return await render_template("success.html")
    return "保存に失敗しました", 500
```
