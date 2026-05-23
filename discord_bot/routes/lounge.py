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


def _is_host(user, session_data) -> bool:
    return str(user["id"]) == str(session_data.get("host_id", ""))


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
        final_scores = await LoungeService.get_final_scores(session_id)
        members = await LoungeService.list_members(session_id)
        is_host = _is_host(user, session_data)
        return await render_template(
            "lounge.html",
            user=user,
            lounge_session=session_data,
            final_scores=final_scores,
            members=members,
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


@lounge_bp.route("/api/sessions/<int:session_id>/final-scores/report", methods=["POST"])
async def api_report_final_score(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    final_rank = data.get("final_rank")
    if final_rank is None or not (1 <= int(final_rank) <= 24):
        return jsonify({"status": "error", "message": "final_rank は 1〜24 で指定してください"}), 400
    ok = await LoungeService.report_final_score(session_id, int(user["id"]), int(final_rank))
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/final-scores")
async def api_get_final_scores(session_id: int):
    if not _current_user():
        return jsonify([]), 401
    scores = await LoungeService.get_final_scores(session_id)
    return jsonify(scores)


@lounge_bp.route("/api/sessions/<int:session_id>/exclude", methods=["POST"])
async def api_exclude_player(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or not _is_host(user, session_data):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    data = await request.get_json()
    excluded = await LoungeService.exclude_player(session_id, int(data.get("user_id")))
    if excluded is None:
        return jsonify({"status": "error"}), 500
    return jsonify({"status": "ok", "excluded": excluded})


async def _do_finish_session(session_id: int):
    """セッション終了フロー（MMR計算 + 称号付与 + Discordロール同期）。"""
    res = await LoungeService.finish_session(session_id)
    if not res or res.get("status") != "ok":
        return False

    # Bridge が MMR 計算済みの結果を返す
    results = res.get("results", [])
    all_titles = await TitleService.list_all()

    for entry in results:
        uid = entry.get("user_id")
        new_mmr = entry.get("new_mmr", 0)
        if not uid:
            continue
        newly_granted_ids = await TitleService.grant_rank(uid, new_mmr)
        for title_id in newly_granted_ids:
            active = await TitleService.get_active(uid)
            granted_title = next((t for t in all_titles if t["id"] == title_id), None)
            if granted_title:
                await _ensure_discord_role(granted_title)
                if active is None:
                    await TitleService.set_active(uid, title_id)
                await _assign_title_role(str(uid), granted_title)
    return True


@lounge_bp.route("/api/sessions/<int:session_id>/finish", methods=["POST"])
async def api_finish_session(session_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    session_data = await LoungeService.get_session(session_id)
    if not session_data or not _is_host(user, session_data):
        return jsonify({"status": "error", "message": "ホストのみ操作できます"}), 403
    ok = await _do_finish_session(session_id)
    return jsonify({"status": "ok" if ok else "error"})


@lounge_bp.route("/api/sessions/<int:session_id>/my-result")
async def api_my_result(session_id: int):
    """セッション終了後の個人結果（最終順位・MMR増加・現在MMR・称号）を返す。"""
    user = _current_user()
    if not user:
        return jsonify({}), 401
    uid_str = str(user["id"])

    final_scores = await LoungeService.get_final_scores(session_id)
    my_entry = next((s for s in final_scores if str(s.get("user_id")) == uid_str), None)

    final_rank = my_entry.get("final_rank") if my_entry else None
    mmr_delta = my_entry.get("mmr_delta", 0) if my_entry else 0
    total_submitted = sum(1 for s in final_scores if s.get("submitted"))

    player = await LoungeService.get_player(int(user["id"]))
    current_mmr = player.get("mmr", 1000) if player else 1000

    all_titles = await TitleService.list_all()
    player_titles = await TitleService.get_player_titles(int(user["id"]))
    earned_ids = {t["id"] for t in player_titles if t.get("earned")}
    active_title_name = None
    for t in sorted(all_titles, key=lambda x: x.get("unlock_threshold") or 0, reverse=True):
        if t["id"] in earned_ids and t.get("unlock_type") == "lounge_rank":
            active_title_name = t["name"]
            break

    return jsonify({
        "final_rank":      final_rank,
        "total_players":   total_submitted,
        "mmr_delta":       mmr_delta,
        "mmr":             current_mmr,
        "rank_name":       active_title_name or "—",
        "is_winner":       final_rank == 1,
    })


@lounge_bp.route("/api/sessions/<int:session_id>/standings")
async def api_standings(session_id: int):
    if not _current_user():
        return jsonify([])
    standings = await LoungeService.get_standings(session_id)
    return jsonify(standings)


@lounge_bp.route("/api/me")
async def api_me():
    """ログインユーザーの MMR とランク称号を返す。"""
    user = _current_user()
    if not user:
        return jsonify({}), 401
    uid = int(user["id"])
    player = await LoungeService.get_player(uid)
    titles = await TitleService.get_player_titles(uid)
    rank_title = None
    for t in sorted(titles, key=lambda x: x.get("unlock_threshold") or 0, reverse=True):
        if t.get("unlock_type") == "lounge_rank" and t.get("earned"):
            rank_title = t.get("name")
            break
    mmr = player.get("mmr", 1000) if player else 1000
    return jsonify({"mmr": mmr, "rank_name": rank_title or "—"})


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
