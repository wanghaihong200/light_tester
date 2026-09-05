-- 计划 10:多端 UI 自动化(幂等,可重复执行;create_all 只建缺失表不 ALTER,此脚本供存量开发库手动对齐)
-- 5 列:ui_scripts.driver_target、ui_runs.driver_target、ui_runs.ai_usage、ui_auth_states.kind、ui_auth_states.app_package
-- 幂等加列:information_schema 判重(同 mysql-alter-plan9.sql 模式),重复执行零报错
SET @db := DATABASE();

-- ui_scripts.driver_target
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_scripts' AND COLUMN_NAME = 'driver_target');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_scripts ADD COLUMN driver_target VARCHAR(16) NOT NULL DEFAULT ''web'' COMMENT ''端:web/android/harmony(由 script.meta.target 派生)''',
    'SELECT ''ui_scripts.driver_target 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_runs.driver_target
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_runs' AND COLUMN_NAME = 'driver_target');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_runs ADD COLUMN driver_target VARCHAR(16) NOT NULL DEFAULT ''web'' COMMENT ''端:web/android/harmony''',
    'SELECT ''ui_runs.driver_target 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_runs.ai_usage
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_runs' AND COLUMN_NAME = 'ai_usage');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_runs ADD COLUMN ai_usage JSON NULL COMMENT ''AI 执行用量:{input_tokens,output_tokens,cost_usd,report_path}''',
    'SELECT ''ui_runs.ai_usage 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_auth_states.kind
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_auth_states' AND COLUMN_NAME = 'kind');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_auth_states ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT ''web_storage'' COMMENT ''登录态种类:web_storage/android_snapshot''',
    'SELECT ''ui_auth_states.kind 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_auth_states.app_package
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_auth_states' AND COLUMN_NAME = 'app_package');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_auth_states ADD COLUMN app_package VARCHAR(200) NULL COMMENT ''应用包名(仅 android_snapshot)''',
    'SELECT ''ui_auth_states.app_package 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
