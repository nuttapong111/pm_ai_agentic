from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.models import Project, ProjectMember, User
from app.db.session import get_db
from app.schemas import MemberInput, MemberOut

router = APIRouter(tags=["Members"])


@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectMember]:
    result = await db.execute(select(ProjectMember).where(ProjectMember.project_id == project.id))
    return list(result.scalars().all())


@router.post("/projects/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(
    body: MemberInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectMember:
    member = ProjectMember(
        project_id=project.id,
        name=body.name,
        email=str(body.email) if body.email else None,
        role=body.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def _get_member_for_user(member_id: UUID, user: User, db: AsyncSession) -> ProjectMember:
    result = await db.execute(
        select(ProjectMember)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.id == member_id, Project.owner_user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบสมาชิก")
    return member


@router.patch("/members/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: UUID,
    body: MemberInput,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectMember:
    member = await _get_member_for_user(member_id, user, db)
    member.name = body.name
    member.email = str(body.email) if body.email else None
    member.role = body.role
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    member_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    member = await _get_member_for_user(member_id, user, db)
    await db.delete(member)
    await db.commit()
