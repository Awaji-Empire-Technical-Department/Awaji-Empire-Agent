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

    // WebSocketでリアルタイム更新
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

    async function refreshStandings() {
        if (!passcode) return;
        const res = await fetch(`/tournament/rooms/${passcode}/standings`);
        // DOMの更新は省略（ページリロードで対応）
    }
})();
