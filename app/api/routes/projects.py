from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.models import (
    CalendarEvent,
    Milestone,
    Project,
    Task,
    TaskStatus,
    User,
)
from app.db.session import get_db
from app.schemas import DashboardSummary, MilestoneOut, ProjectCreate, ProjectOut, TaskOut

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.owner_user_id == user.id, Project.is_archived.is_(False))
    )
    return list(result.scalars().all())


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project = Project(key=body.key.upper(), name=body.name, owner_user_id=user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project: Project = Depends(get_project_for_user)) -> Project:
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    body: ProjectCreate,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project.key = body.key.upper()
    project.name = body.name
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project.is_archived = True
    await db.commit()


@router.get("/{project_id}/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    total = await db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project.id))
    pending = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project.id, Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]))
    )
    done = await db.scalar(
        select(func.count()).select_from(Task).where(Task.project_id == project.id, Task.status == TaskStatus.done)
    )

    ms_result = await db.execute(
        select(Milestone)
        .where(Milestone.project_id == project.id)
        .order_by(Milestone.target_date.asc().nulls_last())
        .limit(1)
    )
    next_ms = ms_result.scalar_one_or_none()

    tasks_result = await db.execute(
        select(Task)
        .where(Task.project_id == project.id, Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]))
        .order_by(Task.due_date.asc().nulls_last())
        .limit(5)
    )
    due_soon = list(tasks_result.scalars().all())

    evt_result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.project_id == project.id)
        .order_by(CalendarEvent.starts_at.asc())
        .limit(1)
    )
    next_event = evt_result.scalar_one_or_none()

    linked_count = 0
    if next_ms:
        linked_count = await db.scalar(
            select(func.count()).select_from(Task).where(Task.milestone_id == next_ms.id)
        ) or 0

    return DashboardSummary(
        task_counts={"total": total or 0, "pending": pending or 0, "done": done or 0},
        next_milestone=MilestoneOut(
            id=next_ms.id,
            name=next_ms.name,
            target_date=next_ms.target_date,
            status=next_ms.status,
            linked_task_count=linked_count,
        )
        if next_ms
        else None,
        due_soon=[TaskOut.model_validate(t) for t in due_soon],
        next_event=next_event,
    )
