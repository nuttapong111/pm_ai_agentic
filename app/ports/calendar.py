from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class CalendarEventDraft:
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    recurrence_rule: str | None = None
    attendee_emails: list[str] | None = None
    create_meet_link: bool = True


@dataclass
class ExternalEventRef:
    event_id: str
    meet_link: str | None = None
    url: str | None = None


class CalendarProvider(ABC):
    @abstractmethod
    async def create_event(self, project_id: UUID, draft: CalendarEventDraft) -> ExternalEventRef:
        pass
