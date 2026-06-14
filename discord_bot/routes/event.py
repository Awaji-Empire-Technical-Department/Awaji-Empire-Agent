# routes/event.py
# イベント参加フォーム機能のルート層。

import json
import os

from quart import Blueprint, redirect, render_template, request, session, url_for, jsonify, current_app, Response

from common.calendar_utils import build_calendar_urls, build_ics
from services.bridge_client import BridgeUnavailableError
from services.event_service import EventService
from services.survey_service import SurveyService
from services.notification_service import NotificationService

event_bp = Blueprint('event', __name__, url_prefix='/event')

DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'https://dashboard.awajiempire.net')

try:
    with open('token.txt', 'r', encoding='utf-8') as f:
        DISCORD_BOT_TOKEN = f.read().strip()
except FileNotFoundError:
    DISCORD_BOT_TOKEN = None


def _current_user():
    return session.get('discord_user')


async def _can_manage_event(event_id: int, user_id) -> bool:
    """イベント（紐づくアンケート）のオーナー or スタッフなら True。"""
    result = await EventService.get_event(event_id)
    if not result:
        return False
    survey_id = result['event']['survey_id']
    owner_id = await SurveyService.get_owner_id(None, survey_id)
    if owner_id and str(owner_id) == str(user_id):
        return True
    return await SurveyService.is_collaborator(survey_id, user_id)


# ============================================================
# イベント作成 API（アンケート保存時に呼ばれる）
# ============================================================

@event_bp.route('/api/create', methods=['POST'])
async def api_create_event():
    user = _current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'unauthorized'}), 401

    data = await request.get_json()
    survey_id = data.get('survey_id')
    title     = data.get('title', '無題のイベント')
    fee       = data.get('fee')
    notes     = data.get('notes')
    location  = data.get('location')
    sessions  = data.get('sessions', [])

    # オーナー確認
    owner_id = await SurveyService.get_owner_id(None, int(survey_id))
    if not owner_id or owner_id != str(user['id']):
        return jsonify({'status': 'error', 'message': 'forbidden'}), 403

    event_id = await EventService.create_event(
        survey_id=int(survey_id),
        title=title,
        fee=int(fee) if fee is not None else None,
        notes=notes,
        location=location or None,
        sessions=sessions,
    )
    if not event_id:
        return jsonify({'status': 'error', 'message': 'create failed'}), 500

    return jsonify({'status': 'ok', 'event_id': event_id})


# ============================================================
# アンケート回答送信後の参加者登録
# ============================================================

@event_bp.route('/api/register', methods=['POST'])
async def api_register_participant():
    user = _current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'unauthorized'}), 401

    data        = await request.get_json()
    event_id    = data.get('event_id')
    response_id = data.get('response_id')
    preferred   = data.get('preferred_session_ids')  # list[int] or None

    token = await EventService.register_participant(
        event_id=int(event_id),
        user_id=int(user['id']),
        response_id=int(response_id) if response_id else None,
        preferred_session_ids=preferred,
    )
    if not token:
        return jsonify({'status': 'error', 'message': 'register failed'}), 500

    return jsonify({'status': 'ok', 'access_token': token})


# ============================================================
# Admin: 応募一覧・管理画面
# ============================================================

@event_bp.route('/<int:event_id>/admin')
async def admin(event_id: int):
    user = _current_user()
    if not user:
        return redirect(url_for('login'))

    try:
        result = await EventService.get_event(event_id)
        if not result:
            return 'Not Found', 404

        event    = result['event']
        sessions = result['sessions']

        # 権限確認（アンケートのオーナー or スタッフ）
        owner_id = await SurveyService.get_owner_id(None, event['survey_id'])
        if not owner_id:
            return 'Forbidden', 403
        if owner_id != str(user['id']) and not await SurveyService.is_collaborator(event['survey_id'], user['id']):
            return 'Forbidden', 403

        participants = await EventService.list_participants(event_id)

        # survey responses から username と回答内容を補完
        survey      = await SurveyService.get_survey(None, event['survey_id'])
        responses   = await SurveyService.get_responses(None, event['survey_id'])
        resp_map    = {str(r['id']): r for r in responses}
        for p in participants:
            resp = resp_map.get(str(p.get('response_id', '')), {})
            if not p.get('username'):
                p['username'] = resp.get('user_name', f"ID:{p['user_id']}")
            import json as _json
            raw_answers = resp.get('answers', '{}')
            p['answers'] = _json.loads(raw_answers) if isinstance(raw_answers, str) else (raw_answers or {})

        from common.survey_utils import parse_questions
        survey_questions = parse_questions(survey['questions']) if survey else []

        # 部ごとの残席計算
        session_stats = {}
        for s in sessions:
            accepted = sum(1 for p in participants if p.get('session_id') == s['id'] and p['approval'] == 'accepted')
            session_stats[s['id']] = {
                'accepted': accepted,
                'capacity': s['capacity'],
                'remaining': (s['capacity'] - accepted) if s['capacity'] else None,
            }

    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

    return await render_template(
        'event_admin.html',
        user=user,
        event=event,
        sessions=sessions,
        participants=participants,
        session_stats=session_stats,
        survey_questions=survey_questions,
    )


