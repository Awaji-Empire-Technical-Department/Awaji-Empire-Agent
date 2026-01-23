import os
import aiomysql
import httpx
from quart import Quart, render_template, request, redirect, url_for, session, current_app
from quart_cors import cors
from dotenv import load_dotenv

# Blueprintの読み込み（routes/survey.py 内でも非同期処理が徹底されているか確認してください）
from routes.survey import survey_bp

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_insecure_key')
    CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
    CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
    REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
    TARGET_GUILD_ID = os.getenv('DISCORD_GUILD_ID')
    
    # DB設定にタイムアウトを追加（重要）
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASS', ''),
        'db': os.getenv('DB_NAME', 'bot_db'),
        'charset': 'utf8mb4',
        'autocommit': True,
        'connect_timeout': 10  # 10秒で接続できなければエラーにする（無限待機防止）
    }

app = Quart(__name__, static_folder='static', static_url_path='/static')
app = cors(app, allow_origin="*")
app.secret_key = Config.SECRET_KEY

# アプリ全体で使えるように変数を初期化
app.db_pool = None

# Blueprintの登録
app.register_blueprint(survey_bp)

# --- ライフサイクル ---
@app.before_serving
async def startup():
    """サーバー起動時にDBプールを作成"""
    try:
        app.logger.info("Attempting to connect to database...")
        # タイムアウト付きでプール作成
        app.db_pool = await aiomysql.create_pool(**Config.DB_CONFIG)
        app.logger.info("✅ Database connection pool created successfully.")
    except Exception as e:
        # DBに繋がらなくてもサーバー自体は起動させる（リトライやエラーページのため）
        # ただしログには致命的エラーとして残す
        app.logger.critical(f"❌ Failed to connect to database: {e}")
        app.db_pool = None

@app.after_serving
async def shutdown():
    """サーバー終了時にDBプールを閉じる"""
    if app.db_pool:
        app.db_pool.close()
        await app.db_pool.wait_closed()
        app.logger.info("Database connection pool closed.")

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
    if not code:
        return "Error: No code provided.", 400

    token_url = 'https://discord.com/api/oauth2/token'
    payload = {
        'client_id': Config.CLIENT_ID,
        'client_secret': Config.CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': Config.REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    # タイムアウト設定付きのクライアントを使用
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # 1. アクセストークン取得 (非同期)
            r = await client.post(token_url, data=payload, headers=headers)
            
            if r.status_code != 200:
                return f"Auth Failed: {r.text}", 400
            
            token_data = r.json()
            access_token = token_data.get("access_token")
            auth_header = {'Authorization': f'Bearer {access_token}'}

            # 2. ギルドチェック (必要な場合のみ)
            if Config.TARGET_GUILD_ID:
                r_guilds = await client.get('https://discord.com/api/users/@me/guilds', headers=auth_header)
                if r_guilds.status_code == 200:
                    guilds = r_guilds.json()
                    # ID比較は文字列同士で行う
                    guild_ids = [str(g['id']) for g in guilds]
                    if str(Config.TARGET_GUILD_ID) not in guild_ids:
                        return await render_template('access_denied.html'), 403
                else:
                    return f"Failed to fetch guilds: {r_guilds.status_code}", 500

            # 3. ユーザー情報取得
            r_user = await client.get('https://discord.com/api/users/@me', headers=auth_header)
            if r_user.status_code != 200:
                return f"Failed to fetch user data: {r_user.status_code}", 500
                
            user_data = r_user.json()

            # セッション保存 (Quartでは代入で自動処理されるが、念のためデータ構造を確定)
            session['discord_user'] = {
                'id': user_data['id'],
                'name': user_data['username'],
                'avatar_url': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
            }
            
            # リダイレクト
            return redirect(url_for('index'))

        except httpx.TimeoutException:
            return "Discord API request timed out.", 504
        except Exception as e:
            current_app.logger.error(f"Callback Error: {e}")
            return f"Internal Error: {e}", 500

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ダッシュボード (Index) ---
@app.route('/')
async def index():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))
    
    # DB接続が失敗している場合のハンドリング
    if not app.db_pool:
        return "Database connection is not available. Please contact administrator.", 503
    
    try:
        async with app.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # クエリ実行
                await cur.execute("SELECT * FROM surveys WHERE owner_id = %s ORDER BY created_at DESC", (user['id'],))
                surveys = await cur.fetchall()
                
                await cur.execute("SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 30")
                logs = await cur.fetchall()

        return await render_template('dashboard.html', user=user, surveys=surveys, logs=logs)
        
    except Exception as e:
        current_app.logger.error(f"Database Error in Index: {e}")
        return f"Database Error: {e}", 500

if __name__ == '__main__':
    # ローカル開発用設定
    app.run(host='0.0.0.0', port=5000)