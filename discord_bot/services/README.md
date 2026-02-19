# `services` ディレクトリ利用ガイド

## 1. 概要

`services` ディレクトリは、**外部システム（Discord API, データベース, ファイルシステムなど）へのI/O（入出力）を伴う共通処理** を格納する場所です。

Cogs（コマンド/イベント層）からビジネスロジックを分離し、かつ `common`（純粋関数層）では扱えない「副作用のある処理」を一元管理するために使用します。

## 2. ディレクトリの役割分担

本プロジェクトでは、ロジックの格納場所を以下のように明確に区別します。

| ディレクトリ | 役割 | I/O (API通信) | 依存ライブラリ | 例 |
| :--- | :--- | :---: | :--- | :--- |
| **`common/`** | **純粋なロジック**<br>計算、文字列整形、定数管理など。 | **なし** | `discord.py` に依存しない（推奨） | `text_utils.py`, `regex.py` |
| **`services/`** | **I/Oを伴う機能**<br>権限操作、DB操作、外部API叩き。 | **あり** | `discord.py`, `requests` 等 | `permission.py`, `database.py` |
| **`cogs/`** | **インターフェース**<br>コマンド受付、イベントハンドリング。 | **あり** | `discord.py` | `mass_mute/cog.py` |

## 3. 実装ルール

1. **原則ステートレスにする**
    Serviceクラスは基本的に「状態（メンバ変数）」を持たせないように設計してください。必要な情報はすべて引数として渡します。
    * Good: `PermissionService.check(channel, user)`
    * Bad: `service = PermissionService(channel); service.check()`

2. **`Context` (ctx) を持ち込まない**
    Service層は特定のコマンドフレームワーク（`commands.Context`）に依存させないでください。代わりに `discord.Guild`, `discord.Member`, `discord.TextChannel` などのモデルオブジェクトを引数に取ります。これにより、スラッシュコマンドやイベント駆動の機能からも再利用可能になります。

3. **エラーハンドリング**
    Service内部で `try-except` を行い、呼び出し元には `True/False` や `Result` オブジェクト、あるいはカスタム例外を返すようにします。生のAPIエラーをそのままCogsに投げないように設計します。

## 4. 実装例

### サービスの定義 (`services/example_service.py`)

```python
import discord

class ExampleService:
    @staticmethod
    async def send_log(channel: discord.TextChannel, message: str) -> bool:
        """
        指定されたチャンネルにログを送信する。
        I/Oが発生するため common ではなく services に配置する。
        """
        if not channel:
            return False

        try:
            await channel.send(f"[LOG] {message}")
            return True
        except discord.Forbidden:
            print("ログ送信の権限がありません")
            return False
```

### サービスの使用 (`cogs/example_cog.py`)

```python
from services.example_service import ExampleService

class SomeFeatureLogic:
    @staticmethod
    async def execute(guild, channel_id):
        channel = guild.get_channel(channel_id)
        
        # Serviceを呼び出す
        result = await ExampleService.send_log(channel, "処理を開始します")
        
        if not result:
            return "ログ送信に失敗しました"
        return "成功"
```

## 5. 注意点

1. **副作用の管理**
    Service層は副作用（外部システムへのI/O）を伴う処理を担当します。そのため、ビジネスロジック層（Cogs）からは副作用を意識して設計してください。

2. **依存関係の管理**
    Service層は依存関係を最小限に抑え、純粋なロジックを提供するように設計してください。これにより、テストや再利用性を向上させることができます。

## 6. 命名規則

* ファイル名: `snake_case.py` (例: `permission.py`)

* クラス名: `PascalCase` (例: `PermissionService`)
