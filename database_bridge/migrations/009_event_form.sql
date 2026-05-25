-- 009_event_form.sql
-- イベント参加フォーム機能: events / event_sessions / event_participants

CREATE TABLE IF NOT EXISTS events (
    id                   INT          NOT NULL AUTO_INCREMENT,
    survey_id            INT          NOT NULL UNIQUE,
    title                VARCHAR(255) NOT NULL,
    fee                  INT          NULL     COMMENT '参加費（円）。NULL=無料',
    notes                TEXT         NULL     COMMENT '全体向け備考',
    status               VARCHAR(20)  NOT NULL DEFAULT 'draft' COMMENT 'draft|open|closed',
    -- 部制なし用の日時（部制ありの場合は event_sessions 側で管理）
    event_date           DATETIME     NULL     COMMENT '開始日時（部制なし用）',
    end_date             DATETIME     NULL     COMMENT '終了日時（部制なし用）。NULL=event_date+2時間',
    application_deadline DATETIME     NULL     COMMENT '応募締切。NULL=無期限',
    created_at           DATETIME     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 部（time slot）。0件なら部制なし。
CREATE TABLE IF NOT EXISTS event_sessions (
    id         INT          NOT NULL AUTO_INCREMENT,
    event_id   INT          NOT NULL,
    name       VARCHAR(100) NOT NULL COMMENT '例: 1部, 2部',
    event_date DATETIME     NULL     COMMENT '開始日時',
    end_date   DATETIME     NULL     COMMENT '終了日時。NULL=event_date+2時間',
    location   VARCHAR(255) NULL     COMMENT '集合場所',
    capacity   INT          NULL     COMMENT '定員。NULL=無制限',
    PRIMARY KEY (id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 参加者ごとの応募・割り当て状況。
CREATE TABLE IF NOT EXISTS event_participants (
    id                   INT         NOT NULL AUTO_INCREMENT,
    event_id             INT         NOT NULL,
    user_id              BIGINT      NOT NULL,
    response_id          INT         NULL     COMMENT 'アンケート回答ID',
    session_id           INT         NULL     COMMENT '割り当て部。NULL=不参加',
    preferred_session_ids TEXT        NULL     COMMENT '希望部IDのJSON配列 例: [1,2]',
    approval             VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending|accepted|rejected|waitlist',
    personal_note        TEXT        NULL     COMMENT 'オーナーの個人メモ（参加者非公開）',
    access_token         VARCHAR(64) NULL     UNIQUE COMMENT '個人確認ページ用トークン',
    notified_at          DATETIME    NULL     COMMENT 'DM送信日時。NULL=未送信',
    PRIMARY KEY (id),
    UNIQUE KEY uq_event_user (event_id, user_id),
    FOREIGN KEY (event_id)   REFERENCES events(id)         ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES event_sessions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
