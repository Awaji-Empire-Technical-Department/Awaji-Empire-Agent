// main.rs
// Why: バイナリエントリポイント。
//      Phase 3-A では「DB 接続ヘルスチェック」だけを行う CLI として機能する。
//      将来的には管理ツールのエントリポイントになる。

use database_bridge::db::connection;
use tracing::info;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // ロギング初期化（RUST_LOG 環境変数で制御）
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("database_bridge=info".parse()?),
        )
        .init();

    // .env 読み込み
    dotenvy::dotenv().ok();

    info!("🚀 database_bridge starting...");

    let pool = connection::create_pool().await?;
    let ok = connection::health_check(&pool).await;

    if ok {
        info!("✅ All checks passed. database_bridge is ready.");
    } else {
        eprintln!("❌ Health check failed. Check DB connection settings.");
        std::process::exit(1);
    }

    Ok(())
}
