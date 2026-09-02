-- UI 自动化录制一期:新增三张表(脚本/执行记录/登录态)
-- 注:CREATE TABLE IF NOT EXISTS,可重复执行(已存在即跳过);
-- 列定义与 app/models.py 的 UiScript / UiRun / UiAuthState 一致,utf8mb4。
USE test_platform;

CREATE TABLE IF NOT EXISTS ui_scripts (
    id INT NOT NULL AUTO_INCREMENT COMMENT '脚本主键ID',
    project_id INT NOT NULL COMMENT '所属项目ID',
    name VARCHAR(200) NOT NULL COMMENT '脚本名称',
    description TEXT NULL COMMENT '脚本描述',
    script JSON NOT NULL COMMENT '脚本DSL文档:{version,meta,variables,steps}',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除(软删除标记)',
    PRIMARY KEY (id),
    CONSTRAINT fk_ui_scripts_project FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='UI自动化脚本表：录制的JSON步骤DSL，跨端中性';

CREATE TABLE IF NOT EXISTS ui_runs (
    id INT NOT NULL AUTO_INCREMENT COMMENT '执行记录主键ID',
    project_id INT NOT NULL COMMENT '所属项目ID',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态：pending/running/completed/failed',
    script_id INT NOT NULL COMMENT '执行的脚本ID',
    script_name VARCHAR(200) NOT NULL DEFAULT '' COMMENT '执行时的脚本名快照(脚本改名/删除不影响历史)',
    mode VARCHAR(10) NOT NULL DEFAULT 'headless' COMMENT '浏览器模式：headless/headed',
    variables JSON NOT NULL COMMENT '用户传入变量覆盖值',
    step_results JSON NOT NULL COMMENT '步骤结果列表:[{step_id,action,status,error,screenshot,elapsed_ms}]',
    steps_total INT NOT NULL DEFAULT 0 COMMENT '总步骤数',
    steps_passed INT NOT NULL DEFAULT 0 COMMENT '通过步骤数',
    steps_failed INT NOT NULL DEFAULT 0 COMMENT '失败步骤数',
    error TEXT NULL COMMENT '整体失败原因(环境级错误,非断言失败)',
    started_at DATETIME NULL COMMENT '开始执行时间',
    finished_at DATETIME NULL COMMENT '终态时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除(软删除标记)',
    PRIMARY KEY (id),
    CONSTRAINT fk_ui_runs_project FOREIGN KEY (project_id) REFERENCES projects (id),
    -- 强外键：脚本一律软删(is_deleted=True)，router 不得物理 delete，否则执行历史断链
    CONSTRAINT fk_ui_runs_script FOREIGN KEY (script_id) REFERENCES ui_scripts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='UI自动化执行记录表：一次脚本回放的步骤级结果';

CREATE TABLE IF NOT EXISTS ui_auth_states (
    id INT NOT NULL AUTO_INCREMENT COMMENT '登录态主键ID',
    project_id INT NOT NULL COMMENT '所属项目ID',
    name VARCHAR(200) NOT NULL COMMENT '登录态名称',
    storage_path VARCHAR(1000) NOT NULL COMMENT 'storage_state JSON 文件存储路径',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除(软删除标记)',
    PRIMARY KEY (id),
    CONSTRAINT fk_ui_auth_states_project FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='UI自动化登录态表：storage_state 文件的登记行';
