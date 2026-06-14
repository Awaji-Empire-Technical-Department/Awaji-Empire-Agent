-- 013_event_checkin.sql
-- 当日モード（チェックイン）: イベント当日の来場確認を記録する。

ALTER TABLE event_participants
    ADD COLUMN checked_in_at DATETIME NULL COMMENT '当日チェックイン日時。NULL=未来場';
