# routes/survey.py
# Role: Web Interface Layer (routes/README.md 準拠)
# - リクエストの受付 → Service呼び出し → レスポンス返却の「交通整理」に徹する
# - DB操作は services/survey_service.py、DM送信は services/notification_service.py に委譲
# - parse_questions は common/survey_utils.py に移動済み
import csv
import io
import json
import os
from collections import Counter

from quart import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from common.survey_utils import parse_questions
from services.log_service import LogService
from services.notification_service import NotificationService
from services.survey_service import SurveyService

# Blueprintの定義
survey_bp = Blueprint('survey', __name__)

# Bot Token の読み込み
# Why: DM送信時にBot Tokenが必要。routes 層では読み込みのみ行い、
#      実際の送信処理は NotificationService に委譲する。
try:
    with open('token.txt', 'r', encoding='utf-8') as f:
        DISCORD_BOT_TOKEN = f.read().strip()
except FileNotFoundError:
    DISCORD_BOT_TOKEN = None

DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'https://dashboard.awajiempire.net')


# ------------------------------------------------------------------
#  ヘルパー
# ------------------------------------------------------------------
async def get_db_pool():
    """DBプールを安全に取得するヘルパー"""
    pool = current_app.db_pool
    if not pool:
        raise RuntimeError("Database connection pool is not initialized.")
    return pool


# ------------------------------------------------------------------
#  ルート定義
# ------------------------------------------------------------------

@survey_bp.route('/create_new', methods=['POST'])
async def create_new():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        new_id = await SurveyService.create_survey(pool, user['id'])
        if new_id is None:
            return "Database Error", 503
        await LogService.log_operation(pool, user['id'], user['name'], "CREATE", f"ID:{new_id} を新規作成")
        return redirect(url_for('survey.edit_survey', survey_id=new_id))
    except Exception as e:
        current_app.logger.error(f"Error in create_new: {e}")
        return "Database Error", 503


