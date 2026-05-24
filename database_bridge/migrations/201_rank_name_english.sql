-- 201_rank_name_english.sql
-- ランク称号名を英語化（閾値・ロールIDは維持）

UPDATE titles SET name = 'Iron',     description = 'ラウンジランク Iron 達成'     WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 0;
UPDATE titles SET name = 'Bronze',   description = 'ラウンジランク Bronze 達成'   WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 2000;
UPDATE titles SET name = 'Silver',   description = 'ラウンジランク Silver 達成'   WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 4000;
UPDATE titles SET name = 'Gold',     description = 'ラウンジランク Gold 達成'     WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 6000;
UPDATE titles SET name = 'Platinum', description = 'ラウンジランク Platinum 達成' WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 8000;
UPDATE titles SET name = 'Diamond',  description = 'ラウンジランク Diamond 達成'  WHERE unlock_type = 'lounge_rank' AND unlock_threshold = 10000;
