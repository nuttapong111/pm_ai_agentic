import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.models import DocumentTemplate, Project, User, WorkProductType
from app.db.session import get_db
from app.schemas import TemplateOut, WorkProductTypeEnum

router = APIRouter(tags=["Templates"])

STORAGE = Path("storage/templates")


@router.get("/projects/{project_id}/templates", response_model=list[TemplateOut])
async def list_templates(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentTemplate]:
    result = await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.project_id == project.id)
    )
    return list(result.scalars().all())


@router.post("/projects/{project_id}/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def upload_template(
    wp_type: WorkProductTypeEnum = Form(..., alias="wpType"),
    file: UploadFile = File(...),
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplate:
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ต้องเป็นไฟล์ .docx")

    STORAGE.mkdir(parents=True, exist_ok=True)
    dest = STORAGE / f"{project.id}_{wp_type.value}.docx"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    result = await db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.project_id == project.id,
            DocumentTemplate.wp_type == WorkProductType(wp_type.value),
        )
    )
    existing = result.scalar_one_or_none()
    version = (existing.version + 1) if existing else 1
    if existing:
        await db.delete(existing)

    template = DocumentTemplate(
        project_id=project.id,
        wp_type=WorkProductType(wp_type.value),
        file_ref=str(dest),
        version=version,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def _get_template_for_user(template_id: UUID, user: User, db: AsyncSession) -> DocumentTemplate:
    result = await db.execute(
        select(DocumentTemplate)
        .join(Project, Project.id == DocumentTemplate.project_id)
        .where(DocumentTemplate.id == template_id, Project.owner_user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบเทมเพลต")
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    template = await _get_template_for_user(template_id, user, db)
    Path(template.file_ref).unlink(missing_ok=True)
    await db.delete(template)
    await db.commit()
