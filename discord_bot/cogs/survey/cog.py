# cogs/survey/cog.py
# Role: Interface Layer (cogs/README.md 準拠)
# - スラッシュコマンド定義のみ
# - 具体的な処理は logic.py へ委譲
import discord
from discord import app_commands
from discord.ext import commands
import os

from .logic import SurveyLogic


class SurveyCog(commands.Cog):
    """アンケート機能 (Interface Layer)

    スラッシュコマンドの受付を担当。
    DB操作・Embed生成のロジックは SurveyLogic に委譲する。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logic = SurveyLogic(
            dashboard_url=os.getenv('DASHBOARD_URL', 'https://dashboard.awajiempire.net'),
        )

    async def cog_load(self):
        await self.logic.initialize_pool()

    async def cog_unload(self):
        await self.logic.close_pool()

    # --- グループコマンド /survey ---
    survey_group = app_commands.Group(name="survey", description="アンケート関連コマンド")

    @survey_group.command(name="create", description="【作成】アンケート作成ページを案内します")
    async def cmd_create(self, interaction: discord.Interaction):
        embed, view = self.logic.build_create_response()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @survey_group.command(name="list", description="【一覧】現在誰でも回答できるアンケートを表示します")
    async def cmd_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await self.logic.build_list_response()
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("現在実施中のアンケートはありません。")

    @survey_group.command(name="my_active", description="【確認】自分が作成し、現在「受付中」になっているアンケートを確認します")
    async def cmd_my_active(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        embed = await self.logic.build_my_active_response(user_id)
        if embed:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "あなたが作成したアンケートの中で、現在「受付中」のものはありません。\n"
                "Webダッシュボードでステータスを確認してください。",
                ephemeral=True,
            )

    @survey_group.command(name="announce", description="【周知】指定したアンケートをチャンネルに通知します（管理者用）")
    @app_commands.describe(survey_id="周知したいアンケートのID")
    @app_commands.checks.has_permissions(administrator=True)
    async def cmd_announce(self, interaction: discord.Interaction, survey_id: int):
        await interaction.response.defer()
        result = await self.logic.build_announce_response(survey_id)
        if result is None:
            await interaction.followup.send(
                f"❌ ID: {survey_id} のアンケートは見つかりませんでした。",
                ephemeral=True,
            )
        elif result == "inactive":
            await interaction.followup.send(
                "⚠️ このアンケートは現在「停止中」です。",
                ephemeral=True,
            )
        else:
            embed, view = result
            await interaction.followup.send(
                content="新しいアンケートが公開されました！",
                embed=embed,
                view=view,
            )
