"""เทสต์คลังคอนเทนต์ 34 แบบ สูตรเลือกคอนเทนต์ persona เทรนด์ และความจำของร้าน (ไม่เรียก AWS ไม่ใช้เน็ต)"""
from datetime import date

import pytest

from belka import memory, personas, strategy, trends
from belka.redline import check_redline

SHOP = {"shop_type": "drink", "customer": "workers", "channels": ["facebook", "delivery"], "avg_price": 55,
        "area": {"province": "นนทบุรี", "district": "ปากเกร็ด"}}
NO_EXT = {"items": [], "status": "offline"}


@pytest.fixture(scope="module")
def cards():
    return personas.match_shop(SHOP)["cards"]


def test_library_has_34_types_with_weights():
    lib = strategy.library()
    assert len(lib) == 34
    assert [c["id"] for c in lib][:3] == ["A1", "A2", "A3"] and lib[-1]["id"] == "G4"
    for c in lib:
        assert c["channels"] and c["segments"] and 1 <= c["effort"] <= 5
        assert all(0 <= w <= 1 for w in c["channels"].values())


def test_personas_10000_all_simulated():
    ps = personas.load_personas()
    assert len(ps) == 10000 and len({p["id"] for p in ps}) == 10000
    assert all(p["simulated"] and p["label"] == "Simulated" for p in ps)


def test_match_returns_three_cards_from_target_segment(cards):
    assert len(cards) == 3
    assert all(c["label"] == "Simulated" for c in cards)
    assert {c["segment"] for c in cards} <= {"วัยทำงาน", "องค์กร/พ่อค้าแม่ค้า", "ครอบครัว"}


def test_price_score_linear_to_zero_at_20pct_over_budget():
    assert personas.price_score(100, [50, 100]) == 100
    assert personas.price_score(110, [50, 100]) == pytest.approx(50)
    assert personas.price_score(120, [50, 100]) == 0


def test_swipe_multiplier_bounds():
    m = 1.0
    for _ in range(5):
        m = personas.apply_swipe(m, "not_my_shop")
    assert m == 0.2
    for _ in range(10):
        m = personas.apply_swipe(m, "exactly")
    assert m == 2.0


def test_gates_lock_with_reasons(cards):
    ranked = strategy.score_all(SHOP, cards)
    by = {r["id"]: r for r in ranked}
    assert by["C4"]["locked"] and "ต้องมีต้นทุนสินค้าที่เกี่ยวข้อง" in by["C4"]["lock_reasons"]
    assert by["D1"]["locked"] and by["F1"]["locked"] and by["E4"]["locked"]
    unlocked = strategy.score_all({**SHOP, "has_costs": True, "consented_contacts": 40}, cards)
    assert not {r["id"]: r for r in unlocked}["D1"]["locked"]
    assert not {r["id"]: r for r in unlocked}["C4"]["locked"]


def test_score_is_sum_of_breakdown(cards):
    for r in strategy.score_all(SHOP, cards):
        b = r["breakdown"]
        base = b["urgent_bonus"] + .3 * b["goal_situation"] + .25 * b["persona"] + .2 * b["feasibility"] \
            + .15 * b["evidence"] + .1 * b["timing"] - b["risk"]
        assert r["score"] == pytest.approx(base * b["interest_multiplier"], abs=0.2)


def test_pick_week_rules(cards):
    shop = {**SHOP, "has_costs": True, "flags": ["ช่วงเงียบ", "บิลต่ำ"]}
    picks = strategy.pick_week(strategy.score_all(shop, cards))
    assert len(picks) == 3
    assert sum(p["is_price_offer"] for p in picks) <= 1
    assert not any(p["locked"] for p in picks)


def test_missing_maps_brings_c1_up(cards):
    ranked = strategy.score_all(SHOP, cards)
    assert [r["id"] for r in ranked].index("C1") < 5


