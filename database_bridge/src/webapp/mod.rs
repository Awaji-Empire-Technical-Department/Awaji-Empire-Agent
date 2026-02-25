// webapp/mod.rs
// Why: Webダッシュボード固有の集計・権限照合クエリを格納する層。
//      db/ を参照するが、bot/ には依存しない。

pub mod dashboard_query;
