-- 004_lobby_updates.sql
-- Description: ロビー機能アップデートに伴うスキーマ変更

-- ユーザー名表示機能のため、user_networks に username カラムを追加
ALTER TABLE user_networks ADD COLUMN username VARCHAR(255) AFTER email;
