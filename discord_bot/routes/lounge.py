# routes/lounge.py
from quart import Blueprint, current_app, render_template, request, session, redirect, url_for, jsonify
from services.lounge_service import LoungeService
from services.bridge_client import BridgeUnavailableError

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
    return await render_template("lounge.html", user=user, view="list")


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
        return await render_template(
            "lounge.html",
            user=user,
            session=session_data,
            standings=standings,
            members=members,
            course_history=course_history,
            view="session",
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


@lounge_bp.route("/api/races/<int:race_id>/approve", methods=["POST"])
async def api_approve_race(race_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    ok = await LoungeService.approve_race(race_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/next-race", methods=["POST"])
async def api_next_race(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    ok = await LoungeService.next_race(session_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/finish", methods=["POST"])
async def api_finish_session(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    ok = await LoungeService.finish_session(session_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/standings")
async def api_standings(session_id: int):
    if not _current_user():
        return jsonify([])
    standings = await LoungeService.get_standings(session_id)
    return jsonify(standings)


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
