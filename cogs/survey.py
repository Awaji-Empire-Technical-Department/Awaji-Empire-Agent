import discord
from discord.ext import commands
import aiomysql
import os
import json
from dotenv import load_dotenv

# .envの読み込み
load_dotenv()

class Survey(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_config = {
            'host': os.getenv('DB_HOST', '127.0.0.1'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASS', ''),
            'db': os.getenv('DB_NAME', 'bot_db'),
            'charset': 'utf8mb4',
            'autocommit': True
        }

    async def get_db_connection(self):
        """データベース接続を作成するヘルパー関数"""
        return await aiomysql.connect(**self.db_config)

    @commands.command(name="create_survey", help="アンケートを作成します: !create_survey 'タイトル' '[\"質問1\", \"質問2\"]'")
    async def create_survey(self, ctx, title: str, *, questions_json: str):
        """
        新しいアンケートを作成します。
        使用例: !create_survey "ランチ会" ["何が食べたい？", "予算は？"]
        """
        # 1. JSON形式のチェック
        try:
            # ユーザーが入力した文字列をJSONとして解析できるか確認
            questions = json.loads(questions_json)
            if not isinstance(questions, list):
                await ctx.send("エラー: 質問はリスト形式 `[\"Q1\", \"Q2\"]` で入力してください。")
                return
        except json.JSONDecodeError:
            await ctx.send("エラー: 質問の形式が正しくありません。正しいJSON形式（`[\"質問1\", \"質問2\"]`）で入力してください。")
            return

        # 2. データベースへの保存
        try:
            conn = await self.get_db_connection()
            async with conn.cursor() as cursor:
                # ★ここが最重要: owner_id に ctx.author.id (実行者のID) を保存
                sql = """
                    INSERT INTO surveys (title, questions, owner_id, is_active, created_at)
                    VALUES (%s, %s, %s, 1, NOW())
                """
                # ctx.author.id は整数なので文字列に変換して保存
                await cursor.execute(sql, (title, json.dumps(questions, ensure_ascii=False), str(ctx.author.id)))
                
            conn.close()
            
            await ctx.send(f"✅ アンケート「{title}」を作成しました！\n管理画面から確認・編集できます。")

        except Exception as e:
            await ctx.send(f"データベースエラーが発生しました: {e}")
            print(f"Error in create_survey: {e}")

    @commands.command(name="list_surveys", help="自分の作成したアンケート一覧を表示します")
    async def list_surveys(self, ctx):
        """自分が作成したアンケートの一覧を表示"""
        try:
            conn = await self.get_db_connection()
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # 自分のID (owner_id) に一致するものだけを取得
                sql = "SELECT id, title, is_active FROM surveys WHERE owner_id = %s ORDER BY created_at DESC LIMIT 10"
                await cursor.execute(sql, (str(ctx.author.id),))
                rows = await cursor.fetchall()
            conn.close()

            if not rows:
                await ctx.send("あなたが作成したアンケートはありません。")
                return

            # 結果を表示
            msg = "**📂 あなたのアンケート一覧**\n"
            for row in rows:
                status = "🟢稼働中" if row['is_active'] else "🔴停止中"
                msg += f"・ID: `{row['id']}` | {status} | **{row['title']}**\n"
            
            await ctx.send(msg)

        except Exception as e:
            await ctx.send(f"エラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(Survey(bot))
