// static/js/event_admin.js
(function () {
    'use strict';

    const EVENT_ID = window.EVENT_ID;

    // ============================================================
    // 参加者更新ヘルパー
    // ============================================================

    function getApproval(pid) {
        const row = document.getElementById(`row-${pid}`);
        return row?.querySelector('.select-approval')?.value ?? 'pending';
    }

    function getSessionId(pid) {
        const row = document.getElementById(`row-${pid}`);
        const val = row?.querySelector('.select-session')?.value;
        return val ? parseInt(val) : null;
    }

    async function patchParticipant(pid, body) {
        await fetch(`/event/api/participant/${pid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    }

    window.updateSession = function (pid, selectEl) {
        const sessionId = selectEl.value ? parseInt(selectEl.value) : null;
        patchParticipant(pid, { approval: getApproval(pid), session_id: sessionId });
    };

    window.updateApproval = function (pid, selectEl) {
        patchParticipant(pid, { approval: selectEl.value, session_id: getSessionId(pid) });
    };

    window.updateNote = function (pid, note) {
        patchParticipant(pid, {
            approval: getApproval(pid),
            session_id: getSessionId(pid),
            personal_note: note,
        });
    };

    // ============================================================
    // 自動割り当て
    // ============================================================

    const APPROVAL_LABELS = { pending: '確認中', accepted: '承認', rejected: '否認', waitlist: '補欠' };

    window.autoAssign = async function () {
        if (!confirm('自動割り当てを実行しますか？\n既に「承認」「否認」済みの方はスキップされます。')) return;
        const res = await fetch(`/event/api/${EVENT_ID}/auto-assign`, { method: 'POST' });
        if (!res.ok) { alert('割り当てに失敗しました'); return; }
        const d = await res.json();
        if (d.status !== 'ok') { alert('割り当てに失敗しました'); return; }

        // レスポンスに含まれる最新の参加者データでDOMを直接更新
        let updated = 0;
        (d.participants || []).forEach(p => {
            const row = document.getElementById(`row-${p.id}`);
            if (!row) return;

            const approvalSel = row.querySelector('.select-approval');
            if (approvalSel && approvalSel.value !== p.approval) {
                approvalSel.value = p.approval;
                updated++;
            }

            const sessionSel = row.querySelector('.select-session');
            if (sessionSel) {
                const newVal = p.session_id != null ? String(p.session_id) : '';
                if (sessionSel.value !== newVal) {
                    sessionSel.value = newVal;
                    updated++;
                }
            }
        });

        alert(`割り当て完了（${updated}件更新）。`);
        // 部ごとの残席カウントはページリロードで最新化
        location.reload();
    };

    // ============================================================
    // 一斉通知
    // ============================================================

    window.notifyAll = async function () {
        if (!confirm('承認・否認・補欠の全員にDiscord DMを送信しますか？\n送信済みの方はスキップされます。')) return;
        const btn = document.getElementById('btn-notify');
        if (btn) btn.disabled = true;
        const res = await fetch(`/event/api/${EVENT_ID}/notify`, { method: 'POST' });
        const d = await res.json();
        if (d.status === 'ok') {
            alert(`${d.sent}件送信しました。ページを更新します。`);
            location.reload();
        } else {
            alert('送信に失敗しました');
            if (btn) btn.disabled = false;
        }
    };

    // ============================================================
    // 確認URL コピー
    // ============================================================

    window.copyConfirmUrl = function (token) {
        const url = `${location.origin}/event/confirm/${token}`;
        navigator.clipboard.writeText(url).then(() => alert('確認URLをコピーしました'));
    };
})();
