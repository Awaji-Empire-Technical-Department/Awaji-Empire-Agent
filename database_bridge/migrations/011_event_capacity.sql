-- 011_event_capacity.sql
-- 部制なしイベントに定員（capacity）を追加

ALTER TABLE events
    ADD COLUMN capacity INT NULL COMMENT '部制なし時の定員。NULL=無制限' AFTER notes;
