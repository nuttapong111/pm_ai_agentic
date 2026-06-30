from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_project_for_user
from app.db.models import ActionItem, Meeting, Project
from app.db.session import get_db
from app.schemas import ActionItemOut, MeetingOut

router = APIRouter(tags=["Meetings"])


@router.get("/projects/{project_id}/meetings", response_model=list[MeetingOut])
async def list_meetings(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[MeetingOut]:
    result = await db.execute(
        select(Meeting)
        .where(Meeting.project_id == project.id)
        .options(selectinload(Meeting.action_items))
        .order_by(Meeting.created_at.desc())
    )
    meetings = list(result.scalars().all())
    out: list[MeetingOut] = []
    for m in meetings:
        out.append(
            MeetingOut(
                id=m.id,
                title=m.title,
                meeting_date=m.meeting_date,
                decisions=m.decisions or [],
                action_items=[
                    ActionItemOut(
                        description=ai.description,
                        owner_id=ai.owner_id,
                        due_date=ai.due_date,
                        is_inferred=ai.is_inferred,
                    )
                    for ai in m.action_items
                ],
            )
        )
    return out
