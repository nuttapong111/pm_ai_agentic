from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.line_handler import LineWebhookHandler
from app.core.tracker_sync import sync_tracker_webhook
from app.db.session import get_db

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/line", status_code=status.HTTP_200_OK)
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
) -> dict[str, str]:
    body = await request.body()
    handler = LineWebhookHandler(db)
    if not handler.verify_signature(body, x_line_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="signature ไม่ถูกต้อง")

    payload = await request.json()
    background_tasks.add_task(handler.process_events, payload)
    return {"status": "ok"}


@router.post("/{provider}", status_code=status.HTTP_200_OK)
async def tracker_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if provider not in ("jira", "clickup"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider ไม่รองรับ")
    payload = await request.json()
    count = await sync_tracker_webhook(db, provider, payload)
    return {"status": "ok", "updated": str(count)}
