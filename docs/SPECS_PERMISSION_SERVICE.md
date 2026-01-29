# Service層導入と権限自動修復機能 仕様書

## 1. 概要

Botの運用において、チャンネルの再作成等により「チャンネルごとの権限設定（Overwrite）」が消失し、機能実行時に `403 Forbidden` (Error Code: 50013) が発生する問題に対処する。

本改修では、Discord APIへのI/Oを伴う共通処理を `services` 層として切り出し、各機能（Cogs）から利用可能な「権限自動修復機能」を提供する。これにより、Botが自身の権限不足を検知した場合、自動的に必要な権限を付与して処理を継続可能にする。

## 2. ディレクトリ構成変更

既存の `common` とは別に、API操作を伴うロジック格納用として `services` を新設する。また、`mass_mute` 機能をディレクトリ構成へ変更する。

```text
Awaji-Empire-Agent/
├── common/              # [既存] 副作用のない純粋なロジック（変更なし）
├── services/            # [新規] Discord API I/Oを伴うサービス
│   ├── __init__.py
│   └── permission.py    # [新規] 権限操作サービス
├── cogs/
│   └── mass_mute/       # [変更] 単一ファイルからディレクトリへ
│       ├── __init__.py
│       ├── cog.py       # [新規] コマンド・イベント定義（I/F層）
│       └── logic.py     # [新規] ビジネスロジック（PermissionServiceを利用）
```

## 3. クラス・メソッド設計

### 3.1 `services.permission.PermissionService`

Discordの権限チェック及び操作を行うステートレスなサービスクラス。

```python
@staticmethod
async def ensure_manage_permission(channel: discord.abc.GuildChannel, bot_member: discord.Member) -> bool:
    """
    指定されたチャンネルに対して、Botが管理権限を持っているかを確認し、必要に応じて自動的に権限を付与する。

    Args:
        channel (discord.abc.GuildChannel): 権限を確認する対象のチャンネル
        bot_member (discord.Member): Botのメンバーオブジェクト

    Returns:
        bool: 権限が確保できていれば True、失敗すれば False
    """
    # 権限確認
    permissions = channel.permissions_for(bot_member)
    if permissions.manage_permissions or permissions.manage_roles:
        return True

    # 権限付与
    try:
        overwrite = channel.overwrites_for(bot_member)
        overwrite.manage_permissions = True
        await channel.set_permissions(bot_member, overwrite=overwrite, reason="Auto-fix: Granting self manage_permissions via PermissionService")
        return True
    except discord.Forbidden:
        # サーバー全体の権限不足など
        logger.error("Failed to grant manage_permissions to bot member: Forbidden")
        return False
```

### 3.2 `cogs.mass_mute.logic.MassMuteLogic`

具体的な通知抑制処理の実装部分。

変更点:

* 処理の冒頭で `PermissionService.ensure_manage_permission` を呼び出す。
* False が返ってきた場合は、処理を中断しエラーハンドリングを行う（例: APIレスポンスとして403エラー相当のメッセージを返す）。

```python
async def mute_users(self, channel: discord.TextChannel, users: List[discord.Member]) -> None:
    """
    指定されたユーザーを指定されたチャンネルでミュートする。

    Args:
        channel (discord.TextChannel): ミュートを適用するチャンネル
        users (List[discord.Member]): ミュートするユーザー一覧
    """
    for user in users:
        try:
            await user.edit(mute=True, reason="Mass mute via MassMuteLogic")
            logger.info(f"Muted {user.mention} in {channel.mention}")
        except discord.Forbidden:
            logger.error(f"Failed to mute {user.mention}: Forbidden")
            continue
```

## 4. 前提条件 (サーバー設定)

本機能が正しく動作するためには、Botのサーバーロール（Discord上の設定）において、以下のいずれかが付与されている必要がある。

1. 管理者 (Administrator) **ただし、この権限は強力なため、十分な注意が必要。**
2. または 「ロールの管理 (Manage Roles)」 および 「チャンネルの管理 (Manage Channels)」 **これらの権限は、より限定的な権限であるため、より安全。**
基本的には2.を選択することを推奨します。

※ これらがない場合、Botは自分自身に権限を付与する操作自体が許可されないため、自動修復は失敗する。
