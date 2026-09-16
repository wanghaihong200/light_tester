-- 计划 16:CI/CD 模块四张新表(Jenkins 连接单行配置 / 执行计划 / 接口用例注册表 / 执行记录,ADR-0012)
-- 幂等性说明:仅 CREATE TABLE IF NOT EXISTS,幂等;开发库手工执行一次,测试库由 conftest drop_all/create_all 自动建。
-- 列默认值与 SQLAlchemy 模型(Python 侧 default)同口径,参照 plan12/plan15 脚本既有格式。
-- 键长注记:interface_cases 唯一键 (project_id, branch, class_name, method) 在 utf8mb4 下
-- 4+200*4+255*4+200*4=2624 字节 ≤ InnoDB 3072 字节上限(class_name 受限 255,裁定 2026-09-16)。

-- Jenkins 连接配置(全局单行,id=1)
CREATE TABLE IF NOT EXISTS jenkins_connection (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '固定为 1(单行配置)',
  base_url VARCHAR(500) NOT NULL COMMENT 'Jenkins 根地址,如 http://localhost:8081',
  api_user VARCHAR(200) NOT NULL COMMENT 'API token 所属 Jenkins 用户名',
  api_token VARCHAR(500) NOT NULL COMMENT 'Jenkins API token(明文,与 automation_repos.repo_token 同口径)',
  gitlab_exposed_base VARCHAR(500) DEFAULT 'http://host.docker.internal:8090' COMMENT 'GitLab 对 Jenkins 容器暴露的根地址(checkout URL 改写目标)',
  credential_id VARCHAR(200) DEFAULT 'gitlab-creds' COMMENT 'Jenkins 侧 GitLab 凭据 ID(pipeline 引用)',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  updated_by INT NULL COMMENT '最后修改人 users.id'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Jenkins 连接配置(全局单行,id=1)';

-- 执行计划:单类型可复用用例选择集合,绑定分支(ADR-0012)
CREATE TABLE IF NOT EXISTS execution_plans (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '计划主键ID',
  project_id INT NOT NULL COMMENT '所属项目ID',
  name VARCHAR(200) NOT NULL COMMENT '计划名称',
  description TEXT NULL COMMENT '计划描述',
  kind VARCHAR(16) NOT NULL COMMENT '计划类型:ui(勾Web自动化脚本)/api(勾接口用例)',
  branch VARCHAR(200) NOT NULL COMMENT '绑定的仓分支(建/编计划先定分支、再勾用例)',
  selection JSON NOT NULL COMMENT '用例选择集合:ui 项 {script_id,name,file} / api 项 {ref,class_name,method};仓是唯一事实源,这里只存引用',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  is_deleted TINYINT(1) DEFAULT 0 COMMENT '是否已删除(软删除标记)',
  created_by INT NULL COMMENT '创建人 users.id',
  updated_by INT NULL COMMENT '最后修改人 users.id',
  KEY idx_execplans_project (project_id),
  CONSTRAINT fk_execplans_project FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行计划:单类型可复用用例选择集合,绑定分支(ADR-0012)';

-- 接口用例注册表:api 仓测试方法引用(仓×分支×类×方法,扫到方法级)
CREATE TABLE IF NOT EXISTS interface_cases (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '注册主键ID',
  project_id INT NOT NULL COMMENT '所属项目ID',
  branch VARCHAR(200) NOT NULL COMMENT '所在分支(各分支独立增量合并)',
  class_name VARCHAR(255) NOT NULL COMMENT '测试类全限定名(键长受限 255:utf8mb4 唯一键不超 InnoDB 3072B 上限)',
  method VARCHAR(200) NOT NULL COMMENT '测试方法名',
  status VARCHAR(16) DEFAULT 'active' COMMENT '存活状态:active(最近扫描存在)/stale(已消失)',
  framework VARCHAR(16) DEFAULT 'testng' COMMENT '测试框架:testng/junit4/junit5',
  file_path VARCHAR(500) NULL COMMENT '仓内相对路径',
  last_commit VARCHAR(64) NULL COMMENT '最近见到的短 commit',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  is_deleted TINYINT(1) DEFAULT 0 COMMENT '是否已删除(软删除标记)',
  UNIQUE KEY uq_iface_case_proj_branch_class_method (project_id, branch, class_name, method),
  KEY idx_ifacecases_project (project_id),
  CONSTRAINT fk_ifacecases_project FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='接口用例注册表:api 仓测试方法引用(仓×分支×类×方法,扫到方法级)';

-- 执行记录(CI Run):一次执行计划的 Jenkins build 落地(ADR-0012)
CREATE TABLE IF NOT EXISTS ci_runs (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '执行记录主键ID',
  project_id INT NOT NULL COMMENT '所属项目ID',
  plan_id INT NOT NULL COMMENT '来源计划ID(计划删除不影响本记录)',
  plan_name VARCHAR(200) DEFAULT '' COMMENT '计划名快照',
  kind VARCHAR(16) NOT NULL COMMENT '类型快照:ui/api',
  branch VARCHAR(200) NOT NULL COMMENT '分支快照',
  selection JSON NOT NULL COMMENT '分支+选择集合快照(含 skipped 标记)',
  status VARCHAR(20) DEFAULT 'queued' COMMENT '状态:queued/running/success/failure/aborted/error',
  jenkins_job VARCHAR(200) DEFAULT '' COMMENT 'Jenkins job 名(light_tester_p{id}_{kind})',
  build_number INT NULL COMMENT 'Jenkins build 号',
  jenkins_url VARCHAR(500) NULL COMMENT 'Jenkins build 页外链',
  total INT DEFAULT 0 COMMENT '用例总数',
  passed INT DEFAULT 0 COMMENT '通过数',
  failed INT DEFAULT 0 COMMENT '失败数(failure+error)',
  skipped INT DEFAULT 0 COMMENT '跳过数',
  results JSON NULL COMMENT '用例行列表 [{class_name,name,status,time_s,message}](≤500 行,message≤2000 字)',
  console_bytes INT DEFAULT 0 COMMENT 'console 日志已拉取字节偏移(progressiveText 游标)',
  freshness JSON NULL COMMENT '触发时新鲜度快照 {on_branch,dirty_files,ahead,stale}',
  error TEXT NULL COMMENT '平台侧失败原因(触发/轮询异常,非用例失败)',
  started_at DATETIME NULL COMMENT 'build 开始时间',
  finished_at DATETIME NULL COMMENT '终态时间',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  created_by INT NULL COMMENT '触发人 users.id',
  KEY idx_ciruns_project (project_id),
  KEY idx_ciruns_plan (plan_id),
  CONSTRAINT fk_ciruns_project FOREIGN KEY (project_id) REFERENCES projects (id),
  CONSTRAINT fk_ciruns_plan FOREIGN KEY (plan_id) REFERENCES execution_plans (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行记录(CI Run):一次执行计划的 Jenkins build 落地(ADR-0012)';
