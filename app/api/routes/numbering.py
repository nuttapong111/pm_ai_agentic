from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_for_user
from app.core.doc_numbering import DocumentNumberingService
from app.db.models import DocumentNumberSequence, NumberReset, Project, WorkProductType
from app.db.session import get_db
from app.schemas import NumberingRuleInput, NumberingRuleOut, WorkProductTypeEnum

router = APIRouter(tags=["Numbering"])


@router.get("/projects/{project_id}/numbering", response_model=list[NumberingRuleOut])
async def list_numbering(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[NumberingRuleOut]:
    result = await db.execute(
        select(DocumentNumberSequence).where(DocumentNumberSequence.project_id == project.id)
    )
    rows = result.scalars().all()
    if rows:
        return [
            NumberingRuleOut(
                wp_type=r.wp_type.value,
                prefix=r.prefix,
                pattern=r.pattern,
                current_seq=r.current_seq,
                reset_period=r.reset_period.value,
            )
            for r in rows
        ]

    svc = DocumentNumberingService(db)
    defaults = []
    for wp in WorkProductType:
        defaults.append(
            NumberingRuleOut(
                wp_type=wp.value,
                prefix=svc._default_prefix(wp),
                pattern="{KEY}-{TYPE}-{SEQ:04d}",
                current_seq=0,
                reset_period="none",
            )
        )
    return defaults


@router.put("/projects/{project_id}/numbering/{wp_type}", response_model=NumberingRuleOut)
async def upsert_numbering(
    wp_type: WorkProductTypeEnum,
    body: NumberingRuleInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> NumberingRuleOut:
    wp = WorkProductType(wp_type.value)
    result = await db.execute(
        select(DocumentNumberSequence).where(
            DocumentNumberSequence.project_id == project.id,
            DocumentNumberSequence.wp_type == wp,
        )
    )
    row = result.scalar_one_or_none()
    svc = DocumentNumberingService(db)
    if not row:
        row = DocumentNumberSequence(
            project_id=project.id,
            wp_type=wp,
            prefix=body.prefix or svc._default_prefix(wp),
            pattern=body.pattern or "{KEY}-{TYPE}-{SEQ:04d}",
            reset_period=NumberReset(body.reset_period) if body.reset_period else NumberReset.none,
        )
        db.add(row)
    else:
        if body.prefix:
            row.prefix = body.prefix
        if body.pattern:
            row.pattern = body.pattern
        if body.reset_period:
            row.reset_period = NumberReset(body.reset_period)
    await db.commit()
    await db.refresh(row)
    return NumberingRuleOut(
        wp_type=row.wp_type.value,
        prefix=row.prefix,
        pattern=row.pattern,
        current_seq=row.current_seq,
        reset_period=row.reset_period.value,
    )
