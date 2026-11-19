"""สร้างคลังลูกค้าจำลอง (Simulated personas) 10,000 คนสำหรับ Belka

    python scripts/generate_personas.py            # เขียน data/personas_10000.json
    python scripts/generate_personas.py --n 500    # จำนวนอื่น

- ข้อมูลทั้งหมดเป็นข้อมูลสมมติ ไม่ใช่ข้อมูลคนจริง ทุกคนติดป้าย "Simulated"
- ใช้ seed คงที่ รันซ้ำได้ผลเดิมทุกครั้ง
- ค่าเฉลี่ยและสัดส่วนในไฟล์นี้เป็นสมมติฐานของทีม (assumption) ยังไม่ผ่านการตรวจกับข้อมูลจริง
  ปรับได้ที่ SEGMENTS ด้านล่าง แล้วรันใหม่
- กลุ่มลูกค้า 8 กลุ่ม ตรงกับคำในคลังคอนเทนต์ 34 แบบ (Belka_สูตรตัดสินใจ_ทุกคอนเทนต์.pdf)
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SEED = 20261118
ROOT = Path(__file__).resolve().parent.parent

PLATFORMS = ["LINE", "Facebook", "Instagram", "TikTok", "Google Maps", "Delivery app", "YouTube"]
FORMATS = ["คลิป", "ภาพเดียว", "สไลด์ภาพ", "โพสต์ข้อความ", "ข้อความ LINE", "ป้าย", "อินโฟกราฟิก", "โพล"]
TRUST_BASE = {"LINE": .75, "Facebook": .6, "Instagram": .6, "TikTok": .5, "Google Maps": .8, "Delivery app": .65, "YouTube": .55}

AREAS = {
    "กรุงเทพฯ": ["ปทุมวัน", "บางรัก", "สาทร", "จตุจักร", "ห้วยขวาง", "ลาดพร้าว", "บางกะปิ", "บางนา", "พระนคร",
                 "ราชเทวี", "ดินแดง", "บางซื่อ", "ธนบุรี", "บางแค", "หลักสี่", "ดอนเมือง"],
    "นนทบุรี": ["เมืองนนทบุรี", "ปากเกร็ด", "บางใหญ่", "บางบัวทอง", "บางกรวย", "ไทรน้อย"],
}
PROVINCE_SHARE = {"กรุงเทพฯ": 0.7, "นนทบุรี": 0.3}

# usage = ค่าเฉลี่ยการใช้งานแพลตฟอร์ม 0–5 ตามลำดับ PLATFORMS
SEGMENTS = {
    "นักศึกษา": dict(share=.18, age=(18, 24), budget=(40, 150), visits=(2, 5),
        usage=[4, 3, 4.5, 4.5, 3, 3.5, 4], shop=(.8, .7, .6),
        fmt={"คลิป": .9, "ภาพเดียว": .7, "สไลด์ภาพ": .8, "โพล": .7}, peak=[(20, 23), (15, 17)], visit=(14, 18),
        archetypes=["นักศึกษาสายคอนเทนต์/ครีเอเตอร์", "นักศึกษาหอพักงบจำกัด", "นักศึกษาสายติวหนังสือ", "นักศึกษากิจกรรมชมรม"],
        likes=["ถ่ายรูปสวย", "ราคาคุ้ม", "ใกล้มหาลัย", "ที่นั่งและปลั๊ก", "เมนูแปลกใหม่", "โปรนักศึกษา"],
        objections=["เงินจำกัด", "ร้านไม่สวยถ่ายรูปไม่ขึ้น", "ไกลจากหอ", "ไม่มีที่นั่ง"]),
    "วัยทำงาน": dict(share=.28, age=(24, 45), budget=(60, 200), visits=(3, 7),
        usage=[4.5, 3.5, 3.5, 3.5, 3.5, 4, 3.5], shop=(.8, .6, .9),
        fmt={"ภาพเดียว": .8, "โพสต์ข้อความ": .6, "ข้อความ LINE": .7, "คลิป": .6}, peak=[(12, 13), (19, 22)], visit=(7, 9),
        archetypes=["ฟรีแลนซ์นั่งทำงานในคาเฟ่", "พนักงานออฟฟิศพักเที่ยง", "พนักงานกะดึก", "พนักงานทำงานที่บ้าน"],
        likes=["เร็ว ไม่ต้องรอ", "ใกล้ที่ทำงาน", "รสชาติคงที่", "ที่นั่งและปลั๊ก", "สั่งล่วงหน้าได้", "ราคาคุ้ม"],
        objections=["ไม่มีเวลารอคิว", "ไม่มีที่นั่ง ไม่มีปลั๊ก", "ราคาสูงกว่าร้านเชน", "ไม่รู้ว่าร้านเปิดกี่โมง"]),
    "ครอบครัว": dict(share=.18, age=(30, 55), budget=(150, 500), visits=(1, 3),
        usage=[4.5, 4, 2.5, 3, 3.5, 3, 3.5], shop=(.5, .8, .9),
        fmt={"ภาพเดียว": .8, "สไลด์ภาพ": .7, "โพสต์ข้อความ": .7, "ป้าย": .6}, peak=[(19, 21), (9, 11)], visit=(11, 14),
        archetypes=["พ่อแม่รับส่งลูก", "ครอบครัวมื้อเย็นวันหยุด", "คนซื้อของฝากไปบ้าน"],
        likes=["ที่จอดรถ", "เมนูเด็ก", "สะอาด", "ปริมาณคุ้ม", "นั่งได้หลายคน"],
        objections=["ไม่มีที่จอดรถ", "ไม่แน่ใจเรื่องความสะอาด", "เมนูเด็กน้อย", "ร้านแคบ"]),
    "วัยอาวุโส": dict(share=.10, age=(55, 75), budget=(40, 150), visits=(2, 6),
        usage=[4.5, 4, 1, 2, 2.5, 1.5, 3.5], shop=(.6, .6, .8),
        fmt={"ข้อความ LINE": .9, "ป้าย": .8, "โพสต์ข้อความ": .7, "ภาพเดียว": .6}, peak=[(6, 8), (18, 20)], visit=(7, 10),
        archetypes=["ผู้สูงวัยตลาดเช้า", "ผู้เกษียณเดินออกกำลังกาย", "ลูกค้าประจำย่านเก่า"],
        likes=["คุ้นเคยกับเจ้าของ", "รสชาติเดิม", "ราคาชัด", "ใกล้บ้าน"],
        objections=["อ่านป้ายเล็กไม่ถนัด", "กลัวราคาขึ้น", "ไม่ใช้แอปสั่ง"]),
    "นักท่องเที่ยว": dict(share=.08, age=(20, 45), budget=(80, 300), visits=(1, 2),
        usage=[2.5, 3, 4, 3.5, 4.8, 2.5, 3], shop=(.8, .7, .8),
        fmt={"ภาพเดียว": .8, "คลิป": .7, "สไลด์ภาพ": .7}, peak=[(9, 11), (20, 22)], visit=(10, 16),
        archetypes=["นักท่องเที่ยวไทยสายคาเฟ่", "นักท่องเที่ยวต่างชาติสายสตรีทฟู้ด", "คนเดินทางผ่านย่าน"],
        likes=["รีวิวดี", "ของประจำถิ่น", "ถ่ายรูปสวย", "หาง่ายบนแผนที่"],
        objections=["หาร้านไม่เจอบนแผนที่", "ไม่มีเมนูภาษาอังกฤษ", "ไม่แน่ใจรีวิว"]),
    "สายสุขภาพ": dict(share=.07, age=(22, 50), budget=(80, 250), visits=(2, 5),
        usage=[4, 3, 4, 3.5, 3.5, 3, 3.5], shop=(.7, .5, .8),
        fmt={"อินโฟกราฟิก": .8, "สไลด์ภาพ": .7, "คลิป": .6}, peak=[(6, 8), (18, 20)], visit=(7, 9),
        archetypes=["สายฟิตเนสหลังออกกำลังกาย", "สายลดหวานลดมัน", "สายมังสวิรัติ"],
        likes=["ส่วนผสมชัด", "ลดหวานได้", "วัตถุดิบดี", "มีตัวเลือกไม่ใส่นม"],
        objections=["ไม่รู้ส่วนผสม", "หวานเกินไป", "ไม่มีตัวเลือกสุขภาพ"]),
    "พรีเมียม": dict(share=.06, age=(28, 55), budget=(150, 450), visits=(1, 4),
        usage=[4, 3, 4, 2.5, 4, 3, 3], shop=(.9, .8, .6),
        fmt={"สไลด์ภาพ": .8, "ภาพเดียว": .8, "อินโฟกราฟิก": .6}, peak=[(20, 22), (7, 9)], visit=(9, 11),
        archetypes=["ผู้บริหารสายกาแฟพิเศษ", "สายของขวัญพรีเมียม", "นักชิมขนมอบ"],
        likes=["วัตถุดิบพรีเมียม", "เรื่องราวของร้าน", "บรรยากาศดี", "แพ็กเกจสวย"],
        objections=["ไม่เห็นความต่างจากร้านทั่วไป", "แพ็กเกจไม่พรีเมียม", "ไม่มีเรื่องเล่า"]),
    "องค์กร/พ่อค้าแม่ค้า": dict(share=.05, age=(25, 55), budget=(300, 2000), visits=(1, 3),
        usage=[5, 3.5, 2.5, 2, 3.5, 3.5, 2.5], shop=(.7, .8, .8),
        fmt={"ข้อความ LINE": .9, "อินโฟกราฟิก": .7, "โพสต์ข้อความ": .6}, peak=[(9, 11), (13, 15)], visit=(10, 12),
        archetypes=["แอดมินสั่งของว่างประชุม", "พ่อค้าแม่ค้าในตลาด", "ฝ่ายบุคคลจัดเลี้ยงพนักงาน"],
        likes=["สั่งจำนวนมากได้", "ออกใบเสร็จได้", "ส่งตรงเวลา", "ราคาชุดชัด"],
        objections=["ไม่แน่ใจว่าทำทันเวลา", "ไม่มีใบเสร็จ", "ไม่มีเมนูชุด"]),
}
DAYS = ["จันทร์-ศุกร์", "เสาร์-อาทิตย์", "ทุกวัน"]


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def make_persona(i: int, rng: random.Random) -> dict:
    seg = rng.choices(list(SEGMENTS), weights=[s["share"] for s in SEGMENTS.values()])[0]
    s = SEGMENTS[seg]
    province = rng.choices(list(PROVINCE_SHARE), weights=list(PROVINCE_SHARE.values()))[0]
    a0 = rng.randint(s["age"][0], s["age"][1] - 4)
    lo = int(round(rng.uniform(s["budget"][0], (s["budget"][0] + s["budget"][1]) / 2) / 5) * 5)
    hi = int(round(rng.uniform(lo + 20, s["budget"][1]) / 5) * 5)
    usage = {p: int(round(clip(rng.gauss(mu, .8), 0, 5))) for p, mu in zip(PLATFORMS, s["usage"])}
    trust = {p: round(clip(rng.gauss(TRUST_BASE[p], .12), 0, 1), 2) for p in PLATFORMS}
    fmt = {f: round(clip(rng.gauss(s["fmt"].get(f, .35), .12), 0, 1), 2) for f in FORMATS}
    drink, bakery, food = s["shop"]
    peak = rng.choice(s["peak"])
    days = rng.choices(DAYS, weights=[.45, .3, .25])[0] if seg != "นักท่องเที่ยว" else "เสาร์-อาทิตย์"
    return {
        "id": f"P{i:05d}",
        "simulated": True,
        "label": "Simulated",
        "segment": seg,
        "archetype": rng.choice(s["archetypes"]),
        "age_range": [a0, a0 + 4],
        "area": {"province": province, "district": rng.choice(AREAS[province])},
        "budget_per_visit": [lo, hi],
        "visits_per_week": rng.randint(*s["visits"]),
        "shop_type_pref": {"drink": round(clip(rng.gauss(drink, .12), 0, 1), 2),
                           "bakery": round(clip(rng.gauss(bakery, .12), 0, 1), 2),
                           "food": round(clip(rng.gauss(food, .12), 0, 1), 2)},
        "likes": rng.sample(s["likes"], 2),
        "objection": rng.choice(s["objections"]),
        "platform_usage": usage,
        "platform_trust": trust,
        "format_pref": fmt,
        "locality": round(clip(rng.gauss(.6 if seg != "นักท่องเที่ยว" else .2, .15), 0, 1), 2),
        "peak_online": {"days": days, "hours": list(peak)},
        "visit_window": [s["visit"][0], s["visit"][1]],
        "diet": {"halal": rng.random() < .06, "vegetarian": rng.random() < (.25 if seg == "สายสุขภาพ" else .04)},
        "accepts_marketing_messages": rng.random() < (.55 if seg in ("วัยอาวุโส", "องค์กร/พ่อค้าแม่ค้า") else .35),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--out", default=str(ROOT / "data" / "personas_10000.json"))
    args = ap.parse_args()
    rng = random.Random(SEED)
    personas = [make_persona(i + 1, rng) for i in range(args.n)]
    meta = {
        "title": "Belka Simulated personas",
        "count": args.n,
        "seed": SEED,
        "simulated": True,
        "note": "ข้อมูลสมมติทั้งหมด ไม่ใช่ข้อมูลคนจริง สัดส่วนและค่าเฉลี่ยเป็นสมมติฐานของทีม (assumption) "
                "ใช้กับสูตร fit และสูตรจับคู่สินค้ากับ persona ใน Belka_สรุปสูตรคำนวณ.pdf หัวข้อ 5",
        "segments": {k: v["share"] for k, v in SEGMENTS.items()},
        "platforms": PLATFORMS,
        "formats": FORMATS,
    }
    Path(args.out).write_text(json.dumps({"_meta": meta, "personas": personas}, ensure_ascii=False,
                                         separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.n} personas → {args.out}")


if __name__ == "__main__":
    main()
