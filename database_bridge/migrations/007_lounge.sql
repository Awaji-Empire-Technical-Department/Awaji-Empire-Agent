-- 007_lounge.sql
-- Phase 2: マリオカートワールド ラウンジシステム固有テーブル

-- ============================================================
-- lounge_players: ラウンジ参加者のMMR・レート管理
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_players (
    user_id         BIGINT PRIMARY KEY,
    mmr             INT NOT NULL DEFAULT 1000,
    peak_mmr        INT NOT NULL DEFAULT 1000,
    total_races     INT NOT NULL DEFAULT 0,
    total_sessions  INT NOT NULL DEFAULT 0,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ============================================================
-- lounge_sessions: ラウンジセッション
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_sessions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    room_id         VARCHAR(32) NOT NULL,   -- matchmaking_rooms.passcode と紐づけ
    mode            ENUM('ffa', '2v', '3v') NOT NULL DEFAULT 'ffa',
    total_races     TINYINT NOT NULL DEFAULT 12,
    current_race    TINYINT NOT NULL DEFAULT 0,
    status          ENUM('waiting', 'in_progress', 'finished') DEFAULT 'waiting',
    host_id         BIGINT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- lounge_race_results: レース単位の結果
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_race_results (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT NOT NULL,
    race_number     TINYINT NOT NULL,
    course_name     VARCHAR(128) NOT NULL,
    is_void         BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id) ON DELETE CASCADE
);

-- ============================================================
-- lounge_race_scores: プレイヤー個別スコア
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_race_scores (
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    race_result_id          BIGINT NOT NULL,
    user_id                 BIGINT NOT NULL,
    position                TINYINT NULL,           -- NULL = 回線落ち
    points                  INT NOT NULL DEFAULT 0,
    is_disconnect           BOOLEAN DEFAULT FALSE,
    disconnect_reported_at  DATETIME NULL,
    status                  ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    FOREIGN KEY (race_result_id) REFERENCES lounge_race_results(id) ON DELETE CASCADE
);

-- ============================================================
-- lounge_teams: チーム編成（2v/3v用）
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_teams (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  BIGINT NOT NULL,
    tag         VARCHAR(16) NOT NULL,
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lounge_team_members (
    team_id     BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES lounge_teams(id) ON DELETE CASCADE
);

-- ============================================================
-- lounge_course_history: コース使用履歴（重複ペナルティ用）
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_course_history (
    session_id  BIGINT NOT NULL,
    course_key  VARCHAR(64) NOT NULL,   -- 正規化済みコース識別子
    PRIMARY KEY (session_id, course_key),
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id) ON DELETE CASCADE
);

-- ============================================================
-- lounge_session_members: セッション参加者一覧
-- ============================================================
CREATE TABLE IF NOT EXISTS lounge_session_members (
    session_id  BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    joined_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, user_id),
    FOREIGN KEY (session_id) REFERENCES lounge_sessions(id) ON DELETE CASCADE
);
