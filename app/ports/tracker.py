from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID


@dataclass
class TaskDraft:
    title: str
    description: str | None = None
    assignee_name: str | None = None
    due_date: date | None = None
    priority: str = "medium"


@dataclass
class ExternalTaskRef:
    provider: str
    key: str
    url: str


class TaskTracker(ABC):
    @abstractmethod
    async def create_task(
        self, project_id: UUID, draft: TaskDraft, idempotency_key: str
    ) -> ExternalTaskRef:
        pass
