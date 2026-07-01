#!/usr/bin/env python3
"""Create database tables from SQLAlchemy models. Run once on Railway after deploy."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.models import Base
from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("OK — database tables ready")


if __name__ == "__main__":
    asyncio.run(main())
