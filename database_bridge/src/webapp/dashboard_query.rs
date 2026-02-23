// webapp/dashboard_query.rs
// Why: Dashboard（Quart）固有の集計クエリをここに格納する。
//      Python の webapp.py::index() 内に直書きされていた SQL を移植・最適化する。

use sqlx::mysql::MySqlPool;
use serde::Serialize;

use crate::db::{log_repo, models::BridgeResult, models::OperationLog, models::Survey, survey_repo};

/// ダッシュボードの初期表示に必要なデータをまとめた返却型。
///
/// Why: Python 側では surveys と logs を直列クエリで取得していたが、
///      `tokio::try_join!` で並列化し、レイテンシを 最大クエリ時間に削減。
#[derive(Debug, Serialize)]
pub struct DashboardData {
    pub surveys: Vec<Survey>,
    pub logs: Vec<OperationLog>,
}

/// ダッシュボード表示に必要なデータを並列クエリで取得する。
///
/// Python (webapp.py::index()): surveys を SELECT → logs を SELECT（直列 2 クエリ）
/// Rust: tokio::try_join! で同時発行（並列 2 クエリ）
pub async fn fetch_dashboard_data(
    pool: &MySqlPool,
    owner_id: &str,
) -> BridgeResult<DashboardData> {
    let (surveys, logs) = tokio::try_join!(
        survey_repo::find_by_owner(pool, owner_id, None),
        log_repo::find_recent(pool, 30),
    )?;

    Ok(DashboardData { surveys, logs })
}

/// ユーザーが属するギルド ID リストと設定ギルド ID を照合する。
///
/// Why: Python では Discord API 呼び出しと照合ロジックが webapp.py に混在していたが、
///      DB 照合部分のみをここに分離する（API 呼び出しは Python 側に残留）。
/// Note: Phase 3-B 以降で DB に guild_members テーブルが追加される場合は
///       本関数でクエリを発行する。現時点ではユーティリティとしてスタブを配置。
pub fn verify_guild_membership(user_guild_ids: &[String], target_guild_id: &str) -> bool {
    user_guild_ids.iter().any(|id| id == target_guild_id)
}
