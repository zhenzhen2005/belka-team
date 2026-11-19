# Structure — Belka (ข้อเสนอ ปรับได้ตามที่ทีมตกลง)

> ทุกอย่างในไฟล์นี้เป็นข้อเสนอของ Kiro (assumption) submission.md ไม่ได้กำหนดโครงโฟลเดอร์
> ตอนนี้ repo มี `agent.py`, `check_bedrock.py`, `pyproject.toml`, `uv.lock`, `docs/` (submission.md, handoff.md), `tests/test_agent.py`, `.kiro/specs/weekly-plan/requirements.md` และ `.kiro/hooks/test-on-save.json` โฟลเดอร์อื่นให้สร้างเมื่อ spec ต้องใช้

## โครงโฟลเดอร์ที่เสนอ
```
my-team/
├── .kiro/
│   ├── steering/            # product.md, tech.md, structure.md, aws.md
│   └── specs/<ชื่อฟีเจอร์>/  # requirements.md, design.md, tasks.md
├── agent.py                 # สร้าง Strands agent (Belka พร้อม tool จำลอง 3 ตัว)
├── check_bedrock.py         # เช็กว่า Bedrock ตอบ (มีอยู่แล้ว)
├── pyproject.toml, uv.lock  # (มีอยู่แล้ว)
├── trust_engine/            # โค้ดคำนวณทั้งหมด ไม่พึ่ง AI และไม่เรียก AWS
│                            #   เช่น profit, discount, marketing_budget, message_gate, channel_planner
├── tools/                   # ฟังก์ชัน @tool ที่ agent เรียก เป็นตัวห่างาน trust_engine
├── prompts/                 # system prompt แยกตามพฤติกรรม
├── data/                    # ข้อมูลตัวอย่าง (seed) เท่านั้น
├── tests/                   # หนึ่งเทสต่อหนึ่ง acceptance criterion
└── docs/                    # submission.md (มีอยู่แล้ว), handoff.md
```

## กฎการตั้งชื่อ
- ไฟล์และโฟลเดอร์ Python: `snake_case`
- ชื่อ spec: `kebab-case` เช่น `weekly-plan`, `message-gate`
- ฟังก์ชัน/ตัวแปร: `snake_case` คลาส: `PascalCase` ค่าคงที่: `UPPER_SNAKE_CASE`
- ไฟล์เทสต์: `tests/test_<ชื่อโมดูล>.py` ฟังก์ชันเทสต์: `test_<ข้อกำหนด>_<พฤติกรรม>` (เช่น `test_req_2_1_gp_deducted_by_channel`)
- ไฟล์ prompt: `prompts/<พฤติกรรม>.md`
- ไฟล์ข้อมูลตัวอย่าง: `data/seed_<ชื่อ>.json` และต้องเป็นข้อมูลสมมติ

## กฎการทำงาน
- หนึ่งเทสต่อหนึ่งเงื่อนไขในแต่ละ requirement เทสต์ต้องไม่เรียก AWS
- ตัวเลขและสูตรอยู่ใน `trust_engine/` เท่านั้น ห้ามกระจายไปใน prompt หรือ `tools/`
- `tools/` ห่าง `trust_engine/` เท่านั้น ไม่มี logic คำนวณของตัวเอง
- ห้ามเพิ่มเครื่องมือโพสต์ให้ agent การโพสต์เป็นโค้ดนอก agent หลังเจ้าของร้านยืนยัน
- ข้อความที่แสดงผู้ใช้ผ่าน `trust_engine/message_gate` ก่อนเสมอ
- หนึ่งงานต่อหนึ่งเซสชัน เมื่อจบให้สรุปไว้ใน `docs/handoff.md`
- ถ้าต้องเปลี่ยนโครงสร้าง ให้บอกทีมและแก้ไฟล์นี้ด้วย
