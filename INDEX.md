# PM Assistant — ชุดเอกสารโปรเจกต์

ผู้ช่วย AI สำหรับ IT Project Manager ทำงานผ่าน LINE: สรุปประชุมเป็นเอกสาร work product
ตาม ISO 29110, เปิดงานเข้า Jira/ClickUp, จัดการนัดหมาย Google Calendar และแจ้งเตือน

## ไฟล์ในชุดนี้

| ไฟล์ | คืออะไร |
|---|---|
| `DESIGN_SPEC.md` | เอกสารออกแบบหลัก — สถาปัตยกรรม, flow (มี Mermaid diagram), โมเดลหลายแพลตฟอร์ม, ISO 29110, requirement (FR/NFR), แผนพัฒนา |
| `openapi.yaml` | API spec (OpenAPI 3.1) — 29 endpoint สำหรับ webhook + หน้าตั้งค่า LIFF |
| `db/schema.sql` | PostgreSQL schema — 23 ตาราง พร้อมคอมเมนต์ (deploy บน Railway) |
| `db/README.md` | อธิบาย schema, วิธีรันเลขเอกสารแบบ atomic, ขั้นตอน deploy, ตัวอย่าง prompt Cursor |
| `design/screens.html` | แคตตาล็อกหน้าจอทั้งหมด 19 หน้า (เปิดในเบราว์เซอร์) |

## ลำดับการอ่านที่แนะนำ

1. `DESIGN_SPEC.md` — เข้าใจภาพรวมระบบ
2. `design/screens.html` — ดูหน้าจอจริง
3. `db/schema.sql` + `db/README.md` — โครงข้อมูล
4. `openapi.yaml` — สัญญา API (เปิดใน Swagger UI / Redoc ได้)

## เริ่มสร้างจริง

วางทั้งหมดนี้ใน repo แล้วใช้เป็น context ให้ Cursor:
- จาก `schema.sql` → generate ORM models + migration
- จาก `openapi.yaml` → scaffold FastAPI routers + Pydantic models
- ยึด `DESIGN_SPEC.md` §11 (แผนเป็นเฟส) เริ่มจาก MVP: ประชุม → memo โดยใช้ mock adapter

แผน diagram ใน `DESIGN_SPEC.md` เป็น Mermaid — เปิดใน GitHub, VS Code (ส่วนขยาย Mermaid)
หรือ viewer ที่รองรับ จะ render เป็นภาพอัตโนมัติ
