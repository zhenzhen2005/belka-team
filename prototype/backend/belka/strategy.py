"""เลือกคอนเทนต์จากคลัง 34 แบบ (A1–G4) ด้วยสูตรตัดสินใจของทีม — โค้ดล้วน อธิบายได้ทุกคะแนน.

ที่มา: Belka_สูตรตัดสินใจ_ทุกคอนเทนต์.pdf
1) เกต: ตัดคอนเทนต์ที่ไม่ผ่านเงื่อนไขก่อน แสดงเป็นการ์ดล็อกพร้อมเหตุผล
2) คะแนน = โบนัสเร่งด่วน (+12) + 0.30 × เป้าหมายและสถานการณ์ + 0.25 × persona + 0.20 × ทำได้จริง
          + 0.15 × หลักฐาน + 0.10 × จังหวะเวลา − ความเสี่ยง
3) เป้าหมายและสถานการณ์ = 100 × (0.5 × สัดส่วนเป้าหมายที่คอนเทนต์ตอบ + 0.5 × น้ำหนักสถานการณ์สูงสุดที่ active)
   (ตีความ "สัดส่วน" เป็นเป้าหมายของคอนเทนต์ที่ตรงกับเป้าหมายร้าน ÷ เป้าหมายทั้งหมดของคอนเทนต์ — ต้องให้ทีมยืนยัน)
4) persona = 100 × Σ w_a × (0.4 × รูปแบบ + 0.3 × ช่องทาง + 0.3 × กลุ่ม)
5) ทำได้จริง = 100 × (0.6 × ผ่านเวลา + 0.4 × ช่องทาง); ผ่านเวลา = 1 − 0.25 × max(0, แรง − ระดับเวลาเจ้าของ)
6) หลักฐาน = (n × ผลเฉลี่ย + 3 × 50) ÷ (n + 3) เริ่มที่ 50  → มาจากความจำของร้าน (memory.py)
7) กฎเลือก: ข้อเสนอราคา active ไม่เกิน 1 · ไม่เกิน 3 งานต่อสัปดาห์ · อันดับ 1–2 ต่างกันไม่เกิน 5 เลือกตัวที่ทำง่ายและเสี่ยงต่ำกว่า
จังหวะเวลา มาจากเรดาร์เทรนด์ (trends.py) ถ้าไม่มีเทรนด์ที่เกี่ยวข้องใช้ 50 (assumption)
"""
from __future__ import annotations

import json
from functools import lru_cache

from .config import PROJECT_DIR
from .personas import APP_CHANNEL, load_personas

LIBRARY_FILE = PROJECT_DIR / "data" / "content_library.json"
URGENT_SITUATIONS = {"รีวิวไม่ดี", "ลูกค้าประจำหาย", "ของเหลือ"}
NEUTRAL_TIMING = 50.0
OFFLINE_FORMATS = {"ป้าย"}
ALWAYS_AVAILABLE = {"Google Maps"}  # ร้านเปิดหน้า Google Maps ได้ฟรีเสมอ (assumption)
DEFAULT_GOALS = ["หาลูกค้าใหม่", "ให้คนมาที่ร้าน"]


@lru_cache(maxsize=1)
def library() -> tuple[dict, ...]:
    return tuple(json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))["content_types"])


def derive_situations(shop: dict, trend_titles: list[str] | None = None) -> dict[str, float]:
    """สถานการณ์ที่ active จากข้อมูลร้าน (แตะเลือก) + ธงที่ร้านบอกเพิ่ม"""
    s: dict[str, float] = {}
    flags = set(shop.get("flags", []))
    for f in flags:
        s[f] = 1.0
    if "google_maps" not in shop.get("channels", []):
        s["แผนที่ไม่ครบ"] = 1.0
    if shop.get("customer") == "tourists":
        s["ย่านท่องเที่ยว"] = 1.0
    if shop.get("customer") == "workers" and shop.get("nearby_office"):
        s["ออฟฟิศใกล้"] = 1.0
    for g in shop.get("goals", []):
        if g == "หาลูกค้าใหม่":
            s["เป้าหมายลูกค้าใหม่"] = 1.0
        if g == "ให้ลูกค้าเก่ากลับ":
            s["เป้าหมายลูกค้าเดิม"] = 1.0
    if trend_titles:
        s["เทศกาล"] = 1.0
    return s


def gate_reasons(c: dict, shop: dict) -> list[str]:
    g, facts, reasons = c["gates"], shop, []
    if g["requires_cost"] and not facts.get("has_costs"):
        reasons.append("ต้องมีต้นทุนสินค้าที่เกี่ยวข้อง")
    if g["min_consented_contacts"] and facts.get("consented_contacts", 0) < g["min_consented_contacts"]:
        reasons.append(f"ผู้ยินยอมรับข้อความ ≥ {g['min_consented_contacts']}")
    if g["min_regular_customers"] and facts.get("regular_customers", 0) < g["min_regular_customers"]:
        reasons.append(f"ลูกค้าประจำ ≥ {g['min_regular_customers']}")
    if g["requires_partner"] and not facts.get("has_partner"):
        reasons.append("ต้องมีพันธมิตร")
    if g["requires_nearby_office"] and not facts.get("nearby_office"):
        reasons.append("ต้องมีออฟฟิศใกล้")
    if g["requires_leftover"] and facts.get("leftover_pct", 0) < 3:
        reasons.append("ต้องมีของเหลือท้ายวัน ≥ 3%")
    if g["blocked_when_full_capacity"] and facts.get("full_capacity"):
        reasons.append("กำลังผลิตเต็ม")
    return reasons


