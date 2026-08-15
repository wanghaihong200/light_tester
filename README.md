# test-platform

测试平台(单机 Web MVP)。领域术语见仓库根 `CONTEXT.md`,架构决策见仓库根 `docs/adr/`。

## 技术栈

FastAPI + SQLAlchemy 2.x + MySQL

### 启动

    python -m venv .venv && source .venv/Scripts/activate
    pip install -r requirements.txt
    cp .env.example .env   # 修改 DATABASE_URL 等
    uvicorn app.main:app --reload --port 8000

接口文档:http://127.0.0.1:8000/docs

### 测试

    pytest -v   # 使用 DATABASE_URL 指向的测试库(默认 test_platform_test)
