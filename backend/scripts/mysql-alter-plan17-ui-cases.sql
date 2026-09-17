-- 计划 17(ADR-0013):interface_cases 扩列承载 web 域用例(Web用例注册表共表)
-- 对开发库执行:docker exec -i cicd-mysql mysql -uroot -proot123 <db> < backend/scripts/mysql-alter-plan17-ui-cases.sql
ALTER TABLE interface_cases
  ADD COLUMN case_type VARCHAR(8) NOT NULL DEFAULT 'api' COMMENT '用例域:api(接口方法)/web(pytest 函数)' AFTER method,
  ADD COLUMN title VARCHAR(500) NULL DEFAULT NULL COMMENT '用例标题快照(web=docstring 首行;api 为空)' AFTER framework,
  ADD COLUMN markers JSON NULL DEFAULT NULL COMMENT '仓侧标记只读快照(web=@pytest.mark 展示串;api 为空)' AFTER title;
