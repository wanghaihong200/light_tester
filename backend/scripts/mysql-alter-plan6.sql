-- 计划6:任务思考摘要列(MySQL 5.7 无 IF NOT EXISTS;重复执行报 Duplicate column name 属预期,即幂等语义)
ALTER TABLE generation_jobs
    ADD COLUMN thinking_text TEXT NULL COMMENT 'AI 思考摘要全文(display=summarized,跨修复轮累积,终态回放用)' AFTER output_text;
