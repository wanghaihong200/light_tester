import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import (
    app_runs, app_scripts, auth, cases, documents, jobs, members, modules, projects, repo,
    ui_auth_states, ui_recordings, ui_runs, ui_scripts, users
)

import app.models  # noqa: F401 — ensure Base.metadata knows all tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # 首次启动引导首个 admin(users 表空则建 admin/admin123)
    from app.bootstrap import ensure_bootstrap_admin
    from app.database import SessionLocal

    with SessionLocal() as _db:
        ensure_bootstrap_admin(_db)
        # Mock 实例开机对账:desired=running 的实例重新拉起(空表 no-op,测试安全)
        from app.mock_service import supervisor
        supervisor.reconcile(_db)
    # 无条件注册主事件循环,使 enqueue_job 可跨线程安全投递(线程安全)
    from app.jobs.pipeline import set_loop
    set_loop(asyncio.get_running_loop())
    # UI 执行器线程同样经主循环把预览帧/步骤事件投递回 bus
    from app.ui_automation.loopref import set_ui_loop
    set_ui_loop(asyncio.get_running_loop())
    supervisor.start_probe_task()  # Mock 实例探活循环(10s 一轮,异常吞掉绝不炸平台)
    workers: list[asyncio.Task] = []
    if settings.anthropic_api_key:  # 无 key 的环境(测试/离线)不启动 worker
        from app.jobs.pipeline import worker_loop

        workers = [asyncio.create_task(worker_loop()) for _ in range(3)]
    yield
    supervisor.stop_probe_task()
    supervisor.shutdown_all()  # 平台停机:全部 mock 子进程关停
    for w in workers:
        w.cancel()
    if workers:
        await asyncio.gather(*workers, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(title="test-platform", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(modules.router)
    app.include_router(cases.router)
    app.include_router(documents.router)
    app.include_router(jobs.router)
    app.include_router(repo.router)
    app.include_router(ui_scripts.router)
    app.include_router(ui_runs.router)
    app.include_router(ui_recordings.router)
    app.include_router(ui_auth_states.router)
    app.include_router(app_scripts.router)
    app.include_router(app_runs.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