@survey_bp.route('/edit/<int:survey_id>')
async def edit_survey(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        survey = await SurveyService.get_survey(pool, survey_id)
    except Exception:
        return "Database Error", 503

    if not survey or str(survey['owner_id']) != str(user['id']):
        return "Forbidden", 403

    questions = parse_questions(survey['questions'])
    return await render_template('edit.html', user=user, survey=survey, questions=questions)


@survey_bp.route('/save_survey', methods=['POST'])
async def save_survey():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    form = await request.form
    sid = form.get('survey_id')
    title = form.get('title')
    q_json = form.get('questions_json')

    try:
        pool = await get_db_pool()
        # オーナーチェック
        owner_id = await SurveyService.get_owner_id(pool, int(sid))
        if not owner_id or owner_id != str(user['id']):
            return "Forbidden", 403

        success = await SurveyService.update_survey(pool, int(sid), title, q_json)
        if not success:
            return "Error", 500
        await LogService.log_operation(pool, user['id'], user['name'], "UPDATE", f"ID:{sid} を更新")
    except Exception as e:
        return f"Error: {e}", 500

    await flash("保存しました", "success")
    return redirect(url_for('index'))


@survey_bp.route('/toggle_status/<int:survey_id>', methods=['POST'])
async def toggle_status(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        success = await SurveyService.toggle_status(pool, survey_id, user['id'])
        if success:
            await LogService.log_operation(pool, user['id'], user['name'], "TOGGLE", f"ID:{survey_id} ステータス変更")
    except Exception as e:
        return f"Error: {e}", 500

    return redirect(url_for('index'))


@survey_bp.route('/delete_survey/<int:survey_id>', methods=['POST'])
async def delete_survey(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        success = await SurveyService.delete_survey(pool, survey_id, user['id'])
        if success:
            await LogService.log_operation(pool, user['id'], user['name'], "DELETE", f"ID:{survey_id} を削除")
    except Exception as e:
        return f"Error: {e}", 500

    return redirect(url_for('index'))


# --- 回答・集計 ---

@survey_bp.route('/form/<int:survey_id>')
async def view_form(survey_id):
    user = session.get('discord_user')
    if not user:
        session['next_url'] = request.url
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        survey = await SurveyService.get_survey(pool, survey_id)
    except Exception:
        return "Database Unavailable", 503

    if not survey or not survey['is_active']:
        return "<h3>Not Found or Inactive</h3><p>このアンケートは現在受け付けていません。</p>", 404

    questions = parse_questions(survey['questions'])
    existing_answers = await SurveyService.get_existing_answers(pool, survey_id, user['id'])

    return await render_template('form.html', survey=survey, questions=questions, existing_answers=existing_answers)


@survey_bp.route('/submit_response', methods=['POST'])
async def submit_response():
    user = session.get('discord_user')
    if not user:
        return "Unauthorized: Please login first", 401

    form = await request.form
    survey_id = form.get('survey_id')
    u_id = user['id']
    u_name = user['name']

    # フォームデータからの回答抽出
    answers = {}
    for key in form:
        if key.startswith('q_') and not key.endswith('_other'):
            q_idx = key.split('_')[1]
            val = form.getlist(key) if key.endswith('[]') else form.get(key)

            if val == '__other__':
                other_text = form.get(f'q_{q_idx}_other', '').strip()
                val = other_text if other_text else 'その他'
            elif isinstance(val, list) and '__other__' in val:
                val.remove('__other__')
                other_text = form.get(f'q_{q_idx}_other', '').strip()
                val.append(other_text if other_text else 'その他')

            answers[q_idx] = val

    pool = await get_db_pool()
    response_id = await SurveyService.save_response(pool, int(survey_id), u_id, u_name, answers)

    if response_id is not None:
        # アンケートタイトル取得
        survey = await SurveyService.get_survey(pool, int(survey_id))
        survey_title = survey['title'] if survey else "アンケート"

        # DM送信
        is_sent = await NotificationService.send_dm(
            bot_token=DISCORD_BOT_TOKEN,
            user_id=u_id,
            survey_title=survey_title,
            survey_id=int(survey_id),
            dashboard_base_url=DASHBOARD_URL,
        )
        if is_sent:
            await SurveyService.mark_dm_sent(pool, response_id)

    return await render_template('submitted.html')


@survey_bp.route('/results/<int:survey_id>')
async def view_results(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        survey = await SurveyService.get_survey(pool, survey_id)
        if not survey or str(survey['owner_id']) != str(user['id']):
            return "Forbidden", 403

        responses = await SurveyService.get_responses(pool, survey_id)
    except Exception:
        return "Database Unavailable", 503

    questions = parse_questions(survey['questions'])
    stats = {}

    for i, q in enumerate(questions):
        q_idx = str(i)
        q_text = q.get('text', '(無題の質問)')
        q_type = q.get('type', 'text')
        stats[q_idx] = {'question': q_text, 'type': q_type, 'data': [], 'total': 0}

        raw_values = []
        for r in responses:
            try:
                ans_json = json.loads(r['answers'])
            except Exception:
                continue
            val = ans_json.get(q_idx)
            if val:
                if isinstance(val, list):
                    raw_values.extend(val)
                else:
                    raw_values.append(val)

        stats[q_idx]['total'] = len(raw_values)
        if q_type in ['radio', 'checkbox', 'select']:
            stats[q_idx]['counts'] = dict(Counter(raw_values))
        else:
            stats[q_idx]['texts'] = raw_values

    return await render_template('results.html', survey=survey, stats=stats, response_count=len(responses))


@survey_bp.route('/download_csv/<int:survey_id>')
async def download_csv(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        pool = await get_db_pool()
        survey = await SurveyService.get_survey(pool, survey_id)
        if not survey or str(survey['owner_id']) != str(user['id']):
            return "Forbidden", 403

        responses = await SurveyService.get_responses(pool, survey_id)
    except Exception:
        return "Database Unavailable", 503

    questions = parse_questions(survey['questions'])
    si = io.StringIO()
    writer = csv.writer(si)

    header = ['回答日時', '回答者']
    for i, q in enumerate(questions):
        q_text = q.get('text', f'Q{i+1}')
        header.append(f"Q{i+1}: {q_text}")
    writer.writerow(header)

    for r in responses:
        row = [str(r['submitted_at']), r['user_name']]
        try:
            ans_json = json.loads(r['answers'])
        except Exception:
            ans_json = {}

        for i in range(len(questions)):
            val = ans_json.get(str(i), '')
            if isinstance(val, list):
                val = ", ".join(val)
            row.append(val)
        writer.writerow(row)

    output = await make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=survey_{survey_id:03}_results.csv"
    output.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    return output
