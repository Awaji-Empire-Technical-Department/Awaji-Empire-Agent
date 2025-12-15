import discord
from discord.ext import commands, tasks
import asyncio
import datetime
from config import ADMIN_USER_ID, MUTE_CHANNEL_NAMES 
from typing import List, Optional

# ----------------------------------------------------
# 権限オブジェクトの定義: 常時通知抑制
# ----------------------------------------------------
MUTE_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,  
    send_messages=True,  
    mention_everyone=False, 
    manage_webhooks=False, 
)

class MassMuteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # config.pyで文字列化されたADMIN_USER_IDを整数に変換
        self.owner_id = self._get_owner_id_int(ADMIN_USER_ID)
        self.target_channel_names: List[str] = MUTE_CHANNEL_NAMES
        
        # タスクをスタート
        self.daily_mute_check.add_exception_type(asyncio.CancelledError)
        self.daily_mute_check.start()

    def cog_unload(self):
        self.daily_mute_check.cancel()
    
    # --- ヘルパー関数 ---
    def _get_owner_id_int(self, admin_id_str: str) -> Optional[int]:
        """設定ファイルから読み込んだID文字列を整数に変換するヘルパー"""
        try:
            return int(admin_id_str)
        except ValueError:
            print(f"[INIT FATAL] ADMIN_USER_ID '{admin_id_str}' is not a valid integer string. DM logging disabled.")
            return None

    async def _send_dm_log(self, message: str, is_error: bool = False):
        """DMログを送信する内部ヘルパー"""
        if self.owner_id is None:
            return

        owner = None
        try:
            owner = await self.bot.fetch_user(self.owner_id) 
        except Exception:
            pass
            
        if owner:
            try:
                await owner.send(message)
                if not is_error:
                    print(f"[DM DEBUG] Log sent successfully.")
            except discord.Forbidden:
                print(f"[DM ERROR] Failed to send DM (Forbidden). User may block DMs.")
            except Exception as e:
                print(f"[DM ERROR] Failed to send DM log to owner: {e}")
        else:
            print(f"[DM WARNING] Cannot send DM. Owner ID {self.owner_id} not found.")

    async def _send_error_dm(self, title: str, description: str):
        """エラー発生時に管理者DMに通知するヘルパー"""
        error_message = f"🚨 **【ミュート機能エラー】{title}** 🚨\n{description}"
        await self._send_dm_log(error_message, is_error=True)

    # ----------------------------------------------------
    # 1. コア機能: チャンネル通知の制御ロジック
    # ----------------------------------------------------
    async def execute_mute_logic(self, trigger: str):
        """
        対象チャンネルの通知権限を操作し、DMでログを送信する共通ロジック。
        """
        
        # Botがサーバーに接続しているかチェック
        if not self.bot.guilds:
            await self._send_error_dm("サーバー未接続", "Botが接続しているサーバーが見つかりませんでした。")
            return

        # Botが参加している唯一のサーバーを取得
        guild = self.bot.guilds[0]
        everyone_role = guild.default_role
        
        # 常に通知オフの権限を適用
        overwrite_to_apply = MUTE_OVERWRITE
        action_desc = "通知オフ (常時抑制)"
        
        channels_updated = 0
        error_messages = []

        for channel_name in self.target_channel_names:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if channel:
                try:
                    await channel.set_permissions(everyone_role, overwrite=overwrite_to_apply)
                    channels_updated += 1
                except discord.Forbidden:
                    msg = f"チャンネル #{channel_name} の権限設定に失敗。Botに『権限の管理』権限が必要です。"
                    print(f"[MUTE ERROR] {msg}")
                    error_messages.append(msg)
                except Exception as e:
                    msg = f"チャンネル #{channel_name} の権限設定中に予期せぬエラーが発生: {e}"
                    print(f"[MUTE ERROR] {msg}")
                    error_messages.append(msg)
            else:
                msg = f"チャンネル '{channel_name}' がサーバーに見つかりませんでした。"
                print(f"[MUTE WARNING] {msg}")
                error_messages.append(msg)
                
        # ログメッセージの生成と送信
        if error_messages:
            status_summary = "\n- ".join(error_messages)
            log_message = f"⚠️ **通知制御エラーが発生しました** ⚠️\n> サーバー: **{guild.name}**\n> 成功: {channels_updated}/{len(self.target_channel_names)} チャンネル\n> エラー詳細:\n- {status_summary}\n> トリガー: **{trigger}**"
            await self._send_dm_log(log_message, is_error=True)
        else:
            log_message = f"✅ 通知制御を実行しました ({action_desc})。\n> サーバー: **{guild.name}**\n> 対象チャンネル: {channels_updated}/{len(self.target_channel_names)} チャンネル\n> トリガー: **{trigger}**"
            await self._send_dm_log(log_message)


    # ----------------------------------------------------
    # 2. 固定時刻タスク
    # ----------------------------------------------------
    @tasks.loop(time=[
        datetime.time(0, 0, tzinfo=datetime.timezone.utc),   # JST 9:00
        datetime.time(8, 0, tzinfo=datetime.timezone.utc),   # JST 17:00
        datetime.time(16, 0, tzinfo=datetime.timezone.utc)  # JST 翌 1:00
    ]) 
    async def daily_mute_check(self):
        print("Daily mute check triggered by fixed time.")
        await self.execute_mute_logic("Daily Task")

    @daily_mute_check.before_loop
    async def before_daily_mute_check(self):
        await self.bot.wait_until_ready()
        print("Waiting for Bot to be ready before starting daily mute check.")


async def setup(bot):
    await bot.add_cog(MassMuteCog(bot))
