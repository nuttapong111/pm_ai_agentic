from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.db.models import WorkProductType


@dataclass
class RenderedDocument:
    doc_number: str
    file_ref: str
    data: dict[str, Any]


class DocumentGenerator(ABC):
    @abstractmethod
    async def render(
        self,
        project_id: UUID,
        wp_type: WorkProductType,
        title: str,
        data: dict[str, Any],
    ) -> RenderedDocument:
        pass
