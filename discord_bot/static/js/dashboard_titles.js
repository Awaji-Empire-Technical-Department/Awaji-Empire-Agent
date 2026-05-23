// static/js/dashboard_titles.js
// Why: dashboard.html の称号管理UIロジックを分離。
(function () {
    'use strict';

    const UNLOCK_LABELS = { manual: '手動', lounge_rank: 'MMR帯', tournament_win: '優勝数' };
    let allTitles = [];

    async function loadTitles() {
        const res = await fetch('/tournament/api/titles');
        allTitles = await res.json();
        renderTitlesTable(allTitles);
    }

    function renderTitlesTable(titles) {
        const tbody = document.getElementById('titles-tbody');
        if (!titles.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--gray);">称号がまだありません</td></tr>';
            return;
        }
        tbody.innerHTML = titles.map(t => `
            <tr>
                <td style="font-family:monospace;color:var(--gray);">#${t.id}</td>
                <td><strong>${t.name}</strong>${t.description ? `<br><small style="color:var(--gray)">${t.description}</small>` : ''}</td>
                <td><span class="badge badge-secondary">${UNLOCK_LABELS[t.unlock_type] || t.unlock_type}</span></td>
                <td style="font-family:monospace;">${t.unlock_threshold ?? '-'}</td>
                <td style="font-family:monospace;font-size:.8rem;color:var(--gray);">${t.discord_role_id || '-'}</td>
                <td>
                    <div class="btn-toolbar">
                        <button class="btn btn-primary btn-icon" title="編集" onclick="editTitle(${t.id})"><i class="fas fa-pen"></i></button>
                        <button class="btn btn-danger btn-icon" title="削除" onclick="deleteTitle(${t.id}, '${t.name.replace(/'/g, "\\'")}')"><i class="fas fa-trash"></i></button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    async function loadPlayerTitles() {
        const res = await fetch('/tournament/api/titles/player/list');
        const titles = await res.json();
        const grid = document.getElementById('player-titles-grid');

        // 「称号なし」ボタン（常に先頭に表示）
        const activeTitle = titles.find(t => t.is_active_title);
        const noneBtn = `
            <button class="btn ${!activeTitle ? 'btn-success' : 'btn-outline'}"
                style="font-size:.85rem;"
                onclick="window.clearTitle()">
                ${!activeTitle ? '✓ ' : ''}称号なし
            </button>`;

        if (!titles.filter(t => t.earned).length) {
            grid.innerHTML = noneBtn + '<span style="color:var(--gray);font-size:.9rem;align-self:center;">獲得済みの称号がありません</span>';
            return;
        }
        grid.innerHTML = noneBtn + titles.map(t => `
            <button class="btn ${t.is_active_title ? 'btn-success' : (t.earned ? 'btn-primary' : 'btn-outline')}"
                style="font-size:.85rem;"
                ${!t.earned ? 'disabled title="未獲得"' : `onclick="window.equipTitle(${t.id})"`}>
                ${t.is_active_title ? '✓ ' : ''}${t.name}
            </button>
        `).join('');
    }

    async function loadActiveTitle() {
        const res = await fetch('/tournament/api/titles/player/active');
        const title = await res.json();
        const badge = document.getElementById('active-title-badge');
        if (title) {
            badge.textContent = title.name;
            badge.className = 'badge badge-success';
        } else {
            badge.textContent = '未設定';
            badge.className = 'badge badge-secondary';
        }
    }

    window.editTitle = function (id) {
        const t = allTitles.find(x => x.id === id);
        if (!t) return;
        document.getElementById('modal-title-id').value = t.id;
        document.getElementById('modal-name').value = t.name;
        document.getElementById('modal-description').value = t.description || '';
        document.getElementById('modal-unlock-type').value = t.unlock_type;
        document.getElementById('modal-threshold').value = t.unlock_threshold ?? '';
        document.getElementById('modal-role-id').value = t.discord_role_id || '';
        document.getElementById('modal-order').value = t.display_order;
        document.getElementById('modal-title-heading').textContent = '称号を編集';
        showModal();
    };

    window.deleteTitle = async function (id, name) {
        if (!confirm(`「${name}」を削除しますか？`)) return;
        await fetch(`/tournament/api/titles/${id}`, { method: 'DELETE' });
        loadTitles();
    };

    window.clearTitle = async function () {
        const res = await fetch('/tournament/api/titles/player/active', { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            await loadActiveTitle();
            await loadPlayerTitles();
        }
    };

    window.equipTitle = async function (titleId) {
        const res = await fetch('/tournament/api/titles/player/active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title_id: titleId }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            await loadActiveTitle();
            await loadPlayerTitles();
        }
    };

    function showModal() {
        document.getElementById('title-modal').style.display = 'flex';
    }

    function hideModal() {
        document.getElementById('title-modal').style.display = 'none';
        ['modal-title-id', 'modal-name', 'modal-description', 'modal-threshold', 'modal-role-id'].forEach(id => {
            document.getElementById(id).value = '';
        });
        document.getElementById('modal-order').value = '0';
    }

    document.getElementById('modal-cancel').addEventListener('click', hideModal);

    document.getElementById('modal-save').addEventListener('click', async () => {
        const id = document.getElementById('modal-title-id').value;
        if (!id) { alert('編集対象の称号が選択されていません'); return; }
        const name = document.getElementById('modal-name').value.trim();
        if (!name) { alert('称号名を入力してください'); return; }

        const body = {
            id: parseInt(id),
            name,
            description: document.getElementById('modal-description').value.trim() || null,
            unlock_type: document.getElementById('modal-unlock-type').value,
            unlock_threshold: document.getElementById('modal-threshold').value
                ? parseInt(document.getElementById('modal-threshold').value) : null,
            discord_role_id: document.getElementById('modal-role-id').value.trim() || null,
            display_order: parseInt(document.getElementById('modal-order').value) || 0,
        };

        await fetch('/tournament/api/titles/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        hideModal();
        loadTitles();
    });

    document.getElementById('btn-change-title').addEventListener('click', async () => {
        const panel = document.getElementById('player-titles-panel');
        const btn = document.getElementById('btn-change-title');
        if (panel.style.display === 'none') {
            await loadPlayerTitles();
            panel.style.display = 'block';
            btn.textContent = '閉じる';
        } else {
            panel.style.display = 'none';
            btn.textContent = '称号を変更する';
        }
    });

    // 初期ロード
    loadTitles();
    loadActiveTitle();
})();
