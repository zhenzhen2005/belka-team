# Tech — Belka

> แหล่งข้อมูล: docs/submission.md (หัวข้อ 07, 08, 16, 17·18, 19) และ pyproject.toml · ข้อความที่ Kiro สันนิษฐานเอง ติดป้าย "(assumption)"

## สถาปัตยกรรม
API-centric, serverless-friendly ประกอบด้วย:
- **Mobile UI:** onboarding · feed · แคปชัน
- **Trust Engine:** โค้ดคำนวณ 100% AI ไม่ยุ่งกับตัวเลข ประกอบด้วย
  34 แบบคอนเทนต์ (A1–G4), discount engine, profit calculator (ต้นทุนวัตถุดิบ + GP ตามช่องทาง),
  งบการตลาดจาก GP ที่ประหยัดได้, message gate, ตัววางช่องทาง/เวลา, learning loop
- **AI assistant:** เลือกกลยุทธ์, เขียนแคปชันไทย, ตอบแชต "ถาม Belka" ด้วย structured output เท่านั้น
- **OCR** สำหรับนำเข้าเมนู, **API** LINE / Meta / Google / TikTok, **dashboard** วัดผลแผนการตลาด

## การตัดสินใจทางเทคนิค
| เรื่อง | การตัดสินใจ | ที่มา |
|---|---|---|
| ตัวเลข | คำนวณด้วยโค้ดใน Trust Engine ไม่ให้ AI คิดเลข | submission 07 |
| การโพสต์ | เฟสแรกเป็น guided posting เจ้าของร้านยืนยันก่อนโพสต์ | submission D-7 |
| Build vs Buy | ซื้อ/ต่อ API เกือบทุกอย่าง สร้างเองเฉพาะสูตรคำนวณ คลังกลยุทธ์ ป้าย/QR | submission 08 |
| ความล้มเหลวของ AI | ตรวจคำตอบอัตโนมัติ → ลองใหม่ → แผนสำรองจาก Trust Engine | submission R1 |
| การพึ่ง API หลายเจ้า | ใส่ abstraction layer เริ่มจาก LINE (ฟรี) | submission R4 |
| ความเร็ว | ตอบ ≤ ~8 วินาที ด้วย prompt/model ที่ปรับแล้ว แคช และแสดงสถานะ | submission S6, R3 |
| ภาษาไทย | human-in-the-loop ตรวจคุณภาพภาษาไทย | submission Go/No-Go ข้อ 3 |
| ภาษา/รันไทม์ | Python >=3.12 จัดการด้วย `uv` | pyproject.toml |
| Agent | Strands Agents SDK ฟังก์ชัน `@tool` พร้อม docstring ชัดเจน | pyproject.toml (`strands-agents`) |
| โมเดล | Amazon Bedrock, ap-southeast-1, `anthropic.claude-sonnet-5` ห้าม model ID ขึ้นต้น `global.` หรือ `apac.` | aws.md, agent.py |
| Region ที่บัญชีทีมอนุญาต | ap-southeast-1, ap-southeast-7, us-east-1 | aws.md |
| คลาวด์ | Amazon Bedrock AgentCore (Runtime ก่อน) AgentCore CLI ปักที่ 0.30.0 ห้าม `@latest` `@preview` | aws.md |
| Agent ไม่มีเครื่องมือโพสต์ | การโพสต์เป็นโค้ดธรรมดานอก agent หลังเจ้าของร้านยืนยัน (assumption: ออกแบบเพื่อบังคับกฎ guided posting) | — |
| ผลลัพธ์จากเครื่องมือคือความจริง | system prompt ให้อ้างเฉพาะสิ่งที่เครื่องมือคืนมา (ตามแบบใน agent.py) | agent.py |

## คำสั่ง (รันในโฟลเดอร์โปรเจกต์)
pyproject.toml มี dependency หลักคือ `strands-agents` และมี pytest ใน dev group พร้อมตั้งค่า pytest (`pythonpath`, `testpaths`)

| งาน | คำสั่ง | หมายเหตุ |
|---|---|---|
| ติดตั้งแพ็กเกจ | `uv sync` | อ่าน pyproject.toml และ uv.lock |
| ล็อกอิน AWS | `aws sso login` | ต้องทำก่อนรันคำสั่งที่เรียก Bedrock (assumption: ชื่อ profile ยังไม่ระบุ ถ้าใช้ profile ให้เติม `--profile`) |
| เช็กว่า Bedrock ตอบ | `uv run check_bedrock.py` | พิมพ์ `READY` เมื่อสำเร็จ |
| คุยกับ agent | `uv run agent.py` | พิมพ์ `exit` เพื่อออก agent.py เป็น Belka (system prompt จาก Agent design ใน `.kiro/specs/weekly-plan/requirements.md`) ใช้ tool จำลอง 3 ตัวกับร้านสมมติ |
| เพิ่ม pytest | `uv add --dev pytest` | เพิ่มแล้วใน pyproject.toml ไม่ต้องทำซ้ำ |
| รันเทสต์ | `uv run pytest` | เทสต์ต้องไม่เรียก AWS ตอนนี้มี `tests/test_agent.py` หนึ่งข้อ และ hook `test-on-save` ใน `.kiro/hooks/` รันคำสั่งนี้เมื่อ Kiro บันทึกไฟล์ .py |

