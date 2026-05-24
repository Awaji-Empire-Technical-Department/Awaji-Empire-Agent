// static/js/tournament.js
(function () {
    'use strict';

    const reportPanel = document.getElementById('report-panel');
    if (!reportPanel) return;

    const passcode = reportPanel.dataset.passcode;

    document.getElementById('btn-report-score')?.addEventListener('click', async () => {
        const matchId = document.getElementById('report-match-id').value;
        const position = parseInt(document.getElementById('report-position').value);
        if (!matchId) { alert('試合を選択してください'); return; }

        const res = await fetch(`/tournament/api/matches/${matchId}/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ position }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            alert('申告しました。Staffの承認をお待ちください。');
        } else {
            alert('申告に失敗しました');
        }
    });

    // ============================================================
    // 順位表DOM更新
    // ============================================================

    async function refreshStandings() {
        if (!passcode) return;
        try {
            const res = await fetch(`/tournament/api/rooms/${passcode}/standings`);
            if (!res.ok) return;
            const standings = await res.json();
            const tbody = document.getElementById('standings-tbody');
            if (!tbody) return;

            if (!standings.length) {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:2rem;color:var(--gray);">まだ結果がありません</td></tr>';
                return;
            }
            tbody.innerHTML = standings.map((s, i) => {
                const name = s.username || s.user_id;
                const pts  = s.total_points ?? 0;
                return `<tr class="${i === 0 ? 'standings-first' : ''}">
                    <td>${i + 1}位</td>
                    <td>${name}</td>
                    <td>${pts}pt</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.warn('refreshStandings error:', err);
        }
    }

    // ============================================================
    // WebSocket（リアルタイム） + 常時ポーリング（5秒）
    // ============================================================

    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);

    ws.addEventListener('message', (e) => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'match.approved') {
                refreshStandings();
            }
        } catch (_) {}
    });

    // 初期ロード
    refreshStandings();
    // 常時ポーリング（WS並走）
    setInterval(refreshStandings, 5000);
})();
