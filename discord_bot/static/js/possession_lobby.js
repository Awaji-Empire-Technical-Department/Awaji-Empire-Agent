// static/js/possession_lobby.js

// ----------------------------------------------------
// グローバル変数群 (lobby.html側で定義済み)
// window.LOBBY_PASSCODE
// window.MY_USER_ID
// window.WEBSOCKET_URL
// ----------------------------------------------------

let socket = null;
let reconnectTimer = null;

// ====================================================
// 1. WebSocket 管理
// ====================================================

function connectWebSocket() {
    console.log(`[WS] Connecting to ${window.WEBSOCKET_URL}...`);
    socket = new WebSocket(window.WEBSOCKET_URL);

    socket.onopen = () => {
        console.log("[WS] Connected successfully.");
        if (reconnectTimer) {
            clearInterval(reconnectTimer);
            reconnectTimer = null;
        }

        // 接続直後に自分の入ってるロビーを伝える (Rustの実装次第ですが、今回はBroadcast購読用に送るのが一般的)
        // もしRust側でロビー単位のチャンネル分離が未実装なら全受信してJS側でフィルタします
        socket.send(JSON.stringify({
            "action": "subscribe",
            "passcode": window.LOBBY_PASSCODE,
            "user_id": window.MY_USER_ID
        }));
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleLobbyEvent(data);
        } catch (e) {
            console.error("[WS] Failed to parse message:", e);
        }
    };

    socket.onclose = () => {
        console.warn("[WS] Connection closed. Attempting to reconnect in 5 seconds...");
        if (!reconnectTimer) {
            reconnectTimer = setInterval(connectWebSocket, 5000);
        }
    };

    socket.onerror = (err) => {
        console.error("[WS] Error:", err);
    };
}

// ====================================================
// 2. イベントハンドリング
// ====================================================

function handleLobbyEvent(event) {
    // 別のロビーのイベントなら無視 (Rust側で全ロビーにブロードキャストしている場合の防御)
    if (event.passcode && event.passcode !== window.LOBBY_PASSCODE) {
        return;
    }

    console.log("[WS] Lobby Event received:", event);

    switch (event.type) {
        case "member_status_updated":
            updateMemberStatus(event.user_id, event.status);
            break;

        case "room_updated":
            // ロビーの設定変更やHost移動時 -> 念のためリロードするかUI部分更新
            // 今回はシンプルにリロードを促すか自動リロード
            console.log("Room updated. Reloading is recommended.");
            break;

        case "tournament_started":
            alert("大会が開始されました！");
            location.reload(); // 大会開始でUIが大きく変わるためリロード推奨
            break;

        case "match_created":
        case "match_winner_reported":
            // ブラケット情報が更新されたので再描画
            loadAndRenderBracket();
            break;

        case "member_joined":
            // 新しいメンバーが入った
            console.log(`User ${event.user_id} joined.`);
            // リストを更新するかリロード (シンプルにリロード)
            location.reload();
            break;

        default:
            console.log("Unhandled event type:", event.type);
    }
}

// ====================================================
// 3. UI 更新ロジック (Status Badge)
// ====================================================

function updateMemberStatus(userId, statusText) {
    const td = document.getElementById(`status-${userId}`);
    if (!td) return;

    let badgeClass = "badge-secondary";
    let iconClass = "fa-circle";
    let label = "オフライン";

    // Status mapping
    // offine -> ⚪
    // online -> 🔵
    // waiting -> 🟢 受付中
    // playing -> 🔴 対戦中
    if (statusText === 'online') {
        badgeClass = "badge-primary";
        label = "オンライン";
    } else if (statusText === 'waiting') {
        badgeClass = "badge-success";
        label = "受付中(ホスト待機)";
    } else if (statusText === 'playing') {
        badgeClass = "badge-danger";
        label = "対戦中";
    }

    td.innerHTML = `<span class="badge ${badgeClass} status-badge"><i class="fas ${iconClass}" style="font-size: 0.7em;"></i> ${label}</span>`;
}

// ====================================================
// 4. Bracketry (トーナメント表) レンダリング
// ====================================================

async function loadAndRenderBracket() {
    const container = document.getElementById('tournament-bracket-container');
    if (!container) return;

    try {
        // Rust API から最新の試合情報を取得
        // ※ CORSやURL設計に合わせてパスは調整。ここでは同一オリジン（QuartがProxyしてる等）を想定するか、
        // Bridge APIが直叩きできるならそちらへ。今回はMock的に表示ロジックのみ組み込みます。

        // 仮データの仕組み: (本来は fetch(`/api/bridge/lobby/rooms/${window.LOBBY_PASSCODE}/matches`) 等)
        const mockData = {
            rounds: [
                {
                    name: "Round 1",
                    matches: [
                        {
                            id: "m1",
                            matchStatus: "Played",
                            homeTeam: { id: "u1", name: "Player 1", isWinner: true },
                            awayTeam: { id: "u2", name: "Player 2", isWinner: false },
                            homeScore: 1,
                            awayScore: 0
                        },
                        {
                            id: "m2",
                            matchStatus: "Scheduled",
                            homeTeam: { id: "u3", name: "Player 3" },
                            awayTeam: { id: "u4", name: "Player 4" }
                        }
                    ]
                },
                {
                    name: "Final",
                    matches: [
                        {
                            id: "m3",
                            matchStatus: "Scheduled",
                            homeTeam: { id: "u1", name: "Player 1" },
                            awayTeam: null // TBD
                        }
                    ]
                }
            ]
        };

        // Containerの中身をクリア
        container.innerHTML = "";

        // Bracketry の初期化
        bracketry.createBracket(mockData, container, {
            disabledItems: [], // UI操作オフ
            navButtonsPosition: 'top',
        });

    } catch (err) {
        console.error("Failed to render bracket:", err);
        container.innerHTML = `<p style="text-align:center; padding-top:180px; color:#888;">ブラケット情報の読み込みに失敗しました</p>`;
    }
}

// ====================================================
// Main Initialization
// ====================================================

document.addEventListener("DOMContentLoaded", () => {
    // 1. WebSocket 接続開始
    connectWebSocket();

    // 2. Tournamentの時のブラケット初回描画
    if (document.getElementById('tournament-bracket-container')) {
        loadAndRenderBracket();
    }
});
