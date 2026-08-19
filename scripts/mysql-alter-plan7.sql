-- 计划 7:生成引擎(Agent SDK)新增列——补充提示词与过程记录
-- MySQL 5.7 无 IF NOT EXISTS;重复执行报 Duplicate column name 属预期,即幂等语义
USE test_platform;
ALTER TABLE generation_jobs ADD COLUMN user_prompt TEXT NULL COMMENT '用户补充提示词(发起生成时可选填写,随任务持久化)' AFTER error;
ALTER TABLE generation_jobs ADD COLUMN tool_trace TEXT NULL COMMENT '过程记录:引擎工具调用的人类可读行(按序累积,终态回放用)' AFTER thinking_text;
