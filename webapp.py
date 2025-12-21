import os
import json
from quart import Quart, render_template, request, redirect, url_for, session, flash
from quart_cors import cors
import aiomysql
from dotenv import load_dotenv
import requests

# .env ファイルの読み込み
load_dotenv()

# アプリケーション設定 (静的ファイルパスを明示)
app = Quart(__name__, static_folder='static', static_url_path='/static')
app = cors(app, allow_origin="*")
app.secret_key = os.getenv('SECRET_KEY', 'super_secret_key_awaji')

# --- 環境変数 ---
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')

# DB設定
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASS', ''),
    'db': os.getenv('DB_NAME', 'bot_db'),
    'charset': 'utf8mb4',
    'autocommit': True
}

pool = None

# --- 起動・終了処理 ---

@app.before_serving
async def startup():
    global pool
    try:
        pool = await aiomysql.create_pool(**DB_CONFIG)
        print("✅ DB Pool Created")
    except Exception as e:
        print(f"❌ DB Connection Error: {e}")

@app.after_serving
async def shutdown():
    if pool:
        pool.close()
        await pool.wait_closed()

# --- ヘルパー関数 ---

async def get_user():
    return session.get('discord_user')

async def log_op(conn, user, command, detail):
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO operation_logs (user_id, user_name, command, detail) VALUES (%s, %s, %s, %s)",
                (str(user['id']), user['name'], command, detail)
            )
    except:
        pass

# --- 認証ルート ---

@app.route('/login')
async def login():
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify"
    )
    return await render_template('login.html', auth_url=discord_auth_url)

@app.route('/callback')
async def callback():
    code = request.args.get('code')
    if not code:
        return "Error: No code provided", 400

    # 1. トークン交換
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    headers = {'Content-Type': 'application_x-www-form-urlencoded'}
    
    try:
        r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
        r.raise_for_status()
        token = r.json().get('access_token')
    except requests.exceptions.RequestException as e:
        # エラー時は詳細を表示しないと原因がわからないため、ここだけ簡易表示
        return f"<h3>Login Error</h3><p>Status: {r.status_code}</p><p>Message: {r.text}</p>", 400

    # 2. ユーザー情報取得
    try:
        headers = {'Authorization': f'Bearer {token}'}
        r_user = requests.get('https://discord.com/api/users/@me', headers=headers)
        r_user.raise_for_status()
        user_data = r_user.json()
    except Exception as e:
        return f"User Info Error: {e}", 400

    # 3. セッション保存
    session['discord_user'] = {
        'id': user_data['id'],
        'name': user_data['username'],
        'avatar_url': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
    }
    return redirect(url_for('index'))

@app.route('/logout')
async def logout():
    session.pop('discord_user', None)
    return redirect(url_for('login'))

# --- アプリ機能ルート ---

@app.route('/')
async def index():
    user = await get_user()
    if not user: return redirect(url_for('login'))
    
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM surveys WHERE owner_id = %s ORDER BY created_at DESC", (user['id'],))
            surveys = await cur.fetchall()
            await cur.execute("SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 30")
            logs = await cur.fetchall()

    return await render_template('dashboard.html', user=user, surveys=surveys, logs=logs)

@app.route('/create_new', methods=['POST'])
async def create_new():
    user = await get_user()
    if not user: return redirect(url_for('login'))

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            sql = "INSERT INTO surveys (owner_id, title, questions, is_active, created_at) VALUES (%s, '無題のアンケート', '[]', FALSE, NOW())"
            await cur.execute(sql, (user['id'],))
            new_id = cur.lastrowid
            await log_op(conn, user, "CREATE", f"ID:{new_id} を新規作成")

    return redirect(url_for('edit_survey', survey_id=new_id))

@app.route('/edit/<int:survey_id>')
async def edit_survey(survey_id):
    user = await get_user()
    if not user: return redirect(url_for('login'))

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
            survey = await cur.fetchone()

    if not survey or str(survey['owner_id']) != str(user['id']):
        return "Forbidden", 403

    try: questions = json.loads(survey['questions'])
    except: questions = []

    return await render_template('edit.html', user=user, survey=survey, questions=questions)

@app.route('/save_survey', methods=['POST'])
async def save_survey():
    user = await get_user()
    if not user: return redirect(url_for('login'))

    form = await request.form
    sid = form.get('survey_id')
    title = form.get('title')
    q_json = form.get('questions_json')

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 所有者チェック
            await cur.execute("SELECT owner_id FROM surveys WHERE id=%s", (sid,))
            row = await cur.fetchone()
            if not row or str(row[0]) != str(user['id']): return "Forbidden", 403

            await cur.execute("UPDATE surveys SET title=%s, questions=%s WHERE id=%s", (title, q_json, sid))
            await log_op(conn, user, "UPDATE", f"ID:{sid} を更新")

    await flash("保存しました", "success")
    return redirect(url_for('index'))

@app.route('/toggle_status/<int:survey_id>', methods=['POST'])
async def toggle_status(survey_id):
    user = await get_user()
    if not user: return redirect(url_for('login'))

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT owner_id, is_active FROM surveys WHERE id=%s", (survey_id,))
            row = await cur.fetchone()
            if row and str(row['owner_id']) == str(user['id']):
                new = not row['is_active']
                await cur.execute("UPDATE surveys SET is_active=%s WHERE id=%s", (new, survey_id))
                await log_op(conn, user, "TOGGLE", f"ID:{survey_id} -> {new}")

    return redirect(url_for('index'))

@app.route('/delete_survey/<int:survey_id>', methods=['POST'])
async def delete_survey(survey_id):
    user = await get_user()
    if not user: return redirect(url_for('login'))

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT owner_id FROM surveys WHERE id=%s", (survey_id,))
            row = await cur.fetchone()
            if row and str(row['owner_id']) == str(user['id']):
                await cur.execute("DELETE FROM surveys WHERE id=%s", (survey_id,))
                await log_op(conn, user, "DELETE", f"ID:{survey_id} を削除")
                await flash("削除しました", "warning")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
