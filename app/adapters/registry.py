from app.adapters.docxtpl_document import DocxTplDocumentGenerator
from app.adapters.local_document import LocalDocumentGenerator
from app.adapters.mock_tracker import MockEmailSender, MockTaskTracker
from app.config import get_settings
from app.ports.calendar import CalendarProvider
from app.ports.document import DocumentGenerator
from app.ports.email import EmailSender
from app.ports.tracker import TaskTracker


class _MockCalendar(CalendarProvider):
    async def create_event(self, project_id, draft):  # type: ignore[no-untyped-def]
        from app.ports.calendar import ExternalEventRef

        return ExternalEventRef(event_id="mock-event", meet_link="https://meet.mock/link")


def get_tracker() -> TaskTracker:
    settings = get_settings()
    if settings.tracker_adapter == "mock":
        return MockTaskTracker()
    raise NotImplementedError(f"tracker adapter '{settings.tracker_adapter}' ยังไม่พร้อม")


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.email_adapter == "mock":
        return MockEmailSender()
    raise NotImplementedError(f"email adapter '{settings.email_adapter}' ยังไม่พร้อม")


def get_calendar() -> CalendarProvider:
    return _MockCalendar()


def get_document_generator() -> DocumentGenerator:
    try:
        import docxtpl  # noqa: F401

        return DocxTplDocumentGenerator()
    except ImportError:
        return LocalDocumentGenerator()
