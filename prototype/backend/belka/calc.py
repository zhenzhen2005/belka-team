"""สูตรคำนวณของ Belka (Trust Engine) — โค้ดล้วน ไม่เรียก AI ไม่เรียก AWS.

ที่มา: Belka_สรุปสูตรคำนวณ.pdf และ Belka_สูตรตัดสินใจ_ทุกคอนเทนต์.pdf ของทีม (13 ต.ค. 2569)
- หัวข้อ 1–4 เป็นสูตรมาตรฐาน
- เกณฑ์ ROI 20% และเพดานต่าง ๆ ทีมตั้งเอง ยังไม่ผ่านการทดสอบกับร้านจริง
- ทุกฟังก์ชันคิดต่อสินค้าหนึ่งรายการ ห้ามใช้เปอร์เซ็นต์เดียวทั้งร้าน
หน่วยเงิน: บาท (float) ปัดผลลัพธ์ที่แสดงเป็นทศนิยม 2 ตำแหน่ง
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev

ROI_THRESHOLD = 0.20          # ROI ≥ 20% → ทำต่อ (ทีมตั้งเอง)
MAX_DISCOUNT = 0.20           # ระบบไม่ลดเกิน 20% (ยกเว้นลดท้ายวัน)
MIN_MARGIN_FOR_PROMO = 0.20   # ตัดสินค้าที่ m < 20%
LABEL_WORTH, LABEL_MAYBE, LABEL_NO = "คุ้ม", "ลุ้น", "ไม่แนะนำ"
SCENARIOS = (0.5, 1.0, 1.5)   # สถานการณ์ต่ำ คาด สูง (คูณกับยอดที่ร้านคาด)
MARKETING_SHARE_OF_GP_SAVED = 0.30  # แบ่ง 30% ของ GP ที่ประหยัดได้เป็นงบการตลาด (Content Document)


def r2(x: float) -> float:
    return round(x + 0.0, 2)


# ---------- 1. ต่อสินค้าหนึ่งรายการ ----------
@dataclass(frozen=True)
class Item:
    name: str
    price: float
    cost: float
    commission_rate: float = 0.0   # เช่น 0.30 สำหรับแอปเดลิเวอรี, 0 สำหรับหน้าร้าน
    per_order_fee: float = 0.0

    def __post_init__(self):
        if self.price <= 0:
            raise ValueError("ราคาต้องมากกว่า 0")
        if self.cost < 0 or not 0 <= self.commission_rate < 1 or self.per_order_fee < 0:
            raise ValueError("ต้นทุน ค่าคอมมิชชัน และค่าต่อออเดอร์ต้องไม่ติดลบ")


def fee(item: Item) -> float:
    """f = อัตราคอมมิชชัน × ราคา + ค่าต่อออเดอร์"""
    return item.commission_rate * item.price + item.per_order_fee


def unit_profit(item: Item) -> float:
    """g = ราคา − ต้นทุน − f"""
    return item.price - item.cost - fee(item)


def margin(item: Item) -> float:
    """m = g ÷ ราคา"""
    return unit_profit(item) / item.price


def lift_needed(delta: float, g: float) -> float | None:
    """L = δ ÷ (g − δ) ยอดที่ต้องเพิ่ม (สัดส่วน) เพื่อคุ้มทุน; None ถ้า δ ≥ g (ไม่แนะนำ)"""
    if delta >= g:
        return None
    return delta / (g - delta)


def lift_label(L: float | None) -> str:
    if L is None:
        return LABEL_NO
    if L <= 0.5:
        return LABEL_WORTH
    if L <= 1.0:
        return LABEL_MAYBE
    return LABEL_NO


def discount_caps(m: float) -> tuple[float, float]:
    """เพดานส่วนลด (สัดส่วนของราคา): คุ้ม ≤ min(m/3, 20%), ลุ้น ≤ min(m/2, 20%)"""
    return min(m / 3, MAX_DISCOUNT), min(m / 2, MAX_DISCOUNT)


def breakeven_discount(g: float, u: float) -> float:
    """δ_be = g × u ÷ (1 + u) ส่วนลดที่ยังเท่าทุนเมื่อยอดเพิ่ม u"""
    return g * u / (1 + u)


def recommend_discount(item: Item, u_conservative: float) -> dict:
    """δ_safe = min(ราคา × เพดานคุ้ม, δ_be ที่ u ระมัดระวัง) ปัดราคาโปรขึ้นเป็นบาทเต็ม แล้วคำนวณ L ใหม่"""
    g, m = unit_profit(item), margin(item)
    if m < MIN_MARGIN_FOR_PROMO:
        return {"eligible": False, "reason": f"มาร์จิ้น {m:.0%} ต่ำกว่า 20% ไม่ควรลดราคา", "margin": r2(m)}
    cap_worth, cap_maybe = discount_caps(m)
    delta_safe = min(item.price * cap_worth, breakeven_discount(g, u_conservative))
    promo_price = math.ceil(item.price - delta_safe)
    delta = item.price - promo_price
    L = lift_needed(delta, g)
    return {
        "eligible": True,
        "price": item.price,
        "promo_price": promo_price,
        "discount_baht": r2(delta),
        "discount_pct": r2(delta / item.price),
        "unit_profit_before": r2(g),
        "unit_profit_after": r2(g - delta),
        "margin_before": r2(m),
        "margin_after": r2((g - delta) / promo_price) if promo_price else 0.0,
        "lift_needed": None if L is None else r2(L),
        "label": lift_label(L),
        "cap_worth_baht": r2(item.price * cap_worth),
        "cap_maybe_baht": r2(item.price * cap_maybe),
    }


# ---------- 2. จำลองสามสถานการณ์ ----------
def simulate_units(g: float, delta: float, q0: float, u_expected: float) -> list[dict]:
    """net = g × ΔQ − δ × (Q0 + ΔQ), ΔQ = u × Q0, K = δ × (Q0 + ΔQ), ROI = net ÷ K"""
    out = []
    for k in SCENARIOS:
        u = u_expected * k
        dq = u * q0
        net = g * dq - delta * (q0 + dq)
        cost = delta * (q0 + dq)
        out.append({"scenario": k, "lift": r2(u), "extra_units": r2(dq), "net": r2(net),
                    "campaign_cost": r2(cost), "roi": None if cost == 0 else r2(net / cost)})
    return out


def simulate_sales(s0: float, m: float, d: float, lifts: tuple[float, ...]) -> list[float]:
    """แบบยอดขายรวม: net = m × S0 × u − d × S0 × (1 + u) (ตัวอย่างในเอกสาร: S0 800, m 0.55, ลด 15%)"""
    return [r2(m * s0 * u - d * s0 * (1 + u)) for u in lifts]


def fixed_cost_lift(campaign_cost: float, m: float, s0: float) -> float:
    """โปรที่มีต้นทุนคงที่: L = K ÷ (m × S0)"""
    return campaign_cost / (m * s0)


def window_margin(rows: list[tuple[Item, float]]) -> float:
    """มาร์จิ้นช่วงเวลา = Σ(g × q) ÷ Σ(ราคา × q) (แสดงผล ไม่ใช่ช่องกรอก)"""
    rev = sum(i.price * q for i, q in rows)
    return sum(unit_profit(i) * q for i, q in rows) / rev if rev else 0.0


# ---------- 3. โปรแต่ละแบบ ----------
def bundle(items: list[Item], discount_baht: float) -> dict:
    """เซ็ต: P_เต็ม = Σราคา, C = Σ(ต้นทุน+f), ส่วนลดเซ็ต ≤ min(10%, เพดานคุ้มของ m_set), P_set ≥ C"""
    p_full = sum(i.price for i in items)
    c = sum(i.cost + fee(i) for i in items)
    m_set = (p_full - c) / p_full
    cap = min(0.10, min(m_set / 3, MAX_DISCOUNT)) * p_full
    p_set = p_full - discount_baht
    g_set = p_full - c
    L = lift_needed(discount_baht, g_set)
    ok = discount_baht <= cap + 1e-9 and p_set >= c
    return {"full_price": r2(p_full), "set_cost": r2(c), "set_margin": r2(m_set), "max_discount": r2(cap),
            "set_price": r2(p_set), "lift_needed": None if L is None else r2(L), "ok": ok}


def threshold_gift(bills_per_day: float, extra_share: float, x: float, avg_bill: float, m: float,
                   already_share: float, gift_cost: float) -> dict:
    """ครบ X แถมของ: net/วัน = บิล × ซื้อเพิ่ม × (X − เฉลี่ย) × m − บิล × (ซื้อเพิ่ม + ถึงอยู่แล้ว) × ต้นทุนของแถม"""
    net = bills_per_day * extra_share * (x - avg_bill) * m - bills_per_day * (extra_share + already_share) * gift_cost
    x_ok = 1.10 * avg_bill <= x <= 1.30 * avg_bill
    gift_ok = gift_cost <= 0.10 * x
    return {"net_per_day": r2(net), "x_in_range": x_ok, "gift_within_10pct": gift_ok, "ok": x_ok and gift_ok and net > 0}


def loyalty_card(gift_cost: float, n: int, avg_price: float, limit: float = 0.12) -> dict:
    """สะสมแต้ม ซื้อ N แถม 1: อัตราต้นทุน = ต้นทุนของแถม ÷ (N × ราคาเฉลี่ย) ต้อง ≤ 10–12% (N = 8–10)"""
    rate = gift_cost / (n * avg_price)
    return {"cost_rate": r2(rate), "ok": rate <= limit and 8 <= n <= 10}


def referral(gift_cost_pair: float, main_price: float, m: float, avg_bill: float, expected_visits: float) -> dict:
    """ชวนเพื่อน: ต้นทุนของแถมทั้งคู่ < 15% ของราคาเมนูหลัก และ < m × ยอดต่อบิล × จำนวนครั้งที่คาดว่าจะกลับมา"""
    value = m * avg_bill * expected_visits
    ok = gift_cost_pair < 0.15 * main_price and gift_cost_pair < value
    return {"expected_value_new_customer": r2(value), "ok": ok}


def end_of_day(item: Item, steps: list[tuple[float, float]], leftover: float) -> dict:
    """ลดท้ายวัน: ราคาลด ≥ ต้นทุน + f; ผลต่อล็อต = Σ(ขายได้ × ราคาลด) − เหลือ × ต้นทุน เทียบทิ้ง = −เหลือ × ต้นทุน
    steps = [(ราคาลด, จำนวนที่ขายได้), ...] ขั้นแรกลดไม่เกิน 20%"""
    floor = item.cost + fee(item)
    prices_ok = all(p >= floor for p, _ in steps)
    first_ok = not steps or steps[0][0] >= item.price * (1 - MAX_DISCOUNT)
    revenue = sum(p * q for p, q in steps)
    return {"price_floor": r2(floor), "lot_result": r2(revenue - leftover * item.cost),
            "discard_result": r2(-leftover * item.cost), "improvement": r2(revenue),
            "ok": prices_ok and first_ok}


def group_order(price_per_set: float, cost: float, fee_baht: float, sets: int) -> dict:
    """ออเดอร์กลุ่ม: ราคาต่อชุด ≥ ต้นทุน + ค่าธรรมเนียม, มาร์จิ้น ≥ 20%, ขั้นต่ำ 10 ชุด"""
    m = (price_per_set - cost - fee_baht) / price_per_set
    return {"margin": r2(m), "ok": price_per_set >= cost + fee_baht and m >= MIN_MARGIN_FOR_PROMO and sets >= 10}


def delivery_promo_allowed(item: Item) -> bool:
    """แอปส่งอาหาร: ใช้ g หลังหักคอมมิชชัน ถ้า m < 20% ห้ามโปรในแอป"""
    return margin(item) >= MIN_MARGIN_FOR_PROMO


def price_change(price: float, old_cost: float, new_cost: float, new_price: float) -> dict:
    """มาร์จิ้นเดิม / ถ้าไม่ปรับราคา / หลังปรับ"""
    return {"margin_old": r2((price - old_cost) / price), "margin_if_unchanged": r2((price - new_cost) / price),
            "margin_new": r2((new_price - new_cost) / new_price)}


# ---------- กำไรแยกช่องทางและงบการตลาดจาก GP (Content Document หัวข้อ 06) ----------
def profit_by_channel(price: float, cost: float, gp_rates: dict[str, float]) -> dict[str, dict]:
    """กำไรต่อออเดอร์แต่ละช่องทาง: ราคา − ต้นทุนวัตถุดิบ − GP (GP ≠ ต้นทุนวัตถุดิบ)"""
    out = {}
    for ch, rate in gp_rates.items():
        it = Item("x", price, cost, commission_rate=rate)
        out[ch] = {"gp_baht": r2(fee(it)), "profit": r2(unit_profit(it)), "margin": r2(margin(it)),
                   "loss": unit_profit(it) < 0}
    return out


def gp_savings(monthly_sales: float, platform_share_before: float, platform_share_after: float,
               gp_rate: float) -> dict:
    """ประหยัด GP เมื่อสัดส่วนออเดอร์ผ่านแพลตฟอร์มลดลง (ยอดขายรวมเท่าเดิม) + งบการตลาด 30%"""
    before = monthly_sales * platform_share_before * gp_rate
    after = monthly_sales * platform_share_after * gp_rate
    saved = before - after
    return {"gp_before": r2(before), "gp_after": r2(after), "saved_per_month": r2(saved),
            "saved_per_year": r2(saved * 12), "marketing_budget": r2(saved * MARKETING_SHARE_OF_GP_SAVED)}


# ---------- 4. วัดผล ----------
def before_after(recorded_sales: float, d: float, s0: float, m: float, campaign_cost: float) -> dict:
    """ก่อน-หลัง (อ่อนที่สุด): S_เต็ม = ยอดที่บันทึก ÷ (1 − d), U = S_เต็ม − S0, net = m × U − K"""
    s_full = recorded_sales / (1 - d)
    uplift = s_full - s0
    return {"sales_at_full_price": r2(s_full), "uplift": r2(uplift), "net": r2(m * uplift - campaign_cost)}


def diff_in_diff(promo_after: float, promo_before: float, ctrl_after: float, ctrl_before: float) -> float:
    """ผล = (ช่วงโปรหลัง − ช่วงโปรก่อน) − (ช่วงเทียบหลัง − ช่วงเทียบก่อน)"""
    return (promo_after - promo_before) - (ctrl_after - ctrl_before)


# t วิกฤตสองด้าน 95% (ค่าประมาณจากตาราง ตามที่เอกสารระบุ)
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
        10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
        18: 2.101, 19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: float) -> float:
    keys = sorted(_T95)
    for k in keys:
        if df <= k:
            return _T95[k]
    return 1.96


def switchback(promo_days: list[float], other_days: list[float]) -> dict:
    """สลับวันเปิด/ปิดโปร: diff, se = √(sd₁²/n₁ + sd₂²/n₂), df แบบ Welch, ช่วง 95% = diff ± t × se"""
    n1, n2 = len(promo_days), len(other_days)
    if n1 < 2 or n2 < 2:
        raise ValueError("ต้องมีอย่างน้อย 2 วันในแต่ละกลุ่ม")
    m1, m2 = mean(promo_days), mean(other_days)
    v1, v2 = stdev(promo_days) ** 2 / n1, stdev(other_days) ** 2 / n2
    se = math.sqrt(v1 + v2)
    df = (v1 + v2) ** 2 / ((v1 ** 2) / (n1 - 1) + (v2 ** 2) / (n2 - 1)) if se else n1 + n2 - 2
    t = t95(math.floor(df))
    diff = m1 - m2
    return {"mean_promo": r2(m1), "mean_other": r2(m2), "diff": r2(diff), "se": r2(se), "df": r2(df),
            "t": t, "ci_low": r2(diff - t * se), "ci_high": r2(diff + t * se)}


def money_per_day(m: float, diff_customers: float, avg_bill: float, discount_per_bill: float,
                  promo_bills: float) -> float:
    """net/วัน = m × diff × ยอดต่อบิล − ส่วนลดต่อบิล × จำนวนบิลวันโปร"""
    return m * diff_customers * avg_bill - discount_per_bill * promo_bills


def decide(net_low: float, net_high: float, roi: float | None) -> str:
    """ช่วงของ net เหนือศูนย์และ ROI ≥ 20% → ทำต่อ; คร่อมศูนย์ → ทำอีกรอบ; ติดลบ → หยุดหรือปรับ"""
    if net_high < 0:
        return "หยุดหรือปรับ"
    if net_low > 0 and roi is not None and roi >= ROI_THRESHOLD:
        return "ทำต่อ"
    return "ทำอีกรอบ"
