from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import get_calendar, get_document_generator, get_email_sender, get_tracker
from app.config import get_settings
from app.core.doc_numbering import DocumentNumberingService
from app.db.models import (
    ActionItem,
    AuditLog,
    CalendarEvent,
    CalendarEventAttendee,
    ConfirmationStatus,
    DocStatus,
    Document,
    Meeting,
    MeetingAttendee,
    Milestone,
    PendingConfirmation,
    ProjectMember,
    Task,
    TaskPriority,
    TaskStatus,
    WorkProductType,
)
from app.ports.calendar import CalendarEventDraft
from app.ports.email import EmailMessage
from app.ports.tracker import TaskDraft
from app.schemas import ExecutionAction, ExecutionResult


class ConfirmationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, confirmation: PendingConfirmation) -> ExecutionResult:
        if confirmation.status != ConfirmationStatus.pending:
            raise ValueError("ร่างถูกจัดการไปแล้ว")
        if confirmation.expires_at < datetime.now(timezone.utc):
            confirmation.status = ConfirmationStatus.expired
            await self.db.commit()
            raise ValueError("ร่างหมดอายุแล้ว")

        confirmation.status = ConfirmationStatus.confirmed
        intent = confirmation.intent
        draft = confirmation.draft_data

        handlers = {
            "meeting_record": self._execute_meeting_record,
            "create_task": self._execute_create_task,
            "calendar_event": self._execute_calendar_event,
            "create_milestone": self._execute_create_milestone,
        }
        handler = handlers.get(intent)
        if not handler:
            result = ExecutionResult(
                status="failed",
                actions=[ExecutionAction(tool=intent, ok=False, error="ยังไม่รองรับ")],
            )
        else:
            result = await handler(confirmation.project_id, draft)

        await self.db.commit()
        return result

    async def cancel(self, confirmation: PendingConfirmation) -> None:
        confirmation.status = ConfirmationStatus.cancelled
        await self.db.commit()

    async def _execute_meeting_record(
        self, project_id: UUID | None, draft: dict[str, Any]
    ) -> ExecutionResult:
        if not project_id:
            raise ValueError("ไม่มีโปรเจกต์")

        numbering = DocumentNumberingService(self.db)
        doc_number = await numbering.get_next_number(project_id, WorkProductType.meeting_record)

        meeting_date = self._parse_date(draft.get("meeting_date"))

        meeting = Meeting(
            project_id=project_id,
            title=draft.get("title", "บันทึกการประชุม"),
            meeting_date=meeting_date,
            raw_notes=draft.get("raw_notes"),
            decisions=draft.get("decisions", []),
        )
        self.db.add(meeting)
        await self.db.flush()

        for name in draft.get("attendees", []):
            self.db.add(MeetingAttendee(meeting_id=meeting.id, name=name))

        for item in draft.get("action_items", []):
            self.db.add(
                ActionItem(
                    meeting_id=meeting.id,
                    project_id=project_id,
                    description=item.get("description", ""),
                    due_date=self._parse_date(item.get("due_date")),
                    is_inferred=bool(item.get("is_inferred", False)),
                )
            )

        doc_data = {
            "doc_number": doc_number,
            "title": meeting.title,
            "meeting_date": str(meeting.meeting_date) if meeting.meeting_date else None,
            "decisions": meeting.decisions,
            "memo_body": draft.get("memo_body", ""),
        }
        doc_gen = get_document_generator()
        rendered = await doc_gen.render(
            project_id, WorkProductType.meeting_record, meeting.title, doc_data
        )

        document = Document(
            project_id=project_id,
            wp_type=WorkProductType.meeting_record,
            doc_number=doc_number,
            title=meeting.title,
            data=doc_data,
            file_ref=rendered.file_ref,
            status=DocStatus.issued,
            source_type="meeting",
            source_id=meeting.id,
            issued_at=datetime.now(timezone.utc),
        )
        self.db.add(document)

        actions: list[ExecutionAction] = [ExecutionAction(tool="document", ok=True, ref=doc_number)]

        recipient_emails = draft.get("recipient_emails", [])
        if recipient_emails:
            email_sender = get_email_sender()
            memo_body = draft.get("memo_body", "")
            email_result = await email_sender.send(
                EmailMessage(
                    to=recipient_emails,
                    subject=f"[Meeting Record] {meeting.title} — {doc_number}",
                    body_html=f"<pre>{memo_body}</pre>",
                    body_text=memo_body,
                ),
                idempotency_key=f"meeting-{meeting.id}",
            )
            actions.append(
                ExecutionAction(
                    tool="email",
                    ok=email_result.ok,
                    ref=email_result.message_id,
                    error=email_result.error,
                )
            )

        self.db.add(
            AuditLog(
                project_id=project_id,
                action="meeting_record.created",
                entity_type="meeting",
                entity_id=meeting.id,
                detail={"doc_number": doc_number},
            )
        )
        status = "success" if all(a.ok for a in actions) else "partial"
        return ExecutionResult(status=status, actions=actions)

    async def _execute_create_task(
        self, project_id: UUID | None, draft: dict[str, Any]
    ) -> ExecutionResult:
        if not project_id:
            raise ValueError("ไม่มีโปรเจกต์")

        assignee_id = draft.get("assignee_id")
        task = Task(
            project_id=project_id,
            title=draft.get("title", "งานใหม่"),
            description=draft.get("description"),
            assignee_id=UUID(assignee_id) if assignee_id else None,
            due_date=self._parse_date(draft.get("due_date")),
            priority=TaskPriority(draft.get("priority", "medium")),
            status=TaskStatus.todo,
            milestone_id=UUID(draft["milestone_id"]) if draft.get("milestone_id") else None,
        )
        self.db.add(task)
        await self.db.flush()

        tracker = get_tracker()
        ext = await tracker.create_task(
            project_id,
            TaskDraft(
                title=task.title,
                description=task.description,
                assignee_name=draft.get("assignee_name"),
                due_date=task.due_date,
                priority=task.priority.value,
            ),
            idempotency_key=f"task-{task.id}",
        )
        task.external_ref = {"provider": ext.provider, "key": ext.key, "url": ext.url}

        self.db.add(
            AuditLog(
                project_id=project_id,
                action="task.created",
                entity_type="task",
                entity_id=task.id,
                detail={"external_key": ext.key},
            )
        )
        return ExecutionResult(
            status="success",
            actions=[
                ExecutionAction(tool="project_plan", ok=True, ref=str(task.id)),
                ExecutionAction(tool=ext.provider, ok=True, ref=ext.key),
            ],
        )

    async def _execute_calendar_event(
        self, project_id: UUID | None, draft: dict[str, Any]
    ) -> ExecutionResult:
        if not project_id:
            raise ValueError("ไม่มีโปรเจกต์")

        starts_at = datetime.fromisoformat(draft["starts_at"])
        ends_at = datetime.fromisoformat(draft["ends_at"]) if draft.get("ends_at") else None
        calendar = get_calendar()
        external = await calendar.create_event(
            project_id,
            CalendarEventDraft(
                title=draft.get("title", "นัดหมาย"),
                starts_at=starts_at,
                ends_at=ends_at,
                recurrence_rule=draft.get("recurrence_rule"),
                attendee_emails=draft.get("attendee_emails", []),
                create_meet_link=draft.get("create_meet_link", True),
            ),
        )

        event = CalendarEvent(
            project_id=project_id,
            title=draft.get("title", "นัดหมาย"),
            starts_at=starts_at,
            ends_at=ends_at,
            recurrence_rule=draft.get("recurrence_rule"),
            meet_link=external.meet_link,
            external_event_id=external.event_id,
        )
        self.db.add(event)
        await self.db.flush()

        for email in draft.get("attendee_emails", []):
            self.db.add(CalendarEventAttendee(event_id=event.id, email=email))

        return ExecutionResult(
            status="success",
            actions=[
                ExecutionAction(tool="calendar", ok=True, ref=external.event_id),
                ExecutionAction(tool="meet", ok=bool(external.meet_link), ref=external.meet_link),
            ],
        )

    async def _execute_create_milestone(
        self, project_id: UUID | None, draft: dict[str, Any]
    ) -> ExecutionResult:
        if not project_id:
            raise ValueError("ไม่มีโปรเจกต์")

        ms = Milestone(
            project_id=project_id,
            name=draft.get("name", "Milestone"),
            description=draft.get("description"),
            target_date=self._parse_date(draft.get("target_date")),
        )
        self.db.add(ms)
        await self.db.flush()

        linked = 0
        for task_id in draft.get("task_ids", []):
            task = await self.db.get(Task, UUID(task_id))
            if task and task.project_id == project_id:
                task.milestone_id = ms.id
                linked += 1

        return ExecutionResult(
            status="success",
            actions=[ExecutionAction(tool="milestone", ok=True, ref=ms.name, error=None)],
        )

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def default_expiry() -> datetime:
        minutes = get_settings().confirmation_timeout_minutes
        return datetime.now(timezone.utc) + timedelta(minutes=minutes)
