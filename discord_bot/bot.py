import discord
from discord.ext import commands
import asyncio
import os
import sys
import mysql.connector
from dotenv import load_dotenv

# .envファイルを読み込む（他の os.getenv より先に呼ぶ）
load_dotenv()

DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'https://dashboard.awajiempire.net')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')
DISCORD_GUILD_ID = os.getenv('DISCORD_GUILD_ID', '')

# コグ（拡張機能）のリスト
COGS = [
    # "cogs.filter" は Phase 2 仕様変更により削除
    "cogs.mass_mute",     # ディレクトリ化（__init__.py 経由）
    "cogs.survey",        # ディレクトリ化（__init__.py 経由）
    "cogs.voice_keeper",  # 変更なし
    "cogs.lobby.tournament", # セキュアロビーシステム (大会役職付与)
    "cogs.stream_comment_reset",  # #配信コメント 月次リセット
]

class MyBot(commands.Bot):
    def __init__(self):
        # インテンツの設定
        intents = discord.Intents.default()
        intents.members = True 
        intents.message_content = True 
        intents.voice_states = True #20260120:寝落ち切断機能
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """
        Bot起動時に一度だけ実行される初期化処理。
        """
        for cog_name in COGS:
            try:
                await self.load_extension(cog_name)
                print(f"LOADED: {cog_name} をロードしました。")
            except Exception as e:
                print(f"ERROR: {cog_name} のロードに失敗しました。")
                print(f"Traceback: {e}")

        # .env の DISCORD_GUILD_ID をチェック
        if DISCORD_GUILD_ID:
            try:
                # 特定のサーバー(ギルド)にだけコマンドを登録・同期
                guild = discord.Object(id=int(DISCORD_GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"Command tree synced to guild {DISCORD_GUILD_ID} successfully.")
            except Exception as e:
                print(f"Failed to sync to guild: {e}")
        else:
            # IDがない場合は、これまで通りグローバル同期
            try:
                await self.tree.sync()
                print("Command tree synced globally.")
            except Exception as e:
                print(f"Failed to global sync: {e}")

    # --- 追加: DB接続用メソッド ---
    def get_db_connection(self):
        """MySQLへの接続オブジェクトを返す"""
        return mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS')
        )

# Botインスタンスの作成
bot = MyBot()

def get_token() -> str | None:
    """環境変数 DISCORD_TOKEN からトークンを取得する"""
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token:
        print("Error: DISCORD_TOKEN が設定されていません。.env を確認してください。", file=sys.stderr)
        return None
    return token

@bot.event
async def on_ready():
    """BotがDiscordに接続・再接続したときに実行される"""
    print('--- Bot is starting up ---', flush=True) # flushを追加
    print('-------------------------------------')
    print('Bot Name: {0.user.name}'.format(bot))
    print('Bot ID: {0.user.id}'.format(bot))
    print('-------------------------------------')
    
    # --- Bridge Connection Check (Rust Bridge 稼働確認) ---
    try:
        from services.bridge_client import bridge_client
        res = await bridge_client.request("GET", "/health")
        if res and res.get("status") == "ok":
            print("✅ Rust Bridge (IPC) connection successful!")
        else:
            print("⚠️ Rust Bridge (IPC) connection failed or returned error.")
    except Exception as e:
        print(f"❌ Rust Bridge connection error: {e}")

    # --- 1. 起動/再接続DMを管理者へ送信 ---
    owner = None
    try:
        owner_id_int = int(ADMIN_USER_ID)
        owner = await bot.fetch_user(owner_id_int) 
    except Exception as e:
        print(f"Error fetching owner user: {e}")

    if owner:
        try:
            status = "再起動/再接続" if bot.is_ready() else "起動完了"
            embed = discord.Embed(
                title=f"Bot {status}",
                description=f"Bot **{bot.user.name}** がオンラインになりました。",
                color=0x4caf50 
            )
            await owner.send(embed=embed)
        except Exception as e:
            print(f"Failed to send status DM to owner: {e}")
    
    # --- 2. mass_mute の実行 ---
    if 'cogs.mass_mute' in bot.extensions:
        mass_mute_cog = bot.get_cog("MassMuteCog")
        if mass_mute_cog:
            asyncio.create_task(mass_mute_cog.execute_mute_logic("Startup/Reconnected"))

    # --- 3. イベント締切スケジューラー起動 ---
    asyncio.create_task(_event_deadline_scheduler())


