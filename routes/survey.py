from quart import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
import json
from collections import Counter
from utils import log_operation
import csv
import io
import httpx
import os
from quart import make_response

# Blueprintの定義
survey_bp = Blueprint('survey', __name__)

# ------------------------------------------------------------------
#  ヘルパー関数
# ------------------------------------------------------------------

# Load Bot Token
try:
    with open('token.txt', 'r', encoding='utf-8') as f:
        DISCORD_BOT_TOKEN = f.read().strip()
except FileNotFoundError:
    DISCORD_BOT_TOKEN = None
    print("WARNING: token.txt not found.")

async def send_dm_notification(user_id, survey_title, survey_id, answers_text=""):
    """
    ユーザーにDMで回答控えと編集用リンクを送信する
    """
    if not DISCORD_BOT_TOKEN:
        print("Token missing, cannot send DM.")
        return False

    url = f"https://discord.com/api/v10/users/@me/channels"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # 1. DMチャンネルを作成/取得
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json={"recipient_id": user_id}, headers=headers)
            if r.status_code not in (200, 201):
                print(f"Failed to create DM channel: {r.text}")
                return False
            channel_id = r.json().get('id')
            
            # 2. メッセージ送信
            msg_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            edit_url = f"http://localhost:5000/form/{survey_id}" # 本番環境ではドメイン変更が必要
            
            content = (
                f"**アンケート回答ありがとうございます**\n"
                f"「{survey_title}」への回答を受け付けました。\n\n"
                f"**回答の修正はこちらから:**\n{edit_url}\n"
            )
            
            payload = {
                "content": content,
                # "embeds": [...] # 必要なら埋め込みにする
            }
            
            r_msg = await client.post(msg_url, json=payload, headers=headers)
            if r_msg.status_code in (200, 201):
                return True
            else:
                print(f"Failed to send DM: {r_msg.text}")
                return False
                
        except Exception as e:
            print(f"Exception in send_dm_notification: {e}")
            return False

def parse_questions(json_str):
    """
    JSON文字列を安全にパースし、必須キーが欠けている場合はデフォルト値を埋める
    """
    try:
        data = json.loads(json_str)
        if not isinstance(data, list):
            return []
        
        # データのサニタイズ（万が一 text や type が無くても落ちないようにする）
        sanitized = []
        for q in data:
            if not isinstance(q, dict): continue
            q['text'] = q.get('text', '(無題の質問)')
            q['type'] = q.get('type', 'text')
            q['options'] = q.get('options', [])
            sanitized.append(q)
        return sanitized
    except:
        return []

# ------------------------------------------------------------------
#  ルート定義: 作成・編集・管理
# ------------------------------------------------------------------

@survey_bp.route('/create_new', methods=['POST'])
async def create_new():
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 初期データ作成
            sql = "INSERT INTO surveys (owner_id, title, questions, is_active, created_at) VALUES (%s, '無題のアンケート', '[]', FALSE, NOW())"
            await cur.execute(sql, (user['id'],))
            new_id = cur.lastrowid
            await log_operation(pool, user, "CREATE", f"ID:{new_id} を新規作成")

    return redirect(url_for('survey.edit_survey', survey_id=new_id))

@survey_bp.route('/edit/<int:survey_id>')
async def edit_survey(survey_id):
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
            survey = await cur.fetchone()

    # 所有権チェック
    if not survey or str(survey['owner_id']) != str(user['id']):
        return "Forbidden: あなたのアンケートではありません", 403

    # 安全にJSONパース
    questions = parse_questions(survey['questions'])

    return await render_template('edit.html', user=user, survey=survey, questions=questions)

@survey_bp.route('/save_survey', methods=['POST'])
async def save_survey():
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    form = await request.form
    sid = form.get('survey_id')
    title = form.get('title')
    q_json = form.get('questions_json')

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 所有権確認
            await cur.execute("SELECT owner_id FROM surveys WHERE id=%s", (sid,))
            row = await cur.fetchone()
            if not row or str(row[0]) != str(user['id']): return "Forbidden", 403

            await cur.execute("UPDATE surveys SET title=%s, questions=%s WHERE id=%s", (title, q_json, sid))
            await log_operation(pool, user, "UPDATE", f"ID:{sid} を更新")

    await flash("保存しました", "success")
    return redirect(url_for('index'))

