# routes/lobby.py
import csv
import io
import time
from quart import Blueprint, current_app, redirect, render_template, request, session, url_for, flash, make_response
from services.lobby_service import LobbyService
from services.bridge_client import BridgeUnavailableError

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
            await flash("大会結果を最終承認しました。Discordでロールが付与されます。", "success")
            # --- 実際にはここで Bot (Cog) にリクエストを送ってロールを付与する等の連携を行う ---
        else:
            await flash("最終承認に失敗しました", "error")
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
