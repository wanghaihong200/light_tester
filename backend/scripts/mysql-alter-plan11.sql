-- 计划 11:automation_repos 多分类自动化仓(一项目×kind 各一仓)
CREATE TABLE IF NOT EXISTS automation_repos (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自动化仓主键ID',
  project_id INT NOT NULL COMMENT '所属项目ID',
  kind VARCHAR(16) NOT NULL COMMENT '仓分类:api/web/app',
  repo_url VARCHAR(500) NOT NULL COMMENT '仓库地址(http(s)/file)',
  repo_token VARCHAR(200) NULL COMMENT '访问仓库的认证 Token',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  is_deleted TINYINT(1) DEFAULT 0 COMMENT '是否已删除(软删除标记)',
  created_by INT NULL COMMENT '创建人 users.id',
  updated_by INT NULL COMMENT '最后修改人 users.id',
  UNIQUE KEY uq_autorepo_project_kind (project_id, kind),
  CONSTRAINT fk_autorepo_project FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自动化工程仓表：一项目×分类(api/web/app)各一仓,分开推送';

-- 存量迁移:Project.git_repo_url 非空的项目 → kind=api 行(幂等:已有行不重复插)
INSERT INTO automation_repos (project_id, kind, repo_url, repo_token)
SELECT p.id, 'api', p.git_repo_url, p.git_token
FROM projects p
WHERE p.git_repo_url IS NOT NULL AND p.git_repo_url <> '' AND p.is_deleted = 0
  AND NOT EXISTS (
    SELECT 1 FROM automation_repos r
    WHERE r.project_id = p.id AND r.kind = 'api' AND r.is_deleted = 0
  );
