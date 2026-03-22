use axum::{
    extract::{ws::{Message, WebSocket, WebSocketUpgrade}, State},
    response::IntoResponse,
};
use futures::{SinkExt, StreamExt};
use serde_json::json;
use crate::api::AppState;

pub async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    let mut rx = state.tx.subscribe();

    // 接続成功メッセージ
    let init_msg = json!({
        "type": "connected",
        "message": "Welcome to Hyouibana Lobby WebSocket"
    }).to_string();
    let _ = sender.send(Message::Text(init_msg.into())).await;

    // ブロードキャストチャネルから受信したメッセージをクライアントへ転送
    let mut send_task = tokio::spawn(async move {
        while let Ok(msg) = rx.recv().await {
            // axum 0.8 では Message::Text は Utf8Bytes 等を受け取るが、String から into() 可能
            if sender.send(Message::Text(msg.into())).await.is_err() {
                break; // クライアントが切断された
            }
        }
    });

    // クライアントからのメッセージを受信（今回は基本サーバープッシュのみだがPing等用）
    let mut recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = receiver.next().await {
            if let Message::Text(text) = msg {
                tracing::debug!("Received ws msg: {}", text);
            }
        }
    });

    // どちらかが終了したらもう一方も終了させる
    tokio::select! {
        _ = (&mut send_task) => recv_task.abort(),
        _ = (&mut recv_task) => send_task.abort(),
    }
}
