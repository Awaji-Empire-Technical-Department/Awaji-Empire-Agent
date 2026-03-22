-- 006_tournament_updates.sql
ALTER TABLE lobby_members ADD COLUMN status VARCHAR(16) DEFAULT 'offline';

ALTER TABLE tournament_matches ADD COLUMN round_num INT DEFAULT 1;
ALTER TABLE tournament_matches ADD COLUMN match_index INT DEFAULT 1;
ALTER TABLE tournament_matches ADD COLUMN next_match_id INT NULL;
ALTER TABLE tournament_matches ADD COLUMN score1 INT DEFAULT 0;
ALTER TABLE tournament_matches ADD COLUMN score2 INT DEFAULT 0;
ALTER TABLE tournament_matches ADD COLUMN win_condition INT DEFAULT 1; -- Necessary wins (1 means 1 win needed, 2 means BO3, etc.)
