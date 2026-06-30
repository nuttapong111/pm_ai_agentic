from datetime import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import NotificationPreference, User
from app.db.session import get_db
from app.schemas import NotificationPreferences

router = APIRouter(prefix="/me", tags=["Notifications"])


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _format_time(value: time | None) -> str | None:
    if not value:
        return None
    return value.strftime("%H:%M")


@router.get("/notification-preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferences:
    pref = await db.get(NotificationPreference, user.id)
    if not pref:
        return NotificationPreferences()
    return NotificationPreferences(
        enabled_types=pref.enabled_types,
        quiet_hours_start=_format_time(pref.quiet_hours_start),
        quiet_hours_end=_format_time(pref.quiet_hours_end),
    )


@router.put("/notification-preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    body: NotificationPreferences,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferences:
    pref = await db.get(NotificationPreference, user.id)
    if not pref:
        pref = NotificationPreference(user_id=user.id)
        db.add(pref)
    pref.enabled_types = body.enabled_types
    pref.quiet_hours_start = _parse_time(body.quiet_hours_start)
    pref.quiet_hours_end = _parse_time(body.quiet_hours_end)
    await db.commit()
    return body
