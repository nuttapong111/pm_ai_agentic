import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentNumberSequence, NumberReset, Project, WorkProductType


class DocumentNumberingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_next_number(self, project_id: UUID, wp_type: WorkProductType) -> str:
        project = await self.db.get(Project, project_id)
        if not project:
            raise ValueError("ไม่พบโปรเจกต์")

        result = await self.db.execute(
            select(DocumentNumberSequence).where(
                DocumentNumberSequence.project_id == project_id,
                DocumentNumberSequence.wp_type == wp_type,
            )
        )
        seq = result.scalar_one_or_none()
        if not seq:
            seq = DocumentNumberSequence(
                project_id=project_id,
                wp_type=wp_type,
                prefix=self._default_prefix(wp_type),
            )
            self.db.add(seq)
            await self.db.flush()

        now = datetime.now(timezone.utc)
        current_year = now.year

        if seq.reset_period == NumberReset.yearly and (
            seq.last_reset_year is None or seq.last_reset_year < current_year
        ):
            new_seq = 1
            last_reset_year = current_year
        else:
            new_seq = seq.current_seq + 1
            last_reset_year = seq.last_reset_year or current_year

        await self.db.execute(
            update(DocumentNumberSequence)
            .where(DocumentNumberSequence.id == seq.id)
            .values(current_seq=new_seq, last_reset_year=last_reset_year)
        )

        return self._format_number(
            pattern=seq.pattern,
            project_key=project.key,
            wp_type=wp_type,
            prefix=seq.prefix,
            seq=new_seq,
            year=current_year,
        )

    @staticmethod
    def _default_prefix(wp_type: WorkProductType) -> str:
        mapping = {
            WorkProductType.meeting_record: "MIN",
            WorkProductType.memo: "MEM",
            WorkProductType.project_plan: "PLN",
            WorkProductType.requirements: "REQ",
            WorkProductType.traceability: "TRC",
            WorkProductType.test_case: "TC",
            WorkProductType.change_request: "CR",
        }
        return mapping.get(wp_type, "DOC")

    @staticmethod
    def _format_number(
        pattern: str,
        project_key: str,
        wp_type: WorkProductType,
        prefix: str,
        seq: int,
        year: int,
    ) -> str:
        result = pattern
        result = result.replace("{KEY}", project_key)
        result = result.replace("{TYPE}", prefix)
        result = result.replace("{YYYY}", str(year))

        def replacer(match: re.Match[str]) -> str:
            width = int(match.group(1))
            return str(seq).zfill(width)

        result = re.sub(r"\{SEQ:(\d+)d\}", replacer, result)
        return result
