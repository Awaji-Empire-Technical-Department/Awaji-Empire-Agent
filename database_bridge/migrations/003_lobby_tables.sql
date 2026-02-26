-- 003_lobby_tables.sql
-- Description: セキュア対戦ロビーシステム用のテーブル定義

-- 1. user_networks（ユーザー情報・WARPキャッシュ）
CREATE TABLE IF NOT EXISTS user_networks (
    discord_id  BIGINT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    virtual_ip  VARCHAR(15),
    is_active   BOOLEAN DEFAULT FALSE,
    is_staff    BOOLEAN DEFAULT FALSE,
    agreed_at   TIMESTAMP NULL,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 2. matchmaking_rooms（動的ロビー）
CREATE TABLE IF NOT EXISTS matchmaking_rooms (
    passcode            VARCHAR(32) PRIMARY KEY,
    host_id             BIGINT NOT NULL,
    mode                ENUM('free', 'tournament') DEFAULT 'free',
    title               VARCHAR(255) DEFAULT '新対戦ロビー',
    tournament_start_at TIMESTAMP NULL,
    is_approved         BOOLEAN DEFAULT FALSE,
    expires_at          TIMESTAMP NOT NULL,
    FOREIGN KEY (host_id) REFERENCES user_networks(discord_id)
);

-- 3. lobby_members（ロビー参加者・役割管理）
CREATE TABLE IF NOT EXISTS lobby_members (
    room_passcode VARCHAR(32),
    user_id       BIGINT,
    role          ENUM('player', 'staff') DEFAULT 'player',
    PRIMARY KEY (room_passcode, user_id),
    FOREIGN KEY (room_passcode) REFERENCES matchmaking_rooms(passcode) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user_networks(discord_id) ON DELETE CASCADE
);

-- 4. tournament_matches（大会ブラケット）
CREATE TABLE IF NOT EXISTS tournament_matches (
    match_id      INT AUTO_INCREMENT PRIMARY KEY,
    room_passcode VARCHAR(32),
    player1_id    BIGINT,
    player2_id    BIGINT,
    winner_id     BIGINT NULL,
    status        ENUM('waiting', 'playing', 'finished') DEFAULT 'waiting',
    FOREIGN KEY (room_passcode) REFERENCES matchmaking_rooms(passcode) ON DELETE CASCADE
);

-- 5. admin_logs（管理操作監査ログ）
-- 既存の operation_logs テーブルに類似していますが、ロビー用の特権監査に特化しています
CREATE TABLE IF NOT EXISTS admin_logs (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id   BIGINT NOT NULL,
    action     VARCHAR(64) NOT NULL,
    target_id  BIGINT,
    detail     TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
