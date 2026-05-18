-- 006_general_tournament.sql
-- Phase 1: 汎用ゲーム大会システム + 称号システム

-- ============================================================
-- game_titles: 対応ゲームマスタ
-- ============================================================
CREATE TABLE IF NOT EXISTS game_titles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(64) NOT NULL,
    match_type  ENUM('1v1', 'multiplayer') NOT NULL,
    max_players TINYINT NOT NULL DEFAULT 2,
    score_type  ENUM('win_loss', 'point_sum') NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE
);

INSERT IGNORE INTO game_titles (id, name, match_type, max_players, score_type) VALUES
    (1, 'マリオカート8 デラックス', 'multiplayer', 12, 'point_sum'),
    (2, 'マリオカートワールド',    'multiplayer', 24, 'point_sum'),
    (3, '遊び大全',                '1v1',          2, 'win_loss'),
    (4, 'その他',                  '1v1',          2, 'win_loss');

-- ============================================================
-- point_tables: 順位ポイント配点マスタ
-- ============================================================
CREATE TABLE IF NOT EXISTS point_tables (
    game_title_id INT NOT NULL,
    position      TINYINT NOT NULL,
    points        INT NOT NULL,
    PRIMARY KEY (game_title_id, position),
    FOREIGN KEY (game_title_id) REFERENCES game_titles(id)
);

-- マリオカート8DX（12人用・公式準拠）
INSERT IGNORE INTO point_tables (game_title_id, position, points) VALUES
    (1,1,15),(1,2,12),(1,3,10),(1,4,9),(1,5,8),
    (1,6,7),(1,7,6),(1,8,5),(1,9,4),(1,10,3),(1,11,2),(1,12,1);

-- マリオカートワールド（24人用 - FEATURE_LOUNGE.md §2.3 準拠）
-- 順位帯別配点
INSERT IGNORE INTO point_tables (game_title_id, position, points) VALUES
    (2,1,15),(2,2,12),(2,3,10),
    (2,4,9),(2,5,9),
    (2,6,8),(2,7,8),
    (2,8,7),(2,9,7),
    (2,10,6),(2,11,6),(2,12,6),
    (2,13,5),(2,14,5),(2,15,5),
    (2,16,4),(2,17,4),(2,18,4),
    (2,19,3),(2,20,3),(2,21,3),
    (2,22,2),(2,23,2),
    (2,24,1);

-- ============================================================
-- matchmaking_rooms: 既存テーブルに大会カラムを追加
-- ============================================================
ALTER TABLE matchmaking_rooms
    ADD COLUMN IF NOT EXISTS game_title_id  INT NULL AFTER mode,
    ADD COLUMN IF NOT EXISTS bracket_format ENUM('single_elimination', 'round_robin') DEFAULT 'single_elimination' AFTER game_title_id,
    ADD COLUMN IF NOT EXISTS wins_required  TINYINT DEFAULT 1 AFTER bracket_format,
    ADD COLUMN IF NOT EXISTS passcode_hash  VARCHAR(64) NULL AFTER wins_required;

-- ============================================================
-- match_scores: 多人数マッチのスコア記録
-- ============================================================
CREATE TABLE IF NOT EXISTS match_scores (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    match_id   INT NOT NULL,
    user_id    BIGINT NOT NULL,
    position   TINYINT NOT NULL,
    points     INT NOT NULL DEFAULT 0,
    status     ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    FOREIGN KEY (match_id) REFERENCES tournament_matches(match_id) ON DELETE CASCADE
);

-- ============================================================
-- titles: 称号マスタ
-- ============================================================
CREATE TABLE IF NOT EXISTS titles (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(64) NOT NULL,
    description         VARCHAR(256) NULL,
    -- unlock_type: tournament_win=大会優勝, lounge_rank=ラウンジMMR帯, manual=手動付与
    unlock_type         ENUM('tournament_win', 'lounge_rank', 'manual') NOT NULL DEFAULT 'manual',
    unlock_threshold    INT NULL,       -- lounge_rank: 下限MMR / tournament_win: 優勝回数
    discord_role_id     VARCHAR(32) NULL,   -- 紐づけるDiscordロールID（未設定可）
    is_active           BOOLEAN DEFAULT TRUE,
    display_order       INT DEFAULT 0,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 初期称号データ
INSERT IGNORE INTO titles (id, name, description, unlock_type, unlock_threshold, display_order) VALUES
    (1,  '鉄',          'ラウンジランク: 鉄（～1999 MMR）',      'lounge_rank', 0,     10),
    (2,  '銅',          'ラウンジランク: 銅（2000～3999 MMR）',   'lounge_rank', 2000,  20),
    (3,  '銀',          'ラウンジランク: 銀（4000～5999 MMR）',   'lounge_rank', 4000,  30),
    (4,  '金',          'ラウンジランク: 金（6000～7999 MMR）',   'lounge_rank', 6000,  40),
    (5,  'プラチナ',    'ラウンジランク: プラチナ（8000～9999）', 'lounge_rank', 8000,  50),
    (6,  'ダイヤ',      'ラウンジランク: ダイヤ（10000～）',      'lounge_rank', 10000, 60),
    (7,  'マスター',    'ラウンジランク: マスター（13000～）',    'lounge_rank', 13000, 70),
    (8,  '覇者',        '大会で初優勝を達成',                     'tournament_win', 1,  80),
    (9,  '連覇の王',    '大会で3回優勝を達成',                    'tournament_win', 3,  90),
    (10, '特別参加者',  '手動付与の特別称号',                     'manual', NULL,       100);

-- ============================================================
-- player_titles: プレイヤーが獲得した称号
-- ============================================================
CREATE TABLE IF NOT EXISTS player_titles (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    title_id    INT NOT NULL,
    earned_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_player_title (user_id, title_id),
    FOREIGN KEY (title_id) REFERENCES titles(id)
);

-- ============================================================
-- player_active_title: 装備中の称号（1人につき最大1つ）
-- ============================================================
CREATE TABLE IF NOT EXISTS player_active_title (
    user_id     BIGINT PRIMARY KEY,
    title_id    INT NOT NULL,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (title_id) REFERENCES titles(id)
);
