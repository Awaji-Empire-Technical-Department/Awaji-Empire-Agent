// lib.rs
// Why: バイナリ (main.rs) とライブラリ (lib.rs) を分離することで、
//      将来的な PyO3 / FFI バインディングや統合テストが書きやすくなる。

pub mod db;
pub mod bot;
pub mod webapp;
pub mod api;