# ============================================================
# 当日モード（チェックイン受付）
# ============================================================

@event_bp.route('/<int:event_id>/checkin')
async def checkin_page(event_id: int):
    """オフ会当日の受付用ページ。承認済み参加者を部ごとに表示しチェックインを行う。"""
    user = _current_user()
    if not user:
        return redirect(url_for('login'))

    try:
        result = await EventService.get_event(event_id)
        if not result:
            return 'Not Found', 404

        event    = result['event']
        sessions = result['sessions']

        if not await _can_manage_event(event_id, user['id']):
            return 'Forbidden', 403

        participants = await EventService.list_participants(event_id)

        # 回答者名を survey responses から補完
        survey    = await SurveyService.get_survey(None, event['survey_id'])
        responses = await SurveyService.get_responses(None, event['survey_id'])
        resp_map  = {str(r['id']): r for r in responses}
        for p in participants:
            resp = resp_map.get(str(p.get('response_id', '')), {})
            if not p.get('username'):
                p['username'] = resp.get('user_name', f"ID:{p['user_id']}")

        # 承認済みのみ対象。部ごとにグルーピング（部なしは None キー）
        accepted = [p for p in participants if p.get('approval') == 'accepted']
        session_map = {s['id']: s for s in sessions}
        grouped = {}
        for p in accepted:
            sid = p.get('session_id')
            grouped.setdefault(sid, []).append(p)

        checked_in_count = sum(1 for p in accepted if p.get('checked_in_at'))

    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

    return await render_template(
        'event_checkin.html',
        user=user,
        event=event,
        sessions=sessions,
        session_map=session_map,
        grouped=grouped,
        accepted_total=len(accepted),
        checked_in_count=checked_in_count,
    )


@event_bp.route('/<int:event_id>/api/participant/<int:participant_id>/checkin', methods=['POST'])
async def api_checkin(event_id: int, participant_id: int):
    """参加者のチェックイン状態を切り替える。"""
    user = _current_user()
    if not user:
        return jsonify({'status': 'error'}), 401
    if not await _can_manage_event(event_id, user['id']):
        return jsonify({'status': 'forbidden'}), 403

    data = await request.get_json()
    checked_in = bool(data.get('checked_in'))
    ok = await EventService.set_checkin(participant_id, checked_in)
    return jsonify({'status': 'ok' if ok else 'error'})


@event_bp.route('/<int:event_id>/api/participant/<int:participant_id>', methods=['DELETE'])
async def api_delete_participant(event_id: int, participant_id: int):
    """応募（参加者＋アンケート回答）を削除する。オーナー/スタッフのみ。"""
    user = _current_user()
    if not user:
        return jsonify({'status': 'error'}), 401
    if not await _can_manage_event(event_id, user['id']):
        return jsonify({'status': 'forbidden'}), 403

    ok = await EventService.delete_participant(participant_id)
    return jsonify({'status': 'ok' if ok else 'error'})


# ============================================================
# Admin API: 参加者ステータス更新
# ============================================================

@event_bp.route('/api/participant/<int:participant_id>', methods=['PATCH'])
async def api_update_participant(participant_id: int):
    user = _current_user()
    if not user:
        return jsonify({'status': 'error'}), 401

    data         = await request.get_json()
    approval     = data.get('approval')
    session_id   = data.get('session_id')
    personal_note = data.get('personal_note')

    ok = await EventService.update_participant(
        participant_id=participant_id,
        approval=approval,
        session_id=session_id,
        personal_note=personal_note,
    )
    return jsonify({'status': 'ok' if ok else 'error'})


# ============================================================
# Admin API: 自動割り当て
# ============================================================

@event_bp.route('/api/<int:event_id>/auto-assign', methods=['POST'])
async def api_auto_assign(event_id: int):
    user = _current_user()
    if not user:
        return jsonify({'status': 'error'}), 401

    ok = await EventService.auto_assign(event_id)
    current_app.logger.info(f"[auto_assign] event_id={event_id} result={ok}")
    return jsonify({'status': 'ok' if ok else 'error'})


# ============================================================
# Admin API: Discord DM一斉通知
# ============================================================

