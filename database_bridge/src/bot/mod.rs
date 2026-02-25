// bot/mod.rs
// Why: Discord Bot 固有のロジック（UPSERT・DM フラグ等）を格納する層。
//      db/ を参照するが、webapp/ には依存しない。

pub mod survey_handler;
