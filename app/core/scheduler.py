"""Background scheduler for due-date and meeting reminders."""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.channels.line_handler import LineNotifier
from app.db.models import (
    CalendarEvent,
    NotificationPreference,
    NotificationType,
    Project,
    ScheduledNotification,
    Task,
    TaskStatus,
    User,
)
from app.db.session import async_session

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
notifier = LineNotifier()


def _in_quiet_hours(pref: NotificationPreference | None, now: datetime) -> bool:
    if not pref or not pref.quiet_hours_start or not pref.quiet_hours_end:
        return False
    t = now.time()
    start, end = pref.quiet_hours_start, pref.quiet_hours_end
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


async def queue_due_reminders() -> None:
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        soon = (now + timedelta(days=1)).date()

        tasks = await db.execute(
            select(Task).where(
                Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
                Task.due_date.is_not(None),
                Task.due_date <= soon,
            )
        )
        for task in tasks.scalars().all():
            proj = await db.get(Project, task.project_id)
            if not proj:
                continue
            user = await db.get(User, proj.owner_user_id)
            if not user:
                continue
            pref = await db.get(NotificationPreference, user.id)
            enabled = pref.enabled_types if pref else ["due_soon", "overdue"]
            ntype = NotificationType.overdue if task.due_date and task.due_date < now.date() else NotificationType.due_soon
            if ntype.value not in enabled:
                continue
            existing = await db.execute(
                select(ScheduledNotification).where(
                    ScheduledNotification.ref_type == "task",
                    ScheduledNotification.ref_id == task.id,
                    ScheduledNotification.type == ntype,
                    ScheduledNotification.status == "pending",
                )
            )
            if existing.scalar_one_or_none():
                continue
            db.add(
                ScheduledNotification(
                    project_id=task.project_id,
                    target_user_id=user.id,
                    type=ntype,
                    ref_type="task",
                    ref_id=task.id,
                    payload={"title": task.title, "due_date": str(task.due_date)},
                    scheduled_at=now,
                )
            )

        events = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.starts_at > now,
                CalendarEvent.starts_at <= now + timedelta(minutes=30),
            )
        )
        for event in events.scalars().all():
            proj = await db.get(Project, event.project_id)
            if not proj:
                continue
            user = await db.get(User, proj.owner_user_id)
            if not user:
                continue
            db.add(
                ScheduledNotification(
                    project_id=event.project_id,
                    target_user_id=user.id,
                    type=NotificationType.meeting_soon,
                    ref_type="calendar_event",
                    ref_id=event.id,
                    payload={"title": event.title, "starts_at": event.starts_at.isoformat(), "meet_link": event.meet_link},
                    scheduled_at=now,
                )
            )
        await db.commit()


async def send_pending_notifications() -> None:
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ScheduledNotification).where(
                ScheduledNotification.status == "pending",
                ScheduledNotification.scheduled_at <= now,
                ScheduledNotification.sent_at.is_(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            user = await db.get(User, row.target_user_id)
            pref = await db.get(NotificationPreference, row.target_user_id) if user else None
            if _in_quiet_hours(pref, now):
                row.status = "skipped"
                continue
            if not user or not user.line_user_id:
                row.status = "failed"
                continue

            payload = row.payload
            if row.type == NotificationType.meeting_soon:
                text = f"🔔 {payload.get('title')} เริ่มในไม่ช้า\n{payload.get('starts_at', '')}"
                if payload.get("meet_link"):
                    text += f"\n{payload['meet_link']}"
            else:
                text = f"📌 งาน: {payload.get('title')}\nกำหนด: {payload.get('due_date')}"

            await notifier.push(user.line_user_id, text)
            row.sent_at = now
            row.status = "sent"
        await db.commit()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(queue_due_reminders, "interval", minutes=15, id="queue_reminders")
    scheduler.add_job(send_pending_notifications, "interval", minutes=1, id="send_notifications")
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