@event_bp.route('/api/<int:event_id>/notify', methods=['POST'])
async def api_notify(event_id: int):
    user = _current_user()
    if not user:
        return jsonify({'status': 'error'}), 401

    try:
        result   = await EventService.get_event(event_id)
        event    = result['event']
        sessions = {s['id']: s for s in result['sessions']}
        participants = await EventService.list_participants(event_id)
    except Exception as e:
        current_app.logger.error(f'api_notify error: {e}')
        return jsonify({'status': 'error'}), 500

    sent = 0
    for p in participants:
        if p.get('notified_at'):
            continue  # 送信済みはスキップ

        sess = sessions.get(p.get('session_id'))
        confirm_url = f"{DASHBOARD_URL}/event/confirm/{p['access_token']}"

        if p['approval'] == 'accepted':
            lines = [
                f"【{event['title']}】参加確定のお知らせ",
                '━━━━━━━━━━━━━━━',
            ]
            if sess:
                lines.append(f"✅ {sess['name']} 参加確定")
                if sess.get('event_date'):
                    lines.append(f"📅 {sess['event_date']}")
                if sess.get('location'):
                    lines.append(f"📍 {sess['location']}")
                # カレンダーURL（部の日時）
                cal = build_calendar_urls(
                    title=f"{event['title']} {sess['name']}",
                    start_str=sess.get('event_date'),
                    end_str=sess.get('end_date'),
                    location=sess.get('location'),
                )
            else:
                # 部制なし: イベント全体の日時
                cal = build_calendar_urls(
                    title=event['title'],
                    start_str=event.get('event_date'),
                    end_str=event.get('end_date'),
                    location=event.get('location'),
                )
            if event.get('fee'):
                lines.append(f"💴 参加費: {event['fee']}円")
            lines += [
                '',
                '📆 カレンダーに追加:',
                f"・Google: <{cal['google']}>",
                f"・Outlook: <{cal['outlook']}>",
                '━━━━━━━━━━━━━━━',
                f'詳細確認: {confirm_url}',
            ]
            message = '\n'.join(lines)

        elif p['approval'] == 'rejected':
            message = (
                f"【{event['title']}】参加について\n"
                "申し訳ございませんが、今回は参加をお断りさせていただきます。\n"
                "またの機会にぜひご参加ください。"
            )

        elif p['approval'] == 'waitlist':
            message = (
                f"【{event['title']}】補欠登録のお知らせ\n"
                "現在補欠となっています。キャンセルが出た場合にご連絡します。\n"
                f"詳細確認: {confirm_url}"
            )
        else:
            continue

        ok = await NotificationService.send_dm_raw(
            bot_token=DISCORD_BOT_TOKEN,
            user_id=str(p['user_id']),
            message=message,
        )
        if ok:
            await EventService.mark_notified(p['id'])
            sent += 1

    return jsonify({'status': 'ok', 'sent': sent})


# ============================================================
# 参加者: 個人確認ページ
# ============================================================

@event_bp.route('/confirm/<token>')
async def confirm(token: str):
    participant = await EventService.get_participant_by_token(token)
    if not participant:
        return 'Not Found', 404

    result = await EventService.get_event(participant['event_id'])
    if not result:
        return 'Not Found', 404

    event    = result['event']
    sessions = {s['id']: s for s in result['sessions']}
    assigned = sessions.get(participant.get('session_id'))

    # カレンダーURL生成（承認時のみ）
    cal_urls = None
    if participant['approval'] == 'accepted':
        if assigned:
            cal_urls = build_calendar_urls(
                title=f"{event['title']} {assigned['name']}",
                start_str=assigned.get('event_date'),
                end_str=assigned.get('end_date'),
                location=assigned.get('location'),
            )
        elif event.get('event_date'):
            cal_urls = build_calendar_urls(
                title=event['title'],
                start_str=event.get('event_date'),
                end_str=event.get('end_date'),
                location=event.get('location'),
            )

    return await render_template(
        'event_confirm.html',
        event=event,
        participant=participant,
        assigned_session=assigned,
        cal_urls=cal_urls,
    )


@event_bp.route('/confirm/<token>/calendar.ics')
async def download_ics(token: str):
    participant = await EventService.get_participant_by_token(token)
    if not participant or participant['approval'] != 'accepted':
        return 'Not Found', 404

    result = await EventService.get_event(participant['event_id'])
    if not result:
        return 'Not Found', 404

    event    = result['event']
    sessions = {s['id']: s for s in result['sessions']}
    assigned = sessions.get(participant.get('session_id'))

    if assigned:
        ics = build_ics(
            title=f"{event['title']} {assigned['name']}",
            start_str=assigned.get('event_date'),
            end_str=assigned.get('end_date'),
            location=assigned.get('location'),
        )
    else:
        ics = build_ics(
            title=event['title'],
            start_str=event.get('event_date'),
            end_str=event.get('end_date'),
            location=event.get('location'),
        )

    return Response(
        ics,
        mimetype='text/calendar',
        headers={'Content-Disposition': 'attachment; filename="event.ics"'},
    )
