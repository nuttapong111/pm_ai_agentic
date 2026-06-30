from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.models import Project, Task, TaskStatus
from app.db.session import get_db
from app.schemas import TaskInput, TaskOut, TaskStatusEnum

router = APIRouter(tags=["Tasks"])


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
    status_filter: TaskStatusEnum | None = Query(None, alias="status"),
    due_before: date | None = Query(None, alias="dueBefore"),
    milestone_id: UUID | None = Query(None, alias="milestoneId"),
) -> list[Task]:
    q = select(Task).where(Task.project_id == project.id)
    if status_filter:
        q = q.where(Task.status == TaskStatus(status_filter.value))
    if due_before:
        q = q.where(Task.due_date <= due_before)
    if milestone_id:
        q = q.where(Task.milestone_id == milestone_id)
    q = q.order_by(Task.due_date.asc().nulls_last())
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> Task:
    task = Task(
        project_id=project.id,
        title=body.title,
        description=body.description,
        assignee_id=body.assignee_id,
        due_date=body.due_date,
        priority=body.priority,
        milestone_id=body.milestone_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: UUID,
    body: TaskInput,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Task:
    result = await db.execute(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(Task.id == task_id, Project.owner_user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบงาน")
    task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.assignee_id is not None:
        task.assignee_id = body.assignee_id
    if body.due_date is not None:
        task.due_date = body.due_date
    if body.priority is not None:
        task.priority = body.priority
    if body.milestone_id is not None:
        task.milestone_id = body.milestone_id
    await db.commit()
    await db.refresh(task)
    return task