## ความปลอดภัยและต้นทุน
- ห้ามใส่ access key, secret, password, token ในโค้ด ไฟล์ หรือแชต ใช้ SSO เท่านั้น
- ไฟล์ `.env` อยู่ใน `.gitignore` แล้ว ห้าม commit
- ห้ามลบหรือแก้ทรัพยากรในบัญชีทีมโดยไม่ถามก่อน
- ต้นแบบใช้ข้อมูลตัวอย่างเท่านั้น ห้ามใช้ข้อมูลส่วนบุคคลจริง (submission มอบหมาย PDPA ให้แพร)
- งบทีมรวม US$500 ถึง 12 ธ.ค. ห้ามเปิดทรัพยากรที่คิดเงินต่อเนื่องโดยไม่ถาม (assumption: ตัวเลขนี้มาจาก steering ฉบับร่างเดิม ไม่มีใน submission)

## ความเสี่ยงและวิธีรับมือ
| ความเสี่ยง | วิธีรับมือ |
|---|---|
| R1 AI ตอบผิดรูปแบบ/ไม่ครบ | ตรวจ → ลองใหม่ → แผนสำรองจาก Trust Engine + เทสต์กรณีผิดรูปแบบ |
| R2 เลิกใช้ (คอนเทนต์ไม่ตรง/ไม่มีเวลา) | แผน ≤10 นาที/วัน + "ทำไม?" + นำร่องร้านจริง |
| R3 AI ตอบช้า | optimize prompt/model · แคช · แสดงสถานะ |
| R4 พึ่งพา API หลายเจ้า | abstraction layer · เริ่ม LINE |
| R5 เคลม "ลดต้นทุน" เกินจริง | เคลมเฉพาะต้นทุนที่คุมได้ (เอเจนซี่/GP/หาลูกค้า) |
| R6 ร้านสับสน GP กับต้นทุนวัตถุดิบ | แยกช่องกรอก · GP หักอัตโนมัติ · ค่าประมาณติดป้าย "แก้ได้" |
| R7 คู่แข่งฟรีจากรัฐ (นกกระซิบ) | วางเป็นเครื่องมือการตลาดที่ใช้คู่กันได้ · freemium |
| C-app auto-posting ติด app review | guided posting เฟสแรก · ขอ review ล่วงหน้า (2–6 สัปดาห์/แพลตฟอร์ม) |
| ข้อความเสี่ยงหลุดถึงร้าน | message gate ที่เป็นโค้ด + เทสต์กรณีคำต้องห้าม (assumption: เทสต์เป็นข้อเสนอของ Kiro) |
| โพสต์โดยร้านไม่ยืนยัน | agent ไม่มีเครื่องมือโพสต์ + เทสต์กรณีไม่ยืนยัน (assumption) |

## สมมติฐาน
ยังไม่ยืนยัน (ตรวจช่วง Pilot): A2 ตัดสินใจคนเดียว · A6 ยอมกรอกต้นทุนแบบง่าย · A7 รู้ GP% ของตัวเอง
ผลกระทบทางเทคนิค: ทุกฟีเจอร์ที่ใช้ต้นทุนหรือ GP ต้องทำงานได้เมื่อร้านไม่กรอกอะไร (ใช้ค่ามาตรฐานติดป้ายค่าประมาณ)

## คำถามที่ต้องให้ทีมตัดสินใจ
1. submission ระบุ **Amazon Quick** เป็น AI chatbot, **Cloud Vision** เป็น OCR และ **QuickSight** เป็น dashboard แต่ pyproject.toml และ aws.md ใช้ Strands + Bedrock + AgentCore ตอนนี้ steering ยึด Strands + Bedrock ตาม repo ทีมต้องยืนยันว่า Amazon Quick, Cloud Vision, QuickSight อยู่นอกขอบเขตต้นแบบหรือไม่ (assumption: อยู่นอกขอบเขตต้นแบบ)
2. ~~ชื่อฟีเจอร์ must-have~~ ตัดสินใจแล้ว: แผนสัปดาห์พร้อมแคปชันและเหตุผล (ดู product.md)
3. ชื่อ AWS profile สำหรับ SSO
