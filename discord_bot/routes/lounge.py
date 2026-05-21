# routes/lounge.py
from quart import Blueprint, current_app, render_template, request, session, redirect, url_for, jsonify
from services.lounge_service import LoungeService
from services.tournament_service import TitleService
from services.bridge_client import BridgeUnavailableError
from routes.tournament import _ensure_discord_role, _assign_title_role

lounge_bp = Blueprint("lounge", __name__, url_prefix="/lounge")


def _current_user():
    return session.get("discord_user")


def _require_login():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))
    return None


# ============================================================
# ラウンジ画面
# ============================================================

@lounge_bp.route("/")
async def index():
    redir = _require_login()
    if redir:
        return redir
    user = _current_user()
    try:
        active_sessions = await LoungeService.list_active_sessions()
    except Exception:
        active_sessions = []
    return await render_template("lounge.html", user=user, view="list", active_sessions=active_sessions)


@lounge_bp.route("/sessions/<int:session_id>")
async def session_view(session_id: int):
    redir = _require_login()
    if redir:
        return redir
    user = _current_user()
    try:
        session_data = await LoungeService.get_session(session_id)
        if not session_data:
            return redirect(url_for("lounge.index"))
        standings = await LoungeService.get_standings(session_id)
        members = await LoungeService.list_members(session_id)
        course_history = await LoungeService.get_course_history(session_id)
        is_host = str(user["id"]) == str(session_data.get("host_id", ""))
        return await render_template(
            "lounge.html",
            user=user,
            lounge_session=session_data,
            standings=standings,
            members=members,
            course_history=course_history,
            view="session",
            is_host=is_host,
        )
    except BridgeUnavailableError:
        return await render_template("maintenance.html"), 503


# ============================================================
# API（Ajax用）
# ============================================================

@lounge_bp.route("/api/sessions", methods=["POST"])
async def api_create_session():
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    session_id = await LoungeService.create_session(
        room_id=data.get("room_id", ""),
        host_id=int(user["id"]),
        mode=data.get("mode", "ffa"),
        total_races=int(data.get("total_races", 12)),
    )
    return jsonify({"status": "ok" if session_id else "error", "session_id": session_id})


@lounge_bp.route("/api/sessions/<int:session_id>/join", methods=["POST"])
async def api_join_session(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    ok = await LoungeService.add_member(session_id, int(user["id"]))
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/races", methods=["POST"])
async def api_create_race(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or str(user["id"]) != str(session_data.get("host_id", "")):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    data = await request.get_json()
    course_name = data.get("course_name", "")
    result = await LoungeService.create_race(session_id, course_name)
    if result:
        return jsonify({"status": "ok", **result})
    return jsonify({"status": "error"}), 500


@lounge_bp.route("/api/races/<int:race_id>/report", methods=["POST"])
async def api_report_score(race_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    position = data.get("position")
    if position is None:
        return jsonify({"status": "error", "message": "position required"}), 400
    ok = await LoungeService.report_score(race_id, int(user["id"]), int(position))
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/races/<int:race_id>/disconnect", methods=["POST"])
async def api_disconnect(race_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    ok = await LoungeService.report_disconnect(race_id, int(user["id"]))
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/races/<int:race_id>/approve", methods=["POST"])
async def api_approve_race(session_id: int, race_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or str(user["id"]) != str(session_data.get("host_id", "")):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    ok = await LoungeService.approve_race(race_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/next-race", methods=["POST"])
async def api_next_race(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or str(user["id"]) != str(session_data.get("host_id", "")):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    ok = await LoungeService.next_race(session_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/finish", methods=["POST"])
async def api_finish_session(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or str(user["id"]) != str(session_data.get("host_id", "")):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403

    ok = await LoungeService.finish_session(session_id)
    if not ok:
        return jsonify({"status": "error"}), 500

    # 全参加者のMMRを確認し、ランク称号を付与 → Discordロール同期
    members = await LoungeService.list_members(session_id)
    for member in members:
        uid = member.get("user_id")
        mmr = member.get("mmr", 0)
        if not uid:
            continue
        newly_granted_ids = await TitleService.grant_rank(uid, mmr)
        for title_id in newly_granted_ids:
            title = await TitleService.get_active(uid)  # 付与されたばかりの称号を取得
            # grant-rank で返るのは title_id のみなので全称号から該当を検索
            all_titles = await TitleService.list_all()
            granted_title = next((t for t in all_titles if t["id"] == title_id), None)
            if granted_title:
                await _ensure_discord_role(granted_title)
                # 装備称号が未設定の場合、自動で最高ランク称号を装備
                if title is None:
                    await TitleService.set_active(uid, title_id)
                await _assign_title_role(str(uid), granted_title)

    return jsonify({"status": "ok"})


@lounge_bp.route("/api/sessions/<int:session_id>/standings")
async def api_standings(session_id: int):
    if not _current_user():
        return jsonify([])
    standings = await LoungeService.get_standings(session_id)
    return jsonify(standings)


@lounge_bp.route("/api/sessions/<int:session_id>/active-race")
async def api_active_race(session_id: int):
    if not _current_user():
        return jsonify({"status": "none"}), 401
    race = await LoungeService.get_active_race(session_id)
    if not race:
        return jsonify({"status": "none"}), 404
    return jsonify(race)


@lounge_bp.route("/api/sessions/<int:session_id>/races/<int:race_id>/scores")
async def api_race_scores(session_id: int, race_id: int):
    if not _current_user():
        return jsonify([]), 401
    scores = await LoungeService.list_race_scores_named(race_id)
    return jsonify(scores)


@lounge_bp.route("/api/sessions/<int:session_id>/races/<int:race_id>/finalize", methods=["POST"])
async def api_finalize_race(session_id: int, race_id: int):
    """承認 + 次のレースへ を一括処理（ホストのみ）"""
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or str(user["id"]) != str(session_data.get("host_id", "")):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    ok1 = await LoungeService.approve_race(race_id)
    if not ok1:
        return jsonify({"status": "error", "message": "承認に失敗しました"}), 500
    ok2 = await LoungeService.next_race(session_id)
    return jsonify({"status": "ok" if ok2 else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/teams", methods=["GET", "POST"])
async def api_teams(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    if request.method == "POST":
        data = await request.get_json()
        team_id = await LoungeService.create_team(
            session_id, data.get("tag", ""), data.get("member_ids", [])
        )
        return jsonify({"status": "ok" if team_id else "error", "team_id": team_id})
    teams = await LoungeService.list_teams(session_id)
    return jsonify(teams)
