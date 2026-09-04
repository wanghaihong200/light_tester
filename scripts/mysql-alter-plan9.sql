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
INSERT INTO users (username, display_name, password_hash, is_admin)
SELECT 'admin', '管理员',
'$2b$12$C6UzMDM.H6dfI/f/IKcEe.6uIz0gSfP8h8Z5F9lXkq7Qv0OZ1WwEe', 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='admin');
