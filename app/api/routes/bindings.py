from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_for_user
from app.db.models import Capability, Connection, Project, ProjectBinding
from app.db.session import get_db
from app.schemas import BindingInput, BindingOut, CapabilityEnum

router = APIRouter(tags=["Bindings"])


@router.get("/projects/{project_id}/bindings", response_model=list[BindingOut])
async def list_bindings(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectBinding]:
    result = await db.execute(select(ProjectBinding).where(ProjectBinding.project_id == project.id))
    return list(result.scalars().all())


@router.put("/projects/{project_id}/bindings/{capability}", response_model=BindingOut)
async def upsert_binding(
    capability: CapabilityEnum,
    body: BindingInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectBinding:
    connection = await db.get(Connection, body.connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบ connection")

    cap = Capability(capability.value)
    result = await db.execute(
        select(ProjectBinding).where(
            ProjectBinding.project_id == project.id,
            ProjectBinding.capability == cap,
        )
    )
    binding = result.scalar_one_or_none()
    if binding:
        binding.connection_id = body.connection_id
        binding.config = body.config
    else:
        binding = ProjectBinding(
            project_id=project.id,
            capability=cap,
            connection_id=body.connection_id,
            config=body.config,
        )
        db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return binding
