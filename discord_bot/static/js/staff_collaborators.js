// staff_collaborators.js
// 共同編集スタッフの検索・追加・削除（オーナーのみ利用）。
// edit.html から読み込まれ、window.initialCollaborators を初期値として描画する。

(function () {
    const card = document.getElementById('staff-card');
    if (!card) return;

    const surveyId = card.dataset.surveyId;
    const searchInput = document.getElementById('staff-search');
    const resultsBox = document.getElementById('staff-search-results');
    const listBox = document.getElementById('staff-list');

    let collaborators = Array.isArray(window.initialCollaborators) ? window.initialCollaborators.slice() : [];

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function renderList() {
        listBox.innerHTML = '';
        if (collaborators.length === 0) {
            listBox.innerHTML = '<span style="color:var(--gray); font-size:.85rem;">スタッフは登録されていません。</span>';
            return;
        }
        collaborators.forEach(function (c) {
            const name = c.username || ('ID:' + c.user_id);
            const badge = document.createElement('span');
            badge.style.cssText = 'display:inline-flex; align-items:center; gap:.4rem; background:#eef2f5; border-radius:16px; padding:.3rem .7rem; font-size:.9rem;';
            badge.innerHTML = '<i class="fas fa-user"></i>' + escapeHtml(name) +
                ' <i class="fas fa-times" style="cursor:pointer; color:var(--danger);" title="削除"></i>';
            badge.querySelector('.fa-times').addEventListener('click', function () {
                removeStaff(c.user_id);
            });
            listBox.appendChild(badge);
        });
    }

    async function addStaff(userId) {
        const res = await fetch('/api/' + surveyId + '/collaborators', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            // 一覧を再取得して反映
            await reload();
        } else {
            alert('スタッフの追加に失敗しました');
        }
    }

    async function removeStaff(userId) {
        if (!confirm('このスタッフを削除しますか？')) return;
        const res = await fetch('/api/' + surveyId + '/collaborators/' + userId, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            collaborators = collaborators.filter(function (c) { return String(c.user_id) !== String(userId); });
            renderList();
        } else {
            alert('スタッフの削除に失敗しました');
        }
    }

    async function reload() {
        const res = await fetch('/api/' + surveyId + '/collaborators');
        if (res.ok) {
            collaborators = await res.json();
            renderList();
        }
    }

    // インクリメンタル検索（デバウンス）
    let timer = null;
    searchInput.addEventListener('input', function () {
        const q = searchInput.value.trim();
        clearTimeout(timer);
        if (q.length < 2) {
            resultsBox.style.display = 'none';
            return;
        }
        timer = setTimeout(async function () {
            const res = await fetch('/api/users/search?q=' + encodeURIComponent(q));
            if (!res.ok) return;
            const users = await res.json();
            renderResults(users);
        }, 250);
    });

    function renderResults(users) {
        resultsBox.innerHTML = '';
        const existing = new Set(collaborators.map(function (c) { return String(c.user_id); }));
        const filtered = users.filter(function (u) { return !existing.has(String(u.user_id)); });
        if (filtered.length === 0) {
            resultsBox.innerHTML = '<div style="padding:.6rem; color:var(--gray); font-size:.85rem;">該当ユーザーなし（新規メンバーは /sync_members で同期できます）</div>';
            resultsBox.style.display = 'block';
            return;
        }
        filtered.forEach(function (u) {
            const item = document.createElement('div');
            item.style.cssText = 'padding:.5rem .7rem; cursor:pointer; border-bottom:1px solid #f0f0f0;';
            item.innerHTML = '<i class="fas fa-user-plus" style="color:var(--accent-blue); margin-right:.5rem;"></i>' + escapeHtml(u.username || ('ID:' + u.user_id));
            item.addEventListener('mouseenter', function () { item.style.background = '#f5f7fa'; });
            item.addEventListener('mouseleave', function () { item.style.background = '#fff'; });
            item.addEventListener('click', function () {
                addStaff(u.user_id);
                searchInput.value = '';
                resultsBox.style.display = 'none';
            });
            resultsBox.appendChild(item);
        });
        resultsBox.style.display = 'block';
    }

    // 外側クリックで候補を閉じる
    document.addEventListener('click', function (e) {
        if (!resultsBox.contains(e.target) && e.target !== searchInput) {
            resultsBox.style.display = 'none';
        }
    });

    renderList();
})();
