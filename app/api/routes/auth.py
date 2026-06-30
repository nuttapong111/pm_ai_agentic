from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token, verify_line_id_token
from app.db.models import LineContext, Project, User
from app.db.session import get_db

router = APIRouter(tags=["Auth"])


class LineAuthRequest(BaseModel):
    idToken: str


class TokenResponse(BaseModel):
    accessToken: str
    userId: str


class ActiveProjectRequest(BaseModel):
    projectId: UUID
    lineSourceType: str = "user"
    lineSourceId: str | None = None


@router.post("/auth/line", response_model=TokenResponse)
async def auth_line(body: LineAuthRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    profile = await verify_line_id_token(body.idToken)
    line_user_id = profile.get("sub")
    if not line_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ไม่พบ LINE user id")

    result = await db.execute(select(User).where(User.line_user_id == line_user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(line_user_id=line_user_id, display_name=profile.get("name"))
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif profile.get("name") and not user.display_name:
        user.display_name = profile.get("name")
        await db.commit()

    token = create_access_token(user.id)
    return TokenResponse(accessToken=token, userId=str(user.id))


@router.put("/me/active-project")
async def set_active_project(
    body: ActiveProjectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    project = await db.get(Project, body.projectId)
    if not project or project.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบโปรเจกต์")

    source_id = body.lineSourceId or user.line_user_id
    result = await db.execute(
        select(LineContext).where(
            LineContext.line_source_type == body.lineSourceType,
            LineContext.line_source_id == source_id,
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx:
        ctx.project_id = body.projectId
    else:
        ctx = LineContext(
            line_source_type=body.lineSourceType,
            line_source_id=source_id,
            project_id=body.projectId,
        )
        db.add(ctx)
    await db.commit()
    return {"status": "ok", "projectId": str(body.projectId)}


@router.get("/me/active-project")
async def get_active_project(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(LineContext).where(
            LineContext.line_source_type == "user",
            LineContext.line_source_id == user.line_user_id,
        )
    )
    ctx = result.scalar_one_or_none()
    if not ctx or not ctx.project_id:
        return {"projectId": None}
    project = await db.get(Project, ctx.project_id)
    if not project:
        return {"projectId": None}
    return {"projectId": str(project.id), "key": project.key, "name": project.name}
