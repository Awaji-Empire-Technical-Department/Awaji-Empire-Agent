-- 008_lounge_final_score.sql
-- Phase 3: ラウンジ申告方式変更（レースごと申告 → セッション最終順位申告）

-- ============================================================
-- lounge_session_members に除外フラグを追加
-- ============================================================
ALTER TABLE lounge_session_members
    ADD COLUMN excluded BOOLEAN NOT NULL DEFAULT FALSE;

-- ============================================================
-- lounge_session_final_scores: セッション最終順位申告テーブル
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_session_final_scores (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    final_rank      TINYINT NOT NULL,       -- 1〜24
    mmr_delta       INT NOT NULL DEFAULT 0, -- finish_session 時に確定
    submitted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_session_user (session_id, user_id),
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id) ON DELETE CASCADE
);

-- ============================================================
-- 廃止テーブルの削除（FK順に削除する）
-- ============================================================
DROP TABLE IF EXISTS lounge_race_scores;
DROP TABLE IF EXISTS lounge_course_history;
DROP TABLE IF EXISTS lounge_race_results;
