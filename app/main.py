from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings, load_yaml_config
from app.core.scheduler import start_scheduler, stop_scheduler

STORAGE_DIR = Path("storage")
LIFF_DIR = Path("liff")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = load_yaml_config()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PM Assistant API",
        version="1.0.0",
        description="REST API สำหรับผู้ช่วย PM บน LINE",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    if STORAGE_DIR.exists():
        app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")
    if LIFF_DIR.exists():
        app.mount("/liff", StaticFiles(directory=str(LIFF_DIR), html=True), name="liff")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
