import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.core.llm import chat_json, llm_available

logger = logging.getLogger(__name__)


@dataclass
class ExtractedActionItem:
    description: str
    owner_name: str | None = None
    due_date: date | None = None
    is_inferred: bool = False


@dataclass
class MeetingExtraction:
    title: str
    meeting_date: date | None
    attendees: list[str]
    decisions: list[str]
    action_items: list[ExtractedActionItem]
    memo_body: str


class MeetingExtractor:
    """Extract structured meeting data from free text. Uses LLM when configured, else rules."""

    async def extract(self, raw_text: str) -> MeetingExtraction:
        if llm_available():
            try:
                return await self._extract_with_llm(raw_text)
            except Exception:
                logger.exception("LLM extraction failed, falling back to rules")

        return self._extract_with_rules(raw_text)

    async def _extract_with_llm(self, raw_text: str) -> MeetingExtraction:
        prompt = f"""สกัดข้อมูลการประชุมจากข้อความด้านล่าง ตอบเป็น JSON เท่านั้น:
{{
  "title": "หัวข้อประชุม",
  "meeting_date": "YYYY-MM-DD หรือ null",
  "attendees": ["ชื่อ1", "ชื่อ2"],
  "decisions": ["มติ1"],
  "action_items": [{{"description": "...", "owner_name": "...", "due_date": "YYYY-MM-DD หรือ null", "is_inferred": false}}],
  "memo_body": "สรุป memo ภาษาไทย"
}}

ข้อความ:
{raw_text}"""
        data = await chat_json(prompt)
        return self._parse_llm_data(data, raw_text)

    def _parse_llm_data(self, data: dict[str, Any], raw_text: str) -> MeetingExtraction:
        action_items = [
            ExtractedActionItem(
                description=item.get("description", ""),
                owner_name=item.get("owner_name"),
                due_date=self._parse_date(item.get("due_date")),
                is_inferred=bool(item.get("is_inferred", False)),
            )
            for item in data.get("action_items", [])
            if item.get("description")
        ]
        return MeetingExtraction(
            title=data.get("title") or "บันทึกการประชุม",
            meeting_date=self._parse_date(data.get("meeting_date")),
            attendees=data.get("attendees", []),
            decisions=data.get("decisions", []),
            action_items=action_items,
            memo_body=data.get("memo_body") or raw_text[:500],
        )

    def _extract_with_rules(self, raw_text: str) -> MeetingExtraction:
        lines = [ln.strip() for ln in raw_text.strip().splitlines() if ln.strip()]
        title = lines[0][:120] if lines else "บันทึกการประชุม"

        attendees: list[str] = []
        decisions: list[str] = []
        action_items: list[ExtractedActionItem] = []

        for line in lines[1:]:
            lower = line.lower()
            if lower.startswith("ผู้เข้าร่วม") or lower.startswith("attendees"):
                names = re.split(r"[:：]", line, maxsplit=1)
                if len(names) > 1:
                    attendees = [n.strip() for n in re.split(r"[,、]", names[1]) if n.strip()]
            elif lower.startswith("มติ") or lower.startswith("decision"):
                decisions.append(re.split(r"[:：]", line, maxsplit=1)[-1].strip())
            elif lower.startswith("action") or "ต้องทำ" in lower or line.startswith("-") or line.startswith("•"):
                desc = re.sub(r"^[-•]\s*", "", line)
                action_items.append(ExtractedActionItem(description=desc, is_inferred=True))

        return MeetingExtraction(
            title=title,
            meeting_date=None,
            attendees=attendees,
            decisions=decisions,
            action_items=action_items,
            memo_body=raw_text,
        )

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
