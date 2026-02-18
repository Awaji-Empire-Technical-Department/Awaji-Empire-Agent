import discord
from discord import app_commands
from discord.ext import commands
import aiomysql
import os
import json

class SurveyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        self.dashboard_url = os.getenv('DASHBOARD_URL', 'https://dashboard.awajiempire.net')

    async def cog_load(self):
        try:
            self.pool = await aiomysql.create_pool(
                host=os.getenv('DB_HOST', '127.0.0.1'),
                user=os.getenv('DB_USER', 'root'),
                password=os.getenv('DB_PASS', ''),
                db=os.getenv('DB_NAME', 'bot_db'),
                autocommit=True
            )
            print("✅ SurveyCog: DB Connected")
        except Exception as e:
            print(f"❌ SurveyCog DB Error: {e}")

    async def cog_unload(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    # --- グループコマンド /survey ---
    survey_group = app_commands.Group(name="survey", description="アンケート関連コマンド")

    @survey_group.command(name="create", description="【作成】アンケート作成ページを案内します")
    async def cmd_create(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 アンケートの作成",
            description="アンケートの作成・編集はWebダッシュボードから行えます。",
            color=discord.Color.green()
        )
        embed.add_field(name="Webダッシュボード", value=self.dashboard_url, inline=False)
        
        view = discord.ui.View()
        button = discord.ui.Button(label="ダッシュボードを開く", style=discord.ButtonStyle.link, url=self.dashboard_url)
        view.add_item(button)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @survey_group.command(name="list", description="【一覧】現在誰でも回答できるアンケートを表示します")
    async def cmd_list(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # 全員の「稼働中」を取得
                await cur.execute("SELECT * FROM surveys WHERE is_active = 1 ORDER BY created_at DESC")
                surveys = await cur.fetchall()

        if not surveys:
            await interaction.followup.send("現在実施中のアンケートはありません。")
            return

        embed = discord.Embed(
            title="📊 現在実施中のアンケート",
            description="以下のリンクから回答できます。",
            color=discord.Color.blue()
        )
        
        for s in surveys:
            url = f"{self.dashboard_url}/form/{s['id']}"
            try:
                q_count = len(json.loads(s['questions']))
            except:
                q_count = "?"
                
            embed.add_field(
                name=f"🆔 {s['id']}: {s['title']}",
                value=f"質問数: {q_count}問\n[👉 回答フォームへ]({url})",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    @survey_group.command(name="my_active", description="【確認】自分が作成し、現在「受付中」になっているアンケートを確認します")
    async def cmd_my_active(self, interaction: discord.Interaction):
        # 自分にしか見えないメッセージ (ephemeral=True) で返す
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # 自分がオーナー かつ is_active=1 のものを検索
                await cur.execute("SELECT * FROM surveys WHERE owner_id = %s AND is_active = 1 ORDER BY created_at DESC", (user_id,))
                surveys = await cur.fetchall()

        if not surveys:
            await interaction.followup.send("あなたが作成したアンケートの中で、現在「受付中」のものはありません。\nWebダッシュボードでステータスを確認してください。", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ あなたの稼働中アンケート",
            description="Webダッシュボードで正しく「公開」設定になっているものです。\nIDを使って `/survey announce` で周知できます。",
            color=discord.Color.green()
        )

        for s in surveys:
            url = f"{self.dashboard_url}/form/{s['id']}"
            embed.add_field(
                name=f"🆔 {s['id']}: {s['title']}",
                value=f"[フォームを確認]({url})",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @survey_group.command(name="announce", description="【周知】指定したアンケートをチャンネルに通知します（管理者用）")
    @app_commands.describe(survey_id="周知したいアンケートのID")
    @app_commands.checks.has_permissions(administrator=True)
    async def cmd_announce(self, interaction: discord.Interaction, survey_id: int):
        await interaction.response.defer()

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
                survey = await cur.fetchone()

        if not survey:
            await interaction.followup.send(f"❌ ID: {survey_id} のアンケートは見つかりませんでした。", ephemeral=True)
            return
        
        if not survey['is_active']:
            await interaction.followup.send(f"⚠️ このアンケートは現在「停止中」です。", ephemeral=True)
            return

        url = f"{self.dashboard_url}/form/{survey['id']}"
        
        embed = discord.Embed(
            title=f"📣 アンケートご協力のお願い",
            description=f"**{survey['title']}**\n\n皆様のご意見をお聞かせください。\n以下のボタンから回答ページへ移動できます。",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/0.png")
        embed.add_field(name="回答リンク", value=url, inline=False)
        embed.set_footer(text=f"Survey ID: {survey['id']} | 淡路帝国執務室")
        
        view = discord.ui.View()
        button = discord.ui.Button(label="回答する", style=discord.ButtonStyle.link, url=url, emoji="📝")
        view.add_item(button)

        await interaction.followup.send(content="新しいアンケートが公開されました！", embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(SurveyCog(bot))