def test_blocked_trends_are_dropped():
    ext = {"items": [{"title": "อุบัติเหตุรถชน", "news": []}, {"title": "เลือกตั้งท้องถิ่น", "news": []},
                     {"title": "ชาไทยปั่น", "news": []}], "status": "fresh"}
    sig = trends.trend_signals("drink", [], today=date(2026, 8, 1), external=ext)
    titles = [s["title"] for s in sig["signals"]]
    assert "ชาไทยปั่น" in titles and sig["blocked_count"] == 2
    assert not any("อุบัติเหตุ" in t or "เลือกตั้ง" in t for t in titles)


def test_loy_krathong_is_urgent_two_days_before():
    sig = trends.trend_signals("drink", [], today=date(2026, 11, 22), external=NO_EXT)
    lk = next(s for s in sig["signals"] if s["title"] == "ลอยกระทง")
    assert lk["urgent"] and lk["days_to_start"] == 0
    scores, because, urgent = trends.timing_scores(sig["signals"])
    assert "G3" in urgent and because["G3"] == "ลอยกระทง"


def test_festival_lifts_g3_to_top(cards):
    sig = trends.trend_signals("drink", [], today=date(2026, 11, 22), external=NO_EXT)
    ranked = strategy.score_all(SHOP, cards, timing=trends.timing_scores(sig["signals"]))
    assert ranked[0]["id"] == "G3" and ranked[0]["trend"] == "ลอยกระทง"


def test_menu_name_trend_is_most_relevant():
    assert trends.classify("ลาเต้มะพร้าว ไวรัล", "drink", ["ลาเต้มะพร้าว"]) == ("food", 1.0)
    assert trends.classify("ดาราคนดังแต่งงาน", "drink", [])[1] < 0.5


def test_parse_rss_sample():
    xml = """<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
    <item><title>มัทฉะลาเต้</title><ht:approx_traffic>2000+</ht:approx_traffic><pubDate>Wed, 18 Nov 2026</pubDate>
    <ht:news_item><ht:news_item_title>ร้านใหม่เปิด</ht:news_item_title></ht:news_item></item></channel></rss>"""
    rows = trends.parse_rss(xml)
    assert rows == [{"title": "มัทฉะลาเต้", "traffic": "2000+", "published": "Wed, 18 Nov 2026", "news": ["ร้านใหม่เปิด"]}]


def test_trends_offline_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "CACHE_FILE", tmp_path / "c.json")
    def boom():
        raise OSError("no network")
    r = trends.get_external_trends(fetcher=boom)
    assert r["status"] == "offline" and r["items"] == []
    r = trends.get_external_trends(fetcher=lambda: [{"title": "ชาไทย", "news": []}])
    assert r["status"] == "fresh"
    assert trends.get_external_trends(fetcher=boom)["status"] == "cache"


def test_memory_evidence_and_interest(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path)
    for _ in range(3):
        memory.record("shop-1", {"type": "skip", "content_id": "A1"})
    memory.record("shop-1", {"type": "result", "content_id": "C1", "outcome": "above"})
    memory.record("shop-1", {"type": "swipe", "archetype": "พนักงานกะดึก", "answer": "not_my_shop"})
    s = memory.summarize(memory.load("shop-1"))
    assert s["evidence"]["C1"]["evidence"] == pytest.approx((1 * 90 + 150) / 4)
    assert s["interest"]["A1"] == pytest.approx(0.85 ** 3)
    assert s["swipes"]["พนักงานกะดึก"] == 0.5
    with pytest.raises(ValueError):
        memory.record("../etc", {"type": "done"})
    with pytest.raises(ValueError):
        memory.record("shop-1", {"type": "hack"})


def test_library_how_texts_pass_redline():
    # ข้อความคำแนะนำในคลังไม่ควรพาไปเคลมเกินจริง (ตรวจเฉพาะส่วน "ทำอย่างไร")
    flagged = [c["id"] for c in strategy.library() if not check_redline(c["how"]).passed]
    assert flagged == []
