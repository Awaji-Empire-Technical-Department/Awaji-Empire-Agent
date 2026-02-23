# cogs/survey/logic.py
# Role: Business Logic Layer (cogs/README.md 準拠)
# - DB操作（services/survey_service.py 経由）
# - Embed/View 生成
# - ctx 非依存
import json
import logging
from typing import Optional, Tuple, Union

import discord

from services.survey_service import SurveyService

logger = logging.getLogger(__name__)


class SurveyLogic:
    """アンケート機能のビジネスロジック。
    
    Why: Phase 3-B 以降、DB 接続は Rust Bridge に集約されたため、
         Python 側での Pool 管理は不要。
    """

    def __init__(self, dashboard_url: str):
        self.dashboard_url = dashboard_url

    def build_create_response(self) -> Tuple[discord.Embed, discord.ui.View]:
        """アンケート作成ページ案内用の Embed と View を生成する。"""
        embed = discord.Embed(
            title="📝 アンケートの作成",
            description="アンケートの作成・編集はWebダッシュボードから行えます。",
            color=discord.Color.green(),
        )
        embed.add_field(name="Webダッシュボード", value=self.dashboard_url, inline=False)

        view = discord.ui.View()
        button = discord.ui.Button(
            label="ダッシュボードを開く",
            style=discord.ButtonStyle.link,
            url=self.dashboard_url,
        )
        view.add_item(button)
        return embed, view

    async def build_list_response(self) -> Optional[discord.Embed]:
        """稼働中アンケート一覧の Embed を生成する。なければ None。"""
        surveys = await SurveyService.get_active_surveys(None)
        if not surveys:
            return None

        embed = discord.Embed(
            title="📊 現在実施中のアンケート",
            description="以下のリンクから回答できます。",
            color=discord.Color.blue(),
        )

        for s in surveys:
            url = f"{self.dashboard_url}/form/{s['id']}"
            try:
                q_count = len(json.loads(s['questions']))
            except Exception:
                q_count = "?"

            embed.add_field(
                name=f"🆔 {s['id']}: {s['title']}",
                value=f"質問数: {q_count}問\n[👉 回答フォームへ]({url})",
                inline=False,
            )
        return embed

    async def build_my_active_response(self, user_id: str) -> Optional[discord.Embed]:
        """自分の稼働中アンケート一覧の Embed を生成する。なければ None。"""
        surveys = await SurveyService.get_surveys_by_owner(
            None, user_id, active_only=True
        )
        if not surveys:
            return None

        embed = discord.Embed(
            title="✅ あなたの稼働中アンケート",
            description=(
                "Webダッシュボードで正しく「公開」設定になっているものです。\n"
                "IDを使って `/survey announce` で周知できます。"
            ),
            color=discord.Color.green(),
        )

        for s in surveys:
            url = f"{self.dashboard_url}/form/{s['id']}"
            embed.add_field(
                name=f"🆔 {s['id']}: {s['title']}",
                value=f"[フォームを確認]({url})",
                inline=False,
            )
        return embed

    async def build_announce_response(
        self,
        survey_id: int,
    ) -> Union[None, str, Tuple[discord.Embed, discord.ui.View]]:
        """アンケート周知用の Embed と View を生成する。
        """
        survey = await SurveyService.get_survey(None, survey_id)
        if not survey:
            return None
        if not survey['is_active']:
            return "inactive"

        url = f"{self.dashboard_url}/form/{survey['id']}"

        embed = discord.Embed(
            title="📣 アンケートご協力のお願い",
            description=(
                f"**{survey['title']}**\n\n"
                "皆様のご意見をお聞かせください。\n"
                "以下のボタンから回答ページへ移動できます。"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/0.png")
        embed.add_field(name="回答リンク", value=url, inline=False)
        embed.set_footer(text=f"Survey ID: {survey['id']} | 淡路帝国執務室")

        view = discord.ui.View()
        button = discord.ui.Button(
            label="回答する",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="📝",
        )
        view.add_item(button)
        return embed, view
