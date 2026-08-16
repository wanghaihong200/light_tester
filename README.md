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

Windows 下也可直接双击 `start.bat`(从任何目录启动都有效,自动切到 backend 并用 .venv 启动;
默认不带 --reload,避免 AI 生成任务进行中因文件变动重启 worker——开发期想自动重启可自行加上)。

### 测试

    pytest -v   # 使用 DATABASE_URL 指向的测试库(默认 test_platform_test)

## 环境变量

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | 必填才启动生成 worker;空则任务停留 pending |
| `AI_MODEL` | 可选,默认 `claude-opus-5` |

## 任务管道(AI 用例生成)

发起即返回任务 ID;进程内 asyncio 队列 + 3 个 worker;同项目串行、跨项目并行;AI 失败任务落 failed+error 可回看;单测全部 mock AI 客户端零网络调用;依赖 `anthropic openpyxl pytest-asyncio` 已入 requirements.txt。
