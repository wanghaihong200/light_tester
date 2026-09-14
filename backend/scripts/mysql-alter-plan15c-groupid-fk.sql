-- DEFER 演进批次(#114):mysql-alter-plan15.sql 建的 mock_rules.group_id 是裸列,
-- 与 models.py(create_all 产物)漂移——本脚本补外键与索引对齐。
-- 刻意不命名约束:MySQL/InnoDB 自动命名(约束名+自动索引),与 create_all 产物形态一致。
-- 幂等性说明:同 plan4-15 约定,重复执行报 Duplicate key name / Duplicate foreign key
-- 即视为已迁移。执行:docker exec -i cicd-mysql mysql -uroot -proot123 test_platform < 本文件

ALTER TABLE mock_rules
  ADD FOREIGN KEY (group_id) REFERENCES mock_rule_groups (id);
