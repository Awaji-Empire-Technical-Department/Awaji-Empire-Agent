// static/js/lounge.js
(function () {
    'use strict';

    // ============================================================
    // 一覧ビュー
    // ============================================================
    if (SESSION_ID === null) {
        const btnCreate = document.getElementById('btn-create-session');
        const form = document.getElementById('create-session-form');
        if (btnCreate && form) {
            btnCreate.addEventListener('click', () => {
                form.style.display = form.style.display === 'none' ? 'block' : 'none';
            });
        }

        const roomInput = document.getElementById('new-session-room');
        if (roomInput) {
            roomInput.addEventListener('input', () => {
                roomInput.value = roomInput.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            });
        }

        const btnSubmit = document.getElementById('btn-submit-session');
        if (btnSubmit) {
            btnSubmit.addEventListener('click', async () => {
                const mode  = document.getElementById('new-session-mode').value;
                const races = parseInt(document.getElementById('new-session-races').value);
                const room  = (roomInput ? roomInput.value : '').trim().toUpperCase();
                if (!room) { alert('ルームIDを入力してください'); return; }
                if (!/^[A-Z0-9]{6}$/.test(room)) { alert('ルームIDは6桁の英数字で入力してください（例: ABC123）'); return; }
                const res  = await fetch('/lounge/api/sessions', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ room_id: room, mode, total_races: races }),
                });
                const data = await res.json();
                if (data.status === 'ok' && data.session_id) {
                    location.href = `/lounge/sessions/${data.session_id}`;
                } else {
                    alert('セッションの作成に失敗しました');
                }
            });
        }
        return;
    }

    // ============================================================
    // セッション進行ビュー
    // ============================================================

    // 参加登録（ページロード時に自動参加）
    fetch(`/lounge/api/sessions/${SESSION_ID}/join`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
    }).catch(() => {});

    // 申告状況キャッシュ: { [user_id]: { submitted, final_rank, excluded } }
    let scoreState = {};

    function $id(id) { return document.getElementById(id); }

    // ============================================================
    // 最終順位申告モーダル
    // ============================================================

    function openFinalReportModal() {
        const overlay = $id('final-report-modal-overlay');
        if (overlay) overlay.style.display = 'flex';
        loadFinalScores();
    }

    function closeFinalReportModal() {
        const overlay = $id('final-report-modal-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    async function loadFinalScores() {
        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/final-scores`);
            if (!res.ok) return;
            const scores = await res.json();
            scores.forEach(s => {
                scoreState[String(s.user_id)] = {
                    submitted: s.submitted,
                    final_rank: s.final_rank,
                    excluded: s.excluded,
                };
            });
            renderFinalScores();
            refreshStandingsTable(scores);
        } catch (err) {
            console.warn('loadFinalScores error:', err);
        }
    }

    function renderFinalScores() {
        const countEl = $id('final-submitted-count');
        const listEl  = $id('final-submission-list');
        if (!countEl || !listEl) return;

        const allIds       = Object.keys(MEMBERS);
        const submittedIds = allIds.filter(id => scoreState[id] && scoreState[id].submitted);
        const total  = allIds.length;
        const done   = submittedIds.length;
        countEl.textContent = `${done} / ${total} 人提出済み`;

        // 自分が申告済みならボタンを無効化
        const myState = scoreState[MY_USER_ID];
        if (myState && myState.submitted) {
            const submitted = $id('final-my-submitted');
            const btn = $id('btn-submit-final-rank');
            if (submitted) submitted.style.display = 'block';
            if (btn) btn.disabled = true;
        }

        listEl.innerHTML = allIds.map(uid => {
            const name  = MEMBERS[uid] || ('ID:' + uid);
            const state = scoreState[uid] || {};
            const isExcluded = state.excluded;
            const dimStyle = isExcluded ? 'opacity:.45;' : '';

            let statusHtml;
            if (state.submitted) {
                statusHtml = `<strong>${state.final_rank}位</strong>`;
            } else {
                statusHtml = `<span style="color:var(--gray);">未申告</span>`;
            }

            const excludeBtn = IS_HOST
                ? `<button class="btn btn-sm ${isExcluded ? 'btn-outline' : 'btn-warning'} exclude-btn"
                       data-uid="${uid}" style="padding:2px 8px; font-size:.78rem; margin-left:6px;">
                       ${isExcluded ? '除外解除' : '除外'}
                   </button>`
                : '';

            const bg = state.submitted ? '#f0fdf4' : '#fafafa';
            const icon = state.submitted
                ? '<i class="fas fa-check" style="color:#28a745;margin-right:6px;"></i>'
                : '<i class="fas fa-hourglass-half" style="margin-right:6px;color:var(--gray);"></i>';

            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;background:${bg};border-radius:4px;font-size:.88rem;${dimStyle}">
                <span>${icon}${name}${isExcluded ? ' <span style="font-size:.75rem;color:var(--gray);">(除外)</span>' : ''}</span>
                <span style="display:flex;align-items:center;">${statusHtml}${excludeBtn}</span>
            </div>`;
        }).join('');

        // 除外ボタンイベント登録（再描画のたびに付け直す）
        listEl.querySelectorAll('.exclude-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const uid = btn.dataset.uid;
                btn.disabled = true;
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/exclude`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(uid) }),
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    if (scoreState[uid]) {
                        scoreState[uid].excluded = data.excluded;
                    } else {
                        scoreState[uid] = { submitted: false, final_rank: null, excluded: data.excluded };
                    }
                    renderFinalScores();
                } else {
                    alert('操作に失敗しました');
                    btn.disabled = false;
                }
            });
        });
    }

    // ============================================================
    // スタンディングテーブル更新
    // ============================================================

    function refreshStandingsTable(scores) {
        const tbody = $id('standings-tbody');
        if (!tbody) return;
        if (!scores || !scores.length) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:2rem;color:var(--gray);">12レース終了後に申告してください</td></tr>';
            return;
        }
        tbody.innerHTML = scores.map(s => {
            const name     = s.username || s.user_id;
            const rank     = s.final_rank;
            const delta    = s.mmr_delta;
            const excluded = s.excluded;
            const dimStyle = excluded ? 'opacity:.45;' : '';
            const rankCell = s.submitted
                ? `<strong>${rank}位</strong>`
                : `<span style="color:var(--gray);">未申告</span>`;
            const deltaCell = delta ? `+${delta}` : '—';
            const isFirst  = rank === 1 && !excluded;
            return `<tr class="${isFirst ? 'standings-first' : ''}" style="${dimStyle}">
                <td>${name}${excluded ? ' <span style="font-size:.75rem;color:var(--gray);">(除外)</span>' : ''}</td>
                <td style="text-align:center;">${rankCell}</td>
                <td style="text-align:right;font-family:monospace;">${deltaCell}</td>
            </tr>`;
        }).join('');
    }

    async function refreshStandings() {
        try {
            const res    = await fetch(`/lounge/api/sessions/${SESSION_ID}/standings`);
            const scores = await res.json();
            scores.forEach(s => {
                scoreState[String(s.user_id)] = {
                    submitted:  s.submitted,
                    final_rank: s.final_rank,
                    excluded:   s.excluded,
                };
            });
            refreshStandingsTable(scores);
        } catch (err) {
            console.warn('refreshStandings error:', err);
        }
    }

    // ============================================================
    // ボタンイベント
    // ============================================================

    const btnOpenModal = $id('btn-open-final-report');
    if (btnOpenModal) btnOpenModal.addEventListener('click', openFinalReportModal);

    const btnCloseModal = $id('final-modal-btn-close');
    if (btnCloseModal) btnCloseModal.addEventListener('click', closeFinalReportModal);

    const overlay = $id('final-report-modal-overlay');
    if (overlay) {
        overlay.addEventListener('click', e => {
            if (e.target === overlay) closeFinalReportModal();
        });
    }

    // 順位申告ボタン
    const btnSubmitRank = $id('btn-submit-final-rank');
    if (btnSubmitRank) {
        btnSubmitRank.addEventListener('click', async () => {
            const rank = parseInt(($id('final-rank-select') || {}).value || '1');
            btnSubmitRank.disabled = true;
            btnSubmitRank.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 送信中...';
            try {
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/final-scores/report`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ final_rank: rank }),
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    if (!scoreState[MY_USER_ID]) scoreState[MY_USER_ID] = { excluded: false };
                    scoreState[MY_USER_ID].submitted  = true;
                    scoreState[MY_USER_ID].final_rank = rank;
                    renderFinalScores();
                } else {
                    alert('申告に失敗しました');
                    btnSubmitRank.disabled = false;
                }
            } catch (err) {
                console.error(err);
                alert('通信エラーが発生しました');
                btnSubmitRank.disabled = false;
            } finally {
                btnSubmitRank.innerHTML = '<i class="fas fa-paper-plane"></i> 申告する';
            }
        });
    }

    // ホスト: 終了確定ボタン（モーダル内）
    const btnModalFinish = $id('modal-btn-finish');
    if (btnModalFinish) {
        btnModalFinish.addEventListener('click', async () => {
            const submitted = Object.values(scoreState).filter(s => s.submitted && !s.excluded).length;
            const total     = Object.keys(MEMBERS).length;
            if (submitted < total) {
                if (!confirm(`まだ ${total - submitted} 人が未申告です。終了しますか？\n未申告者は MMR 対象外になります。`)) return;
            }
            btnModalFinish.disabled = true;
            btnModalFinish.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 処理中...';
            try {
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/finish`, { method: 'POST' });
                const data = await res.json();
                if (data.status !== 'ok') {
                    alert('終了処理に失敗しました');
                    btnModalFinish.disabled = false;
                    btnModalFinish.innerHTML = '<i class="fas fa-flag-checkered"></i> 終了確定・MMR反映';
                    return;
                }
                // API成功時点でホストはすぐに表示（WSを待たない）
                showResultModal();
            } catch (err) {
                console.error(err);
                alert('通信エラーが発生しました');
                btnModalFinish.disabled = false;
                btnModalFinish.innerHTML = '<i class="fas fa-flag-checkered"></i> 終了確定・MMR反映';
            }
        });
    }

    // セッション終了ボタン（メインUI）→ モーダルを開くだけ
    const btnFinish = $id('btn-finish-session');
    if (btnFinish) {
        btnFinish.addEventListener('click', () => {
            openFinalReportModal();
        });
    }

    // スタンディング手動更新
    const btnRefresh = $id('btn-refresh-standings');
    if (btnRefresh) btnRefresh.addEventListener('click', refreshStandings);

    // ============================================================
    // セッション終了結果モーダル
    // ============================================================
    async function showResultModal() {
        if (resultModalShown) return;
        resultModalShown = true;
        closeFinalReportModal();
        const overlay = $id('result-modal-overlay');
        if (!overlay) { location.href = '/'; return; }
        overlay.style.display = 'flex';

        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/my-result`);
            if (res.ok) {
                const d = await res.json();

                const rankNum = $id('result-rank-num');
                if (rankNum) rankNum.textContent = d.final_rank ?? '—';
                const totalPl = $id('result-total-players');
                if (totalPl) totalPl.textContent = d.total_players ? `/ ${d.total_players}人中` : '';

                const mmrDelta = $id('result-mmr-delta');
                if (mmrDelta) mmrDelta.textContent = d.mmr_delta != null ? `+${d.mmr_delta}` : '—';
                const mmr = $id('result-mmr');
                if (mmr) mmr.textContent = (d.mmr ?? '—') + ' MMR';
                const rankName = $id('result-rank-name');
                if (rankName) rankName.textContent = d.rank_name || '—';

                if (d.is_winner) {
                    const header = $id('result-header');
                    if (header) header.style.background = 'linear-gradient(135deg,#b8860b,#ffd700)';
                    const trophy = $id('result-trophy');
                    if (trophy) trophy.textContent = '🏆';
                    const msg = $id('result-special-msg');
                    if (msg) {
                        msg.style.display = 'block';
                        msg.innerHTML = '🏆 <strong>セッション優勝！</strong><br>称号「覇者」が進呈される可能性があります。';
                    }
                }
            }
        } catch (_) {}

        let sec = 10;
        const cdEl  = $id('result-countdown');
        const timer = setInterval(() => {
            sec--;
            if (cdEl) cdEl.textContent = sec;
            if (sec <= 0) { clearInterval(timer); location.href = '/'; }
        }, 1000);

        const btnDash = $id('result-btn-dashboard');
        if (btnDash) btnDash.addEventListener('click', () => { clearInterval(timer); location.href = '/'; });
    }

    // ============================================================
    // WebSocket（自動再接続付き）
    // ============================================================
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    let ws = null;
    let wsReconnectTimer = null;

    function handleWsMessage(msg) {
        const msgSid = Number(msg.session_id);
        if (msgSid !== SESSION_ID) return;

        if (msg.type === 'lounge.final_score_reported') {
            const uid = String(msg.user_id);
            if (!scoreState[uid]) scoreState[uid] = { excluded: false };
            scoreState[uid].submitted  = true;
            scoreState[uid].final_rank = msg.final_rank;
            renderFinalScores();
            refreshStandings();
        }

        if (msg.type === 'lounge.member_excluded') {
            const uid = String(msg.user_id);
            if (!scoreState[uid]) scoreState[uid] = { submitted: false, final_rank: null };
            scoreState[uid].excluded = msg.excluded;
            renderFinalScores();
        }

        if (msg.type === 'lounge.session_finished') {
            showResultModal();
        }
    }

    // 結果モーダルの二重表示防止フラグ
    let resultModalShown = false;

    // WS切断中にポーリングで状態を補完するタイマー
    let pollTimer = null;

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(pollTick, 10000);
    }

    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    async function pollTick() {
        await loadFinalScores();
        // セッションが終了済みになっていたらモーダルを表示
        if (!resultModalShown) {
            try {
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/status`);
                const data = await res.json();
                if (data.status === 'finished') showResultModal();
            } catch (_) {}
        }
    }

    function connectWs() {
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
        ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);

        ws.addEventListener('open', () => {
            console.log('[Lounge WS] connected');
            stopPolling();
            // 切断中に発生した変化を再取得して画面を最新化
            pollTick();
        });

        ws.addEventListener('message', (e) => {
            let msg;
            try { msg = JSON.parse(e.data); } catch (_) { return; }
            handleWsMessage(msg);
        });

        ws.addEventListener('error', (e) => {
            console.warn('[Lounge WS] error', e);
        });

        ws.addEventListener('close', () => {
            console.warn('[Lounge WS] disconnected, reconnecting in 3s...');
            // 切断中はポーリングで状態を補完
            startPolling();
            wsReconnectTimer = setTimeout(connectWs, 3000);
        });
    }

    // 初期ロード
    loadFinalScores();
    connectWs();

    // セッションが既に終了済みの状態でページを開いた場合はすぐ結果モーダルを表示
    if (SESSION_FINISHED) {
        showResultModal();
    }
})();
