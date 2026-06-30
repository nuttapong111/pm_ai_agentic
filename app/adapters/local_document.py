from pathlib import Path
from typing import Any
from uuid import UUID

from app.db.models import WorkProductType
from app.ports.document import DocumentGenerator, RenderedDocument


class LocalDocumentGenerator(DocumentGenerator):
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
        # MVP: store JSON placeholder; Phase 2 uses docxtpl with uploaded templates
        doc_number = data.get("doc_number", "DRAFT")
        filename = f"{project_id}_{wp_type.value}_{doc_number}.json"
        path = self.storage_dir / filename
        path.write_text(str({"title": title, "data": data}), encoding="utf-8")
        return RenderedDocument(doc_number=doc_number, file_ref=str(path), data=data)
