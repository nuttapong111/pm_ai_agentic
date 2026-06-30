from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentTemplate, WorkProductType
from app.db.session import async_session
from app.ports.document import DocumentGenerator, RenderedDocument


class DocxTplDocumentGenerator(DocumentGenerator):
    def __init__(self, storage_dir: str = "storage/documents") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def render(
        self,
        project_id: UUID,
        wp_type: WorkProductType,
        title: str,
        data: dict[str, Any],
    ) -> RenderedDocument:
        doc_number = data.get("doc_number", "DRAFT")
        template_path = await self._get_template_path(project_id, wp_type)
        out_name = f"{project_id}_{wp_type.value}_{doc_number}.docx"
        out_path = self.storage_dir / out_name

        if template_path and template_path.exists():
            try:
                from docxtpl import DocxTemplate

                doc = DocxTemplate(str(template_path))
                doc.render({**data, "title": title})
                doc.save(str(out_path))
                return RenderedDocument(doc_number=doc_number, file_ref=str(out_path), data=data)
            except Exception:
                pass

        # fallback: plain text file
        txt_path = out_path.with_suffix(".txt")
        txt_path.write_text(
            f"{title}\n{'='*40}\n" + "\n".join(f"{k}: {v}" for k, v in data.items()),
            encoding="utf-8",
        )
        return RenderedDocument(doc_number=doc_number, file_ref=str(txt_path), data=data)

    async def _get_template_path(self, project_id: UUID, wp_type: WorkProductType) -> Path | None:
        async with async_session() as db:
            result = await db.execute(
                select(DocumentTemplate)
                .where(DocumentTemplate.project_id == project_id, DocumentTemplate.wp_type == wp_type)
                .order_by(DocumentTemplate.version.desc())
            )
            tpl = result.scalar_one_or_none()
            return Path(tpl.file_ref) if tpl else None
