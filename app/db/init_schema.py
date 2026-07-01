"""Ensure PostgreSQL tables exist (idempotent create_all)."""

from __future__ import annotations

import logging

from app.db.models import Base
from app.db.session import engine

logger = logging.getLogger(__name__)


async def ensure_database_schema() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema ready")
    except Exception:
        logger.exception("Database schema init failed")
