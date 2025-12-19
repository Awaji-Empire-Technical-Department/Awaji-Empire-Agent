import os
import logging
import socket
import requests.packages.urllib3.util.connection as urllib3_cn
from flask import Flask, render_template, request, redirect, url_for, Response, session, abort
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from urllib.parse import quote_plus
from flask_discord import DiscordOAuth2Session, requires_authorization, Unauthorized

# ==========================================
# ★ ログ設定
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==========================================
# ★ IPv4強制パッチ (通信対策)
# ==========================================
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# --- 1. 設定読み込み ---
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "awaji_empire_secret_key")

# --- 2. Discord設定 ---
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_BOT_TOKEN"] = "" 

TARGET_GUILD_ID = os.getenv("AWAJI_GUILD_ID")

discord = DiscordOAuth2Session(app)

# --- 3. データベース接続 ---
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_NAME = os.getenv('DB_NAME', 'bot_db')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')

_user = quote_plus(DB_USER)
_pass = quote_plus(DB_PASS)
DATABASE_URI = f"mysql+pymysql://{_user}:{_pass}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"
engine = create_engine(DATABASE_URI, pool_recycle=3600, echo=False)


# --- 4. 認証・権限チェック ---

@app.errorhandler(Unauthorized)
def redirect_unauthorized(e):
    return render_template("login.html")

def check_guild_membership():
    if not TARGET_GUILD_ID:
        return True
    try:
        user_guilds = discord.fetch_guilds()
        is_member = any(str(g.id) == str(TARGET_GUILD_ID) for g in user_guilds)
        if not is_member:
            abort(403, "アクセス権限がありません：指定されたサーバーのメンバーではありません。")
    except Exception as e:
        logging.error(f"Guild Check Failed: {e}")
        return redirect(url_for('logout'))


# --- 5. ルート定義 ---

@app.route("/login")
def login():
    return discord.create_session(scope=["identify", "guilds"])

@app.route("/callback")
def callback():
    try:
        discord.callback()
        return redirect(url_for("index"))
    except Exception as e:
        logging.error(f"Callback Failed: {e}")
        return f"ログイン処理に失敗しました: {e}", 500

@app.route("/logout")
def logout():
    discord.revoke()
    return redirect(url_for("login"))


@app.route('/')
@requires_authorization
def index():
    check_guild_membership()
    user = discord.fetch_user()
    user_id = str(user.id)

    try:
        # 自分のアンケートを取得
        query_surveys = text("SELECT * FROM surveys WHERE owner_id = :uid ORDER BY created_at DESC")
        surveys_df = pd.read_sql(query_surveys, engine, params={"uid": user_id})

        query_logs = "SELECT * FROM mute_logs ORDER BY executed_at DESC LIMIT 50"
        logs_df = pd.read_sql(query_logs, engine)

        return render_template('index.html', 
                               user=user, 
                               surveys=surveys_df.to_dict(orient='records'), 
                               logs=logs_df.to_dict(orient='records'))
    except Exception as e:
        logging.error(f"Index Error: {e}")
        return f"エラー: {e}", 500


@app.route('/edit_survey/<int:survey_id>', methods=['GET', 'POST'])
@requires_authorization
def edit_survey(survey_id):
    check_guild_membership()
    user_id = str(discord.fetch_user().id)

    try:
        query = text("SELECT * FROM surveys WHERE id = :id")
        df = pd.read_sql(query, engine, params={"id": survey_id})
        
        if df.empty:
            return "Survey not found", 404
        
        survey_data = df.iloc[0].to_dict()
        
        # 所有権チェック
        if str(survey_data.get('owner_id')) != user_id:
            return "このアンケートを編集する権限がありません。", 403

        if request.method == 'POST':
            new_title = request.form.get('title')
            new_questions = request.form.get('questions')
            status_val = request.form.get('is_active')
            new_status = 1 if status_val == '1' else 0

            with engine.connect() as conn:
                sql = text("""
                    UPDATE surveys 
                    SET title = :title, is_active = :status, questions = :questions 
                    WHERE id = :id AND owner_id = :uid
                """)
                conn.execute(sql, {
                    "title": new_title, "status": new_status, 
                    "questions": new_questions, "id": survey_id, "uid": user_id
                })
                conn.commit()
            return redirect(url_for('index'))

        return render_template('edit.html', survey=survey_data)

    except Exception as e:
        logging.error(f"Edit Error: {e}")
        return f"エラー: {e}", 500


# --- ★復活させた機能 (エラーの原因だった部分) ---

@app.route('/toggle_status/<int:survey_id>')
@requires_authorization
def toggle_status(survey_id):
    """ステータス切替"""
    check_guild_membership()
    user_id = str(discord.fetch_user().id)
    
    try:
        with engine.connect() as conn:
            # 自分のIDと一致する場合のみ更新
            sql = text("UPDATE surveys SET is_active = NOT is_active WHERE id = :id AND owner_id = :uid")
            conn.execute(sql, {"id": survey_id, "uid": user_id})
            conn.commit()
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Toggle Error: {e}")
        return redirect(url_for('index'))


@app.route('/delete_survey/<int:survey_id>')
@requires_authorization
def delete_survey(survey_id):
    """削除"""
    check_guild_membership()
    user_id = str(discord.fetch_user().id)

    try:
        with engine.connect() as conn:
            # 自分のIDと一致する場合のみ削除
            sql = text("DELETE FROM surveys WHERE id = :id AND owner_id = :uid")
            conn.execute(sql, {"id": survey_id, "uid": user_id})
            conn.commit()
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Delete Error: {e}")
        return redirect(url_for('index'))


@app.route('/download_csv/<int:survey_id>')
@requires_authorization
def download_survey_csv(survey_id):
    """CSVダウンロード"""
    check_guild_membership()
    user_id = str(discord.fetch_user().id)

    try:
        query = text("SELECT * FROM surveys WHERE id = :id AND owner_id = :uid")
        df = pd.read_sql(query, engine, params={"id": survey_id, "uid": user_id})
        
        if df.empty:
            return "権限がないか、データが存在しません。", 403

        return Response(
            df.to_csv(index=False),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=survey_{survey_id}.csv"}
        )
    except Exception as e:
        logging.error(f"CSV Error: {e}")
        return f"エラー: {e}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
