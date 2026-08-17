-- scripts/mysql-alter-plan4.sql
-- 计划 4:generation_jobs 加 artifacts 列(可重复执行)
SET @db := DATABASE();
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'generation_jobs' AND COLUMN_NAME = 'artifacts'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE generation_jobs ADD COLUMN artifacts JSON NULL COMMENT ''接口生成产物文件清单:[{\"path\":...,\"action\":\"created|overwritten\"}];用例生成任务为NULL'' AFTER is_deleted',
    'SELECT ''artifacts 列已存在,跳过'' AS msg');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
