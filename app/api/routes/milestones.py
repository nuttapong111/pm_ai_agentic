from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_for_user
from app.db.models import Milestone, Project, Task
from app.db.session import get_db
from app.schemas import MilestoneInput, MilestoneOut

router = APIRouter(tags=["Milestones"])


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneOut])
async def list_milestones(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[MilestoneOut]:
    result = await db.execute(select(Milestone).where(Milestone.project_id == project.id))
    milestones = list(result.scalars().all())
    out: list[MilestoneOut] = []
    for ms in milestones:
        count = await db.scalar(select(func.count()).select_from(Task).where(Task.milestone_id == ms.id)) or 0
        out.append(
            MilestoneOut(
                id=ms.id,
                name=ms.name,
                target_date=ms.target_date,
                status=ms.status,
                linked_task_count=count,
            )
        )
    return out


@router.post("/projects/{project_id}/milestones", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    body: MilestoneInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> MilestoneOut:
    ms = Milestone(
        project_id=project.id,
        name=body.name,
        description=body.description,
        target_date=body.target_date,
    )
    db.add(ms)
    await db.commit()
    await db.refresh(ms)
    return MilestoneOut(id=ms.id, name=ms.name, target_date=ms.target_date, status=ms.status, linked_task_count=0)
