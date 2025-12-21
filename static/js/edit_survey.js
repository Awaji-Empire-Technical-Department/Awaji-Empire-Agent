/**
 * アンケート編集画面用スクリプト
 */

// グローバル変数 (HTML側から初期データを受け取る)
let questions = window.initialQuestions || [];

document.addEventListener('DOMContentLoaded', function() {
    renderQuestions();

    // フォーム送信時の処理
    const form = document.getElementById('surveyForm');
    if (form) {
        form.onsubmit = function() {
            // JSON文字列に変換してhidden inputにセット
            document.getElementById('questionsJson').value = JSON.stringify(questions);
            return true;
        };
    }
});

// 質問リストを描画
function renderQuestions() {
    const container = document.getElementById('questionsContainer');
    if (!container) return;

    container.innerHTML = '';
    
    questions.forEach((q, index) => {
        let qText = q.question || q; 
        let qType = q.type || 'text';
        let options = q.options || [];

        // CSSクラスに合わせてHTMLを生成
        const html = `
        <div class="form-group" style="padding: 15px; border: 1px solid #eee; border-radius: 4px; margin-bottom: 15px; background: #fff;">
            <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                <span class="status-badge closed">Q${index + 1}</span>
                <button type="button" class="btn btn-orange" style="padding: 2px 8px; font-size: 0.8em;" onclick="removeQuestion(${index})">削除</button>
            </div>
            
            <div class="form-group">
                <input type="text" placeholder="質問文を入力" value="${escapeHtml(qText)}" 
                       onchange="updateQ(${index}, 'question', this.value)">
            </div>
            
            <div style="display:flex; gap:10px;">
                <div style="flex:1;">
                    <select class="form-control" style="width:100%; padding:10px; border-radius:4px; border:1px solid #ddd;" 
                            onchange="updateQ(${index}, 'type', this.value)">
                        <option value="text" ${qType==='text'?'selected':''}>記述式</option>
                        <option value="radio" ${qType==='radio'?'selected':''}>ラジオボタン</option>
                        <option value="checkbox" ${qType==='checkbox'?'selected':''}>チェックボックス</option>
                    </select>
                </div>
                <div style="flex:2;">
                    <input type="text" placeholder="選択肢 (カンマ区切り: 赤,青,黄)" 
                           value="${escapeHtml(options.join(','))}" 
                           ${qType==='text' ? 'disabled' : 'style="background:white;"'}
                           onchange="updateQ(${index}, 'options', this.value)">
                </div>
            </div>
        </div>`;
        container.insertAdjacentHTML('beforeend', html);
    });
}

// 質問追加
window.addQuestion = function() {
    questions.push({ type: 'text', question: '', options: [] });
    renderQuestions();
};

// 質問削除
window.removeQuestion = function(index) {
    questions.splice(index, 1);
    renderQuestions();
};

// データ更新
window.updateQ = function(index, field, value) {
    if (field === 'options') {
        questions[index].options = value.split(',').map(s => s.trim()).filter(s => s);
    } else {
        questions[index][field] = value;
    }
    if (field === 'type') renderQuestions();
};

function escapeHtml(text) {
    if (!text) return "";
    return text.toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
