"""Create and publish LINE Rich Menu (requires image upload)."""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH = 2500
HEIGHT = 1686
ROW_H = HEIGHT // 2
COL_W = WIDTH // 3

LABELS = [
    ("โปรเจกต์", "#0f6e56"),
    ("สรุปประชุม", "#185fa5"),
    ("ลงงาน", "#534ab7"),
    ("งานค้าง", "#854f0b"),
    ("เอกสาร", "#993c1d"),
    ("ช่วยเหลือ", "#5f5e5a"),
]


def build_rich_menu_definition(liff_url: str) -> dict[str, Any]:
    return {
        "size": {"width": WIDTH, "height": HEIGHT},
        "selected": True,
        "name": "PM Assistant Menu",
        "chatBarText": "เมนู",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": COL_W, "height": ROW_H},
                "action": {"type": "uri", "uri": f"{liff_url}#/projects"},
            },
            {
                "bounds": {"x": COL_W, "y": 0, "width": COL_W, "height": ROW_H},
                "action": {"type": "message", "text": "สรุปประชุม"},
            },
            {
                "bounds": {"x": COL_W * 2, "y": 0, "width": WIDTH - COL_W * 2, "height": ROW_H},
                "action": {"type": "message", "text": "ลงงาน"},
            },
            {
                "bounds": {"x": 0, "y": ROW_H, "width": COL_W, "height": HEIGHT - ROW_H},
                "action": {"type": "postback", "data": "action:pending_tasks", "displayText": "งานค้าง"},
            },
            {
                "bounds": {"x": COL_W, "y": ROW_H, "width": COL_W, "height": HEIGHT - ROW_H},
                "action": {"type": "uri", "uri": f"{liff_url}#/documents"},
            },
            {
                "bounds": {"x": COL_W * 2, "y": ROW_H, "width": WIDTH - COL_W * 2, "height": HEIGHT - ROW_H},
                "action": {"type": "message", "text": "ช่วยเหลือ"},
            },
        ],
    }


def generate_rich_menu_image() -> bytes:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f7f9fb")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 72)
    except OSError:
        font = ImageFont.load_default()

    for i, (label, color) in enumerate(LABELS):
        col, row = i % 3, i // 3
        x0, y0 = col * COL_W, row * ROW_H
        x1 = x0 + (COL_W if col < 2 else WIDTH - COL_W * 2)
        y1 = y0 + (ROW_H if row == 0 else HEIGHT - ROW_H)
        draw.rectangle([x0 + 8, y0 + 8, x1 - 8, y1 - 8], fill="white", outline="#e3e6ea", width=4)
        draw.rectangle([x0 + 8, y0 + 8, x1 - 8, y0 + 28], fill=color)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x0 + (x1 - x0 - tw) // 2
        ty = y0 + (y1 - y0 - th) // 2 + 10
        draw.text((tx, ty), label, fill="#1f2937", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def resolve_liff_url(liff_id: str, app_base_url: str) -> str:
    if liff_id:
        return f"https://liff.line.me/{liff_id}"
    base = app_base_url.rstrip("/")
    return f"{base}/liff/"


def setup_rich_menu(
    channel_access_token: str,
    liff_id: str = "",
    app_base_url: str = "http://localhost:8000",
    *,
    replace_existing: bool = True,
) -> str:
    """Create rich menu, upload image, set as default. Returns richMenuId."""
    liff_url = resolve_liff_url(liff_id, app_base_url)
    menu = build_rich_menu_definition(liff_url)
    headers_json = {"Authorization": f"Bearer {channel_access_token}", "Content-Type": "application/json"}
    image_bytes = generate_rich_menu_image()

    with httpx.Client(timeout=60) as client:
        if replace_existing:
            listed = client.get("https://api.line.me/v2/bot/richmenu/list", headers=headers_json)
            if listed.status_code == 200:
                for item in listed.json().get("richmenus", []):
                    rid = item["richMenuId"]
                    client.delete(f"https://api.line.me/v2/bot/richmenu/{rid}", headers=headers_json)
                    logger.info("Deleted old rich menu %s", rid)

        created = client.post("https://api.line.me/v2/bot/richmenu", headers=headers_json, json=menu)
        if created.status_code != 200:
            raise RuntimeError(f"Create rich menu failed: {created.status_code} {created.text}")

        rich_menu_id = created.json()["richMenuId"]

        upload_headers = {
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "image/png",
        }
        uploaded = client.post(
            f"https://api.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers=upload_headers,
            content=image_bytes,
        )
        if uploaded.status_code != 200:
            client.delete(f"https://api.line.me/v2/bot/richmenu/{rich_menu_id}", headers=headers_json)
            raise RuntimeError(f"Upload image failed: {uploaded.status_code} {uploaded.text}")

        linked = client.post(
            f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
            headers=headers_json,
        )
        if linked.status_code != 200:
            raise RuntimeError(f"Set default rich menu failed: {linked.status_code} {linked.text}")

    return rich_menu_id
