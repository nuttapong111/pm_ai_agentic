from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.config import get_settings
from app.db.models import Document, Project, User, WorkProductType
from app.db.session import get_db
from app.schemas import DocumentListResponse, DocumentOut, WorkProductTypeEnum

router = APIRouter(tags=["Documents"])


@router.get("/projects/{project_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
    wp_type: WorkProductTypeEnum | None = Query(None, alias="wpType"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> DocumentListResponse:
    q = select(Document).where(Document.project_id == project.id)
    if wp_type:
        q = q.where(Document.wp_type == WorkProductType(wp_type.value))
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            q = q.where(Document.created_at < cursor_dt)
        except ValueError:
            pass
    q = q.order_by(Document.created_at.desc()).limit(limit + 1)
    result = await db.execute(q)
    docs = list(result.scalars().all())
    next_cursor = None
    if len(docs) > limit:
        docs = docs[:limit]
        next_cursor = docs[-1].created_at.isoformat()
    return DocumentListResponse(
        items=[DocumentOut.model_validate(d) for d in docs],
        next_cursor=next_cursor,
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        select(Document)
        .join(Project, Project.id == Document.project_id)
        .where(Document.id == document_id, Project.owner_user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบเอกสาร")

    settings = get_settings()
    url = f"{settings.app_base_url}/storage/{doc.file_ref.replace('storage/', '')}"
    return {"downloadUrl": url}
