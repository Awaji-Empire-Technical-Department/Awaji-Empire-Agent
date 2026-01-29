# `cogs` ディレクトリ利用ガイド

## 1. 概要

`cogs` ディレクトリは、Discord Botの **インターフェース（入出力）** を定義する場所です。
ユーザーからのコマンド入力(`Context`)やDiscord上のイベント(`Event`)を受け取り、適切なロジックへ処理を委譲し、結果をユーザーに返却する役割を持ちます。

**本プロジェクトの方針:**
これまでの「1機能1ファイル」から、「1機能1ディレクトリ」構成へ移行し、**Cog（インターフェース）と Logic（処理）を分離** します。

## 2. ディレクトリ構成

機能ごとにディレクトリを作成し、その中に役割ごとのファイルを配置します。

```text
cogs/
└── 機能名/ (例: mass_mute)
    ├── __init__.py    # パッケージ定義
    ├── cog.py         # Discordコマンド・イベント定義 (Interface)
    └── logic.py       # ビジネスロジック (Implementation)
```

## 3. ファイルの役割と責務

### `cog.py` **(The Interface)**

役割: Discordコマンド・イベント定義（インターフェース）を定義します。

- コマンド定義 (`@commands.command`, `@app_commands.command`)
- イベント定義 (`@commands.Cog.listener`)
- 引数の受け取りとバリデーション
- レスポンス返却 (`await ctx.send(...)`)
- 具体的な処理は記述せず, `logic.py` へ委譲する

### `logic.py` **(The Business Logic)**

役割: 具体的な処理を定義します。

- `discord.Guild` や `discord.Member` などの Discord API を使用して、具体的な処理を定義します。
- 共通処理が必要な場合は `services` ディレクトリ、`common` ディレクトリを参照してください。
- `ctx` (Context) オブジェクトに依存させない (推奨)。
  - 理由: テストしやすくするため、またスラッシュコマンド等への移行を容易にするため。

## 4. データフローのイメージ

ユーザーがコマンドを実行した際の処理の流れは以下の通りです。

```
sequenceDiagram
    participant User
    participant Cog (cog.py)
    participant Logic (logic.py)
    participant Service (services/)
    
    User->>Cog: コマンド実行 (!mute)
    Cog->>Logic: 処理を依頼 (引数: guild, channel_id)
    
    Logic->>Service: 権限チェック (PermissionService)
    Service-->>Logic: OK / NG (自動修復)
    
    alt 権限OK
        Logic->>Logic: ミュート処理実行
        Logic-->>Cog: 結果(Success)
        Cog-->>User: "完了しました"
    else 権限NG / エラー
        Logic-->>Cog: 結果(Error)
        Cog-->>User: "エラーが発生しました"
    end
```

## 5. 実装例

`cogs/example_feature/cog.py`

```python
import discord
from discord.ext import commands
from .logic import ExampleLogic

class ExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def hello(self, ctx):
        # 1. 入力を受け取る
        user = ctx.author
        
        # 2. ロジックに投げる (ctxそのものではなく必要なデータを渡す)
        result_message = await ExampleLogic.generate_greeting(user)
        
        # 3. 結果を返す
        await ctx.send(result_message)

async def setup(bot):
    await bot.add_cog(ExampleCog(bot))
```

`cogs/example_feature/logic.py`

```python
import discord
from services.some_service import SomeService

class ExampleLogic:
    @staticmethod
    async def generate_greeting(user: discord.Member) -> str:
        # 複雑な処理やServiceの呼び出しはここで行う
        if await SomeService.is_special_user(user):
            return f"ようこそ、特別会員の {user.display_name} さん！"
        else:
            return f"こんにちは、{user.display_name} さん。"
```

## 6. コマンド定義時の注意点

- **権限デコレータ**: `@commands.has_permissions(...)` は `cog.py` 側に記述します(ユーザーが実行権限を持っているかのチェックはインターフェースの責務)。
- **エラーハンドリング**: `logic.py` から帰ってきたエラー情報に基づき、ユーザーにわかりやすいメッセージを返すのは `cog.py` の役割です。
