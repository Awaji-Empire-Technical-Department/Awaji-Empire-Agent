-- 004_add_lobby_description.sql

-- Add description column to matchmaking_rooms table
ALTER TABLE matchmaking_rooms
ADD COLUMN description TEXT NULL AFTER title;
