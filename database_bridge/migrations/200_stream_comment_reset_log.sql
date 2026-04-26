-- 200_stream_comment_reset_log.sql
-- Why: #配信コメント チャンネルの月次リセット・Self Heal ログを永続化する。

CREATE TABLE IF NOT EXISTS stream_comment_reset_log (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    executed_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    triggered_by  VARCHAR(64)     NOT NULL COMMENT 'voice_keeper | fallback_scheduler | self_heal | Discord user ID',
    event_type    ENUM('monthly_reset', 'self_heal', 'manual_reset') NOT NULL,
    status        ENUM('success', 'partial', 'failed') NOT NULL,
    error_message TEXT            NULL,
    INDEX idx_executed_at (executed_at),
    INDEX idx_event_type  (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
