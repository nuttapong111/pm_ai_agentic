import logging
import uuid

from app.ports.email import EmailMessage, EmailResult, EmailSender
from app.ports.tracker import ExternalTaskRef, TaskDraft, TaskTracker

logger = logging.getLogger(__name__)


class MockTaskTracker(TaskTracker):
    _sent_keys: set[str] = set()

    async def create_task(
        self, project_id: uuid.UUID, draft: TaskDraft, idempotency_key: str
    ) -> ExternalTaskRef:
        if idempotency_key in self._sent_keys:
            logger.info("mock_tracker: idempotent hit %s", idempotency_key)
            return ExternalTaskRef(provider="mock", key=f"MOCK-{idempotency_key[:8]}", url="https://mock.local/task")
        self._sent_keys.add(idempotency_key)
        key = f"MOCK-{uuid.uuid4().hex[:6].upper()}"
        logger.info("mock_tracker: created %s for project %s — %s", key, project_id, draft.title)
        return ExternalTaskRef(provider="mock", key=key, url=f"https://mock.local/tasks/{key}")


class MockEmailSender(EmailSender):
    _sent_keys: set[str] = set()

    async def send(self, message: EmailMessage, idempotency_key: str) -> EmailResult:
        if idempotency_key in self._sent_keys:
            return EmailResult(message_id=f"mock-{idempotency_key[:8]}", ok=True)
        self._sent_keys.add(idempotency_key)
        logger.info(
            "mock_email: to=%s subject=%s",
            message.to,
            message.subject,
        )
        return EmailResult(message_id=f"mock-{uuid.uuid4().hex[:12]}", ok=True)
