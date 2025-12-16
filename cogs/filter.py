import discord
from discord.ext import commands
from config import CODE_CHANNEL_ID, ADMIN_USER_ID
from typing import Optional

class FilterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # IDをconfigから文字列として取得し、整数に変換
        self.code_channel_id = self._get_id_int(CODE_CHANNEL_ID, "CODE_CHANNEL_ID")
        self.owner_id = self._get_id_int(ADMIN_USER_ID, "ADMIN_USER_ID")

    def _get_id_int(self, id_str: str, name: str) -> Optional[int]:
        """設定ファイルから読み込んだID文字列を整数に変換するヘルパー"""
        try:
            return int(id_str)
        except ValueError:
            print(f"[INIT FATAL] Config Error: {name} '{id_str}' is not a valid integer string. Check config.py.")
            return None

    # --- DM送信ヘルパー ---
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
            except discord.Forbidden:
                print(f"[DM ERROR] Failed to send DM (Forbidden) by FilterCog.")
            except Exception as e:
                print(f"[DM ERROR] Failed to send DM log to owner by FilterCog: {e}")
        else:
            print(f"[DM WARNING] Cannot send DM. Owner ID {self.owner_id} not found.")

    # ----------------------------------------------------
    # イベント: メッセージ受信時のフィルタリング処理
    # ----------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message):
        
        # 1. フィルタリング不要なメッセージを無視
        if message.author.bot:
            return 
        if self.code_channel_id is None:
            return
        if message.channel.id != self.code_channel_id:
            return 

        # 2. コードチャンネルでのフィルタリング
        # 添付ファイルがあるかどうかをチェック
        if not message.attachments:
            try:
                # メッセージの削除
                await message.delete()
                
                # DMでの警告を管理者へ送信
                warning_message = (
                    f"⚠️ **メッセージ削除警告** ⚠️\n"
                    f"チャンネル: **#{message.channel.name}**\n"
                    f"理由: このチャンネルでは、**添付ファイル付きのメッセージのみ**が許可されています。\n"
                    f"送信者: {message.author.name}"
                )
                await self._send_dm_log(warning_message)
                
            except discord.Forbidden:
                print(f"[FILTER ERROR] Bot lacks permission to delete message or send DM to author.")
            except Exception as e:
                print(f"[FILTER ERROR] An error occurred during filtering: {e}")


async def setup(bot):
    await bot.add_cog(FilterCog(bot))