@survey_bp.route('/toggle_status/<int:survey_id>', methods=['POST'])
async def toggle_status(survey_id):
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT owner_id, is_active FROM surveys WHERE id=%s", (survey_id,))
            row = await cur.fetchone()
            if row and str(row['owner_id']) == str(user['id']):
                new_status = not row['is_active']
                await cur.execute("UPDATE surveys SET is_active=%s WHERE id=%s", (new_status, survey_id))
                await log_operation(pool, user, "TOGGLE", f"ID:{survey_id} ステータス -> {new_status}")

    return redirect(url_for('index'))

@survey_bp.route('/delete_survey/<int:survey_id>', methods=['POST'])
async def delete_survey(survey_id):
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT owner_id FROM surveys WHERE id=%s", (survey_id,))
            row = await cur.fetchone()
            if row and str(row['owner_id']) == str(user['id']):
                await cur.execute("DELETE FROM surveys WHERE id=%s", (survey_id,))
                await log_operation(pool, user, "DELETE", f"ID:{survey_id} を削除")

    return redirect(url_for('index'))

# ------------------------------------------------------------------
#  ルート定義: 回答・集計
# ------------------------------------------------------------------

@survey_bp.route('/form/<int:survey_id>')
async def view_form(survey_id):
    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
            survey = await cur.fetchone()

    if not survey or not survey['is_active']:
        return "<h3>Not Found or Inactive</h3><p>このアンケートは現在受け付けていません。</p>", 404

    # ここでもヘルパーを使って安全に読み込む
    questions = parse_questions(survey['questions'])
    
    # 既存の回答を取得（ログインユーザーのみ）
    existing_answers = {}
    user = session.get('discord_user')
    if user:
        pool = current_app.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT answers FROM survey_responses WHERE survey_id=%s AND user_id=%s",
                    (survey_id, user['id'])
                )
                row = await cur.fetchone()
                if row:
                    try:
                        existing_answers = json.loads(row['answers'])
                    except:
                        pass

    return await render_template('form.html', survey=survey, questions=questions, existing_answers=existing_answers)

@survey_bp.route('/submit_response', methods=['POST'])
async def submit_response():
    form = await request.form
    survey_id = form.get('survey_id')
    user = session.get('discord_user')
    
    # ユーザー情報（未ログインならGuest）
    u_id = user['id'] if user else None
    u_name = user['name'] if user else 'Guest'

    answers = {}
    for key in form:
        # q_0, q_1... を取得（_otherは除外）
        if key.startswith('q_') and not key.endswith('_other'):
            q_idx = key.split('_')[1]
            val = form.getlist(key) if key.endswith('[]') else form.get(key)
            
            # 「その他」の処理ロジック
            # ラジオボタン: 値が "__other__" ならテキスト入力を採用
            if val == '__other__':
                other_text = form.get(f'q_{q_idx}_other', '').strip()
                val = other_text if other_text else 'その他'
            
            # チェックボックス: リスト内に "__other__" があればテキスト入力と置換
            elif isinstance(val, list) and '__other__' in val:
                val.remove('__other__')
                other_text = form.get(f'q_{q_idx}_other', '').strip()
                val.append(other_text if other_text else 'その他')
            
            answers[q_idx] = val

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            # 既に回答があるかチェック
            await cur.execute(
                "SELECT id FROM survey_responses WHERE survey_id=%s AND user_id=%s",
                (survey_id, u_id)
            )
            existing_row = await cur.fetchone()
            
            answers_json = json.dumps(answers, ensure_ascii=False)
            response_id = None
            
            if existing_row:
                # UPDATE
                response_id = existing_row['id']
                await cur.execute(
                    """
                    UPDATE survey_responses 
                    SET answers=%s, submitted_at=NOW(), dm_sent=FALSE 
                    WHERE id=%s
                    """,
                    (answers_json, response_id)
                )
            else:
                # INSERT
                await cur.execute(
                    """
                    INSERT INTO survey_responses (survey_id, user_id, user_name, answers, submitted_at, dm_sent) 
                    VALUES (%s, %s, %s, %s, NOW(), FALSE)
                    """,
                    (survey_id, u_id, u_name, answers_json)
                )
                response_id = cur.lastrowid
                
            # アンケートタイトル取得（DM用）
            await cur.execute("SELECT title FROM surveys WHERE id=%s", (survey_id,))
            s_row = await cur.fetchone()
            survey_title = s_row['title'] if s_row else "アンケート"

            # DM送信処理 (非同期で待つか、バックグラウンドにするか。要件は「非同期で実行」だがawaitでも良い)
            # ここではシンプルにawaitして結果をDBに反映する
            is_sent = await send_dm_notification(u_id, survey_title, survey_id)
            
            if is_sent:
                await cur.execute("UPDATE survey_responses SET dm_sent=TRUE WHERE id=%s", (response_id,))

    return await render_template('submitted.html')