async def _event_deadline_scheduler():
    """1分毎に締切済みイベントを処理する: auto_assign → closed → DM一斉送信。"""
    await bot.wait_until_ready()
    from services.event_service import EventService
    from services.notification_service import NotificationService
    from common.calendar_utils import build_calendar_urls

    bot_token = os.getenv('DISCORD_TOKEN', '').strip() or None

    while not bot.is_closed():
        try:
            events = await EventService.get_events_past_deadline()
            for ev in events:
                event_id = ev['id']
                print(f"[deadline_scheduler] Processing event_id={event_id} title={ev['title']}")

                await EventService.auto_assign(event_id)
                await EventService.update_status(event_id, 'closed')

                result   = await EventService.get_event(event_id)
                sessions = {s['id']: s for s in result['sessions']} if result else {}
                participants = await EventService.list_participants(event_id)

                for p in participants:
                    if p.get('notified_at'):
                        continue

                    sess = sessions.get(p.get('session_id'))
                    confirm_url = f"{DASHBOARD_URL}/event/confirm/{p['access_token']}"

                    if p['approval'] == 'accepted':
                        if sess:
                            cal = build_calendar_urls(
                                title=f"{ev['title']} {sess['name']}",
                                start_str=sess.get('event_date'),
                                end_str=sess.get('end_date'),
                                location=sess.get('location'),
                            )
                            lines = [
                                f"【{ev['title']}】参加確定のお知らせ",
                                '━━━━━━━━━━━━━━━',
                                f"✅ {sess['name']} 参加確定",
                            ]
                            if sess.get('event_date'):
                                lines.append(f"📅 {sess['event_date']}")
                            if sess.get('location'):
                                lines.append(f"📍 {sess['location']}")
                        else:
                            cal = build_calendar_urls(
                                title=ev['title'],
                                start_str=ev.get('event_date'),
                                end_str=ev.get('end_date'),
                                location=ev.get('location'),
                            )
                            lines = [
                                f"【{ev['title']}】参加確定のお知らせ",
                                '━━━━━━━━━━━━━━━',
                                '✅ 参加確定',
                            ]
                            if ev.get('event_date'):
                                lines.append(f"📅 {ev['event_date']}")
                            if ev.get('location'):
                                lines.append(f"📍 {ev['location']}")
                        if ev.get('fee'):
                            lines.append(f"💴 参加費: {ev['fee']}円")
                        lines += [
                            '',
                            '📆 カレンダーに追加:',
                            f"・Google: {cal['google']}",
                            f"・Outlook: {cal['outlook']}",
                            '━━━━━━━━━━━━━━━',
                            f'詳細確認: {confirm_url}',
                        ]
                        message = '\n'.join(lines)

                    elif p['approval'] in ('rejected', 'waitlist'):
                        message = (
                            f"【{ev['title']}】参加について\n"
                            "申し訳ございませんが、今回は参加をお断りさせていただきます。\n"
                            "またの機会にぜひご参加ください。"
                        )
                    else:
                        continue

                    if bot_token:
                        ok = await NotificationService.send_dm_raw(
                            bot_token=bot_token,
                            user_id=str(p['user_id']),
                            message=message,
                        )
                        if ok:
                            await EventService.mark_notified(p['id'])

        except Exception as e:
            print(f"[deadline_scheduler] error: {e}")

        await asyncio.sleep(60)


if __name__ == '__main__':
    bot_token = get_token()

    if bot_token:
        try:
            bot.run(bot_token, reconnect=True)
        except discord.LoginFailure:
            print("Error: Invalid token in token.txt")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    else:
        print("Bot execution aborted due to missing or invalid token.")
