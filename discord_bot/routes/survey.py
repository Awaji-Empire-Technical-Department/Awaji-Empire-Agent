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
from services.bridge_client import BridgeUnavailableError
from services.event_service import EventService
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
#  ルート定義
# ------------------------------------------------------------------

@survey_bp.route('/create_new', methods=['POST'])
async def create_new():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        # None を渡しても内部で Rust Bridge を使うため動作する
        new_id = await SurveyService.create_survey(None, user['id'])
        if new_id is None:
            return "Database Error (Bridge)", 503
        await LogService.log_operation(None, user['id'], user['name'], "CREATE", f"ID:{new_id} を新規作成")
        return redirect(url_for('survey.edit_survey', survey_id=new_id))
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception as e:
        current_app.logger.error(f"Error in create_new: {e}")
        return "System Error", 503


@survey_bp.route('/edit/<int:survey_id>')
async def edit_survey(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        survey = await SurveyService.get_survey(None, survey_id)
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception:
        return "System Error", 503

    if not survey or str(survey['owner_id']) != str(user['id']):
        return "Forbidden", 403

    questions = parse_questions(survey['questions'])
    event_info = await EventService.get_event_by_survey(survey_id)
    return await render_template('edit.html', user=user, survey=survey, questions=questions, event_info=event_info)


@survey_bp.route('/save_survey', methods=['POST'])
async def save_survey():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    form = await request.form
    sid = form.get('survey_id')
    title = form.get('title')
    q_json = form.get('questions_json')
    event_settings_raw = form.get('event_settings_json', '')

    try:
        # オーナーチェック
        owner_id = await SurveyService.get_owner_id(None, int(sid))
        if not owner_id or owner_id != str(user['id']):
            return "Forbidden", 403

        success = await SurveyService.update_survey(None, int(sid), title, q_json)
        if not success:
            return "Error", 500
        await LogService.log_operation(None, user['id'], user['name'], "UPDATE", f"ID:{sid} を更新")

        # イベント設定の保存
        current_app.logger.info(f"[save_survey] sid={sid} event_settings_raw={event_settings_raw!r}")

        if event_settings_raw:
            try:
                es = json.loads(event_settings_raw)
            except (json.JSONDecodeError, ValueError):
                current_app.logger.warning(f"[save_survey] event_settings_json parse failed: {event_settings_raw!r}")
                es = {}

            current_app.logger.info(f"[save_survey] is_event_form={es.get('is_event_form')} sessions={es.get('sessions')}")
            existing_event = await EventService.get_event_by_survey(int(sid))
            current_app.logger.info(f"[save_survey] existing_event={'あり' if existing_event else 'なし'}")

            if es.get('is_event_form'):
                # datetime-local 形式 "YYYY-MM-DDTHH:MM" を MySQL DATETIME 互換 "YYYY-MM-DDTHH:MM:SS" に正規化
                def _norm_dt(v):
                    if v and 'T' in v and v.count(':') == 1:
                        return v + ':00'
                    return v or None

                def _clean_session(s):
                    return {
                        'name':       s.get('name') or '部',
                        'event_date': _norm_dt(s.get('event_date')),
                        'end_date':   _norm_dt(s.get('end_date')),
                        'location':   s.get('location') or None,
                        'capacity':   int(s['capacity']) if s.get('capacity') not in (None, '') else None,
                    }
                sessions = [_clean_session(s) for s in (es.get('sessions') or [])]
                fee_raw = es.get('fee')
                fee = int(fee_raw) if fee_raw else None
                capacity_raw = es.get('capacity')
                capacity = int(capacity_raw) if capacity_raw else None
                if existing_event is None:
                    event_id = await EventService.create_event(
                        survey_id=int(sid),
                        title=title,
                        fee=fee,
                        notes=es.get('notes') or None,
                        capacity=capacity,
                        location=es.get('location') or None,
                        event_date=_norm_dt(es.get('event_date')),
                        end_date=_norm_dt(es.get('end_date')),
                        application_deadline=_norm_dt(es.get('application_deadline')),
                        sessions=sessions,
                    )
                    current_app.logger.info(f"[save_survey] create_event result: event_id={event_id}")
                    if not event_id:
                        current_app.logger.error(f"[save_survey] create_event failed for survey_id={sid}")
                        await flash("イベント設定の保存に失敗しました（bridge接続を確認してください）", "error")
                else:
                    ok = await EventService.update_event(
                        event_id=existing_event['event']['id'],
                        title=title,
                        fee=fee,
                        notes=es.get('notes') or None,
                        capacity=capacity,
                        location=es.get('location') or None,
                        event_date=_norm_dt(es.get('event_date')),
                        end_date=_norm_dt(es.get('end_date')),
                        application_deadline=_norm_dt(es.get('application_deadline')),
                        sessions=sessions,
                    )
                    current_app.logger.info(f"[save_survey] update_event result: ok={ok}")

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
        success = await SurveyService.toggle_status(None, survey_id, user['id'])
        if success:
            await LogService.log_operation(None, user['id'], user['name'], "TOGGLE", f"ID:{survey_id} ステータス変更")
    except Exception as e:
        return f"Error: {e}", 500

    return redirect(url_for('index'))


@survey_bp.route('/delete_survey/<int:survey_id>', methods=['POST'])
async def delete_survey(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        success = await SurveyService.delete_survey(None, survey_id, user['id'])
        if success:
            await LogService.log_operation(None, user['id'], user['name'], "DELETE", f"ID:{survey_id} を削除")
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
        survey = await SurveyService.get_survey(None, survey_id)
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception:
        return "System Error", 503

    if not survey or not survey['is_active']:
        return "<h3>Not Found or Inactive</h3><p>このアンケートは現在受け付けていません。</p>", 404

    questions = parse_questions(survey['questions'])
    existing_answers = await SurveyService.get_existing_answers(None, survey_id, user['id'])
    event_info = await EventService.get_event_by_survey(survey_id)

    prev_attending = ''
    prev_preferred = []
    session_stats = None
    if event_info:
        event_id = event_info['event']['id']
        my_participation = await EventService.get_my_participation(
            event_id=event_id,
            user_id=int(user['id']),
        )
        if my_participation:
            raw_pref = my_participation.get('preferred_session_ids')
            if raw_pref is not None:
                prev_attending = 'yes'
                try:
                    prev_preferred = json.loads(raw_pref) if isinstance(raw_pref, str) else raw_pref
                except (json.JSONDecodeError, TypeError):
                    prev_preferred = []
            else:
                prev_attending = 'no'
        session_stats = await EventService.get_session_stats(event_id)

    return await render_template(
        'form.html',
        survey=survey,
        questions=questions,
        existing_answers=existing_answers,
        event_info=event_info,
        prev_attending=prev_attending,
        prev_preferred=prev_preferred,
        session_stats=session_stats,
    )


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

    response_id = await SurveyService.save_response(None, int(survey_id), u_id, u_name, answers)

    if response_id is not None:
        survey = await SurveyService.get_survey(None, int(survey_id))
        survey_title = survey['title'] if survey else "アンケート"

        event_info = await EventService.get_event_by_survey(int(survey_id))

        if event_info:
            # イベントフォーム: 参加者登録 → 確認URL付きDMを送信
            event = event_info.get('event', {})
            attending = form.get('event_attending')
            if attending == 'yes':
                raw = form.getlist('event_preferred_sessions[]')
                preferred_ids = [int(v) for v in raw if v.isdigit()]
            else:
                preferred_ids = None
            token = await EventService.register_participant(
                event_id=event['id'],
                user_id=int(u_id),
                response_id=response_id,
                preferred_session_ids=preferred_ids,
            )
            if token:
                confirm_url = f"{DASHBOARD_URL}/event/confirm/{token}"
                msg = (
                    f"【{survey_title}】への応募を受け付けました。\n"
                    f"応募内容の確認はこちらから:\n{confirm_url}"
                )
                is_sent = await NotificationService.send_dm_raw(
                    bot_token=DISCORD_BOT_TOKEN,
                    user_id=u_id,
                    message=msg,
                )
                if is_sent:
                    await SurveyService.mark_dm_sent(None, response_id)
        else:
            # 通常アンケート: 従来のDM
            is_sent = await NotificationService.send_dm(
                bot_token=DISCORD_BOT_TOKEN,
                user_id=u_id,
                survey_title=survey_title,
                survey_id=int(survey_id),
                dashboard_base_url=DASHBOARD_URL,
            )
            if is_sent:
                await SurveyService.mark_dm_sent(None, response_id)

    return await render_template('submitted.html')


@survey_bp.route('/results/<int:survey_id>')
async def view_results(survey_id):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        survey = await SurveyService.get_survey(None, survey_id)
        if not survey or str(survey['owner_id']) != str(user['id']):
            return "Forbidden", 403

        # イベントフォームの場合はイベント管理画面へリダイレクト
        event_info = await EventService.get_event_by_survey(survey_id)
        if event_info:
            return redirect(url_for('event.admin', event_id=event_info['event']['id']))

        responses = await SurveyService.get_responses(None, survey_id)
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception:
        return "System Error", 503

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
                # Rust Bridge からは既に dict/list にパースされて返ってくる想定
                # (BridgeError マッピングで JSON パースエラーはハンドリング済み)
                ans_json = r['answers']
                if isinstance(ans_json, str):
                    ans_json = json.loads(ans_json)
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
        survey = await SurveyService.get_survey(None, survey_id)
        if not survey or str(survey['owner_id']) != str(user['id']):
            return "Forbidden", 403

        responses = await SurveyService.get_responses(None, survey_id)
        event_info = await EventService.get_event_by_survey(survey_id)
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception:
        return "System Error", 503

    questions = parse_questions(survey['questions'])
    si = io.StringIO()
    writer = csv.writer(si)

    # イベントフォームの場合: 参加者情報を response_id で引けるよう map 化
    participant_map = {}
    session_map = {}
    if event_info:
        event_id = event_info['event']['id']
        participants = await EventService.list_participants(event_id)
        participant_map = {str(p['response_id']): p for p in participants if p.get('response_id')}
        session_map = {s['id']: s['name'] for s in event_info.get('sessions', [])}

    # ヘッダー行
    header = ['回答日時', '回答者']
    if event_info:
        header += ['参加意思', '状態', '割り当て部', '希望部']
    for i, q in enumerate(questions):
        q_text = q.get('text', f'Q{i+1}')
        header.append(f"Q{i+1}: {q_text}")
    writer.writerow(header)

    APPROVAL_LABELS = {'pending': '確認中', 'accepted': '承認', 'rejected': '否認', 'waitlist': '補欠'}

    for r in responses:
        row = [str(r['submitted_at']), r['user_name']]

        if event_info:
            p = participant_map.get(str(r['id']))
            if p:
                # 参加意思: preferred_session_ids が None なら不参加
                attending = '不参加' if p.get('preferred_session_ids') is None else '参加'
                approval = APPROVAL_LABELS.get(p.get('approval', ''), p.get('approval', ''))
                assigned = session_map.get(p.get('session_id')) if p.get('session_id') else ''
                # 希望部: preferred_session_ids JSON から部名リストに変換
                try:
                    pref_ids = json.loads(p['preferred_session_ids']) if isinstance(p.get('preferred_session_ids'), str) else []
                    preferred = ', '.join(session_map.get(sid, str(sid)) for sid in pref_ids) if pref_ids else ''
                except Exception:
                    preferred = ''
                row += [attending, approval, assigned, preferred]
            else:
                row += ['', '', '', '']

        try:
            ans_json = r['answers']
            if isinstance(ans_json, str):
                ans_json = json.loads(ans_json)
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
