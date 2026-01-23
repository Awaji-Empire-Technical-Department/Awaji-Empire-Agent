import os
import requests
import aiomysql
from quart import Quart, render_template, request, redirect, url_for, session
from quart_cors import cors
from dotenv import load_dotenv
import httpx

# Blueprintの読み込み
from routes.survey import survey_bp

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_insecure_key')
    CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
    CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
    REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
    TARGET_GUILD_ID = os.getenv('DISCORD_GUILD_ID')
    
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASS', ''),
        'db': os.getenv('DB_NAME', 'bot_db'),
        'charset': 'utf8mb4',
        'autocommit': True
    }

app = Quart(__name__, static_folder='static', static_url_path='/static')
app = cors(app, allow_origin="*")
app.secret_key = Config.SECRET_KEY

# アプリ全体で使えるようにDB設定を保存（survey.pyで使うため）
app.aiomysql = aiomysql 
app.db_pool = None

# ★Blueprint（アンケート機能）を登録
app.register_blueprint(survey_bp)

# --- ライフサイクル ---
@app.before_serving
async def startup():
    try:
        # app.db_pool に接続プールを格納
        app.db_pool = await aiomysql.create_pool(**Config.DB_CONFIG)
        app.logger.info("✅ Database connection pool created.")
    except Exception as e:
        app.logger.critical(f"❌ Failed to connect to database: {e}")

@app.after_serving
async def shutdown():
    if app.db_pool:
        app.db_pool.close()
        await app.db_pool.wait_closed()

# --- コンテキストプロセッサ ---
@app.context_processor
def inject_css_version():
    try:
        css_path = os.path.join(app.static_folder, 'style.css')
        version = int(os.path.getmtime(css_path))
    except:
        version = 1
    return dict(css_ver=version)

# --- 認証ルート (Auth) ---
@app.route('/login')
async def login():
    scope = "identify guilds"
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={Config.CLIENT_ID}"
        f"&redirect_uri={Config.REDIRECT_URI}&response_type=code&scope={scope}"
    )
    return await render_template('login.html', auth_url=discord_auth_url)

@app.route('/callback')
async def callback():
    code = request.args.get('code')
    if not code: return "Error: No code provided.", 400

    token_url = 'https://discord.com/api/oauth2/token'
    payload = {
        'client_id': Config.CLIENT_ID,
        'client_secret': Config.CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': Config.REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    async with httpx.AsyncClient() as client:
        try:
            # 1. トークン取得を非同期で行う
            r = await client.post(token_url, data=payload, headers=headers)
            if r.status_code != 200: return f"Auth Failed: {r.text}", 400
            
            token_data = r.json()
            auth_header = {'Authorization': f'Bearer {token_data.get("access_token")}'}

            # 2. ギルド確認とユーザー情報取得を並列、もしくは非同期で実行
            # ここを await することで、待機中に他のユーザーの処理を邪魔しなくなります
            if Config.TARGET_GUILD_ID:
                r_guilds = await client.get('https://discord.com/api/users/@me/guilds', headers=auth_header)
                if r_guilds.status_code == 200:
                    guild_ids = [g['id'] for g in r_guilds.json()]
                    if str(Config.TARGET_GUILD_ID) not in guild_ids:
                        return await render_template('access_denied.html'), 403

            r_user = await client.get('https://discord.com/api/users/@me', headers=auth_header)
            user_data = r_user.json()

            # セッション保存処理（以下略）
            session['discord_user'] = {
                'id': user_data['id'],
                'name': user_data['username'],
                'avatar_url': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
            }
            return redirect(url_for('index'))

        except Exception as e:
            return f"Error: {e}", 500

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ダッシュボード (Index) ---
@app.route('/')
async def index():
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))
    
    async with app.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM surveys WHERE owner_id = %s ORDER BY created_at DESC", (user['id'],))
            surveys = await cur.fetchall()
            await cur.execute("SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 30")
            logs = await cur.fetchall()

    return await render_template('dashboard.html', user=user, surveys=surveys, logs=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
