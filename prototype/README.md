# prototype/ — ต้นแบบอ้างอิงสำหรับ spec weekly-plan

> **ไม่ใช่ตัวที่ทีมส่งงาน** โค้ดหลักต้องสร้างตาม `.kiro/specs/weekly-plan/` ด้วย Kiro (requirements, design, tasks ของทีม)
> โฟลเดอร์นี้มีโค้ดที่รันได้แล้ว ใช้ดูเป็นตัวอย่างตอนให้ Kiro ทำแต่ละ task และใช้ลองข้อเสนอ P-1 ถึง P-3 ใน `.kiro/steering/product.md`
> เพิ่มเมื่อ 18 พ.ย. 2026 · ไม่ได้แก้ไฟล์เดิมของทีม นอกจากเพิ่มส่วนท้ายใน `product.md` และ `docs/handoff.md` (สำรองไว้ที่ `_backup-2026-11-18/`)

## มีอะไรบ้าง
| ไฟล์ | ทำอะไร |
|---|---|
| `backend/belka/redline.py` | red-line gate ด้วยโค้ดล้วน คืนคำที่มีปัญหา เหตุผล และคำแนะนำ |
| `backend/belka/trust_engine.py` | เลือกช่องทาง/วัน/เวลา/นาที และเนื้อหาสำรองของทุกแบบร้าน |
| `backend/belka/agent.py` | Strands agent บน Bedrock (`anthropic.claude-sonnet-5` @ ap-southeast-1) มีเครื่องมือ `check_redline` |
| `backend/belka/planner.py` | เวลาจำกัด 8 วินาที ลองใหม่ ตรวจซ้ำ แผนสำรองต่องานและทั้งชุด ปฏิเสธ model ID ผิดกฎ |
| `backend/belka/api.py` | FastAPI: `/api/plan`, `/api/redline`, `/api/health` และเสิร์ฟ `web/` |
| `web/index.html` | หน้าเว็บขนาดมือถือ: onboarding แตะ 3 ขั้น (P-1) + การ์ดงานวันนี้ 1 ใบ (P-2) |
| `mobile/` | แอป Expo (P-3 ขัดกับ D1 ของทีม ใช้หลังทีมอนุมัติเท่านั้น) |
| `scripts/check_setup.py` | ตรวจ R1/R10 ตามกฎบัญชีทีม |
| `backend/tests/` | เทสต์ 218 ข้อ ไม่เรียก AWS |

## รัน (จากโฟลเดอร์ my-team)
ใช้ virtualenv ของโปรเจกต์ผ่าน `uv` ไม่ต้องแก้ `pyproject.toml` ของทีม

```bash
cd prototype/backend

# เทสต์ (ไม่เรียก AWS)
uv run --with fastapi pytest

# ลองแผนโดยไม่เรียก AI
uv run python -m belka.cli plan --fallback

# R11: เอเจนต์เรียกเครื่องมือ check_redline จริง (ต้อง aws sso login ก่อน)
uv run python -m belka.cli redline

# เปิดหน้าเว็บ (เฉพาะเครื่องนี้ ตาม D1)
uv run --with fastapi --with uvicorn uvicorn belka.api:app --host 127.0.0.1 --port 8000
# แล้วเปิด http://127.0.0.1:8000
```

ตรวจความพร้อม R1/R10: `cd prototype && uv run --with fastapi --with uvicorn python scripts/check_setup.py`

## ใช้กับ task ไหนของทีม
| task ใน `.kiro/specs/weekly-plan/tasks.md` | ดูตัวอย่างที่ | หมายเหตุ |
|---|---|---|
| 3 Gate and safe text | `redline.py`, `_fallback_content` ใน `trust_engine.py` | spec ทีมต้องการ normalise ข้อความ (5.11) และตารางคำแทน (5.3) เพิ่ม |
| 5 Slots and minutes | `build_slots` ใน `trust_engine.py` | spec ทีมต้องรองรับวันปิดร้าน และรวมนาทีต่อวันไม่เกิน 10 |
| 6 Fallback and pipeline | `fallback_task`, `merge_ai_tasks` | spec ทีมให้ใช้ชื่อร้าน/เมนูจาก seed (3.8, 7.9) |
| 9 Prompt, tools, agent | `agent.py` | ใช้ system prompt ของทีมใน requirements "Agent design" แทนของต้นแบบ |
| 10–11 AI client, service | `planner.py` (`_call_with_deadline`, ลองใหม่, `config_refused`) | spec ทีมแยก cause code และลองใหม่เฉพาะ timeout/invalid_format |
| 13 Web app | `web/index.html` | ใช้เป็นแบบหน้าจอ ถ้าทีมรับ P-1/P-2 |

