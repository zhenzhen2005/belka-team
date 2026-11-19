"""จับคู่ลูกค้าจำลอง (Simulated) กับร้าน และคะแนนความเหมาะของแพลตฟอร์ม — โค้ดล้วน.

สูตรจาก Belka_สรุปสูตรคำนวณ.pdf หัวข้อ 5:
- จับคู่สินค้ากับ persona: 0.25×ราคา + 0.20×จุดเด่น + 0.15×pain point + 0.15×ช่องทาง + 0.15×ใกล้ร้านและเวลา
  (น้ำหนักรวม 0.90 ตามเอกสาร ระบบหารด้วย 0.90 เพื่อให้เต็ม 100 — ต้องให้ทีมยืนยันว่าตั้งใจแบบนี้)
  ราคา: 100 ถ้าอยู่ในงบ ลดเป็นเส้นตรงถึง 0 ที่เกินงบ 20% · เกตฮาลาล/เจ
- fit[p] = 100 × (0.40 × การใช้งาน/5 + 0.25 × ความเชื่อมั่น + 0.20 × รูปแบบ + 0.15 × ความเป็นท้องถิ่น × ความใกล้ร้าน)
  fit_discover = fit × DISC, fit_retain = fit × RETAIN · เวลาโพสต์ = ต้นช่วงใช้สูง − 30 ถึง 60 นาที
- ตัวคูณจากการปัดการ์ด: ×0.5 / ×1.2 / ×1.5 ขอบล่าง 0.2 ขอบบน 2.0
"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .config import PROJECT_DIR

PERSONA_FILE = PROJECT_DIR / "data" / "personas_10000.json"
WEIGHTS = {"price": .25, "feature": .20, "pain": .15, "channel": .15, "proximity": .15}
WEIGHT_SUM = sum(WEIGHTS.values())  # 0.90

# ลูกค้าส่วนใหญ่ที่ร้านเลือกตอน onboarding → กลุ่มในคลัง persona
CUSTOMER_TO_SEGMENTS = {
    "workers": ["วัยทำงาน", "องค์กร/พ่อค้าแม่ค้า"],
    "students": ["นักศึกษา"],
    "locals": ["ครอบครัว", "วัยอาวุโส", "วัยทำงาน"],
    "tourists": ["นักท่องเที่ยว", "พรีเมียม"],
}
APP_CHANNEL = {"line": "LINE", "facebook": "Facebook", "google_maps": "Google Maps", "delivery": "Delivery app",
               "instagram": "Instagram", "tiktok": "TikTok"}
# รูปแบบที่ใช้ได้บนแต่ละแพลตฟอร์ม (ใช้หาค่า "รูปแบบ" ในสูตร fit)
PLATFORM_FORMATS = {
    "LINE": ["ข้อความ LINE", "ภาพเดียว", "โพล"], "Facebook": ["โพสต์ข้อความ", "ภาพเดียว", "สไลด์ภาพ"],
    "Instagram": ["ภาพเดียว", "สไลด์ภาพ", "คลิป", "โพล"], "TikTok": ["คลิป"], "YouTube": ["คลิป"],
    "Google Maps": ["ภาพเดียว", "โพสต์ข้อความ"], "Delivery app": ["ภาพเดียว"],
}
# DISC = ช่วยหาลูกค้าใหม่ RETAIN = ช่วยให้ลูกค้ากลับมา (assumption: ทีมยังไม่ได้กำหนดค่า)
DISC = {"TikTok": 1.0, "Instagram": .85, "Google Maps": .9, "Facebook": .7, "YouTube": .8, "Delivery app": .6, "LINE": .3}
RETAIN = {"LINE": 1.0, "Facebook": .7, "Instagram": .6, "Google Maps": .5, "Delivery app": .5, "TikTok": .4, "YouTube": .4}
SWIPE = {"not_my_shop": .5, "similar": 1.2, "exactly": 1.5}


@lru_cache(maxsize=1)
def load_personas(path: str = str(PERSONA_FILE)) -> tuple[dict, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(data["personas"])


def price_score(avg_price: float | None, budget: list[float]) -> float:
    if avg_price is None:
        return 70.0  # ไม่มีราคา: กลาง ๆ (assumption)
    hi = budget[1]
    if avg_price <= hi:
        return 100.0
    over = (avg_price - hi) / hi
    return max(0.0, 100.0 * (1 - over / 0.20))


def proximity(persona: dict, area: dict | None) -> float:
    if not area:
        return .6
    if persona["area"]["district"] == area.get("district"):
        return 1.0
    if persona["area"]["province"] == area.get("province"):
        return .6
    return .2


def channel_score(persona: dict, channels: list[str]) -> float:
    names = [APP_CHANNEL[c] for c in channels if c in APP_CHANNEL] or ["Google Maps"]
    return 100.0 * max(persona["platform_usage"].get(n, 0) for n in names) / 5


def match_score(persona: dict, shop: dict) -> float | None:
    """คะแนน 0–100 ของ persona กับร้าน; None ถ้าไม่ผ่านเกต (ฮาลาล/เจ)"""
    if persona["diet"]["halal"] and shop.get("halal") is False:
        return None
    if persona["diet"]["vegetarian"] and shop.get("vegetarian_options") is False:
        return None
    seg_targets = CUSTOMER_TO_SEGMENTS.get(shop.get("customer", ""), [])
    feature = 100.0 * persona["shop_type_pref"].get(shop["shop_type"], .5)
    shop_tags = set(shop.get("tags", []))
    pain = 100.0 if shop_tags & set(persona["likes"]) else (80.0 if persona["segment"] in seg_targets else 40.0)
    prox = 100.0 * proximity(persona, shop.get("area"))
    raw = (WEIGHTS["price"] * price_score(shop.get("avg_price"), persona["budget_per_visit"])
           + WEIGHTS["feature"] * feature + WEIGHTS["pain"] * pain
           + WEIGHTS["channel"] * channel_score(persona, shop.get("channels", []))
           + WEIGHTS["proximity"] * prox)
    return raw / WEIGHT_SUM


def platform_fit(persona: dict, platform: str, prox: float) -> dict:
    fmt = max(persona["format_pref"].get(f, 0) for f in PLATFORM_FORMATS[platform])
    fit = 100 * (.40 * persona["platform_usage"][platform] / 5 + .25 * persona["platform_trust"][platform]
                 + .20 * fmt + .15 * persona["locality"] * prox)
    return {"fit": round(fit, 1), "discover": round(fit * DISC[platform], 1), "retain": round(fit * RETAIN[platform], 1)}


def post_time(peak_hours: list[int]) -> str:
    """ต้นช่วงใช้สูง − 30 ถึง 60 นาที"""
    h = peak_hours[0]
    return f"{(h - 1) % 24:02d}:00–{(h - 1) % 24:02d}:30"


def apply_swipe(multiplier: float, answer: str) -> float:
    return max(.2, min(2.0, multiplier * SWIPE[answer]))


def match_shop(shop: dict, top_groups: int = 3, swipes: dict[str, float] | None = None) -> dict:
    """จัดอันดับ persona ทั้งคลัง แล้วรวมเป็นกลุ่ม archetype สำหรับการ์ด #1 #2 #3"""
    swipes = swipes or {}
    scored = []
    for p in load_personas():
        s = match_score(p, shop)
        if s is None:
            continue
        s *= swipes.get(p["archetype"], 1.0)
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    top = scored[: max(300, len(scored) // 10)]  # 10% บนสุด
    groups: dict[str, list] = defaultdict(list)
    for s, p in top:
        groups[p["archetype"]].append((s, p))
    ranked = sorted(groups.items(), key=lambda kv: -(sum(x[0] for x in kv[1]) / len(kv[1])) * len(kv[1]) ** .5)
    cards = []
    total = len(top)
    for rank, (arch, rows) in enumerate(ranked[:top_groups], 1):
        ps = [p for _, p in rows]
        rep = ps[0]
        usage = {pl: sum(p["platform_usage"][pl] for p in ps) / len(ps) for pl in rep["platform_usage"]}
        best_pl = sorted(usage, key=lambda k: -usage[k])[:2]
        prox = sum(proximity(p, shop.get("area")) for p in ps) / len(ps)
        fits = {pl: platform_fit(rep, pl, prox) for pl in best_pl}
        likes = _top([l for p in ps for l in p["likes"]], 2)
        cards.append({
            "rank": rank,
            "label": "Simulated",
            "archetype": arch,
            "segment": rep["segment"],
            "age_range": [min(p["age_range"][0] for p in ps), max(p["age_range"][1] for p in ps)],
            "share_of_top": round(len(ps) / total, 3),
            "personas_in_group": len(ps),
            "avg_score": round(sum(x[0] for x in rows) / len(rows), 1),
            "budget_per_visit": [round(_median([p["budget_per_visit"][0] for p in ps])),
                                 round(_median([p["budget_per_visit"][1] for p in ps]))],
            "likes": likes,
            "objection": _top([p["objection"] for p in ps], 1)[0],
            "peak_online": {"days": _top([p["peak_online"]["days"] for p in ps], 1)[0],
                            "hours": rep["peak_online"]["hours"]},
            "post_time": post_time(rep["peak_online"]["hours"]),
            "top_platforms": fits,
            "sample_ids": [p["id"] for p in ps[:5]],
        })
    return {"personas_scored": len(scored), "cards": cards,
            "note": "ลูกค้าจำลองจากคลัง 10,000 คน (Simulated) ไม่ใช่ข้อมูลลูกค้าจริงของร้าน"}


def _top(values: list[str], n: int) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for v in values:
        counts[v] += 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
