from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.security import (
    build_oauth_url,
    encrypt_credentials,
    pop_oauth_state,
    store_oauth_state,
)
from app.db.models import Connection, ConnectionType, User
from app.db.session import get_db
from app.schemas import ConnectionOut, ConnectionTypeEnum

router = APIRouter(prefix="/connections", tags=["Connections"])


class AuthorizeRequest(BaseModel):
    type: ConnectionTypeEnum


class AuthorizeResponse(BaseModel):
    authorizationUrl: str


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Connection]:
    result = await db.execute(select(Connection).where(Connection.owner_user_id == user.id))
    return list(result.scalars().all())


@router.post("/authorize", response_model=AuthorizeResponse)
async def authorize_connection(
    body: AuthorizeRequest,
    user: User = Depends(get_current_user),
) -> AuthorizeResponse:
    state = store_oauth_state(user.id, body.type.value)
    url = build_oauth_url(body.type.value, state)
    return AuthorizeResponse(authorizationUrl=url)


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    meta = pop_oauth_state(state)
    if not meta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="state ไม่ถูกต้อง")

    conn_type = ConnectionType(meta["type"])
    credentials = encrypt_credentials({"code": code, "mock": True})

    connection = Connection(
        owner_user_id=UUID(meta["user_id"]),
        type=conn_type,
        display_name=f"{conn_type.value.title()} (connected)",
        credentials=credentials,
        metadata_={"oauth": True},
        status="connected",
    )
    db.add(connection)
    await db.commit()

    settings = get_settings()
    return RedirectResponse(url=f"{settings.app_base_url}/liff/#/connections?ok=1")


@router.get("/oauth/mock")
async def oauth_mock(
    type: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    return await oauth_callback(code="mock-code", state=state, db=db)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    connection = await db.get(Connection, connection_id)
    if not connection or connection.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบ connection")
    connection.status = "revoked"
    await db.delete(connection)
    await db.commit()
