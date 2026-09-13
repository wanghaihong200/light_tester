-- 计划 15 验收调整(2026-09-13):透传由实例级移至规则组级
-- 用户验收反馈:透传针对的是"被 mock 的原始接口",而组才与原始接口一一对应,实例级粒度不对。
-- 幂等性约定同 plan4-15:重复执行报 Duplicate column 即视为已迁移。

-- 1) 规则组加透传两列
ALTER TABLE mock_rule_groups
  ADD COLUMN passthrough_enabled TINYINT(1) DEFAULT 0
    COMMENT '组级透传开关:组路由命中但组内规则全不中时,转发原始请求到该组真实上游' AFTER enabled,
  ADD COLUMN upstream_base_url VARCHAR(500) NULL
    COMMENT '组对应的被 mock 原始接口 base_url;透传开启时必填' AFTER passthrough_enabled;

-- 2) 实例表去透传两列(功能已移至组级;开发库仅冒烟残留数据,无保留价值)
ALTER TABLE mock_instances
  DROP COLUMN passthrough_enabled,
  DROP COLUMN upstream_base_url;
