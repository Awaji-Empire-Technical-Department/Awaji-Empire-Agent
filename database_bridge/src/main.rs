// main.rs
// Why: HTTP サーバーエントリエントリポイント (IPC用)。
//      Phase 3-B では axum を使用してローカルのリクエストを受け付ける。

use database_bridge::db::connection;
use std::net::SocketAddr;
use tracing::{error, info};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // ロギング初期化（RUST_LOG 環境変数で制御）
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("database_bridge=info".parse()?)
                .add_directive("tower_http=debug".parse()?),
        )
        .init();

    // .env 読み込み
    dotenvy::dotenv().ok();

    info!("🚀 database_bridge starting...");

    // DB接続プールの作成
    let pool = match connection::create_pool().await {
        Ok(p) => p,
        Err(e) => {
            error!("❌ Failed to create DB pool: {}", e);
            std::process::exit(1);
        }
    };

    // 起動時のヘルスチェック
    if connection::health_check(&pool).await {
        info!("✅ Initial DB connection check passed.");
    } else {
        error!("❌ Initial DB health check failed.");
        std::process::exit(1);
    }

    // マイグレーションの自動実行
    info!("🔄 Running database migrations...");
    if let Err(e) = sqlx::migrate!("./migrations").run(&pool).await {
        error!("❌ Failed to run database migrations: {}", e);
        std::process::exit(1);
    }
    info!("✅ Database migrations applied successfully.");

    // ルーターの設定
    let app = database_bridge::api::create_router(pool);

    // アドレスの設定 (デフォルト 127.0.0.1:7878)
    let addr = SocketAddr::from(([127, 0, 0, 1], 7878));
    info!("📡 Listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
