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

    // 参加登録
    fetch(`/lounge/api/sessions/${SESSION_ID}/join`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
    }).catch(() => {});

    // 提出状況キャッシュ
    let submissionState = {};

    // ---- ヘルパー: 要素取得 ----
    function $id(id) { return document.getElementById(id); }

    // ============================================================
    // モーダル表示制御
    // ============================================================

    function showModal() {
        const el = $id('race-modal-overlay');
        if (el) el.style.display = 'flex';
    }

    function hideModal() {
        const el = $id('race-modal-overlay');
        if (el) el.style.display = 'none';
        currentRaceId  = null;
        submissionState = {};
    }

    /** ホスト用：コース名入力フェーズ */
    function openSetupPhase() {
        const setup  = $id('modal-phase-setup');
        const report = $id('modal-phase-report');
        if (setup)  setup.style.display  = 'block';
        if (report) report.style.display = 'none';

        const label = $id('modal-header-label');
        const cname = $id('modal-course-name');
        const rnum  = $id('modal-race-num');
        const input = $id('modal-course-input');
        if (label) label.textContent = 'レース設定';
        if (cname) cname.textContent = 'コース名を入力';
        if (rnum)  rnum.textContent  = '';
        if (input) { input.value = ''; input.focus(); }

        showModal();
    }

    /** 全員：順位申告フェーズ */
    function openReportPhase(raceId, courseName, raceNumber) {
        currentRaceId  = raceId;
        submissionState = {};

        const setup  = $id('modal-phase-setup');
        const report = $id('modal-phase-report');
        if (setup)  setup.style.display  = 'none';
        if (report) report.style.display = 'block';

        const label = $id('modal-header-label');
        const cname = $id('modal-course-name');
        const rnum  = $id('modal-race-num');
        if (label) label.textContent = 'レース進行中';
        if (cname) cname.textContent = courseName;
        if (rnum)  rnum.textContent  = `第 ${raceNumber} レース`;

        // 申告フォームをリセット
        const btnRep = $id('modal-btn-report');
        const btnDc  = $id('modal-btn-disconnect');
        const submitted = $id('modal-my-submitted');
        if (btnRep)    btnRep.disabled    = false;
        if (btnDc)     btnDc.disabled     = false;
        if (submitted) submitted.style.display = 'none';

        showModal();
        loadSubmissions(raceId);
    }

    // ============================================================
    // 提出状況
    // ============================================================

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
        } catch (err) {
            console.warn('loadSubmissions error:', err);
        }
    }

    function renderSubmissions() {
        const countEl = $id('modal-submitted-count');
        const listEl  = $id('modal-submission-list');
        if (!countEl || !listEl) return;

        const memberIds    = Object.keys(MEMBERS);
        const submittedIds = Object.keys(submissionState).filter(id => submissionState[id].submitted);
        const total = memberIds.length;
        const done  = submittedIds.length;

        countEl.textContent = `${done} / ${total} 人提出済み`;

        // 自分が提出済みか
        if (submissionState[MY_USER_ID] && submissionState[MY_USER_ID].submitted) {
            const s = $id('modal-my-submitted');
            if (s) s.style.display = 'block';
            const r = $id('modal-btn-report');
            const d = $id('modal-btn-disconnect');
            if (r) r.disabled = true;
            if (d) d.disabled = true;
        }

        // 全員提出済みかつ非ホスト → 承認待ちメッセージを表示
        const waitingEl = $id('modal-waiting-host');
        if (waitingEl) {
            waitingEl.style.display = (done >= total && total > 0) ? 'block' : 'none';
        }

        const allIds = [...new Set([...memberIds, ...submittedIds])];
        listEl.innerHTML = allIds.map(uid => {
            const name = MEMBERS[uid] || ('ID:' + uid);
            const s    = submissionState[uid];
            if (s && s.submitted) {
                const label = s.is_disconnect
                    ? '<span style="color:#dc3545;">回線落ち</span>'
                    : `<strong>${s.position}位</strong>`;
                return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;background:#f0fdf4;border-radius:4px;font-size:.88rem;">
                    <span><i class="fas fa-check" style="color:#28a745;margin-right:6px;"></i>${name}</span>
                    <span>${label}</span>
                </div>`;
            }
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;background:#fafafa;border-radius:4px;font-size:.88rem;color:var(--gray);">
                <span><i class="fas fa-hourglass-half" style="margin-right:6px;"></i>${name}</span>
                <span>未提出</span>
            </div>`;
        }).join('');
    }

    // ============================================================
    // ボタンイベント
    // ============================================================

    // ホスト：「レース開始」→ セットアップフェーズを開く
    const btnNewRace = $id('btn-new-race');
    if (btnNewRace) {
        btnNewRace.addEventListener('click', function () {
            openSetupPhase();
        });
    }

    // ホスト：セットアップフェーズの「開始する」
    const btnStartRace = $id('modal-btn-start-race');
    if (btnStartRace) {
        btnStartRace.addEventListener('click', async function () {
            const input  = $id('modal-course-input');
            const course = input ? input.value.trim() : '';
            if (!course) {
                if (input) input.focus();
                return;
            }
            btnStartRace.disabled = true;
            btnStartRace.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 開始中...';

            try {
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/races`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ course_name: course }),
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    // ホストは即座に申告フェーズへ（WSを待たない）
                    const raceNum = data.race_number || (parseInt(($id('current-race') || {}).textContent || '0') + 1);
                    openReportPhase(data.race_id, course, raceNum);
                    if (data.duplicate_course) {
                        alert(`⚠️ 「${course}」は既にこのセッションで使用されたコースです！`);
                    }
                } else {
                    alert('レース開始に失敗しました');
                }
            } catch (err) {
                console.error('race start error:', err);
                alert('通信エラーが発生しました');
            } finally {
                btnStartRace.disabled = false;
                btnStartRace.innerHTML = '<i class="fas fa-flag"></i> このコースでレースを開始する';
            }
        });
    }

    // 申告ボタン
    const btnReport = $id('modal-btn-report');
    if (btnReport) {
        btnReport.addEventListener('click', async function () {
            if (!currentRaceId) return;
            const pos  = parseInt(($id('modal-report-position') || {}).value || '1');
            const res  = await fetch(`/lounge/api/races/${currentRaceId}/report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ position: pos }),
            });
            const data = await res.json();
            if (data.status === 'ok') {
                submissionState[MY_USER_ID] = { submitted: true, position: pos, is_disconnect: false };
                renderSubmissions();
            } else {
                alert('申告に失敗しました');
            }
        });
    }

    // 回線落ち報告
    const btnDc = $id('modal-btn-disconnect');
    if (btnDc) {
        btnDc.addEventListener('click', async function () {
            if (!currentRaceId) return;
            if (!confirm('回線落ちを報告しますか？')) return;
            const res  = await fetch(`/lounge/api/races/${currentRaceId}/disconnect`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
            });
            const data = await res.json();
            if (data.status === 'ok') {
                submissionState[MY_USER_ID] = { submitted: true, position: null, is_disconnect: true };
                renderSubmissions();
            }
        });
    }

    // ホスト：結果確定・次のレースへ
    const btnFinalize = $id('modal-btn-finalize');
    if (btnFinalize) {
        btnFinalize.addEventListener('click', async function () {
            if (!currentRaceId) return;
            const memberCount    = Object.keys(MEMBERS).length;
            const submittedCount = Object.values(submissionState).filter(s => s.submitted).length;
            if (submittedCount < memberCount) {
                if (!confirm(`まだ ${memberCount - submittedCount} 人が未提出です。それでも確定しますか？`)) return;
            }
            btnFinalize.disabled = true;
            btnFinalize.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 処理中...';
            try {
                const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/races/${currentRaceId}/finalize`, { method: 'POST' });
                const data = await res.json();
                if (data.status !== 'ok') {
                    alert('確定に失敗しました');
                    btnFinalize.disabled = false;
                    btnFinalize.innerHTML = '<i class="fas fa-check-double"></i> 結果確定・次のレースへ';
                }
            } catch (err) {
                console.error('finalize error:', err);
                btnFinalize.disabled = false;
                btnFinalize.innerHTML = '<i class="fas fa-check-double"></i> 結果確定・次のレースへ';
            }
        });
    }

    // セッション終了
    const btnFinish = $id('btn-finish-session');
    if (btnFinish) {
        btnFinish.addEventListener('click', async function () {
            if (!confirm('セッションを終了しますか？')) return;
            await fetch(`/lounge/api/sessions/${SESSION_ID}/finish`, { method: 'POST' });
        });
    }

    // スタンディング手動更新
    const btnRefresh = $id('btn-refresh-standings');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', refreshStandings);
    }

    // ============================================================
    // スタンディング更新
    // ============================================================

    async function refreshStandings() {
        try {
            const res      = await fetch(`/lounge/api/sessions/${SESSION_ID}/standings`);
            const standings = await res.json();
            const tbody    = $id('standings-tbody');
            if (!tbody) return;
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
        } catch (err) {
            console.warn('refreshStandings error:', err);
        }
    }

    // ============================================================
    // ページロード時：進行中レースを復元
    // ============================================================
    fetch(`/lounge/api/sessions/${SESSION_ID}/active-race`)
        .then(res => res.ok ? res.json() : null)
        .then(race => {
            if (race && race.race_id) {
                openReportPhase(race.race_id, race.course_name, race.race_number);
            }
        })
        .catch(() => {});

    // ============================================================
    // セッション終了結果モーダル
    // ============================================================
    async function showResultModal() {
        const overlay = $id('result-modal-overlay');
        if (!overlay) { location.href = '/'; return; }
        overlay.style.display = 'flex';

        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/my-result`);
            if (res.ok) {
                const d = await res.json();

                // 順位
                const rankNum = $id('result-rank-num');
                if (rankNum) rankNum.textContent = d.rank ?? '—';
                const totalPl = $id('result-total-players');
                if (totalPl) totalPl.textContent = d.total_players ? `/ ${d.total_players}人中` : '';

                // ポイント・MMR・ランク
                const pts = $id('result-points');
                if (pts) pts.textContent = (d.total_points ?? 0) + ' pt';
                const mmr = $id('result-mmr');
                if (mmr) mmr.textContent = (d.mmr ?? '—') + ' MMR';
                const rankName = $id('result-rank-name');
                if (rankName) rankName.textContent = d.rank_name || '—';

                // 優勝演出
                if (d.is_winner) {
                    const header = $id('result-header');
                    if (header) header.style.background = 'linear-gradient(135deg,#b8860b,#ffd700)';
                    const trophy = $id('result-trophy');
                    if (trophy) trophy.textContent = '🏆';
                    const msg = $id('result-special-msg');
                    if (msg) {
                        msg.style.display = 'block';
                        msg.innerHTML = '🏆 <strong>セッション優勝！</strong><br>称号「覇者」が進呈される可能性があります。<br><span style="font-size:.82rem;color:var(--gray);">3回優勝で「連覇の王」も狙えます</span>';
                    }
                }
            }
        } catch (_) {}

        // 10秒カウントダウン → ダッシュボードへ
        let sec = 10;
        const cdEl = $id('result-countdown');
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

        if (msg.type === 'lounge.race_created' && msgSid === SESSION_ID) {
            if (!IS_HOST || !currentRaceId) {
                openReportPhase(msg.race_id, msg.course_name, msg.race_number);
            }
            if (msg.duplicate_course) {
                alert(`⚠️ コース重複: 「${msg.course_name}」は既に使用済みです！`);
            }
        }

        // 申告データをWSメッセージから直接反映（HTTPフェッチ不要）
        if ((msg.type === 'lounge.score_reported' || msg.type === 'lounge.disconnect_reported')
                && Number(msg.race_id) === currentRaceId) {
            submissionState[String(msg.user_id)] = {
                submitted: true,
                position: msg.position ?? null,
                is_disconnect: msg.is_disconnect ?? false,
            };
            renderSubmissions();
        }

        if (msg.type === 'lounge.race_advanced' && msgSid === SESSION_ID) {
            hideModal();
            refreshStandings();
            const el = $id('current-race');
            if (el) el.textContent = parseInt(el.textContent || '0') + 1;
        }

        if (msg.type === 'lounge.race_approved') {
            refreshStandings();
        }

        if (msg.type === 'lounge.session_finished' && msgSid === SESSION_ID) {
            hideModal();
            showResultModal();
        }
    }

    function connectWs() {
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
        ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);

        ws.addEventListener('open', () => {
            console.log('[Lounge WS] connected');
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
            wsReconnectTimer = setTimeout(connectWs, 3000);
        });
    }

    connectWs();
})();
