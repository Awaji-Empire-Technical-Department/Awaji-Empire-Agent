// db/connection.rs
// Why: DB 接続プールの生成・管理をここに一元化する。
//      Python 側では SurveyLogic と webapp.py がそれぞれ個別にプールを生成していたが、
//      Rust では Arc<Pool> を共有する設計とする。

use sqlx::mysql::{MySqlPool, MySqlPoolOptions};
use tracing::{error, info};

use super::models::BridgeResult;

/// 環境変数から MariaDB 接続 URL を構築する。
///
/// Why: Python の `_build_database_url()` に相当する。
///      ここだけに接続 URL のフォーマット知識を集約する。
fn build_url() -> String {
    let user = std::env::var("DB_USER").unwrap_or_else(|_| "root".into());
    let password = std::env::var("DB_PASS").unwrap_or_default();
    let host = std::env::var("DB_HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let database = std::env::var("DB_NAME").unwrap_or_else(|_| "bot_db".into());
    format!("mysql://{user}:{password}@{host}/{database}")
}

/// MariaDB コネクションプールを生成して返す。
///
/// Why: `pool_recycle=3600` (Python) 相当は sqlx では
///      `idle_timeout` で設定する。
pub async fn create_pool() -> BridgeResult<MySqlPool> {
    let url = build_url();
    let pool = MySqlPoolOptions::new()
        .max_connections(10)
        .idle_timeout(std::time::Duration::from_secs(3600)) // Python の pool_recycle 相当
        .connect(&url)
        .await?;

    info!("✅ Database connection pool created.");
    Ok(pool)
}

/// 接続の疎通確認（起動時ヘルスチェック用）。
///
/// Why: Python の `bot.py::get_db_connection()` は同期接続で起動時テストを行っていた。
///      Rust では非同期で簡易クエリを発行して確認する。
pub async fn health_check(pool: &MySqlPool) -> bool {
    match sqlx::query("SELECT 1").execute(pool).await {
        Ok(_) => {
            info!("✅ Database health check passed.");
            true
        }
        Err(e) => {
            error!("❌ Database health check failed: {e}");
            false
        }
    }
}
