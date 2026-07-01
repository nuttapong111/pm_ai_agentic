#!/usr/bin/env python3
"""Setup LINE rich menu — run once after deploy or when LINE credentials change."""

import os
import sys

from app.channels.rich_menu import resolve_liff_url, setup_rich_menu

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LIFF_ID = os.environ.get("LINE_LIFF_ID", "")
BASE = os.environ.get("APP_BASE_URL", "http://localhost:8000")

if not TOKEN:
    print("ERROR: ตั้ง LINE_CHANNEL_ACCESS_TOKEN ก่อน")
    sys.exit(1)

if not LIFF_ID:
    print("WARNING: ไม่มี LINE_LIFF_ID — ปุ่ม LIFF จะใช้ URL ตรง อาจไม่เปิดในแอป LINE ได้")
    print(f"         LIFF URL ที่จะใช้: {resolve_liff_url('', BASE)}")

try:
    menu_id = setup_rich_menu(TOKEN, LIFF_ID, BASE)
    print(f"OK — Rich menu พร้อมใช้งาน: {menu_id}")
    print("เปิดแชทบอทใหม่ (ปิดแล้วเปิดใหม่) ถ้ายังไม่เห็นเมนู")
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)
