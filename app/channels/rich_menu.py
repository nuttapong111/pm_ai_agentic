"""Create and publish LINE Rich Menu (requires image upload)."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH = 2500
HEIGHT = 1686
ROW_H = HEIGHT // 2
COL_W = WIDTH // 3

_active_rich_menu_id: str | None = None

LABELS = [
    ("โปรเจกต์", "#0f6e56"),
    ("สรุปประชุม", "#185fa5"),
    ("ลงงาน", "#534ab7"),
    ("งานค้าง", "#854f0b"),
    ("เอกสาร", "#993c1d"),
    ("ช่วยเหลือ", "#5f5e5a"),
]

_FONT_PATHS = [
    Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

ICONS = ("folder", "meeting", "task", "pending", "document", "help")


def get_active_rich_menu_id() -> str | None:
    return _active_rich_menu_id


def fetch_user_rich_menu_id(channel_access_token: str, line_user_id: str) -> str | None:
    headers = {"Authorization": f"Bearer {channel_access_token}"}
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"https://api.line.me/v2/bot/user/{line_user_id}/richmenu",
            headers=headers,
        )
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning("Fetch user rich menu failed: %s %s", resp.status_code, resp.text)
        return None
    return resp.json().get("richMenuId")


def resolve_rich_menu_id(channel_access_token: str) -> str | None:
    menu_id = get_active_rich_menu_id()
    if menu_id:
        return menu_id
    return fetch_default_rich_menu_id(channel_access_token)


def ensure_user_rich_menu_linked(channel_access_token: str, line_user_id: str) -> bool:
    """Link default rich menu to a user if they don't have one yet."""
    menu_id = resolve_rich_menu_id(channel_access_token)
    if not menu_id:
        return False
    current = fetch_user_rich_menu_id(channel_access_token, line_user_id)
    if current == menu_id:
        return True
    link_rich_menu_to_user(channel_access_token, menu_id, line_user_id)
    return True


def rich_menu_status(channel_access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {channel_access_token}"}
    with httpx.Client(timeout=30) as client:
        listed = client.get("https://api.line.me/v2/bot/richmenu/list", headers=headers)
        default_resp = client.get("https://api.line.me/v2/bot/user/all/richmenu", headers=headers)

    menus: list[dict[str, Any]] = []
    if listed.status_code == 200:
        menus = listed.json().get("richmenus", [])

    default_id: str | None = None
    if default_resp.status_code == 200:
        default_id = default_resp.json().get("richMenuId")

    return {
        "menuCount": len(menus),
        "menus": [
            {"richMenuId": m.get("richMenuId"), "name": m.get("name"), "selected": m.get("selected")}
            for m in menus
        ],
        "defaultRichMenuId": default_id,
        "activeInProcess": get_active_rich_menu_id(),
    }


def liff_action_url(liff_id: str, app_base_url: str, page: str) -> str:
    """LINE rich menu URIs must NOT contain # fragments — use query params."""
    if liff_id:
        return f"https://liff.line.me/{liff_id}?page={page}"
    return f"{app_base_url.rstrip('/')}/liff/?page={page}"


def build_rich_menu_definition(liff_id: str, app_base_url: str) -> dict[str, Any]:
    return {
        "size": {"width": WIDTH, "height": HEIGHT},
        "selected": True,
        "name": "PM Assistant Menu",
        "chatBarText": "เมนู",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": COL_W, "height": ROW_H},
                "action": {"type": "uri", "uri": liff_action_url(liff_id, app_base_url, "projects")},
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
                "action": {"type": "uri", "uri": liff_action_url(liff_id, app_base_url, "documents")},
            },
            {
                "bounds": {"x": COL_W * 2, "y": ROW_H, "width": WIDTH - COL_W * 2, "height": HEIGHT - ROW_H},
                "action": {"type": "message", "text": "ช่วยเหลือ"},
            },
        ],
    }


