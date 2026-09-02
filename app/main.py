import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import cases, documents, jobs, modules, projects, repo, ui_scripts

import app.models  # noqa: F401 — ensure Base.metadata knows all tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # 无条件注册主事件循环,使 enqueue_job 可跨线程安全投递(线程安全)
    from app.jobs.pipeline import set_loop
    set_loop(asyncio.get_running_loop())
    workers: list[asyncio.Task] = []
    if settings.anthropic_api_key:  # 无 key 的环境(测试/离线)不启动 worker
        from app.jobs.pipeline import worker_loop

        workers = [asyncio.create_task(worker_loop()) for _ in range(3)]
    yield
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
    app.include_router(projects.router)
    app.include_router(modules.router)
    app.include_router(cases.router)
    app.include_router(documents.router)
    app.include_router(jobs.router)
    app.include_router(repo.router)
    app.include_router(ui_scripts.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
