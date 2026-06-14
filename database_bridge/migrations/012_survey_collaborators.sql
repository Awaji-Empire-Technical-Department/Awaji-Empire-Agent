-- 012_survey_collaborators.sql
-- スタッフ共同編集: フォーム（survey）の編集・管理権限をオーナー以外にも共有する。
-- user_id は Discord ユーザーID。ユーザー名は user_networks との JOIN で解決する。

CREATE TABLE IF NOT EXISTS survey_collaborators (
    survey_id INT      NOT NULL,
    user_id   BIGINT   NOT NULL COMMENT 'Discord ユーザーID（共同編集スタッフ）',
    added_at  DATETIME NOT NULL DEFAULT NOW(),
    PRIMARY KEY (survey_id, user_id),
    FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
