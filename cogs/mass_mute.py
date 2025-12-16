import discord
from discord.ext import commands, tasks
import asyncio
import datetime
# 🚨 修正点: configから新しい2つのリストをインポート 🚨
from config import ADMIN_USER_ID, MUTE_ONLY_CHANNEL_NAMES, READ_ONLY_MUTE_CHANNEL_NAMES
from typing import List, Optional

# ----------------------------------------------------
# 権限オブジェクトの定義
# 🚨 修正点: send_messages を削除し、カテゴリ/チャンネルの既存設定を尊重する 🚨
# ----------------------------------------------------

# 1. 通知抑制のみを行う権限 (すべての対象チャンネルに適用)
MUTE_OVERWRITE = discord.PermissionOverwrite(
    read_messages=True,  
    # send_messages は設定しない (カテゴリ/チャンネルの既存設定を尊重)
    mention_everyone=False, 
    manage_webhooks=False, 
)

class MassMuteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = self._get_owner_id_int(ADMIN_USER_ID)
        
        # 🚨 修正点: 2つのリストを統合して、処理対象となる全チャンネル名をリストアップ 🚨
        self.all_target_channel_names: List[str] = MUTE_ONLY_CHANNEL_NAMES + READ_ONLY_MUTE_CHANNEL_NAMES
        
        self.daily_mute_check.add_exception_type(asyncio.CancelledError)
        self.daily_mute_check.start()

    def cog_unload(self):
        self.daily_mute_check.cancel()
    
    # --- ヘルパー関数 (変更なし) ---
    def _get_owner_id_int(self, admin_id_str: str) -> Optional[int]:
        try:
            return int(admin_id_str)
        except ValueError:
            print(f"[INIT FATAL] ADMIN_USER_ID '{admin_id_str}' is not a valid integer string. DM logging disabled.")
            return None

    async def _send_dm_log(self, message: str, is_error: bool = False):
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
        error_message = f"🚨 **【ミュート機能エラー】{title}** 🚨\n{description}"
        await self._send_dm_log(error_message, is_error=True)

    # ----------------------------------------------------
    # 1. コア機能: チャンネル通知の制御ロジック
    # ----------------------------------------------------
    async def execute_mute_logic(self, trigger: str):
        
        if not self.bot.guilds:
            await self._send_error_dm("サーバー未接続", "Botが接続しているサーバーが見つかりませんでした。")
            return

        guild = self.bot.guilds[0]
        everyone_role = guild.default_role
        
        channels_updated = 0
        error_messages = []
        
        # すべての対象チャンネルをループし、MUTE_OVERWRITE (通知抑制のみ) を適用
        for channel_name in self.all_target_channel_names:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if channel:
                try:
                    # MUTE_OVERWRITE を適用 (通知抑制のみ)
                    await channel.set_permissions(everyone_role, overwrite=MUTE_OVERWRITE)
                    channels_updated += 1
                    print(f"[MUTE SUCCESS] Channel #{channel_name} set to Notification Off.")
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
            log_message = f"⚠️ **通知制御エラーが発生しました** ⚠️\n> サーバー: **{guild.name}**\n> 成功: {channels_updated}/{len(self.all_target_channel_names)} チャンネル\n> エラー詳細:\n- {status_summary}\n> トリガー: **{trigger}**"
            await self._send_dm_log(log_message, is_error=True)
        else:
            log_message = f"✅ 通知制御を実行しました。\n> サーバー: **{guild.name}**\n> 対象チャンネル: {channels_updated}/{len(self.all_target_channel_names)} チャンネル\n> トリガー: **{trigger}**"
            await self._send_dm_log(log_message)


    # ----------------------------------------------------
    # 2. 固定時刻タスク (変更なし)
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
