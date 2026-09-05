# 轻测试 LightTester

AI 测试平台(单机 Web MVP):用例树管理(xmind 导图视图)、AI 生成功能用例、AI 生成接口脚本、
Web UI 自动化(录制/执行)、用户体系与项目级权限。前后端同仓(monorepo)。

## 目录结构

| 目录 | 内容 | 技术栈 |
|---|---|---|
| [`backend/`](backend/) | FastAPI 服务(用例树/文档库/AI 生成任务管道+Agent SDK 引擎/UI 自动化录制执行/用户权限)、平台技能副本 `.claude/skills/` | Python 3.12 · FastAPI · SQLAlchemy · MySQL · claude-agent-sdk · Playwright |
| [`frontend/`](frontend/) | Vue3 单页应用(导图编辑器/任务抽屉/Monaco/Web 自动化/用户管理) | Vue3 · TypeScript · Element Plus · simple-mind-map · Monaco |

各自的详细说明见 [`backend/README.md`](backend/README.md) 与 [`frontend/README.md`](frontend/README.md)。

## 快速开始

```bash
# 后端(需 MySQL;启动时自动建表并引导 admin/admin123)
cd backend
py -3.12 -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000                           # 接口文档 http://127.0.0.1:8000/docs

# 前端
cd frontend
npm install                                                # 国内可加 --registry=https://registry.npmmirror.com
npm run dev                                                # http://localhost:5173(代理 /api → 8000)
```

> 本仓库由原 `light_tester_backend` / `light_tester_frontend` 两仓合并而来(git subtree,完整提交历史保留);
> 旧两仓已归档。
