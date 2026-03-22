import csv
import io
import time
import httpx
import os
from quart import Blueprint, current_app, redirect, render_template, request, session, url_for, flash, make_response, jsonify
from services.lobby_service import LobbyService
from services.bridge_client import BridgeUnavailableError

def get_bot_token():
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except Exception:
        return None

async def assign_winner_role_via_api(user_id: str, tournament_name: str, guild_id: str):
    token = get_bot_token()
    if not token or not guild_id: return False
    
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    
    role_name = f"{tournament_name} 優勝"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Fetch roles
            res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers)
            if res.status_code != 200: return False
            roles = res.json()
            
            target_role_id = None
            for r in roles:
                if r["name"] == role_name:
                    target_role_id = r["id"]
                    break
                    
            # 2. Create role if not exists
            if not target_role_id:
                payload = {
                    "name": role_name, 
                    "color": 0xFFD700, 
                    "hoist": True 
                }
                res = await client.post(f"https://discord.com/api/v10/guilds/{guild_id}/roles", json=payload, headers=headers)
                if res.status_code in (200, 201):
                    target_role_id = res.json()["id"]
                else:
                    return False
                    
            # 3. Assign role
            res = await client.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{target_role_id}", headers=headers)
            return res.status_code == 204
    except Exception as e:
        current_app.logger.error(f"Failed to assign role via REST API: {e}")
        return False

lobby_bp = Blueprint('lobby', __name__, url_prefix='/lobby')

@lobby_bp.route('/create', methods=['POST'])
async def create_lobby():
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    form = await request.form
    passcode = form.get('passcode')
    mode = form.get('mode', 'free') # 'free' or 'tournament'
    title = form.get('title', '新対戦ロビー')
    description = form.get('description', '').strip() or None

    if not passcode:
        await flash("合言葉は必須です", "error")
        return redirect(url_for('index'))

    try:
        success = await LobbyService.create_room(passcode, int(user['id']), mode, title, description)
        if success:
            await flash(f"ロビー「{title}」を作成しました", "success")
            return redirect(url_for('lobby.view_lobby', passcode=passcode))
        else:
            await flash("ロビーの作成に失敗しました。合言葉が既に使用されている可能性があります。", "error")
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503
    except Exception as e:
        current_app.logger.error(f"Lobby create error: {e}")
        await flash("システムエラーが発生しました", "error")

    return redirect(url_for('index'))

@lobby_bp.route('/<passcode>')
async def view_lobby(passcode):
    user = session.get('discord_user')
    if not user:
        session['next_url'] = request.url
        return redirect(url_for('login'))

    try:
        room = await LobbyService.get_room(passcode)
        if not room:
            await flash("指定されたロビーは存在しないか、期限切れです", "error")
            return redirect(url_for('index'))

        members = await LobbyService.get_members(passcode)
        # 現在のユーザーがどのロールで参加しているかを判定
        my_role = None
        for m in members:
            if str(m.get('user_id')) == str(user['id']):
                my_role = m.get('role')
                break
                
        is_host = str(room.get('host_id')) == str(user['id'])

        return await render_template(
            'lobby.html', 
            user=user, 
            room=room, 
            members=members, 
            my_role=my_role,
            is_host=is_host
        )
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

@lobby_bp.route('/<passcode>/join', methods=['POST'])
async def join_lobby(passcode):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    form = await request.form
    
    # checkbox の場合は on が来る、チェックがなければキー自体が存在しない
    is_player = form.get('role_player') == 'on'
    is_staff = form.get('role_staff') == 'on'

    role = 'player'
    if is_staff and not is_player:
        role = 'staff'
    # 両方ON、またはデフォはとりあえず 'player' 扱いとし、
    # 'staff'の複数ロール持ちは本仕様では 'staff' を優先するか 'player'＋フラグとするが
    # ここではシンプルに staff が true なら staff テーブルまたは DB スキーマに合わせて処理
    # (要求仕様に従い、現状のDBでは ENUM('player', 'staff') なので、staff指定があれば staff にする)
    if is_staff:
        role = 'staff'

    try:
        success = await LobbyService.join_lobby(passcode, int(user['id']), role)
        if success:
            await flash("ロビーに参加しました", "success")
        else:
            await flash("ロビーの参加に失敗しました", "error")
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

    return redirect(url_for('lobby.view_lobby', passcode=passcode))

@lobby_bp.route('/<passcode>/transfer', methods=['POST'])
async def transfer_host(passcode):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    form = await request.form
    new_host_id = form.get('new_host_id')

    try:
        room = await LobbyService.get_room(passcode)
        if not room or str(room.get('host_id')) != str(user['id']):
            await flash("ホスト権限譲渡の権限がありません", "error")
            return redirect(url_for('lobby.view_lobby', passcode=passcode))

        if new_host_id:
            success = await LobbyService.update_room(passcode, new_host_id=int(new_host_id))
            if success:
                await flash("ホスト権限を譲渡しました", "success")
            else:
                await flash("ホスト権限の譲渡に失敗しました", "error")
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

    return redirect(url_for('lobby.view_lobby', passcode=passcode))