@survey_bp.route('/results/<int:survey_id>')
async def view_results(survey_id):
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            # アンケート取得
            await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
            survey = await cur.fetchone()
            if not survey or str(survey['owner_id']) != str(user['id']): return "Forbidden", 403
            
            # 回答取得
            await cur.execute("SELECT * FROM survey_responses WHERE survey_id=%s ORDER BY submitted_at DESC", (survey_id,))
            responses = await cur.fetchall()

    # 質問データの安全な読み込み
    questions = parse_questions(survey['questions'])

    # 集計ロジック
    stats = {}
    for i, q in enumerate(questions):
        q_idx = str(i)
        
        # .get() で安全に取得（これがクラッシュ防止の肝）
        q_text = q.get('text', '(無題の質問)')
        q_type = q.get('type', 'text')

        stats[q_idx] = {'question': q_text, 'type': q_type, 'data': [], 'total': 0}

        raw_values = []
        for r in responses:
            try:
                ans_json = json.loads(r['answers'])
            except:
                continue # JSON壊れてたらスキップ
                
            val = ans_json.get(q_idx)
            if val:
                if isinstance(val, list): raw_values.extend(val)
                else: raw_values.append(val)

        stats[q_idx]['total'] = len(raw_values)
        
        if q_type in ['radio', 'checkbox', 'select']:
            stats[q_idx]['counts'] = dict(Counter(raw_values))
        else:
            stats[q_idx]['texts'] = raw_values

    return await render_template('results.html', survey=survey, stats=stats, response_count=len(responses))

@survey_bp.route('/download_csv/<int:survey_id>')
async def download_csv(survey_id):
    user = session.get('discord_user')
    if not user: return redirect(url_for('login'))

    pool = current_app.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor(current_app.aiomysql.DictCursor) as cur:
            # アンケート情報取得
            await cur.execute("SELECT * FROM surveys WHERE id=%s", (survey_id,))
            survey = await cur.fetchone()
            if not survey or str(survey['owner_id']) != str(user['id']): return "Forbidden", 403
            
            # 全回答取得
            await cur.execute("SELECT * FROM survey_responses WHERE survey_id=%s ORDER BY submitted_at DESC", (survey_id,))
            responses = await cur.fetchall()

    # 質問定義をパース（ヘルパー関数を使用）
    questions = parse_questions(survey['questions'])

    # CSVデータをメモリ上で作成
    si = io.StringIO()
    writer = csv.writer(si)

    # 1行目: ヘッダー
    header = ['回答日時', '回答者']
    for i, q in enumerate(questions):
        q_text = q.get('text', f'Q{i+1}')
        header.append(f"Q{i+1}: {q_text}")
    writer.writerow(header)

    # 2行目以降: データ
    for r in responses:
        row = [str(r['submitted_at']), r['user_name']]
        try:
            ans_json = json.loads(r['answers'])
        except:
            ans_json = {}

        for i in range(len(questions)):
            val = ans_json.get(str(i), '')
            if isinstance(val, list):
                val = ", ".join(val)
            row.append(val)
        
        writer.writerow(row)

    # レスポンス作成 (★ここを修正: await を追加！)
    output = await make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=survey_{survey_id:03}_results.csv"
    output.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    return output
