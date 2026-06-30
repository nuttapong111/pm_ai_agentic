#!/usr/bin/env python3
"""Create a dev JWT for testing LIFF/API endpoints."""

import sys
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import get_settings


def main() -> None:
    user_id = sys.argv[1] if len(sys.argv) > 1 else str(uuid.uuid4())
    settings = get_settings()
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    print(f"User ID: {user_id}")
    print(f"Bearer token:\n{token}")


if __name__ == "__main__":
    main()
