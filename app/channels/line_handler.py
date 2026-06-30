import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.orchestrator import Orchestrator
from app.db.models import LineContext, User

logger = logging.getLogger(__name__)


class LineNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def reply(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        if not self.settings.line_channel_access_token:
            logger.warning("LINE_CHANNEL_ACCESS_TOKEN not set — skip reply")
            return

        url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Authorization": f"Bearer {self.settings.line_channel_access_token}",
            "Content-Type": "application/json",
        }
        payload = {"replyToken": reply_token, "messages": messages}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code >= 400:
                logger.error("LINE reply failed: %s %s", resp.status_code, resp.text)

    async def push(self, line_user_id: str, text: str) -> None:
        if not self.settings.line_channel_access_token:
            logger.warning("LINE_CHANNEL_ACCESS_TOKEN not set — skip push")
            return
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {self.settings.line_channel_access_token}",
            "Content-Type": "application/json",
        }
        payload = {"to": line_user_id, "messages": [{"type": "text", "text": text}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code >= 400:
                logger.error("LINE push failed: %s %s", resp.status_code, resp.text)

    def build_messages(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        if response.get("type") == "confirm_card":
            text = response["text"]
            cid = response["confirmation_id"]
            confirm_text = response.get("confirm_text", "ยืนยันดำเนินการ?")
            return [
                {"type": "text", "text": text},
                {
                    "type": "template",
                    "altText": confirm_text,
                    "template": {
                        "type": "confirm",
                        "text": confirm_text,
                        "actions": [
                            {"type": "postback", "label": "ยืนยัน", "data": f"confirm:{cid}"},
                            {"type": "postback", "label": "ยกเลิก", "data": f"cancel:{cid}"},
                        ],
                    },
                },
            ]
        return [{"type": "text", "text": response.get("text", "")}]


class LineWebhookHandler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.notifier = LineNotifier()
        self.orchestrator = Orchestrator(db)

    def verify_signature(self, body: bytes, signature: str | None) -> bool:
        if self.settings.app_env == "development" and not self.settings.line_channel_secret:
            return True
        if not signature or not self.settings.line_channel_secret:
            return False
        hash_digest = hmac.new(
            self.settings.line_channel_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(hash_digest).decode()
        return hmac.compare_digest(expected, signature)

    async def process_events(self, payload: dict[str, Any]) -> None:
        for event in payload.get("events", []):
            try:
                await self._handle_event(event)
            except Exception:
                logger.exception("Failed to handle LINE event")

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        source = event.get("source", {})
        source_type = source.get("type", "user")
        source_id = source.get("userId") or source.get("groupId") or source.get("roomId")
        if not source_id:
            return

        user = await self._get_or_create_user(source.get("userId", source_id))
        line_context = await self._get_or_create_context(source_type, source_id)

        if event_type == "message" and event.get("message", {}).get("type") == "text":
            text = event["message"]["text"]
            response = await self.orchestrator.handle_message(user, line_context, text)
            reply_token = event.get("replyToken")
            if reply_token:
                messages = self.notifier.build_messages(response)
                await self.notifier.reply(reply_token, messages)

        elif event_type == "postback":
            data = event.get("postback", {}).get("data", "")
            response = await self.orchestrator.handle_postback(line_context, data)
            reply_token = event.get("replyToken")
            if reply_token:
                messages = self.notifier.build_messages(response)
                await self.notifier.reply(reply_token, messages)

    async def _get_or_create_user(self, line_user_id: str) -> User:
        result = await self.db.execute(select(User).where(User.line_user_id == line_user_id))
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(line_user_id=line_user_id)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def _get_or_create_context(self, source_type: str, source_id: str) -> LineContext:
        result = await self.db.execute(
            select(LineContext).where(
                LineContext.line_source_type == source_type,
                LineContext.line_source_id == source_id,
            )
        )
        ctx = result.scalar_one_or_none()
        if ctx:
            return ctx
        ctx = LineContext(line_source_type=source_type, line_source_id=source_id)
        self.db.add(ctx)
        await self.db.commit()
        await self.db.refresh(ctx)
        return ctx
