// static/js/lounge.js
(function () {
    'use strict';

    // ============================================================
    // 一覧ビュー
    // ============================================================
    if (SESSION_ID === null) {
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

    // ============================================================
    // セッション進行ビュー
    // ============================================================

    // 参加登録
    fetch(`/lounge/api/sessions/${SESSION_ID}/join`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
    });

    // --- DOM参照 ---
    const overlay       = document.getElementById('race-modal-overlay');
    const phaseSetup    = document.getElementById('modal-phase-setup');
    const phaseReport   = document.getElementById('modal-phase-report');
    const modalHeaderLabel = document.getElementById('modal-header-label');
    const modalCourseName  = document.getElementById('modal-course-name');
    const modalRaceNum     = document.getElementById('modal-race-num');
    const modalSubmittedCount = document.getElementById('modal-submitted-count');
    const modalSubmissionList = document.getElementById('modal-submission-list');
    const modalMySubmitted    = document.getElementById('modal-my-submitted');

    // 提出状況キャッシュ: user_id(string) -> {submitted, position, is_disconnect}
    let submissionState = {};

    // ============================================================
    // フェーズ制御
    // ============================================================

    /** ホスト用：セットアップフェーズでモーダルを開く */
    function openSetupPhase() {
        if (phaseSetup)  phaseSetup.style.display  = 'block';
        if (phaseReport) phaseReport.style.display = 'none';
        if (modalHeaderLabel) modalHeaderLabel.textContent = 'レース設定';
        modalCourseName.textContent = 'コース名を入力してください';
        modalRaceNum.textContent    = '';
        if (document.getElementById('modal-course-input')) {
            document.getElementById('modal-course-input').value = '';
        }
        overlay.style.display = 'flex';
    }

    /** 全員：申告フェーズに切り替える（レース開始後） */
    function openReportPhase(raceId, courseName, raceNumber) {
        currentRaceId = raceId;
        if (phaseSetup)  phaseSetup.style.display  = 'none';
        if (phaseReport) phaseReport.style.display = 'block';
        if (modalHeaderLabel) modalHeaderLabel.textContent = 'レース進行中';
        modalCourseName.textContent = courseName;
        modalRaceNum.textContent    = `第 ${raceNumber} レース`;
        // 申告状態リセット
        submissionState = {};
        const btnReport = document.getElementById('modal-btn-report');
        const btnDc     = document.getElementById('modal-btn-disconnect');
        if (btnReport) btnReport.disabled = false;
        if (btnDc)     btnDc.disabled     = false;
        if (modalMySubmitted) modalMySubmitted.style.display = 'none';
        overlay.style.display = 'flex';
        // 既存の提出状況を取得（ページリロード時の復元含む）
        loadSubmissions(raceId);
    }

    function closeModal() {
        overlay.style.display = 'none';
        currentRaceId = null;
        submissionState = {};
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
        } catch (_) {}
    }

    function renderSubmissions() {
        if (!modalSubmittedCount || !modalSubmissionList) return;
        const memberIds   = Object.keys(MEMBERS);
        const submittedIds = Object.keys(submissionState).filter(id => submissionState[id].submitted);
        const total = memberIds.length;
        const done  = submittedIds.length;

        modalSubmittedCount.textContent = `${done} / ${total} 人提出済み`;

        // 自分が提出済みなら入力欄を無効化
        if (submissionState[MY_USER_ID]?.submitted) {
            if (modalMySubmitted) modalMySubmitted.style.display = 'block';
            const btn = document.getElementById('modal-btn-report');
            if (btn) btn.disabled = true;
            const dc = document.getElementById('modal-btn-disconnect');
            if (dc)  dc.disabled  = true;
        }

        // 提出一覧（メンバー + 提出済みのゲスト）
        const allIds = [...new Set([...memberIds, ...submittedIds])];
        modalSubmissionList.innerHTML = allIds.map(uid => {
            const name = MEMBERS[uid] || `ID:${uid}`;
            const s    = submissionState[uid];
            if (s?.submitted) {
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
    // ホスト操作
    // ============================================================

    // 「レース開始」→ セットアップフェーズを開く
    document.getElementById('btn-new-race')?.addEventListener('click', () => {
        openSetupPhase();
    });

    // セットアップフェーズ：「このコースでレースを開始する」
    document.getElementById('modal-btn-start-race')?.addEventListener('click', async () => {
        const courseInput = document.getElementById('modal-course-input');
        const course = courseInput ? courseInput.value.trim() : '';
        if (!course) { courseInput?.focus(); return; }

        const btn = document.getElementById('modal-btn-start-race');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 開始中...';

        const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/races`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course_name: course }),
        });
        const data = await res.json();

        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-flag"></i> このコースでレースを開始する';

        if (data.status === 'ok') {
            // ホストは直接申告フェーズへ（WSを待たない）
            // race_numberはAPIレスポンスにないのでactive-raceで取得
            openReportPhase(data.race_id, course, '...');
            // race_numberを補完
            fetchAndUpdateRaceNum(data.race_id);

            if (data.duplicate_course) {
                alert(`⚠️ 「${course}」は既にこのセッションで使用されたコースです！`);
            }
        } else {
            alert('レース開始に失敗しました');
        }
    });

    async function fetchAndUpdateRaceNum(raceId) {
        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/active-race`);
            if (res.ok) {
                const data = await res.json();
                if (data.race_id === raceId && modalRaceNum) {
                    modalRaceNum.textContent = `第 ${data.race_number} レース`;
                    const el = document.getElementById('current-race');
                    if (el) el.textContent = data.race_number;
                }
            }
        } catch (_) {}
    }

    // 結果確定・次のレースへ（ホストのみ）
    document.getElementById('modal-btn-finalize')?.addEventListener('click', async () => {
        if (!currentRaceId) return;
        const memberCount    = Object.keys(MEMBERS).length;
        const submittedCount = Object.values(submissionState).filter(s => s.submitted).length;
        if (submittedCount < memberCount) {
            const proceed = confirm(`まだ ${memberCount - submittedCount} 人が未提出です。それでも確定しますか？`);
            if (!proceed) return;
        }
        const btn = document.getElementById('modal-btn-finalize');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 処理中...';
        const res  = await fetch(`/lounge/api/sessions/${SESSION_ID}/races/${currentRaceId}/finalize`, { method: 'POST' });
        const data = await res.json();
        if (data.status !== 'ok') {
            alert('確定に失敗しました');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-check-double"></i> 結果確定・次のレースへ';
        }
        // 成功時は lounge.race_advanced WS でモーダルが閉じ、standings更新
    });

    // セッション終了
    document.getElementById('btn-finish-session')?.addEventListener('click', async () => {
        if (!confirm('セッションを終了しますか？')) return;
        await fetch(`/lounge/api/sessions/${SESSION_ID}/finish`, { method: 'POST' });
        // WS lounge.session_finished で結果モーダルが開く
    });

    // ============================================================
    // ゲスト操作（申告フォーム）
    // ============================================================

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

    // ============================================================
    // スタンディング更新
    // ============================================================

    document.getElementById('btn-refresh-standings')?.addEventListener('click', refreshStandings);

    async function refreshStandings() {
        try {
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
        } catch (_) {}
    }

    // ============================================================
    // ページロード時: 進行中のレースを復元
    // ============================================================
    (async () => {
        try {
            const res = await fetch(`/lounge/api/sessions/${SESSION_ID}/active-race`);
            if (!res.ok) return;
            const race = await res.json();
            if (race && race.race_id) {
                // 既にスコアがあるか確認（終了済みセッションの誤検知防止）
                openReportPhase(race.race_id, race.course_name, race.race_number);
            }
        } catch (_) {}
    })();

    // ============================================================
    // セッション終了結果モーダル
    // ============================================================
    async function showResultModal() {
        const resultOverlay = document.getElementById('result-modal-overlay');
        if (!resultOverlay) { location.href = '/'; return; }
        resultOverlay.style.display = 'flex';
        try {
            const res = await fetch('/lounge/api/me');
            if (res.ok) {
                const data = await res.json();
                const elMmr  = document.getElementById('result-mmr');
                const elRank = document.getElementById('result-rank');
                if (elMmr)  elMmr.textContent  = `${data.mmr} MMR`;
                if (elRank) elRank.textContent  = data.rank_name || '—';
            }
        } catch (_) {}
        document.getElementById('result-btn-dashboard')?.addEventListener('click', () => {
            location.href = '/';
        });
        setTimeout(() => { location.href = '/'; }, 15000);
    }

    // ============================================================
    // WebSocket（他ユーザーへのリアルタイム通知）
    // ============================================================
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${wsProto}://${location.host}/ws/hyouibana`);

    ws.addEventListener('message', (e) => {
        try {
            const msg = JSON.parse(e.data);
            // session_id の型を統一して比較
            const msgSid = Number(msg.session_id);

            if (msg.type === 'lounge.race_created' && msgSid === SESSION_ID) {
                // ホストは既にopenReportPhaseを呼んでいるため、非ホストのみ処理
                if (!IS_HOST) {
                    openReportPhase(msg.race_id, msg.course_name, msg.race_number);
                } else if (!currentRaceId) {
                    // ホストでも未開封なら開く（ページリロード直後など）
                    openReportPhase(msg.race_id, msg.course_name, msg.race_number);
                }
                if (msg.duplicate_course) {
                    alert(`⚠️ コース重複: 「${msg.course_name}」は既に使用済みです！`);
                }
            }

            if (msg.type === 'lounge.score_reported' && Number(msg.race_id) === currentRaceId) {
                loadSubmissions(currentRaceId);
            }

            if (msg.type === 'lounge.disconnect_reported' && Number(msg.race_id) === currentRaceId) {
                loadSubmissions(currentRaceId);
            }

            if (msg.type === 'lounge.race_advanced' && msgSid === SESSION_ID) {
                closeModal();
                refreshStandings();
                const el = document.getElementById('current-race');
                if (el) el.textContent = parseInt(el.textContent || '0') + 1;
            }

            if (msg.type === 'lounge.race_approved') {
                refreshStandings();
            }

            if (msg.type === 'lounge.session_finished' && msgSid === SESSION_ID) {
                closeModal();
                showResultModal();
            }
        } catch (_) {}
    });
})();
