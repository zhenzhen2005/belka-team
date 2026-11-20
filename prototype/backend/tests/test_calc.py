"""เทสต์สูตรคำนวณ ใช้ตัวอย่างตัวเลขจาก Belka_สรุปสูตรคำนวณ.pdf และ Content Document เป็นตัวตรวจ"""
import pytest

from belka import calc
from belka.calc import Item


def test_latte_example_from_team_formula_doc():
    # ลาเต้ 60 ต้นทุน 24 → g = 36, m = 0.60, เพดานคุ้ม 12 บาท ลด 8 บาท → L = 8 ÷ 28 = 0.286
    latte = Item("ลาเต้", 60, 24)
    assert calc.unit_profit(latte) == 36
    assert calc.margin(latte) == pytest.approx(0.60)
    worth, maybe = calc.discount_caps(calc.margin(latte))
    assert latte.price * worth == pytest.approx(12)
    assert calc.lift_needed(8, 36) == pytest.approx(8 / 28)
    assert round(calc.lift_needed(8, 36), 3) == 0.286
    assert calc.lift_label(calc.lift_needed(8, 36)) == "คุ้ม"


def test_sales_scenarios_example():
    # S0 = 800, m = 0.55, ลด 15% ยอดเพิ่ม 30% / 60% / 90% → −24 / +72 / +168 บาทต่อวัน
    assert calc.simulate_sales(800, 0.55, 0.15, (0.3, 0.6, 0.9)) == [-24, 72, 168]


def test_gp_savings_example_from_content_document():
    # ร้านเล็ก 20,000/เดือน ผ่านแพลตฟอร์ม 80% → 50% GP 30% → 4,800 → 3,000 ประหยัด 1,800
    r = calc.gp_savings(20000, 0.8, 0.5, 0.30)
    assert (r["gp_before"], r["gp_after"], r["saved_per_month"], r["saved_per_year"]) == (4800, 3000, 1800, 21600)
    assert r["marketing_budget"] == 540


def test_profit_by_channel_example():
    # ออเดอร์ 200 ต้นทุน 80: Grab GP 30% → กำไร 60, หน้าร้าน → 120 (สั่งตรงได้กำไร 2 เท่า)
    r = calc.profit_by_channel(200, 80, {"grab": 0.30, "direct": 0.0})
    assert r["grab"]["profit"] == 60 and r["direct"]["profit"] == 120


def test_fee_includes_commission_and_per_order():
    it = Item("x", 100, 40, commission_rate=0.3, per_order_fee=5)
    assert calc.fee(it) == 35 and calc.unit_profit(it) == 25


def test_discount_not_recommended_when_delta_ge_profit():
    assert calc.lift_needed(36, 36) is None
    assert calc.lift_label(None) == "ไม่คุ้ม"


@pytest.mark.parametrize("L,label", [(0.3, "คุ้ม"), (0.5, "คุ้ม"), (0.8, "เสี่ยง"), (1.0, "เสี่ยง"), (1.2, "ไม่คุ้ม")])
def test_lift_labels(L, label):
    assert calc.lift_label(L) == label


def test_recommend_discount_rounds_promo_up_and_respects_cap():
    r = calc.recommend_discount(Item("ลาเต้", 60, 24), u_conservative=0.3)
    # δ_be = 36 × 0.3 ÷ 1.3 = 8.31 < เพดาน 12 → ราคาโปร ceil(51.69) = 52, ลด 8
    assert r["promo_price"] == 52 and r["discount_baht"] == 8 and r["label"] == "คุ้ม"
    assert r["discount_baht"] <= r["cap_worth_baht"]


def test_low_margin_item_not_eligible_for_promo():
    r = calc.recommend_discount(Item("น้ำเปล่า", 10, 9), u_conservative=0.5)
    assert r["eligible"] is False


