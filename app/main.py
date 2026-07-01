from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.channels.rich_menu import setup_rich_menu
from app.config import get_settings, load_yaml_config
from app.core.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage")
LIFF_DIR = Path("liff")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = load_yaml_config()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    settings = get_settings()
    if settings.rich_menu_auto_setup and settings.line_channel_access_token:
        try:
            menu_id = await asyncio.to_thread(
                setup_rich_menu,
                settings.line_channel_access_token,
                settings.line_liff_id,
                settings.app_base_url,
            )
            logger.info("Auto rich menu setup OK: %s", menu_id)
        except Exception:
            logger.exception("Auto rich menu setup failed")
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