@lobby_bp.route('/<passcode>/approve', methods=['POST'])
async def approve_winner(passcode):
    # トーナメントの最終承認（仮実装）
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))
        
    try:
        room = await LobbyService.get_room(passcode)
        if not room or str(room.get('host_id')) != str(user['id']):
            await flash("承認権限がありません", "error")
            return redirect(url_for('lobby.view_lobby', passcode=passcode))
            
        success = await LobbyService.update_room(passcode, is_approved=True)
        if success:
            guild_id = os.getenv('DISCORD_GUILD_ID')
            title = room.get('title', '新対戦ロビー')
            
            # Since the backend doesn't yet explicitly compute the winner here,
            # this assumes the logic for fetching winner_id exists or will exist soon.
            # For now, if the API starts returning a specific tournament winner from the match tree,
            # we'd use it. Since the DB matches handle winner_id, ideally we fetch the final match winner.
            # Since this is a simple implementation, if we can't get the winner right away, we just flash success.
            # In a full tournament flow, the room data should contain the known final winner.
            
            # To simulate, if LobbyService provides a get_tournament_winner
            winner_id = None
            try:
                matches = await LobbyService._fetch_tournament_matches(passcode) # Using internal logic
                # For Bracketry format, finding the final match
                # Let's say if it exists, grab winner_id
                if matches and len(matches) > 0:
                    final_match = sorted(matches, key=lambda m: m.get('round_num', 0))[-1]
                    winner_id = final_match.get('winner_id')
            except Exception:
                pass

            if winner_id and guild_id:
                role_assigned = await assign_winner_role_via_api(str(winner_id), title, guild_id)
                if role_assigned:
                    await flash("大会結果を最終承認しました。Discordで優勝ロールが付与されました！", "success")
                else:
                    await flash("大会結果を承認しましたが、Discordロールの付与に失敗しました。", "warning")
            else:
                await flash("大会結果を承認しました。（優勝者が未確定かGuildID未設定のためロール付与はスキップしました）", "success")
        else:
            await flash("最終承認に失敗しました", "error")
    except BridgeUnavailableError:
         return await render_template('maintenance.html'), 503
         
    return redirect(url_for('lobby.view_lobby', passcode=passcode))

@lobby_bp.route('/api/status', methods=['POST'])
async def update_my_status():
    """フロントエンドのJSから自分のステータスを更新するAPI"""
    user = session.get('discord_user')
    if not user:
        return jsonify({"status": "error", "message": "unauthorized"}), 401
    
    data = await request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "bad request"}), 400
        
    passcode = data.get('passcode')
    status = data.get('status')
    
    if not passcode or not status:
        return jsonify({"status": "error", "message": "missing params"}), 400
        
    try:
        success = await LobbyService.update_member_status(passcode, int(user['id']), status)
        if success:
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "failed to update"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@lobby_bp.route('/<passcode>/start', methods=['POST'])
async def start_tournament(passcode):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))
        
    try:
        room = await LobbyService.get_room(passcode)
        if not room or str(room.get('host_id')) != str(user['id']):
            await flash("大会開始の権限がありません", "error")
            return redirect(url_for('lobby.view_lobby', passcode=passcode))
            
        success = await LobbyService.start_tournament(passcode)
        if success:
            await flash("大会を開始しました！", "success")
        else:
            await flash("大会の開始に失敗しました", "error")
    except BridgeUnavailableError:
         return await render_template('maintenance.html'), 503
         
    return redirect(url_for('lobby.view_lobby', passcode=passcode))

@lobby_bp.route('/<passcode>/export_csv')
async def export_csv(passcode):
    # 大会結果CSVエクスポート（モック実装: 実運用には試合情報が含まれる）
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))
        
    try:
        room = await LobbyService.get_room(passcode)
        if not room:
            return "Room not found", 404
            
        is_staff = False
        members = await LobbyService.get_members(passcode)
        for m in members:
            if str(m.get('user_id')) == str(user['id']) and m.get('role') == 'staff':
                is_staff = True
                break
                
        is_host = str(room.get('host_id')) == str(user['id'])
        
        if not (is_host or is_staff):
            return "Forbidden: Requires Host or Staff privileges", 403

        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(['パスコード', 'ユーザーID', 'ロール'])
        for m in members:
            writer.writerow([passcode, m.get('user_id'), m.get('role')])
            
        output = await make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=lobby_{passcode}_export.csv"
        output.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
        return output
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

@lobby_bp.route('/<passcode>/delete', methods=['POST'])
async def delete_lobby(passcode):
    user = session.get('discord_user')
    if not user:
        return redirect(url_for('login'))

    try:
        room = await LobbyService.get_room(passcode)
        if not room or str(room.get('host_id')) != str(user['id']):
            await flash("ロビー削除の権限がありません", "error")
            return redirect(url_for('lobby.view_lobby', passcode=passcode))

        success = await LobbyService.delete_room(passcode)
        if success:
            await flash("ロビーを削除しました", "success")
        else:
            await flash("ロビーの削除に失敗しました", "error")
    except BridgeUnavailableError:
        return await render_template('maintenance.html'), 503

    return redirect(url_for('index'))
