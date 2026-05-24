-- 010_event_location.sql
-- events テーブルに location カラムを追加（部制なし時のカレンダー場所情報）

ALTER TABLE events
    ADD COLUMN location VARCHAR(255) NULL COMMENT '集合場所（部制なし用）' AFTER notes;
