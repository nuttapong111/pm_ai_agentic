from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.confirmation import ConfirmationService
from app.core.meeting_extractor import MeetingExtractor
from app.core.task_extractor import TaskExtractor
from app.db.models import (
    CalendarEvent,
    LineContext,
    PendingConfirmation,
    Project,
    ProjectMember,
    Task,
    TaskStatus,
    User,
)


class Intent(str, Enum):
    meeting_record = "meeting_record"
    create_task = "create_task"
    query_tasks = "query_tasks"
    calendar_event = "calendar_event"
    create_milestone = "create_milestone"
    unknown = "unknown"
    greeting = "greeting"


class Orchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.meeting_extractor = MeetingExtractor()
        self.task_extractor = TaskExtractor()

    async def handle_message(
        self,
        user: User,
        line_context: LineContext,
        text: str,
    ) -> dict[str, Any]:
        intent = self._classify_intent(text)

        if intent == Intent.greeting:
            return {
                "type": "text",
                "text": (
                    "สวัสดีครับ ผมเป็นผู้ช่วย PM\n"
                    "ลองพิมพ์:\n"
                    "• สรุปประชุม — วางบันทึกการประชุม\n"
                    "• ลงงาน — เพิ่ม task\n"
                    "• งานค้าง — ดูสถานะงาน\n"
                    "• นัดหมาย — สร้าง event ปฏิทิน\n"
                    "• milestone — สร้าง milestone"
                ),
            }

        if not line_context.project_id:
            return {
                "type": "text",
                "text": "ยังไม่ได้เลือกโปรเจกต์ กรุณาตั้งค่าโปรเจกต์ผ่านเมนู LIFF ก่อนครับ",
            }

        if intent == Intent.meeting_record:
            return await self._draft_meeting(line_context, text)
        if intent == Intent.create_task:
            return await self._draft_task(line_context, text)
        if intent == Intent.query_tasks:
            return await self._query_tasks(line_context)
        if intent == Intent.calendar_event:
            return await self._draft_calendar(line_context, text)
        if intent == Intent.create_milestone:
            return await self._draft_milestone(line_context, text)

        return {
            "type": "text",
            "text": "ผมยังไม่เข้าใจคำสั่งนี้ ลองพิมพ์ 'สรุปประชุม' หรือ 'ช่วยเหลือ' ครับ",
        }

    async def handle_postback(
        self,
        line_context: LineContext,
        data: str,
    ) -> dict[str, Any]:
        if data.startswith("confirm:"):
            confirmation_id = UUID(data.split(":", 1)[1])
            result = await self.db.execute(
                select(PendingConfirmation).where(PendingConfirmation.id == confirmation_id)
            )
            confirmation = result.scalar_one_or_none()
            if not confirmation:
                return {"type": "text", "text": "ไม่พบร่างที่ต้องการยืนยัน"}

            service = ConfirmationService(self.db)
            try:
                exec_result = await service.execute(confirmation)
                lines = [f"✅ ดำเนินการสำเร็จ ({exec_result.status})"]
                for a in exec_result.actions:
                    icon = "✓" if a.ok else "✗"
                    lines.append(f"{icon} {a.tool}: {a.ref or a.error or '-'}")
                return {"type": "text", "text": "\n".join(lines)}
            except ValueError as exc:
                return {"type": "text", "text": f"❌ {exc}"}

        if data.startswith("cancel:"):
            confirmation_id = UUID(data.split(":", 1)[1])
            result = await self.db.execute(
                select(PendingConfirmation).where(PendingConfirmation.id == confirmation_id)
            )
            confirmation = result.scalar_one_or_none()
            if confirmation:
                service = ConfirmationService(self.db)
                await service.cancel(confirmation)
            return {"type": "text", "text": "ยกเลิกร่างแล้วครับ"}

        if data == "action:pending_tasks":
            return await self._query_tasks(line_context)

        return {"type": "text", "text": "คำสั่งไม่รู้จัก"}

    async def _draft_meeting(self, line_context: LineContext, text: str) -> dict[str, Any]:
        extraction = await self.meeting_extractor.extract(text)
        recipient_emails = await self._project_emails(line_context.project_id)

        draft_data: dict[str, Any] = {
            "title": extraction.title,
            "meeting_date": extraction.meeting_date.isoformat() if extraction.meeting_date else None,
            "attendees": extraction.attendees,
            "decisions": extraction.decisions,
            "action_items": [
                {
                    "description": ai.description,
                    "owner_name": ai.owner_name,
                    "due_date": ai.due_date.isoformat() if ai.due_date else None,
                    "is_inferred": ai.is_inferred,
                }
                for ai in extraction.action_items
            ],
            "memo_body": extraction.memo_body,
            "raw_notes": text,
            "recipient_emails": recipient_emails,
        }
        return await self._save_draft(
            line_context, Intent.meeting_record.value, draft_data,
            self._format_meeting_preview(extraction),
            "ยืนยันส่ง Meeting Record และอีเมล?",
        )

    async def _draft_task(self, line_context: LineContext, text: str) -> dict[str, Any]:
        extraction = await self.task_extractor.extract(text)
        assignee_id = None
        if extraction.assignee_name and line_context.project_id:
            result = await self.db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == line_context.project_id,
                    ProjectMember.name.ilike(f"%{extraction.assignee_name}%"),
                )
            )
            member = result.scalar_one_or_none()
            if member:
                assignee_id = str(member.id)

        draft_data = {
            "title": extraction.title,
            "description": extraction.description,
            "assignee_name": extraction.assignee_name,
            "assignee_id": assignee_id,
            "due_date": extraction.due_date.isoformat() if extraction.due_date else None,
            "priority": extraction.priority,
        }
        lines = [
            "📋 ร่างงานใหม่",
            f"หัวข้อ: {extraction.title}",
        ]
        if extraction.assignee_name:
            lines.append(f"ผู้รับ: {extraction.assignee_name}")
        if extraction.due_date:
            lines.append(f"กำหนดส่ง: {extraction.due_date}")
        lines.append(f"ความสำคัญ: {extraction.priority}")

        return await self._save_draft(
            line_context, Intent.create_task.value, draft_data,
            "\n".join(lines),
            "ยืนยันลง Project Plan และเปิด card?",
        )

    async def _draft_calendar(self, line_context: LineContext, text: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        starts = now + timedelta(days=1)
        starts = starts.replace(hour=10, minute=0, second=0, microsecond=0)
        ends = starts + timedelta(hours=1)
        emails = await self._project_emails(line_context.project_id)
        title = text
        for prefix in ("นัดหมาย", "calendar", "ประชุม"):
            if title.lower().startswith(prefix):
                title = title[len(prefix) :].strip(" :—-")
                break

        draft_data = {
            "title": title or "นัดหมาย",
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO" if "ประจำ" in text or "weekly" in text.lower() else None,
            "attendee_emails": emails,
            "create_meet_link": True,
        }
        lines = [
            "📅 ร่างนัดหมาย",
            f"หัวข้อ: {draft_data['title']}",
            f"เริ่ม: {starts.strftime('%d/%m/%Y %H:%M')}",
        ]
        if draft_data["recurrence_rule"]:
            lines.append("ความถี่: รายสัปดาห์")
        return await self._save_draft(
            line_context, Intent.calendar_event.value, draft_data,
            "\n".join(lines),
            "ยืนยันสร้างนัดหมายใน Calendar?",
        )

    async def _draft_milestone(self, line_context: LineContext, text: str) -> dict[str, Any]:
        name = text
        for prefix in ("milestone", "ไมล์สโตน"):
            if name.lower().startswith(prefix):
                name = name[len(prefix) :].strip(" :—-")
                break
        draft_data = {"name": name or "Milestone ใหม่", "description": text, "task_ids": []}
        return await self._save_draft(
            line_context, Intent.create_milestone.value, draft_data,
            f"🏁 ร่าง Milestone\nชื่อ: {draft_data['name']}",
            "ยืนยันสร้าง milestone?",
        )

    async def _query_tasks(self, line_context: LineContext) -> dict[str, Any]:
        if not line_context.project_id:
            return {"type": "text", "text": "ยังไม่ได้เลือกโปรเจกต์"}

        today = date.today()
        result = await self.db.execute(
            select(Task)
            .where(
                Task.project_id == line_context.project_id,
                Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
            )
            .order_by(Task.due_date.asc().nulls_last())
            .limit(10)
        )
        tasks = list(result.scalars().all())
        if not tasks:
            return {"type": "text", "text": "ไม่มีงานค้างครับ 🎉"}

        lines = ["📌 งานค้าง:"]
        for t in tasks:
            due = ""
            if t.due_date:
                if t.due_date < today:
                    due = f" ⚠️ เลย { (today - t.due_date).days } วัน"
                elif t.due_date == today:
                    due = " 📅 วันนี้"
                else:
                    due = f" 📅 {t.due_date}"
            ext = (t.external_ref or {}).get("key", "")
            lines.append(f"• {t.title}{due}" + (f" [{ext}]" if ext else ""))

        evt = await self.db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.project_id == line_context.project_id)
            .where(CalendarEvent.starts_at >= datetime.now(timezone.utc))
            .order_by(CalendarEvent.starts_at.asc())
            .limit(1)
        )
        next_evt = evt.scalar_one_or_none()
        if next_evt:
            lines.append(f"\n📅 ประชุมถัดไป: {next_evt.title} — {next_evt.starts_at.strftime('%d/%m %H:%M')}")

        return {"type": "text", "text": "\n".join(lines)}

    async def _project_emails(self, project_id: UUID | None) -> list[str]:
        if not project_id:
            return []
        result = await self.db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return [m.email for m in result.scalars().all() if m.email]

    async def _save_draft(
        self,
        line_context: LineContext,
        intent: str,
        draft_data: dict[str, Any],
        preview: str,
        confirm_text: str,
    ) -> dict[str, Any]:
        confirmation = PendingConfirmation(
            line_context_id=line_context.id,
            project_id=line_context.project_id,
            intent=intent,
            draft_data=draft_data,
            expires_at=ConfirmationService.default_expiry(),
        )
        self.db.add(confirmation)
        await self.db.commit()
        await self.db.refresh(confirmation)
        return {
            "type": "confirm_card",
            "text": preview,
            "confirmation_id": str(confirmation.id),
            "confirm_text": confirm_text,
        }

    @staticmethod
    def _format_meeting_preview(extraction) -> str:
        lines = [f"📋 ร่าง Meeting Record", f"หัวข้อ: {extraction.title}"]
        if extraction.meeting_date:
            lines.append(f"วันที่: {extraction.meeting_date}")
        if extraction.attendees:
            lines.append(f"ผู้เข้าร่วม: {', '.join(extraction.attendees)}")
        if extraction.decisions:
            lines.append("มติ:")
            lines.extend(f"  • {d}" for d in extraction.decisions)
        if extraction.action_items:
            lines.append("Action items:")
            for ai in extraction.action_items:
                tag = " (ระบบเดา)" if ai.is_inferred else ""
                lines.append(f"  • {ai.description}{tag}")
        return "\n".join(lines)

    @staticmethod
    def _classify_intent(text: str) -> Intent:
        t = text.strip().lower()
        if t in ("สวัสดี", "hello", "hi", "ช่วยเหลือ", "help"):
            return Intent.greeting
        if any(kw in t for kw in ("สรุปประชุม", "บันทึกประชุม", "meeting record")):
            return Intent.meeting_record
        if any(kw in t for kw in ("ลงงาน", "เพิ่มงาน", "create task")) or (t.startswith("task") and "ค้าง" not in t):
            return Intent.create_task
        if any(kw in t for kw in ("งานค้าง", "สถานะงาน", "ค้าง")):
            return Intent.query_tasks
        if any(kw in t for kw in ("นัดหมาย", "calendar", "ประชุมประจำ")):
            return Intent.calendar_event
        if any(kw in t for kw in ("milestone", "ไมล์สโตน")):
            return Intent.create_milestone
        return Intent.unknown