def test_delivery_promo_blocked_when_margin_below_20pct():
    assert calc.delivery_promo_allowed(Item("ข้าว", 60, 25, commission_rate=0.30)) is True   # m = 28%
    assert calc.delivery_promo_allowed(Item("ข้าว", 60, 35, commission_rate=0.30)) is False  # m = 12%


def test_simulate_units_three_scenarios():
    rows = calc.simulate_units(g=36, delta=8, q0=20, u_expected=0.4)
    assert [r["scenario"] for r in rows] == [0.5, 1.0, 1.5]
    mid = rows[1]  # ΔQ = 8 → net = 36×8 − 8×28 = 64, K = 224
    assert mid["net"] == 64 and mid["campaign_cost"] == 224 and mid["roi"] == pytest.approx(0.29, abs=0.01)


def test_bundle_rules():
    a, b = Item("ลาเต้", 60, 24), Item("บราวนี่", 45, 18)
    ok = calc.bundle([a, b], discount_baht=10)
    assert ok["full_price"] == 105 and ok["set_cost"] == 42 and ok["ok"]
    assert calc.bundle([a, b], discount_baht=30)["ok"] is False  # เกิน 10%


def test_threshold_gift_conditions():
    r = calc.threshold_gift(bills_per_day=40, extra_share=0.2, x=120, avg_bill=100, m=0.5, already_share=0.1, gift_cost=10)
    assert r["x_in_range"] and r["gift_within_10pct"]
    assert r["net_per_day"] == pytest.approx(40 * 0.2 * 20 * 0.5 - 40 * 0.3 * 10)


def test_loyalty_and_referral():
    assert calc.loyalty_card(gift_cost=50, n=10, avg_price=50)["ok"] is True   # 10%
    assert calc.loyalty_card(gift_cost=80, n=10, avg_price=50)["ok"] is False  # 16%
    assert calc.referral(gift_cost_pair=8, main_price=60, m=0.6, avg_bill=80, expected_visits=3)["ok"]


def test_end_of_day_price_floor():
    croissant = Item("ครัวซองต์", 55, 20)
    good = calc.end_of_day(croissant, [(45, 4), (30, 3)], leftover=1)
    assert good["ok"] and good["lot_result"] == 45 * 4 + 30 * 3 - 20
    assert calc.end_of_day(croissant, [(15, 5)], leftover=0)["ok"] is False  # ต่ำกว่าต้นทุน


def test_group_order_rules():
    assert calc.group_order(60, 30, 5, sets=12)["ok"] is True
    assert calc.group_order(60, 30, 5, sets=8)["ok"] is False


def test_price_change_margins():
    r = calc.price_change(50, 20, 26, 55)
    assert r == {"margin_old": 0.6, "margin_if_unchanged": 0.48, "margin_new": 0.53}


def test_before_after_and_did():
    r = calc.before_after(recorded_sales=850, d=0.15, s0=800, m=0.55, campaign_cost=100)
    assert r["sales_at_full_price"] == 1000 and r["uplift"] == 200 and r["net"] == 10
    assert calc.diff_in_diff(12, 8, 10, 9) == 3


def test_switchback_welch_interval():
    promo = [12, 13, 11, 14, 12, 13, 12]
    other = [8, 9, 8, 10, 8, 9, 8]
    r = calc.switchback(promo, other)
    assert r["diff"] == pytest.approx(3.86, abs=0.01)
    assert r["ci_low"] < r["diff"] < r["ci_high"] and r["ci_low"] > 0


def test_decision_rule():
    assert calc.decide(9, 240, 1.82) == "ทำต่อ"
    assert calc.decide(-20, 50, 0.3) == "ทำอีกรอบ"
    assert calc.decide(-80, -5, -0.2) == "หยุดหรือปรับ"
    assert calc.decide(5, 30, 0.1) == "ทำอีกรอบ"   # ROI ต่ำกว่า 20%


def test_invalid_item_rejected():
    with pytest.raises(ValueError):
        Item("x", 0, 10)
