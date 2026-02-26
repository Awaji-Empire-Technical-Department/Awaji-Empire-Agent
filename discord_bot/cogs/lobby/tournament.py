import discord
from discord.ext import commands

class TournamentLobbyCog(commands.Cog, name="大会ロビー管理"):
    """
    セキュア対戦ロビーシステムのバックグラウンド処理を担当するCog。
    主にWebAPIからの「最終承認」を受けて優勝者ロールを付与する。
    """
    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------
    # アプリケーションコマンドから手動で呼び出すテスト用
    # (実際はWeb API側からBridge経由、またはCogへの直接コールで動く想定)
    # ---------------------------------------------------------
    @discord.app_commands.command(name="test_assign_winner", description="[DEBUG] 大会優勝者ロール付与テスト")
    @discord.app_commands.default_permissions(administrator=True)
    async def assign_winner_role(self, interaction: discord.Interaction, user: discord.Member, tournament_name: str):
        # 実際にはこれは Webapp (Quart) の `approve_winner` ルートから
        # Bot プロセスに何らかのシグナルが送られた際に呼び出される裏処理のイメージ。
        # 単体プロセスで動いているのであれば共有イベントやRedis PubSub等が考えられますが、
        # 今回はPython側での実装例として記述しています。
        try:
            guild = interaction.guild
            role_name = f"{tournament_name} 優勝"
            
            # その名前のロールを探す
            role = discord.utils.get(guild.roles, name=role_name)
            
            # なければ新規作成
            if not role:
                role = await guild.create_role(
                    name=role_name, 
                    color=discord.Color.gold(), 
                    hoist=True, 
                    reason="大会ロビーシステムによる自動生成"
                )
                
            # ユーザーに付与
            await user.add_roles(role, reason="大会の最終承認完了による自動付与")
            await interaction.response.send_message(f"🏆 {user.mention} に `{role_name}` ロールを付与しました！", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("Botの権限が不足しています。(ロールの管理権限が必要です)", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TournamentLobbyCog(bot))