prompt ตัวอย่างใน Kiro:
```
#spec:weekly-plan ทำ task 3.1 โดยดู prototype/backend/belka/redline.py เป็นตัวอย่าง
แต่ทำตาม requirements 5.10 และ 5.11 ของ spec ทีมเป็นหลัก ถ้าต้นแบบขัดกับ spec ให้เชื่อ spec
```

## ต่างจาก spec ของทีมตรงไหน (อย่าลอกส่วนนี้)
| เรื่อง | ต้นแบบ | spec ทีม |
|---|---|---|
| ข้อมูลร้าน | onboarding แตะ 3 ขั้น (P-1) | เลือกร้านจาก `data/seed_*.json` (Req 1) |
| ใครเลือกช่องทาง | Trust Engine (โค้ด) | AI เลือก Trust Engine ตรวจ (D2) |
| หน้าจอหลัก | การ์ดงานวันนี้ 1 ใบ (P-2) | แผน 3 งานในหน้าเดียว (2.8) |
| เก็บแผน | ในเบราว์เซอร์ (localStorage) | ไฟล์ `var/plans/<shop_id>.json` (Req 9) |
| แก้แคปชัน | ได้ ต้องผ่าน gate | อยู่นอกขอบเขต |
| ยกเลิกระหว่างรอ / กันกดซ้ำ | ไม่มี | มี (Req 8) |
| figure rule, ป้องกัน injection ใน profile | ไม่มี | มี (10.2, Req 11) |
| ตรวจ Host/Origin | ไม่มี | มี (2.2) |
| แอปมือถือ | Expo (P-3) | ไม่ทำแอป native (D1) |

## เปิดเว็บ (18 พ.ย. 2569)
```bash
cd ~/Documents/my-team/prototype/backend
uv run --with fastapi --with uvicorn uvicorn belka.api:app --host 127.0.0.1 --port 8000
```
แล้วเปิด http://127.0.0.1:8000 (ถ้าต้องการให้ AI เขียนแผน/ตอบแชท ต้อง `aws sso login` ก่อน ไม่งั้นใช้คำตอบมาตรฐานอัตโนมัติ)

## แบรนด์และสติกเกอร์
- `brand/stickers/` สติกเกอร์กระรอก 53 ตัว ตัดจากไฟล์ของทีมใน Downloads (พื้นโปร่งใส ≤360px) รายชื่อใน `index.json`
- `brand/belka-app-icon-512.png`, `-192.png` ไอคอนแอปความละเอียดสูง (ทำมุมโปร่งใสจากไฟล์ 1254px ของทีม)
- `brand/belka-shop-logo.jpg` โลโก้ป้ายร้าน Belka
- ใช้ในเว็บ: หน้าต้อนรับ, ไอคอนตัวเลือก 3 ขั้น, แท็บล่าง, มุมการ์ดทุกใบ, อวาตาร์ลูกค้าจำลองแยกกลุ่ม, ไอคอนกลุ่มคอนเทนต์ A–G, ตอนโหลด, แชทถาม Belka
- เวอร์ชันก่อนหน้าเก็บไว้ที่ `_backup-2026-11-18/prototype-v1/`

## อัปเดต 18 พ.ย. 2569 (เย็น)
- onboarding เป็น 4 ขั้น: ขั้นที่ 4 ให้เลือกกลุ่มลูกค้าจำลอง 1–3 กลุ่มก่อน จึงได้แผน (ส่งใน `ShopProfile.personas`; เวลาโพสต์ใช้ของกลุ่มที่เลือก)
- แผนไม่ซ้ำรายสัปดาห์: `ShopProfile.history` เก็บประเภทงานของสัปดาห์ก่อน ๆ, `trust_engine.POOLS` หมุนงานแต่ละช่องทาง (ครบ 4 สัปดาห์จึงวนกลับ) งานตั้งค่าครั้งเดียว (ปักหมุด/เปิด LINE OA) ไม่ทำซ้ำ
- แท็บไอเดีย: การ์ด "วิเคราะห์แผนสัปดาห์นี้", ปุ่ม 📌 ใส่ในแผน (สูงสุด 3 งาน, ข้อเสนอราคา 1 งาน), หน้าต่าง "ไปวิเคราะห์ร้านของคุณ"
- วัดผลโปรใช้ปฏิทินแตะวัน (มีโปร/ไม่มีโปร) แทนการพิมพ์ตัวเลข
- แก้บั๊ก: กดช่องพิมพ์ใน "ถาม Belka" แล้วหน้าต่างปิด
- ใช้ AI (Bedrock) เฉพาะเขียนแผน/แคปชัน (`/api/plan`) และตอบแชท (`/api/ask`) · ส่วนที่เหลือเป็นโค้ดล้วน
- ปฏิทินเทศกาลและ trend radar อ่านที่ `data/trend_calendar.json` / Google Trends RSS
