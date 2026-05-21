// static/js/lounge.js
(function () {
    'use strict';

    if (SESSION_ID === null) {
        // ============ 一覧ビュー ============
        const btnCreate = document.getElementById('btn-create-session');
        const form = document.getElementById('create-session-form');
        btnCreate?.addEventListener('click', () => {
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
        });

        const roomInput = document.getElementById('new-session-room');
        roomInput?.addEventListener('input', () => {
            roomInput.value = roomInput.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
        });

        document.getElementById('btn-submit-session')?.addEventListener('click', async () => {
            const mode = document.getElementById('new-session-mode').value;
            const races = parseInt(document.getElementById('new-session-races').value);
            const room = roomInput.value.trim().toUpperCase();
            if (!room) { alert('ルームIDを入力してください'); return; }
            if (!/^[A-Z0-9]{6}$/.test(room)) { alert('ルームIDは6桁の英数字で入力してください（例: ABC123）'); return; }

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

    // 参加登録（重複はDBがINSERT IGNOREで吸収）
    fetch(`/lounge/api/sessions/${SESSION_ID}/join`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });

    // --- モーダル制御 ---
    const overlay = document.getElementById('race-modal-overlay');
    const modalCourseName = document.getElementById('modal-course-name');
    const modalRaceNum = document.getElementById('modal-race-num');
    const modalSubmissionList = document.getElementById('modal-submission-list');
    const modalSubmittedCount = document.getElementById('modal-submitted-count');
    const modalMySubmitted = document.getElementById('modal-my-submitted');

    // 提出状況: user_id -> {submitted: bool, position: int|null, is_disconnect: bool}
    let submissionState = {};

    function openModal(raceId, courseName, raceNumber) {
        currentRaceId = raceId;
        modalCourseName.textContent = courseName;
        modalRaceNum.textContent = `第 ${raceNumber} レース`;
        overlay.style.display = 'flex';
        // 自分の申告フォームをリセット
        const reportSection = document.getElementById('modal-report-section');
        if (reportSection) {
            document.getElementById('modal-report-position').value = '1';
            modalMySubmitted.style.display = 'none';
            document.getElementById('modal-btn-report').disabled = false;
            document.getElementById('modal-btn-disconnect').disabled = false;
        }
        // 提出状況をロード
        submissionState = {};
        loadSubmissions(raceId);
    }

    function closeModal() {
        overlay.style.display = 'none';
        currentRaceId = null;
        submissionState = {};
    }

    async function loadSubmissions(raceId) {
        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/races/${raceId}/scores`);
            if (!res.ok) return;
            const scores = await res.json();
            scores.forEach(s => {
                submissionState[String(s.user_id)] = {
                    submitted: true,
                    position: s.position,
                    is_disconnect: s.is_disconnect,
                };
            });
            renderSubmissions();
        } catch (_) {}
    }

    function renderSubmissions() {
        const memberIds = Object.keys(MEMBERS);
        const submittedIds = Object.keys(submissionState).filter(id => submissionState[id].submitted);
        const total = memberIds.length;
        const done = submittedIds.length;

        modalSubmittedCount.textContent = `${done} / ${total} 人提出済み`;

        // 自分が提出済みか
        if (submissionState[MY_USER_ID]?.submitted) {
            modalMySubmitted.style.display = 'block';
            const btn = document.getElementById('modal-btn-report');
            if (btn) btn.disabled = true;
            const dc = document.getElementById('modal-btn-disconnect');
            if (dc) dc.disabled = true;
        }

        // 提出一覧
        const allIds = [...new Set([...memberIds, ...submittedIds])];
        modalSubmissionList.innerHTML = allIds.map(uid => {
            const name = MEMBERS[uid] || uid;
            const s = submissionState[uid];
            if (s?.submitted) {
                const label = s.is_disconnect
                    ? '<span style="color:#dc3545;">回線落ち</span>'
                    : `<strong>${s.position}位</strong>`;
                return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:#f0fdf4;border-radius:4px;font-size:.88rem;">
                    <span><i class="fas fa-check" style="color:#28a745;margin-right:6px;"></i>${name}</span>
                    <span>${label}</span>
                </div>`;
            } else {
                return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:#fafafa;border-radius:4px;font-size:.88rem;color:var(--gray);">
                    <span><i class="fas fa-hourglass-half" style="margin-right:6px;"></i>${name}</span>
                    <span>未提出</span>
                </div>`;
            }
        }).join('');
    }

    // モーダル内申告
    document.getElementById('modal-btn-report')?.addEventListener('click', async () => {
        if (!currentRaceId) return;
        const position = parseInt(document.getElementById('modal-report-position').value);
        const res = await fetch(`/lounge/api/races/${currentRaceId}/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ position }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            submissionState[MY_USER_ID] = { submitted: true, position, is_disconnect: false };
            renderSubmissions();
        } else {
            alert('申告に失敗しました');
        }
    });

    document.getElementById('modal-btn-disconnect')?.addEventListener('click', async () => {
        if (!currentRaceId) return;
        if (!confirm('回線落ちを報告しますか？')) return;
        const res = await fetch(`/lounge/api/races/${currentRaceId}/disconnect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        if (data.status === 'ok') {
            submissionState[MY_USER_ID] = { submitted: true, position: null, is_disconnect: true };
            renderSubmissions();
        }
    });

    // ホスト: 結果確定・次のレースへ
    document.getElementById('modal-btn-finalize')?.addEventListener('click', async () => {
        if (!currentRaceId) return;
        const memberCount = Object.keys(MEMBERS).length;
        const submittedCount = Object.values(submissionState).filter(s => s.submitted).length;
        if (submittedCount < memberCount) {
            const proceed = confirm(`まだ ${memberCount - submittedCount} 人が未提出です。それでも確定しますか？`);
            if (!proceed) return;
        }
        const btn = document.getElementById('modal-btn-finalize');
        btn.disabled = true;
        btn.textContent = '処理中...';
        const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/races/${currentRaceId}/finalize`, {
            method: 'POST',
        });
        const data = await res.json();
        if (data.status !== 'ok') {
            alert('確定に失敗しました');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-check-double"></i> 結果確定・次のレースへ';
        }
        // 成功時はWS lounge.race_advanced でモーダルが閉じる
    });

    // レース開始（ホストのみ）
    document.getElementById('btn-new-race')?.addEventListener('click', async () => {
        const course = document.getElementById('course-name-input').value.trim();
        if (!course) { alert('コース名を入力してください'); return; }
        const btn = document.getElementById('btn-new-race');
        btn.disabled = true;
        const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/races`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course_name: course }),
        });
        const data = await res.json();
        btn.disabled = false;
        if (data.status === 'ok') {
            document.getElementById('course-name-input').value = '';
            // WSイベントでモーダルが開く（ホスト自身も受信する）
            if (data.duplicate_course) {
                alert(`⚠️ 「${course}」は既にこのセッションで使用されたコースです！`);
            }
        } else {
            alert('レース開始に失敗しました');
        }
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

    // ページロード時: 進行中のレースがあればモーダルを復元
    (async () => {
        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/active-race`);
            if (res.ok) {
                const race = await res.json();
                if (race.race_id) {
                    openModal(race.race_id, race.course_name, race.race_number);
                }
            }
        } catch (_) {}
    })();

    // --- セッション終了・MMR結果モーダル ---
    async function showResultModal() {
        const overlay = document.getElementById('result-modal-overlay');
        if (!overlay) { location.href = '/'; return; }
        overlay.style.display = 'flex';
        try {
            const res = await fetch('/lounge/api/me');
            if (res.ok) {
                const data = await res.json();
                document.getElementById('result-mmr').textContent = `${data.mmr} MMR`;
                document.getElementById('result-rank').textContent = data.rank_name || '—';
            }
        } catch (_) {}
        document.getElementById('result-btn-dashboard')?.addEventListener('click', () => {
            location.href = '/';
        });
        // 15秒後に自動リダイレクト
        setTimeout(() => { location.href = '/'; }, 15000);
    }

    // セッション終了ボタン（ホストが手動終了する場合も結果モーダルを表示）
    document.getElementById('btn-finish-session')?.addEventListener('click', async () => {
        if (!confirm('セッションを終了しますか？')) return;
        await fetch(`/lounge/api/sessions/${SESSION_ID}/finish`, { method: 'POST' });
        // WSイベント lounge.session_finished でモーダルが開く
    });

    // WebSocket リアルタイム更新
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);
    ws.addEventListener('message', (e) => {
        try {
            const msg = JSON.parse(e.data);

            if (msg.type === 'lounge.race_created' && msg.session_id === SESSION_ID) {
                openModal(msg.race_id, msg.course_name, msg.race_number);
                if (msg.duplicate_course) {
                    alert(`⚠️ コース重複: 「${msg.course_name}」は既に使用済みです！`);
                }
            }

            if (msg.type === 'lounge.score_reported' && msg.race_id === currentRaceId) {
                const uid = String(msg.user_id);
                if (!submissionState[uid]?.submitted) {
                    // 位置情報はWS経由では届かないのでAPIで補完
                    loadSubmissions(currentRaceId);
                }
            }

            if (msg.type === 'lounge.disconnect_reported' && msg.race_id === currentRaceId) {
                loadSubmissions(currentRaceId);
            }

            if (msg.type === 'lounge.race_advanced' && msg.session_id === SESSION_ID) {
                closeModal();
                refreshStandings();
                const el = document.getElementById('current-race');
                if (el) el.textContent = parseInt(el.textContent) + 1;
            }

            if (msg.type === 'lounge.race_approved' && currentRaceId) {
                refreshStandings();
            }

            if (msg.type === 'lounge.session_finished' && msg.session_id === SESSION_ID) {
                closeModal();
                showResultModal();
            }
        } catch (_) {}
    });
})();
