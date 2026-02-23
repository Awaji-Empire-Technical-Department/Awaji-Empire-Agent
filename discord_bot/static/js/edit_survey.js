// --- Microsoft Forms風 アンケートエディタ (条件分岐 & その他対応版) ---

let questions = window.initialQuestions || [];

document.addEventListener('DOMContentLoaded', () => {
    renderQuestions();
});

function renderQuestions() {
    const container = document.getElementById('questionsContainer');
    container.innerHTML = '';

    questions.forEach((q, index) => {
        // --- カード枠の作成 ---
        const card = document.createElement('div');
        card.className = 'panel';
        card.style.position = 'relative';
        card.style.borderLeft = '4px solid var(--accent-blue)';
        card.style.padding = '20px';
        card.style.marginBottom = '20px';

        // 削除ボタン
        const deleteBtn = document.createElement('button');
        deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
        deleteBtn.className = 'btn btn-gray btn-sm';
        deleteBtn.style.position = 'absolute';
        deleteBtn.style.top = '15px';
        deleteBtn.style.right = '15px';
        deleteBtn.onclick = () => removeQuestion(index);

        // 質問番号バッジ
        const qNum = document.createElement('span');
        qNum.className = 'status-badge active';
        qNum.textContent = `Q${index + 1}`;
        qNum.style.marginBottom = '10px';
        qNum.style.marginRight = '10px';

        // 質問文入力
        const qInput = document.createElement('input');
        qInput.type = 'text';
        qInput.placeholder = '質問を入力してください';
        qInput.value = q.text || '';
        qInput.style.width = '100%';
        qInput.style.padding = '10px';
        qInput.style.marginBottom = '15px';
        qInput.style.fontWeight = 'bold';
        qInput.style.border = '1px solid #ddd';
        qInput.style.borderRadius = '4px';
        qInput.oninput = (e) => { questions[index].text = e.target.value; updateHiddenJson(); };

        // 質問タイプ選択
        const typeSelect = document.createElement('select');
        typeSelect.style.padding = '8px';
        typeSelect.style.marginBottom = '15px';
        typeSelect.style.width = '100%';
        typeSelect.innerHTML = `
            <option value="text">記述式 (テキスト)</option>
            <option value="radio">ラジオボタン (1つ選択)</option>
            <option value="checkbox">チェックボックス (複数選択)</option>
        `;
        typeSelect.value = q.type || 'text';
        typeSelect.onchange = (e) => {
            questions[index].type = e.target.value;
            if (['radio', 'checkbox'].includes(e.target.value) && !questions[index].options) {
                questions[index].options = ['選択肢1'];
            }
            renderQuestions();
        };

        card.appendChild(deleteBtn);
        card.appendChild(qNum);
        card.appendChild(qInput);
        card.appendChild(typeSelect);

        // --- 選択肢エリア ---
        if (['radio', 'checkbox'].includes(q.type)) {
            const optionsContainer = document.createElement('div');
            optionsContainer.className = 'options-list';

            (q.options || []).forEach((opt, optIdx) => {
                const optRow = document.createElement('div');
                optRow.style.display = 'flex';
                optRow.style.alignItems = 'center';
                optRow.style.marginBottom = '8px';
                
                const icon = document.createElement('i');
                icon.className = q.type === 'radio' ? 'far fa-circle' : 'far fa-square';
                icon.style.color = '#ccc';
                icon.style.marginRight = '8px';

                const optInput = document.createElement('input');
                optInput.type = 'text';
                optInput.value = opt;
                optInput.placeholder = `選択肢 ${optIdx + 1}`;
                optInput.style.flex = '1';
                optInput.style.padding = '8px';
                optInput.style.border = '1px solid #eee';
                optInput.oninput = (e) => { questions[index].options[optIdx] = e.target.value; updateHiddenJson(); };

                // 選択肢削除ボタン
                const delOptBtn = document.createElement('button');
                delOptBtn.innerHTML = '<i class="fas fa-times"></i>';
                delOptBtn.style.background = 'none';
                delOptBtn.style.border = 'none';
                delOptBtn.style.color = '#999';
                delOptBtn.style.cursor = 'pointer';
                delOptBtn.style.marginLeft = '5px';
                delOptBtn.onclick = () => {
                    questions[index].options.splice(optIdx, 1);
                    renderQuestions();
                };

                optRow.appendChild(icon);
                optRow.appendChild(optInput);
                optRow.appendChild(delOptBtn);
                optionsContainer.appendChild(optRow);
            });

            // 「選択肢を追加」ボタン
            const btnArea = document.createElement('div');
            btnArea.style.display = 'flex';
            btnArea.style.gap = '15px';
            btnArea.style.marginTop = '10px';

            const addOptBtn = document.createElement('button');
            addOptBtn.className = 'btn-text-only';
            addOptBtn.style.color = 'var(--accent-blue)';
            addOptBtn.style.background = 'none';
            addOptBtn.style.border = 'none';
            addOptBtn.style.cursor = 'pointer';
            addOptBtn.innerHTML = '<i class="fas fa-plus"></i> 選択肢を追加';
            addOptBtn.onclick = (e) => {
                e.preventDefault();
                questions[index].options.push(`選択肢 ${questions[index].options.length + 1}`);
                renderQuestions();
            };

            // ★「その他」を追加スイッチ
            const otherLabel = document.createElement('label');
            otherLabel.style.display = 'flex';
            otherLabel.style.alignItems = 'center';
            otherLabel.style.cursor = 'pointer';
            otherLabel.style.fontSize = '0.9rem';
            otherLabel.style.color = '#666';
            
            const otherCheck = document.createElement('input');
            otherCheck.type = 'checkbox';
            otherCheck.checked = !!questions[index].has_other;
            otherCheck.style.marginRight = '5px';
            otherCheck.onchange = (e) => {
                questions[index].has_other = e.target.checked;
                updateHiddenJson();
            };
            
            otherLabel.appendChild(otherCheck);
            otherLabel.appendChild(document.createTextNode('「その他」を追加'));

            btnArea.appendChild(addOptBtn);
            btnArea.appendChild(otherLabel);
            card.appendChild(optionsContainer);
            card.appendChild(btnArea);
        }

        // --- ★条件分岐 (ロジック) 設定エリア ---
        // Q1以外で設定可能（前の質問に依存するため）
        if (index > 0) {
            const logicArea = document.createElement('div');
            logicArea.style.marginTop = '20px';
            logicArea.style.paddingTop = '15px';
            logicArea.style.borderTop = '1px dashed #eee';

            const logicTitle = document.createElement('div');
            logicTitle.style.fontWeight = 'bold';
            logicTitle.style.fontSize = '0.9rem';
            logicTitle.style.marginBottom = '10px';
            logicTitle.style.color = '#555';
            logicTitle.innerHTML = '<i class="fas fa-code-branch"></i> 表示条件 (Branch Logic)';
            
            // ロジックデータ: { trigger_idx: 0, trigger_val: "A" }
            const logic = questions[index].logic || {};

            // 1. トリガーとなる質問を選ぶ
            const triggerSelect = document.createElement('select');
            triggerSelect.style.padding = '5px';
            triggerSelect.style.marginRight = '10px';
            triggerSelect.innerHTML = '<option value="">(常に表示)</option>';
            
            // 自分より前の、選択式の質問だけを候補にする
            for (let i = 0; i < index; i++) {
                if (['radio', 'select'].includes(questions[i].type)) { // checkboxは複雑なので一旦除外推奨だが今回はradioメインで
                    triggerSelect.innerHTML += `<option value="${i}" ${logic.trigger_idx == i ? 'selected' : ''}>Q${i+1}: ${questions[i].text.substring(0,10)}...</option>`;
                }
            }

            // 2. トリガーとなる回答を選ぶ
            const valSelect = document.createElement('select');
            valSelect.style.padding = '5px';
            valSelect.style.display = logic.trigger_idx !== undefined ? 'inline-block' : 'none';

            const updateValOptions = (targetIdx) => {
                valSelect.innerHTML = '<option value="">回答を選択...</option>';
                if (targetIdx !== '' && questions[targetIdx]) {
                    questions[targetIdx].options.forEach(opt => {
                        valSelect.innerHTML += `<option value="${opt}" ${logic.trigger_val == opt ? 'selected' : ''}>${opt}</option>`;
                    });
                }
            };

            if (logic.trigger_idx !== undefined) updateValOptions(logic.trigger_idx);

            // イベント処理
            triggerSelect.onchange = (e) => {
                const tidx = e.target.value;
                if (tidx === '') {
                    delete questions[index].logic;
                    valSelect.style.display = 'none';
                } else {
                    questions[index].logic = { trigger_idx: tidx, trigger_val: '' };
                    valSelect.style.display = 'inline-block';
                    updateValOptions(tidx);
                }
                updateHiddenJson();
            };

            valSelect.onchange = (e) => {
                if (questions[index].logic) {
                    questions[index].logic.trigger_val = e.target.value;
                    updateHiddenJson();
                }
            };

            logicArea.appendChild(logicTitle);
            logicArea.appendChild(document.createTextNode('この質問は '));
            logicArea.appendChild(triggerSelect);
            logicArea.appendChild(valSelect);
            logicArea.appendChild(document.createTextNode(' が選ばれた時だけ表示する'));

            card.appendChild(logicArea);
        }

        container.appendChild(card);
    });

    updateHiddenJson();
}

function addQuestion() {
    questions.push({ text: '', type: 'text', options: [], has_other: false });
    renderQuestions();
}

function removeQuestion(index) {
    if (confirm('この質問を削除しますか？')) {
        questions.splice(index, 1);
        renderQuestions();
    }
}

function updateHiddenJson() {
    document.getElementById('questionsJson').value = JSON.stringify(questions);
}

document.getElementById('surveyForm').addEventListener('submit', () => {
    updateHiddenJson();
});
