from fastapi import APIRouter, Header, HTTPException, status

from app.channels.rich_menu import rich_menu_status, setup_rich_menu
from app.config import get_settings
from app.db.init_schema import ensure_database_schema

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/rich-menu/setup")
async def admin_setup_rich_menu(
    x_setup_secret: str | None = Header(default=None, alias="X-Setup-Secret"),
) -> dict[str, str]:
    """One-time rich menu setup (ใช้บน Railway โดยไม่ต้องรัน script local)."""
    settings = get_settings()
    secret = settings.setup_secret or settings.jwt_secret
    if not x_setup_secret or x_setup_secret != secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="secret ไม่ถูกต้อง")

    if not settings.line_channel_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ไม่มี LINE_CHANNEL_ACCESS_TOKEN")

    try:
        menu_id = setup_rich_menu(
            settings.line_channel_access_token,
            settings.line_liff_id,
            settings.app_base_url,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {"richMenuId": menu_id, "status": "ok"}


@router.get("/rich-menu/status")
async def admin_rich_menu_status(
    x_setup_secret: str | None = Header(default=None, alias="X-Setup-Secret"),
) -> dict:
    """ตรวจสอบว่า rich menu ถูกสร้างและตั้งเป็น default หรือยัง"""
    settings = get_settings()
    secret = settings.setup_secret or settings.jwt_secret
    if not x_setup_secret or x_setup_secret != secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="secret ไม่ถูกต้อง")

    if not settings.line_channel_access_token:
        return {
            "hasToken": False,
            "menuCount": 0,
            "defaultRichMenuId": None,
            "error": "ไม่มี LINE_CHANNEL_ACCESS_TOKEN",
        }

    try:
        status_data = rich_menu_status(settings.line_channel_access_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "hasToken": True,
        "liffIdSet": bool(settings.line_liff_id),
        "appBaseUrl": settings.app_base_url,
        **status_data,
    }


@router.post("/db/init")
async def admin_init_database(
    x_setup_secret: str | None = Header(default=None, alias="X-Setup-Secret"),
) -> dict[str, str]:
    settings = get_settings()
    secret = settings.setup_secret or settings.jwt_secret
    if not x_setup_secret or x_setup_secret != secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="secret ไม่ถูกต้อง")
    await ensure_database_schema()
    return {"status": "ok"}
