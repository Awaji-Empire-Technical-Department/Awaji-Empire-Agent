// static/js/dashboard_lobby.js
// Why: dashboard.html の大会作成フォーム、モード切替ロジックを分離。
(function () {
    'use strict';

    const modeFree       = document.getElementById('mode-free');
    const modeTournament = document.getElementById('mode-tournament');
    const options        = document.getElementById('tournament-options');
    const selectGame     = document.getElementById('select-game-title');
    const bracketGroup   = document.getElementById('bracket-format-group');
    const winsLabel      = document.getElementById('wins-label');

    function onModeChange() {
        const isTournament = modeTournament && modeTournament.checked;
        if (options) options.style.display = isTournament ? 'block' : 'none';
    }

    function onGameChange() {
        if (!selectGame) return;
        const selected = selectGame.options[selectGame.selectedIndex];
        const matchType = selected ? selected.dataset.matchType : '1v1';

        if (matchType === 'multiplayer') {
            // multiplayer は総当たり固定・レース数入力に切替
            if (bracketGroup) bracketGroup.style.display = 'none';
            if (winsLabel) winsLabel.textContent = 'レース数';
            const bracketSelect = document.querySelector('select[name="bracket_format"]');
            if (bracketSelect) bracketSelect.value = 'round_robin';
        } else {
            if (bracketGroup) bracketGroup.style.display = 'block';
            if (winsLabel) winsLabel.textContent = 'n本先取';
        }
    }

    modeFree       && modeFree.addEventListener('change', onModeChange);
    modeTournament && modeTournament.addEventListener('change', onModeChange);
    selectGame     && selectGame.addEventListener('change', onGameChange);

    // 初期状態を反映
    onModeChange();
    onGameChange();
})();