def _load_font(size: int = 64) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        p = Path(path)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    logger.warning("No Thai font found — rich menu labels may not render")
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, cx: int, cy: int, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), text, fill=fill, font=font)


def _draw_icon(draw: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, color: str) -> None:
    s = 56
    if kind == "folder":
        draw.rounded_rectangle([cx - s, cy - s + 10, cx + s, cy + s], radius=12, outline=color, width=8)
        draw.rounded_rectangle([cx - s + 8, cy - s - 6, cx - s + 50, cy - s + 18], radius=8, fill=color)
    elif kind == "meeting":
        draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=8)
        draw.line([cx, cy - s + 16, cx, cy], fill=color, width=8)
        draw.line([cx, cy, cx + s - 16, cy + 10], fill=color, width=8)
    elif kind == "task":
        draw.rounded_rectangle([cx - s + 8, cy - s, cx + s, cy + s], radius=12, outline=color, width=8)
        draw.line([cx - s + 24, cy + 4, cx - 8, cy + 28], fill=color, width=8)
        draw.line([cx - 8, cy + 28, cx + s - 12, cy - 20], fill=color, width=8)
    elif kind == "pending":
        draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=8)
        draw.arc([cx - s + 12, cy - s + 12, cx + s - 12, cy + s - 12], start=90, end=360, fill=color, width=8)
        draw.line([cx, cy, cx, cy - 24], fill=color, width=8)
    elif kind == "document":
        draw.polygon(
            [(cx - s + 8, cy - s), (cx + s - 20, cy - s), (cx + s, cy - s + 20), (cx + s, cy + s), (cx - s + 8, cy + s)],
            outline=color,
            width=8,
        )
        for y in range(cy - 20, cy + 30, 22):
            draw.line([cx - s + 28, y, cx + s - 20, y], fill=color, width=6)
    else:
        draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=8)
        _center(draw, "?", ImageFont.load_default(), cx, cy, color)


def generate_rich_menu_image() -> bytes:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f7f9fb")
    draw = ImageDraw.Draw(img)
    label_font = _load_font(56)

    for i, (label, color) in enumerate(LABELS):
        col, row = i % 3, i // 3
        x0, y0 = col * COL_W, row * ROW_H
        x1 = x0 + (COL_W if col < 2 else WIDTH - COL_W * 2)
        y1 = y0 + (ROW_H if row == 0 else HEIGHT - ROW_H)
        cx = (x0 + x1) // 2

        draw.rectangle([x0 + 8, y0 + 8, x1 - 8, y1 - 8], fill="white", outline="#e3e6ea", width=4)
        draw.rectangle([x0 + 8, y0 + 8, x1 - 8, y0 + 36], fill=color)
        _draw_icon(draw, ICONS[i], cx, y0 + (y1 - y0) // 2 - 30, color)
        _center(draw, label, label_font, cx, y0 + (y1 - y0) // 2 + 70, "#1f2937")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def link_rich_menu_to_user(channel_access_token: str, rich_menu_id: str, line_user_id: str) -> None:
    headers = {"Authorization": f"Bearer {channel_access_token}"}
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"https://api.line.me/v2/bot/user/{line_user_id}/richmenu/{rich_menu_id}",
            headers=headers,
        )
    if resp.status_code != 200:
        logger.warning("Link rich menu to user failed: %s %s", resp.status_code, resp.text)


def setup_rich_menu(
    channel_access_token: str,
    liff_id: str = "",
    app_base_url: str = "http://localhost:8000",
    *,
    replace_existing: bool = True,
) -> str:
    """Create rich menu, upload image, set as default. Returns richMenuId."""
    global _active_rich_menu_id
    menu = build_rich_menu_definition(liff_id, app_base_url)
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
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
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

    _active_rich_menu_id = rich_menu_id
    logger.info("Rich menu ready: %s", rich_menu_id)
    return rich_menu_id
