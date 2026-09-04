-- 计划 9:用户体系(幂等,可重复执行;create_all 也会建新表,此脚本供存量开发库手动对齐)
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(64) NOT NULL,
  password_hash VARCHAR(100) NOT NULL,
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台用户';

CREATE TABLE IF NOT EXISTS project_members (
  id INT AUTO_INCREMENT PRIMARY KEY,
  project_id INT NOT NULL,
  user_id INT NOT NULL,
  role VARCHAR(16) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_project_member (project_id, user_id),
  CONSTRAINT fk_pm_project FOREIGN KEY (project_id) REFERENCES projects (id),
  CONSTRAINT fk_pm_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员';

-- bootstrap admin(仅在 users 空时插入;密码为 admin123 的 bcrypt 哈希,占位用——
-- 实际由后端启动时 ensure_bootstrap_admin 以运行时哈希创建,此 INSERT 兜底纯 SQL 场景)
-- ⚠ 此 INSERT 写入的哈希是无效占位:若本库只跑了本脚本、从未启动过后端,
-- 登录会失败且启动引导不会修复该行。处置:DELETE FROM users WHERE username='admin';
-- 然后启动后端,由 ensure_bootstrap_admin 以运行时哈希重建 admin/admin123。
INSERT INTO users (username, display_name, password_hash, is_admin)
SELECT 'admin', '管理员',
'$2b$12$C6UzMDM.H6dfI/f/IKcEe.6uIz0gSfP8h8Z5F9lXkq7Qv0OZ1WwEe', 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='admin');

-- ------------------------------------------------------------------
-- Task 11:归属列 created_by/updated_by(5 表 × 2 列)
-- 幂等加列:information_schema 判重(同 mysql-alter-plan4.sql 模式),重复执行零报错
-- ------------------------------------------------------------------
SET @db := DATABASE();

-- projects.created_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'created_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE projects ADD COLUMN created_by INT NULL COMMENT ''创建人 users.id''',
    'SELECT ''projects.created_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- projects.updated_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'updated_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE projects ADD COLUMN updated_by INT NULL COMMENT ''最后修改人 users.id''',
    'SELECT ''projects.updated_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- documents.created_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'created_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE documents ADD COLUMN created_by INT NULL COMMENT ''创建人 users.id''',
    'SELECT ''documents.created_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- documents.updated_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'updated_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE documents ADD COLUMN updated_by INT NULL COMMENT ''最后修改人 users.id''',
    'SELECT ''documents.updated_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- generation_jobs.created_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'generation_jobs' AND COLUMN_NAME = 'created_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE generation_jobs ADD COLUMN created_by INT NULL COMMENT ''创建人 users.id''',
    'SELECT ''generation_jobs.created_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- generation_jobs.updated_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'generation_jobs' AND COLUMN_NAME = 'updated_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE generation_jobs ADD COLUMN updated_by INT NULL COMMENT ''最后修改人 users.id''',
    'SELECT ''generation_jobs.updated_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_scripts.created_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_scripts' AND COLUMN_NAME = 'created_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_scripts ADD COLUMN created_by INT NULL COMMENT ''创建人 users.id''',
    'SELECT ''ui_scripts.created_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_scripts.updated_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_scripts' AND COLUMN_NAME = 'updated_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_scripts ADD COLUMN updated_by INT NULL COMMENT ''最后修改人 users.id''',
    'SELECT ''ui_scripts.updated_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_auth_states.created_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_auth_states' AND COLUMN_NAME = 'created_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_auth_states ADD COLUMN created_by INT NULL COMMENT ''创建人 users.id''',
    'SELECT ''ui_auth_states.created_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ui_auth_states.updated_by
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'ui_auth_states' AND COLUMN_NAME = 'updated_by');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE ui_auth_states ADD COLUMN updated_by INT NULL COMMENT ''最后修改人 users.id''',
    'SELECT ''ui_auth_states.updated_by 已存在,跳过'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