def persona_reps(cards: list[dict]) -> list[tuple[float, dict, str]]:
    """(น้ำหนัก, persona ตัวแทน, กลุ่ม) ของการ์ดลูกค้าจำลองแต่ละใบ"""
    if not cards:
        return []
    by_id = {p["id"]: p for p in load_personas()}
    total_w = sum(card.get("share_of_top", 1) for card in cards) or 1
    return [(card.get("share_of_top", 1) / total_w, by_id[card["sample_ids"][0]], card["segment"])
            for card in cards if card.get("sample_ids") and card["sample_ids"][0] in by_id]


def persona_component(c: dict, reps: list[tuple[float, dict, str]]) -> float:
    if not reps:
        return 50.0
    acc = 0.0
    for w, rep, segment in reps:
        fmt = max((rep["format_pref"].get(f, 0) for f in c["formats"]), default=0)
        ch = max((wt * rep["platform_usage"].get(name, 0) / 5 for name, wt in c["channels"].items()), default=0)
        grp = c["segments"].get(segment, 0)
        acc += w * (.4 * fmt + .3 * ch + .3 * grp)
    return 100 * acc


def feasibility(c: dict, shop: dict) -> float:
    owner_time = shop.get("owner_time_level", 2)
    time_ok = 1 - .25 * max(0, c["effort"] - owner_time)
    names = [APP_CHANNEL[x] for x in shop.get("channels", []) if x in APP_CHANNEL] + sorted(ALWAYS_AVAILABLE)
    ch_ok = max((c["channels"].get(n, 0) for n in names), default=0)
    if set(c["formats"]) & OFFLINE_FORMATS:
        ch_ok = max(ch_ok, .6)  # ป้ายหน้าร้านทำได้โดยไม่ต้องมีช่องทางออนไลน์ (assumption)
    return 100 * (.6 * max(0, time_ok) + .4 * ch_ok)


def score_all(shop: dict, cards: list[dict], memory_summary: dict | None = None,
              timing: tuple[dict, dict, set] | None = None) -> list[dict]:
    mem = memory_summary or {"evidence": {}, "interest": {}}
    t_scores, t_because, t_urgent = timing or ({}, {}, set())
    festival_titles = [t_because[k] for k in ("G3",) if k in t_because and t_scores.get(k, 0) >= 80]
    situations = derive_situations(shop, festival_titles)
    goals = set(shop.get("goals") or DEFAULT_GOALS)
    reps = persona_reps(cards)
    out = []
    for c in library():
        locks = gate_reasons(c, shop)
        # สัดส่วนเป้าหมายของคอนเทนต์ที่ตรงกับเป้าหมายร้าน (การตีความของเรา ต้องให้ทีมยืนยัน)
        share_goals = len(goals & set(c["goals"])) / len(c["goals"]) if c["goals"] else 0
        best_sit = max((w for s, w in c["situations"].items() if s in situations), default=0)
        goal_sit = 100 * (.5 * share_goals + .5 * best_sit)
        pers = persona_component(c, reps)
        feas = feasibility(c, shop)
        ev = mem["evidence"].get(c["id"], {}).get("evidence", 50.0)
        tim = t_scores.get(c["id"], NEUTRAL_TIMING)
        urgent = any(c["situations"].get(s, 0) >= .5 and s in situations for s in URGENT_SITUATIONS) or c["id"] in t_urgent
        bonus = 12 if urgent else 0
        base = bonus + .30 * goal_sit + .25 * pers + .20 * feas + .15 * ev + .10 * tim - c["risk"]
        total = base * mem["interest"].get(c["id"], 1.0)
        out.append({
            "id": c["id"], "name": c["name"], "group": c["group"], "group_name": c["group_name"],
            "locked": bool(locks), "lock_reasons": locks, "score": round(total, 1),
            "breakdown": {"urgent_bonus": bonus, "goal_situation": round(goal_sit, 1), "persona": round(pers, 1),
                          "feasibility": round(feas, 1), "evidence": round(ev, 1), "timing": round(tim, 1),
                          "risk": c["risk"], "interest_multiplier": round(mem["interest"].get(c["id"], 1.0), 2)},
            "trend": t_because.get(c["id"]), "effort": c["effort"], "risk": c["risk"],
            "is_price_offer": c["is_price_offer"], "channels": c["channels"], "formats": c["formats"],
            "how": c["how"], "measure": c["measure"], "formula": c["formula"],
        })
    out.sort(key=lambda x: (x["locked"], -x["score"]))
    return out


def pick_week(ranked: list[dict], max_tasks: int = 3) -> list[dict]:
    """กฎเลือก: ข้อเสนอราคาไม่เกิน 1 · ไม่เกิน 3 งาน · อันดับ 1–2 ต่างกัน ≤ 5 เลือกตัวที่ง่ายและเสี่ยงต่ำกว่า"""
    open_ = [r for r in ranked if not r["locked"]]
    if len(open_) >= 2 and open_[0]["score"] - open_[1]["score"] <= 5:
        a, b = open_[0], open_[1]
        if (b["effort"], b["risk"]) < (a["effort"], a["risk"]):
            open_[0], open_[1] = b, a
    picks, price_offers, groups_used = [], 0, []
    for r in open_:
        if r["is_price_offer"]:
            if price_offers >= 1:
                continue
            price_offers += 1
        picks.append(r)
        groups_used.append(r["group"])
        if len(picks) == max_tasks:
            break
    return picks
