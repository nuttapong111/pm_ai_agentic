"""Sync external tracker status changes into canonical tasks."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, TaskStatus

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "done": TaskStatus.done,
    "complete": TaskStatus.done,
    "closed": TaskStatus.done,
    "in progress": TaskStatus.in_progress,
    "in_progress": TaskStatus.in_progress,
    "blocked": TaskStatus.blocked,
    "cancelled": TaskStatus.cancelled,
    "todo": TaskStatus.todo,
    "open": TaskStatus.todo,
}


async def sync_tracker_webhook(db: AsyncSession, provider: str, payload: dict[str, Any]) -> int:
    updated = 0
    external_key = _extract_external_key(provider, payload)
    new_status = _extract_status(provider, payload)
    if not external_key or not new_status:
        logger.info("tracker webhook %s: no key/status in payload", provider)
        return 0

    mapped = _STATUS_MAP.get(new_status.lower())
    if not mapped:
        return 0

    result = await db.execute(select(Task))
    for task in result.scalars().all():
        ref = task.external_ref or {}
        if ref.get("provider") == provider and ref.get("key") == external_key:
            task.status = mapped
            updated += 1

    if updated:
        await db.commit()
    return updated


def _extract_external_key(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "jira":
        issue = payload.get("issue", {})
        return issue.get("key") or payload.get("key")
    if provider == "clickup":
        return payload.get("task_id") or payload.get("id")
    return payload.get("key")


def _extract_status(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "jira":
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        status = fields.get("status", {})
        return status.get("name")
    if provider == "clickup":
        return payload.get("status") or payload.get("status_type")
    return payload.get("status")
