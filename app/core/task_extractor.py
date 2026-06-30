import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.config import get_settings


@dataclass
class TaskExtraction:
    title: str
    description: str | None = None
    assignee_name: str | None = None
    due_date: date | None = None
    priority: str = "medium"


class TaskExtractor:
    async def extract(self, raw_text: str) -> TaskExtraction:
        settings = get_settings()
        if settings.openai_api_key:
            try:
                return await self._extract_with_llm(raw_text)
            except Exception:
                pass
        return self._extract_with_rules(raw_text)

    async def _extract_with_llm(self, raw_text: str) -> TaskExtraction:
        import json

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        prompt = f"""สกัดข้อมูลงานจากข้อความ ตอบ JSON:
{{"title":"...", "description":"...", "assignee_name":"...", "due_date":"YYYY-MM-DD|null", "priority":"low|medium|high|urgent"}}

ข้อความ: {raw_text}"""
        response = await client.chat.completions.create(
            model=get_settings().openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content or "{}")
        due = data.get("due_date")
        due_date = date.fromisoformat(due[:10]) if due and due != "null" else None
        return TaskExtraction(
            title=data.get("title") or raw_text[:80],
            description=data.get("description"),
            assignee_name=data.get("assignee_name"),
            due_date=due_date,
            priority=data.get("priority", "medium"),
        )

    def _extract_with_rules(self, raw_text: str) -> TaskExtraction:
        text = raw_text.strip()
        for prefix in ("ลงงาน", "เพิ่มงาน", "create task", "task:"):
            if text.lower().startswith(prefix):
                text = text[len(prefix) :].strip(" :—-")
                break
        assignee = None
        due_date = None
        m = re.search(r"(?:มอบให้|assignee|ผู้รับ)\s*[:：]?\s*(\S+)", text, re.I)
        if m:
            assignee = m.group(1)
        if "พรุ่งนี้" in text:
            due_date = date.today() + timedelta(days=1)
        elif "ศุกร์" in text:
            due_date = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 or 7)
        return TaskExtraction(title=text[:120] or "งานใหม่", assignee_name=assignee, due_date=due_date)
