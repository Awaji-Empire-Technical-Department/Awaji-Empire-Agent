/**
 * form.js - アンケート回答フォームのインタラクション制御
 *
 * 責務:
 *  - 条件分岐 (Branch Logic) による質問パネルの表示/非表示
 *  - 「その他」テキストフィールドの有効/無効切り替え
 *  - 非表示パネルの required 属性の動的制御（バリデーション回避）
 */

/**
 * ラジオボタンの選択状態を読み取り、条件分岐ロジックを評価する。
 * 回答フォームの onchange イベントおよびページロード時に呼ばれる。
 */
function checkLogic() {
    // 現在チェック済みのラジオボタンから { 質問インデックス: 回答値 } を構築
    const ans = {};
    document.querySelectorAll('input[type=radio]:checked').forEach(r => {
        // name属性は "q_0", "q_1" ... の形式
        ans[r.name.split('_')[1]] = r.value;
    });

    // 各質問パネルの表示/非表示を制御
    document.querySelectorAll('.q-panel').forEach(p => {
        const tIdx = p.dataset.trg;
        const tVal = p.dataset.val;

        if (tIdx) {
            // 条件: 指定のトリガー質問に指定の回答が選ばれていたら表示
            if (ans[tIdx] === tVal) {
                p.classList.remove('hidden');
                p.classList.add('fade-in');
                toggleReq(p, true);
            } else {
                p.classList.remove('fade-in');
                p.classList.add('hidden');
                toggleReq(p, false);
            }
        }
    });

    // 「その他」ラジオの状態に応じてテキスト入力を有効化/無効化
    document.querySelectorAll('input[value=__other__]').forEach(r => {
        const txt = r.parentElement.querySelector('input[type=text]');
        if (txt) {
            txt.disabled = !r.checked;
            if (r.checked) txt.focus();
        }
    });
}

/**
 * チェックボックスの「その他」入力を切り替える。
 * @param {HTMLInputElement} chk - 「その他」チェックボックス要素
 */
function toggleOther(chk) {
    const txt = chk.parentElement.querySelector('input[type=text]');
    if (txt) {
        txt.disabled = !chk.checked;
        if (chk.checked) txt.focus();
    }
}

/**
 * パネル内のラジオボタンの required 属性を動的に設定する。
 * 非表示パネルの required を外してバリデーションエラーを防ぐ。
 *
 * @param {HTMLElement} panel - 対象の質問パネル
 * @param {boolean} req - true: required を付加 / false: required を除去
 */
function toggleReq(panel, req) {
    panel.querySelectorAll('input[type=radio]').forEach(i => {
        if (req) {
            i.setAttribute('required', '');
        } else {
            i.removeAttribute('required');
        }
    });
}

// ページロード時に初期状態を評価（既存回答の復元後に条件分岐を適用）
window.addEventListener('DOMContentLoaded', checkLogic);
