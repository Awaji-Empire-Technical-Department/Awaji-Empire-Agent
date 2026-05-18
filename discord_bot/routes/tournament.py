# routes/tournament.py
import os
import httpx
from quart import Blueprint, current_app, render_template, request, session, redirect, url_for, flash, jsonify
from services.tournament_service import TournamentService, TitleService
from services.lobby_service import LobbyService
from services.bridge_client import BridgeUnavailableError

tournament_bp = Blueprint("tournament", __name__, url_prefix="/tournament")

GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

# ランク称号ごとのDiscordロール色（unlock_threshold → color int）
_LOUNGE_RANK_COLORS = {
    0:     0x95A5A6,  # 鉄: グレー
    2000:  0xCD7F32,  # 銅: ブロンズ
    4000:  0xBDC3C7,  # 銀: シルバー
    6000:  0xF1C40F,  # 金: ゴールド
    8000:  0x00BFFF,  # プラチナ: ライトブルー
    10000: 0x1ABC9C,  # ダイヤ: シアン
    13000: 0x9B59B6,  # マスター: パープル
}
_TOURNAMENT_WIN_COLOR = 0xFFD700  # 大会優勝系: ゴールド


def _get_bot_token() -> str:
    try:
        with open("token.txt") as f:
            return f.read().strip()
    except Exception:
        return ""


def _current_user():
    return session.get("discord_user")


def _require_login():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))
    return None


async def _sync_discord_title_role(user_id: str, new_title: dict, old_role_id: str | None):
    """装備称号変更時にDiscordロールを付け替える（旧ロール外し → 新ロール付与）"""
    token = _get_bot_token()
    if not token or not GUILD_ID:
        return
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if old_role_id:
                await client.delete(
                    f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}/roles/{old_role_id}",
                    headers=headers,
                )
            new_role_id = new_title.get("discord_role_id")
            if new_role_id:
                await client.put(
                    f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}/roles/{new_role_id}",
                    headers=headers,
                )
    except Exception as e:
        current_app.logger.warning(f"Discord role sync failed: {e}")


async def _ensure_discord_role(title: dict) -> str | None:
    """称号に紐づくDiscordロールを確保する。
    - discord_role_id が設定済みならそのまま返す
    - 未設定なら新規作成してDBに書き戻してから返す
    """
    role_id = title.get("discord_role_id")
    if role_id:
        return role_id

    token = _get_bot_token()
    if not token or not GUILD_ID:
        return None

    unlock_type = title.get("unlock_type", "manual")
    threshold = title.get("unlock_threshold")

    if unlock_type == "lounge_rank":
        color = _LOUNGE_RANK_COLORS.get(threshold, 0x95A5A6)
    elif unlock_type == "tournament_win":
        color = _TOURNAMENT_WIN_COLOR
    else:
        color = 0x95A5A6

    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles",
                headers=headers,
                json={"name": title["name"], "color": color, "hoist": False, "mentionable": False},
            )
            if res.status_code not in (200, 201):
                current_app.logger.warning(f"Role create failed: {res.status_code} {res.text}")
                return None
            new_role_id = res.json()["id"]

        await TitleService.update_discord_role_id(title["id"], new_role_id)
        current_app.logger.info(f"Created Discord role '{title['name']}' → {new_role_id}")
        return new_role_id
    except Exception as e:
        current_app.logger.warning(f"ensure_discord_role failed: {e}")
        return None


async def _assign_title_role(discord_user_id: str, title: dict):
    """ロールを確保してそのユーザーに付与する（装備称号切替ではなく獲得時の付与）"""
    role_id = await _ensure_discord_role(title)
    if not role_id:
        return
    token = _get_bot_token()
    if not token or not GUILD_ID:
        return
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_user_id}/roles/{role_id}",
                headers=headers,
            )
    except Exception as e:
        current_app.logger.warning(f"assign_title_role failed: {e}")


# ============================================================
# 大会一覧 / 作成
# ============================================================

@tournament_bp.route("/")
async def index():
    redir = _require_login()
    if redir:
        return redir
    user = _current_user()
    try:
        games = await TournamentService.list_game_titles()
        lobbies = await LobbyService.get_active_rooms()
        tournament_lobbies = [l for l in lobbies if l.get("mode") == "tournament"]
        return await render_template(
            "tournament.html",
            user=user,
            games=games,
            lobbies=tournament_lobbies,
        )
    except BridgeUnavailableError:
        return await render_template("maintenance.html"), 503


