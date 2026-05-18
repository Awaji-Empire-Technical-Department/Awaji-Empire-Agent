// static/js/lounge.js
(function () {
    'use strict';

    if (SESSION_ID === null) {
        // 一覧ビュー
        const btnCreate = document.getElementById('btn-create-session');
        const form = document.getElementById('create-session-form');
        btnCreate?.addEventListener('click', () => {
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
        });

        document.getElementById('btn-submit-session')?.addEventListener('click', async () => {
            const mode = document.getElementById('new-session-mode').value;
            const races = parseInt(document.getElementById('new-session-races').value);
            const room = document.getElementById('new-session-room').value.trim();
            if (!room) { alert('ルームIDを入力してください'); return; }

            const res = await fetch('/lounge/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_id: room, mode, total_races: races }),
            });
            const data = await res.json();
            if (data.status === 'ok' && data.session_id) {
                location.href = `/lounge/sessions/${data.session_id}`;
            } else {
                alert('セッションの作成に失敗しました');
            }
        });
        return;
    }

    // ============ セッション進行ビュー ============

    // 参加登録
    fetch(`/lounge/api/sessions/${SESSION_ID}/join`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });

    // 順位申告
    document.getElementById('btn-report')?.addEventListener('click', async () => {
        if (!currentRaceId) { alert('現在進行中のレースがありません'); return; }
        const position = parseInt(document.getElementById('report-position').value);
        const res = await fetch(`/lounge/api/races/${currentRaceId}/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ position }),
        });
        const data = await res.json();
        alert(data.status === 'ok' ? '申告しました！' : '申告に失敗しました');
    });

    // 回線落ち報告
    document.getElementById('btn-disconnect')?.addEventListener('click', async () => {
        if (!currentRaceId) { alert('現在進行中のレースがありません'); return; }
        if (!confirm('回線落ちを報告しますか？')) return;
        await fetch(`/lounge/api/races/${currentRaceId}/disconnect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
    });

    // レース開始（Staff）
    document.getElementById('btn-new-race')?.addEventListener('click', async () => {
        const course = document.getElementById('course-name-input').value.trim();
        if (!course) { alert('コース名を入力してください'); return; }
        const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/races`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course_name: course }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            currentRaceId = data.race_id;
            document.getElementById('course-name-input').value = '';
            if (data.duplicate_course) {
                alert(`⚠️ 「${course}」は既にこのセッションで使用されたコースです！`);
            }
        } else {
            alert('レース開始に失敗しました');
        }
    });

    // レース承認（Staff）
    document.getElementById('btn-approve-race')?.addEventListener('click', async () => {
        if (!currentRaceId) { alert('承認するレースがありません'); return; }
        if (!confirm('このレースの結果を承認しますか？')) return;
        await fetch(`/lounge/api/races/${currentRaceId}/approve`, { method: 'POST' });
        await refreshStandings();
        currentRaceId = null;
    });

    // 次レースへ（Staff）
    document.getElementById('btn-next-race')?.addEventListener('click', async () => {
        await fetch(`/lounge/api/sessions/${SESSION_ID}/next-race`, { method: 'POST' });
        location.reload();
    });

    // セッション終了（Staff）
    document.getElementById('btn-finish-session')?.addEventListener('click', async () => {
        if (!confirm('セッションを終了しますか？')) return;
        await fetch(`/lounge/api/sessions/${SESSION_ID}/finish`, { method: 'POST' });
        location.reload();
    });

    // ランキング更新
    document.getElementById('btn-refresh-standings')?.addEventListener('click', refreshStandings);

    async function refreshStandings() {
        const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/standings`);
        const standings = await res.json();
        const tbody = document.getElementById('standings-tbody');
        if (!standings.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--gray);">まだ結果がありません</td></tr>';
            return;
        }
        tbody.innerHTML = standings.map((s, i) => `
            <tr class="${i === 0 ? 'standings-first' : ''}">
                <td>${i + 1}</td>
                <td>${s.username || s.user_id}</td>
                <td><strong>${s.total_points || 0}</strong></td>
                <td style="color:var(--gray);">${s.first_place_count || 0}</td>
            </tr>
        `).join('');
    }

    // WebSocketでリアルタイム更新
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);
    ws.addEventListener('message', (e) => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.session_id !== SESSION_ID) return;
            if (msg.type === 'lounge.race_approved') {
                refreshStandings();
            } else if (msg.type === 'lounge.race_created') {
                currentRaceId = msg.race_id;
                document.getElementById('current-race').textContent = msg.race_number;
                if (msg.duplicate_course) {
                    alert(`⚠️ コース重複: 「${msg.course_name}」は既に使用済みです！`);
                }
            } else if (msg.type === 'lounge.session_finished') {
                alert('セッションが終了しました');
                location.reload();
            }
        } catch (_) {}
    });
})();
