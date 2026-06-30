from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.confirmation import ConfirmationService
from app.db.models import PendingConfirmation
from app.db.session import get_db
from app.schemas import ExecutionResult

router = APIRouter(prefix="/confirmations", tags=["Confirmations"])


@router.post("/{confirmation_id}/confirm", response_model=ExecutionResult)
async def confirm_draft(
    confirmation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExecutionResult:
    result = await db.execute(
        select(PendingConfirmation).where(PendingConfirmation.id == confirmation_id)
    )
    confirmation = result.scalar_one_or_none()
    if not confirmation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบร่าง")

    service = ConfirmationService(db)
    try:
        return await service.execute(confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{confirmation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_draft(
    confirmation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(PendingConfirmation).where(PendingConfirmation.id == confirmation_id)
    )
    confirmation = result.scalar_one_or_none()
    if not confirmation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบร่าง")

    service = ConfirmationService(db)
    await service.cancel(confirmation)
