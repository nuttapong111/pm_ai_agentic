"""LLM helper — default: Google Gemini (free tier via AI Studio)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def llm_available() -> bool:
    s = get_settings()
    if s.llm_provider == "gemini":
        return bool(s.gemini_api_key)
    return bool(s.openai_api_key)


async def chat_json(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("ไม่มี GEMINI_API_KEY")
        return await _gemini_json(prompt)
    if settings.openai_api_key:
        return await _openai_json(prompt)
    raise ValueError("ไม่มี LLM API key")


async def _gemini_json(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    model = settings.gemini_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


async def _openai_json(prompt: str) -> dict[str, Any]:
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")
