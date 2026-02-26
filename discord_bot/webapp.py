import os
import httpx
from quart import Quart, render_template, request, redirect, url_for, session, current_app
from quart_cors import cors
from dotenv import load_dotenv

from routes.survey import survey_bp
from routes.lobby import lobby_bp
from services.lobby_service import LobbyService
from services.bridge_client import BridgeUnavailableError
from services.survey_service import SurveyService
from services.log_service import LogService

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_insecure_key')
    CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
    CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
    REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
    TARGET_GUILD_ID = os.getenv('DISCORD_GUILD_ID')
    CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')

app = Quart(__name__, static_folder='static', static_url_path='/static')
app = cors(app, allow_origin="*")
app.secret_key = Config.SECRET_KEY

# Blueprintの登録
app.register_blueprint(survey_bp)
app.register_blueprint(lobby_bp)

# --- ライフサイクル ---
@app.before_serving
async def startup():
    """サーバー起動時の処理 (現在は Rust Bridge があるため何もしない)"""
    app.logger.info("Webapp starting (Bridge IPC enabled)")

@app.after_serving
async def shutdown():
    """サーバー終了時の処理"""
    app.logger.info("Webapp shutting down")

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
# ... (login, callback, logout は変更なしのため省略。実際はそのまま残す)
# 省略記法が使えないため、全量を書くか、diff を工夫する。
# ここでは一旦 index のみを書き換える。

# --- 認証ルート (Auth) ---
@app.route('/login')
async def login():
    scope = "identify email guilds"
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
            
            # --- Cloudflare WARP IP Sync ---
            user_email = user_data.get('email')
            virtual_ip = None
            
            # DEBUG LOGGING
            debug_log = [f"User Email from Discord: {user_email}"]
            debug_log.append(f"Has Account ID: {bool(Config.CLOUDFLARE_ACCOUNT_ID)}")
            debug_log.append(f"Has API Token: {bool(Config.CLOUDFLARE_API_TOKEN)}")

            if user_email and Config.CLOUDFLARE_ACCOUNT_ID and Config.CLOUDFLARE_API_TOKEN:
                cf_url = f"https://api.cloudflare.com/client/v4/accounts/{Config.CLOUDFLARE_ACCOUNT_ID}/devices?per_page=1000"
                cf_headers = {
                    "Authorization": f"Bearer {Config.CLOUDFLARE_API_TOKEN}",
                    "Content-Type": "application/json"
                }
                debug_log.append(f"Requesting CF API: {cf_url}")
                try:
                    r_cf = await client.get(cf_url, headers=cf_headers, timeout=10.0)
                    debug_log.append(f"CF API Status: {r_cf.status_code}")
                    if r_cf.status_code == 200:
                        cf_data = r_cf.json()
                        if cf_data.get("success"):
                            devices = cf_data.get("result", [])
                            debug_log.append(f"Found {len(devices)} devices in CF")
                            for device in devices:
                                d_email = device.get("user", {}).get("email")
                                if d_email == user_email:
                                    virtual_ip = device.get("ip")
                                    debug_log.append(f"Matched device! IP: {virtual_ip}")
                                    break
                            if not virtual_ip:
                                debug_log.append("No matching email found in CF devices.")
                        else:
                            debug_log.append(f"CF API returned success=false: {cf_data.get('errors')}")
                    else:
                        debug_log.append(f"CF API failed response: {r_cf.text}")
                except Exception as e:
                    debug_log.append(f"CF API Exception: {e}")
                    current_app.logger.error(f"Failed to fetch CF devices: {e}")
            else:
                debug_log.append("Skipping CF fetch due to missing email or config.")

            # Write debug log to logger instead of file
            for line in debug_log:
                current_app.logger.info(f"[CF_DEBUG] {line}")

            # Rust Bridge へユーザー情報を同期
            discord_id = int(user_data['id'])
            try:
                await LobbyService.sync_user(
                    discord_id=discord_id,
                    email=user_email or "",
                    virtual_ip=virtual_ip
                )
            except BridgeUnavailableError:
                current_app.logger.warning("Failed to sync user: Bridge unavailable")
            except Exception as e:
                current_app.logger.error(f"Failed to sync user: {e}")
            
            # リダイレクト
            next_url = session.pop('next_url', None)
            if next_url:
                return redirect(next_url)
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
    
    try:
        # SurveyService 経由で取得 (Rust Bridge を利用)
        surveys = await SurveyService.get_surveys_by_owner(None, user['id'])
        
        # LogService 経由で取得 (Rust Bridge を利用)
        logs = await LogService.get_recent_logs(None, limit=30)
        
        # LobbyService 経由でアクティブなロビーを取得
        lobbies = await LobbyService.get_active_rooms()

        return await render_template('dashboard.html', user=user, surveys=surveys, logs=logs, lobbies=lobbies)
        
    except BridgeUnavailableError:
        current_app.logger.warning("Bridge unavailable on index: rendering maintenance page")
        return await render_template('maintenance.html'), 503
    except Exception as e:
        current_app.logger.error(f"Error in Index Dashboard: {e}")
        return f"System Error: {e}", 500

if __name__ == '__main__':
    # ローカル開発用設定
    app.run(host='0.0.0.0', port=5000)