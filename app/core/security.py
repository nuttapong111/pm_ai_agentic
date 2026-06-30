import base64
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from jose import jwt

from app.config import get_settings

_oauth_states: dict[str, dict[str, Any]] = {}


def _fernet() -> Fernet:
    key = get_settings().app_encryption_key.encode()
    # Fernet needs 32 url-safe base64-encoded bytes
    derived = base64.urlsafe_b64encode(key.ljust(32, b"0")[:32])
    return Fernet(derived)


def encrypt_credentials(data: dict[str, Any]) -> dict[str, Any]:
    token = _fernet().encrypt(json.dumps(data).encode())
    return {"ciphertext": token.decode()}


def decrypt_credentials(blob: dict[str, Any]) -> dict[str, Any]:
    if "ciphertext" not in blob:
        return blob
    try:
        raw = _fernet().decrypt(blob["ciphertext"].encode())
        return json.loads(raw.decode())
    except (InvalidToken, json.JSONDecodeError):
        return {}


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def verify_line_id_token(id_token: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.app_env == "development" and id_token.startswith("dev:"):
        return {"sub": id_token.split(":", 1)[1], "name": "Dev User"}

    url = "https://api.line.me/oauth2/v2.1/verify"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            data={"id_token": id_token, "client_id": settings.line_liff_id},
            timeout=30,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LINE id token ไม่ถูกต้อง")
    return resp.json()


def store_oauth_state(user_id: UUID, connection_type: str) -> str:
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "user_id": str(user_id),
        "type": connection_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return state


def pop_oauth_state(state: str) -> dict[str, Any] | None:
    return _oauth_states.pop(state, None)


def build_oauth_url(connection_type: str, state: str) -> str:
    settings = get_settings()
    base = settings.app_base_url.rstrip("/")
    redirect = f"{base}/v1/connections/oauth/callback"

    if connection_type == "google":
        client_id = settings.google_client_id or "GOOGLE_CLIENT_ID"
        scopes = "https://www.googleapis.com/auth/calendar%20https://www.googleapis.com/auth/drive.file%20email"
        return (
            f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}"
            f"&redirect_uri={redirect}&response_type=code&scope={scopes}&state={state}&access_type=offline"
        )
    if connection_type == "gmail":
        client_id = settings.google_client_id or "GOOGLE_CLIENT_ID"
        scopes = "https://www.googleapis.com/auth/gmail.send%20email"
        return (
            f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}"
            f"&redirect_uri={redirect}&response_type=code&scope={scopes}&state={state}&access_type=offline"
        )
    if connection_type == "jira":
        return f"{base}/v1/connections/oauth/mock?type=jira&state={state}"
    if connection_type == "clickup":
        return f"{base}/v1/connections/oauth/mock?type=clickup&state={state}"

    return f"{base}/v1/connections/oauth/mock?type={connection_type}&state={state}"
