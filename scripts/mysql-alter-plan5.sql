-- 计划5:任务可回看性与统计完整性(幂等,可重复执行)
ALTER TABLE generation_jobs
    ADD COLUMN IF NOT EXISTS output_text TEXT NULL COMMENT 'AI 流式输出全文(跨修复轮累积,终态回放用)' AFTER artifacts,
    ADD COLUMN IF NOT EXISTS started_at DATETIME NULL COMMENT '任务开始执行时间' AFTER output_text,
    ADD COLUMN IF NOT EXISTS finished_at DATETIME NULL COMMENT '任务终态(完成/失败)时间' AFTER started_at;
