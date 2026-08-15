from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import projects


def create_app() -> FastAPI:
    app = FastAPI(title="test-platform")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(projects.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
