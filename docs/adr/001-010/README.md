# ADR 001–010: Phase 2〜4 基盤アーキテクチャ

このディレクトリには、プロジェクト初期の基盤構築フェーズ（Phase 2〜4）に関する Architecture Decision Record が収録されています。

## 一覧

| No. | タイトル | ステータス | 日付 |
|-----|---------|-----------|------|
| [ADR-001](001-phase2-architecture-refactoring.md) | Phase 2 アーキテクチャ刷新・モジュール分離 | 承認済み | 2026-02-21 |
| [ADR-002](002-phase3-rust-database-bridge.md) | Phase 3 Rust Database Bridge 導入 | 承認済み | 2026-02-23 |
| [ADR-003](003-phase3b-python-rust-ipc-method.md) | Python ↔ Rust 通信方式に HTTP-based IPC を採用 | 承認済み | 2026-02-23 |
| [ADR-004](004-phase3c-bridge-error-and-css-split.md) | BridgeUnavailableError 導入と CSS 分割リファクタリング | 承認済み | 2026-02-24 |
| [ADR-005](005-phase3d-survey-response-fix.md) | Rust Bridge 型不一致修正・survey_responses UNIQUE KEY 追加 | 承認済み | 2026-02-25 |
| [ADR-006](006-phase3d-mass-mute-self-unblocking.md) | Bot 自身の権限復旧（Self-unblocking）の導入 | 承認済み | 2026-02-25 |
| [ADR-007](007-rust-migration-permission-engine.md) | 権限エンジンおよびログ統合の Rust 移行 | 承認済み | 2026-02-26 |
| [ADR-008](008-secure-lobby-system.md) | セキュア対戦ロビーシステムのアーキテクチャ選定 | 承認済み | 2026-02-26 |
| [ADR-009](009-lobby-system-fixes.md) | セキュア対戦ロビーシステム不具合修正・仕様補完 (Phase 4.1) | 承認済み | — |
| [ADR-010](010-lobby-websocket-tournament.md) | セキュア対戦ロビーの WebSocket 化と大会支援機能拡充 (Phase 4.2) | 実装済み | — |

## 概要

- **ADR-001〜004**: Python モノリスから Rust Bridge を挟んだ多層アーキテクチャへの刷新。HTTP-based IPC による Python ↔ Rust 通信方式の確立。
- **ADR-005〜006**: Phase 3-D の緊急修正。型不一致・DB スキーマ修正、および Bot 自身が権限を失った際の自己復旧メカニズムの導入。
- **ADR-007**: 権限エンジン・ログ基盤を Rust に移行し、パフォーマンスと一貫性を向上。
- **ADR-008〜010**: セキュアな対戦ロビーシステムの設計・実装・WebSocket 化。大会管理機能の拡充。
