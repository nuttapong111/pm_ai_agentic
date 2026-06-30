#!/usr/bin/env python3
"""Setup LINE rich menu for PM Assistant."""

import os
import sys

import httpx

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LIFF_ID = os.environ.get("LINE_LIFF_ID", "")
BASE = os.environ.get("APP_BASE_URL", "http://localhost:8000")

if not TOKEN:
    print("Set LINE_CHANNEL_ACCESS_TOKEN")
    sys.exit(1)

liff_url = f"https://liff.line.me/{LIFF_ID}" if LIFF_ID else f"{BASE}/liff/"

menu = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "PM Assistant Menu",
    "chatBarText": "เมนู",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
            "action": {"type": "uri", "uri": f"{liff_url}#/projects"},
        },
        {
            "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
            "action": {"type": "message", "text": "สรุปประชุม"},
        },
        {
            "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
            "action": {"type": "message", "text": "ลงงาน"},
        },
        {
            "bounds": {"x": 0, "y": 843, "width": 833, "height": 843},
            "action": {"type": "postback", "data": "action:pending_tasks"},
        },
        {
            "bounds": {"x": 833, "y": 843, "width": 834, "height": 843},
            "action": {"type": "uri", "uri": f"{liff_url}#/documents"},
        },
        {
            "bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
            "action": {"type": "message", "text": "ช่วยเหลือ"},
        },
    ],
}

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

with httpx.Client() as client:
    resp = client.post("https://api.line.me/v2/bot/richmenu", headers=headers, json=menu, timeout=30)
    print(resp.status_code, resp.text)
    if resp.status_code == 200:
        rich_menu_id = resp.json()["richMenuId"]
        client.post(
            f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
            headers=headers,
            timeout=30,
        )
        print(f"Rich menu set: {rich_menu_id}")
