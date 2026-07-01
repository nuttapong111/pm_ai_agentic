from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/liff", tags=["LIFF"])


@router.get("/config")
async def liff_config() -> dict[str, str]:
    settings = get_settings()
    return {"liffId": settings.line_liff_id}