@tournament_bp.route("/rooms/<passcode>")
async def room_detail(passcode: str):
    redir = _require_login()
    if redir:
        return redir
    user = _current_user()
    try:
        room = await LobbyService.get_room(passcode)
        if not room:
            await flash("大会が見つかりません", "error")
            return redirect(url_for("tournament.index"))
        games = await TournamentService.list_game_titles()
        standings = await TournamentService.get_standings(passcode)
        return await render_template(
            "tournament.html",
            user=user,
            room=room,
            games=games,
            standings=standings,
            view="room",
        )
    except BridgeUnavailableError:
        return await render_template("maintenance.html"), 503


# ============================================================
# スコア申告 API（Ajax用）
# ============================================================

@tournament_bp.route("/api/matches/<int:match_id>/report", methods=["POST"])
async def api_report_score(match_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error", "message": "unauthorized"}), 401
    data = await request.get_json()
    position = data.get("position")
    if position is None:
        return jsonify({"status": "error", "message": "position required"}), 400
    ok = await TournamentService.report_score(match_id, int(user["id"]), int(position))
    return jsonify({"status": "ok" if ok else "error"})


@tournament_bp.route("/api/matches/<int:match_id>/approve", methods=["POST"])
async def api_approve_match(match_id: int):
    user = _current_user()
    if not user:
        return jsonify({"status": "error", "message": "unauthorized"}), 401

    ok = await TournamentService.approve_match(match_id)
    if not ok:
        return jsonify({"status": "error"})

    # winner_id が渡された場合、大会優勝称号を自動付与
    data = await request.get_json(silent=True) or {}
    winner_id = data.get("winner_id")
    if winner_id:
        newly_granted_ids = await TitleService.grant_tournament_win(int(winner_id))
        all_titles = await TitleService.list_all()
        for title_id in newly_granted_ids:
            granted_title = next((t for t in all_titles if t["id"] == title_id), None)
            if granted_title:
                await _ensure_discord_role(granted_title)
                active = await TitleService.get_active(int(winner_id))
                if active is None:
                    await TitleService.set_active(int(winner_id), title_id)
                await _assign_title_role(str(winner_id), granted_title)

    return jsonify({"status": "ok"})


# ============================================================
# 称号管理（dashboard.html から呼び出し）
# ============================================================

@tournament_bp.route("/api/titles")
async def api_list_titles():
    if not _current_user():
        return jsonify([])
    titles = await TitleService.list_all()
    return jsonify(titles)


@tournament_bp.route("/api/titles/save", methods=["POST"])
async def api_save_title():
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    title_id = await TitleService.upsert(
        name=data.get("name", ""),
        description=data.get("description"),
        unlock_type=data.get("unlock_type", "manual"),
        unlock_threshold=data.get("unlock_threshold"),
        discord_role_id=data.get("discord_role_id"),
        display_order=data.get("display_order", 0),
        title_id=data.get("id"),
    )
    return jsonify({"status": "ok" if title_id else "error", "id": title_id})


@tournament_bp.route("/api/titles/<int:title_id>", methods=["DELETE"])
async def api_delete_title(title_id: int):
    if not _current_user():
        return jsonify({"status": "error"}), 401
    ok = await TitleService.delete(title_id)
    return jsonify({"status": "ok" if ok else "error"})


@tournament_bp.route("/api/titles/player/grant", methods=["POST"])
async def api_grant_title():
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    target_user_id = data.get("user_id", int(user["id"]))
    title_id = data.get("title_id")
    if not title_id:
        return jsonify({"status": "error", "message": "title_id required"}), 400
    ok = await TitleService.grant(int(target_user_id), int(title_id))
    return jsonify({"status": "ok" if ok else "error"})


@tournament_bp.route("/api/titles/player/active", methods=["GET"])
async def api_get_active_title():
    user = _current_user()
    if not user:
        return jsonify(None)
    title = await TitleService.get_active(int(user["id"]))
    return jsonify(title)


@tournament_bp.route("/api/titles/player/active", methods=["POST"])
async def api_set_active_title():
    user = _current_user()
    if not user:
        return jsonify({"status": "error"}), 401
    data = await request.get_json()
    title_id = data.get("title_id")
    if not title_id:
        return jsonify({"status": "error", "message": "title_id required"}), 400

    # 現在の装備称号のロールIDを取得してから切り替え
    old_title = await TitleService.get_active(int(user["id"]))
    old_role_id = old_title.get("discord_role_id") if old_title else None

    ok = await TitleService.set_active(int(user["id"]), int(title_id))
    if ok:
        new_title = await TitleService.get_active(int(user["id"]))
        if new_title:
            await _sync_discord_title_role(user["id"], new_title, old_role_id)
    return jsonify({"status": "ok" if ok else "error"})


@tournament_bp.route("/api/titles/player/list")
async def api_player_title_list():
    user = _current_user()
    if not user:
        return jsonify([])
    titles = await TitleService.get_player_titles(int(user["id"]))
    return jsonify(titles)
