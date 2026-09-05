-- 计划5:任务可回看性与统计完整性
-- 注:MySQL 5.7 不支持 ADD COLUMN IF NOT EXISTS,故用三条独立 ALTER;
-- 重复执行会报 Duplicate column name,属预期(幂等语义:已存在即说明执行过)。
ALTER TABLE generation_jobs
    ADD COLUMN output_text TEXT NULL COMMENT 'AI 流式输出全文(跨修复轮累积,终态回放用)' AFTER artifacts;
ALTER TABLE generation_jobs
    ADD COLUMN started_at DATETIME NULL COMMENT '任务开始执行时间' AFTER output_text;
ALTER TABLE generation_jobs
    ADD COLUMN finished_at DATETIME NULL COMMENT '任务终态(完成/失败)时间' AFTER started_at;
