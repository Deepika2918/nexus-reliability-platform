"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from nexus.api.operator import router as operator_router
from nexus.api.simulation import router as simulation_router
from nexus.api.system import router as system_router
from nexus.api.work import router as work_router
from nexus.api.workers import router as workers_router
from nexus.config import settings
from nexus.database import get_db
from nexus.engine.recovery import recovery_loop

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()
    task: asyncio.Task | None = None
    if settings.recovery_loop_enabled:
        task = asyncio.create_task(recovery_loop(get_db))
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="NEXUS", version="0.1.0", lifespan=lifespan)

    app.include_router(work_router)
    app.include_router(workers_router)
    app.include_router(operator_router)
    app.include_router(simulation_router)
    app.include_router(system_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def dashboard() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
