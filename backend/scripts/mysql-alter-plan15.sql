-- 计划 15:规则组实体化(method/path 上移到组,迁移保序)+ 透传字段 + 命中 outcome/response_body
-- 幂等性说明:CREATE TABLE IF NOT EXISTS 幂等;ALTER 幂等靠"开发库只跑一次"约定,重复执行会报
-- Duplicate column —— 与既有 plan4-12 脚本约定一致,报错即可视为已迁移。

CREATE TABLE IF NOT EXISTS mock_rule_groups (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '规则组主键ID',
  instance_id INT NOT NULL COMMENT '所属实例ID',
  method VARCHAR(10) NOT NULL COMMENT 'HTTP 方法(大写),组级',
  path_template VARCHAR(500) NOT NULL COMMENT '路径:精确或 /a/{var} 模板,组级',
  description TEXT NULL COMMENT '规则组描述(可空)',
  enabled TINYINT(1) DEFAULT 1 COMMENT '组级停用=整组不参与匹配',
  sort_order INT DEFAULT 0 COMMENT '组间排序,小者先匹配',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  is_deleted TINYINT(1) DEFAULT 0 COMMENT '是否已删除(软删除标记)',
  created_by INT NULL COMMENT '创建人 users.id',
  updated_by INT NULL COMMENT '最后修改人 users.id',
  KEY idx_mockgroups_instance (instance_id),
  CONSTRAINT fk_mockgroups_instance FOREIGN KEY (instance_id) REFERENCES mock_instances (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='规则组表:实例内 method+路径模板 相同的规则的容器,以「METHOD / 路径」命名,组间+组内两级有序匹配(ADR-0011)';

-- 1) 规则表先加 group_id 列(回填前置条件)
ALTER TABLE mock_rules
  ADD COLUMN group_id INT NULL COMMENT '所属规则组' AFTER instance_id;

-- 2) 建组:按 (instance, method, path_template) 归组;组序=该路由在旧全局序中的最小 sort_order(=首现位置,保序);
--    只为仍存活规则的路由建组(全软删路由不建,历史命中按 method/path 仍可追溯)
INSERT INTO mock_rule_groups (instance_id, method, path_template, description, enabled, sort_order, created_at, updated_at, is_deleted)
SELECT instance_id, method, path_template, NULL, 1, MIN(sort_order), NOW(), NOW(), 0
FROM mock_rules WHERE is_deleted = 0
GROUP BY instance_id, method, path_template;

-- 3) 规则挂组(含软删行,保命中记录追溯);全软删路由的软删行 group_id 留 NULL
UPDATE mock_rules r JOIN mock_rule_groups g
  ON g.instance_id = r.instance_id AND g.method = r.method AND g.path_template = r.path_template
SET r.group_id = g.id
WHERE r.group_id IS NULL;

-- 4) 规则表去 method/path(已上移到组)
ALTER TABLE mock_rules DROP COLUMN method, DROP COLUMN path_template;

-- 5) 实例透传字段
ALTER TABLE mock_instances
  ADD COLUMN passthrough_enabled TINYINT(1) DEFAULT 0 COMMENT '透传开关:未命中转发原始请求到上游' AFTER default_body,
  ADD COLUMN upstream_base_url VARCHAR(500) NULL COMMENT '上游真实服务 base_url;透传开启时必填' AFTER passthrough_enabled;

-- 6) 命中记录 outcome + response_body;存量行按 matched 归结
ALTER TABLE mock_hits
  ADD COLUMN outcome VARCHAR(16) DEFAULT 'fallback' COMMENT '结局:matched/fallback/forwarded' AFTER matched,
  ADD COLUMN response_body TEXT NULL COMMENT '实际响应体(64KB 截断)' AFTER request_body;
UPDATE mock_hits SET outcome = CASE WHEN matched = 1 THEN 'matched' ELSE 'fallback' END;
