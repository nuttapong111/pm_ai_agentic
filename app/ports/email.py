from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmailMessage:
    to: list[str]
    subject: str
    body_html: str
    body_text: str | None = None


@dataclass
class EmailResult:
    message_id: str
    ok: bool
    error: str | None = None


class EmailSender(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage, idempotency_key: str) -> EmailResult:
        pass
