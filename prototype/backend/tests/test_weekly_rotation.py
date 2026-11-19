"""แผนแต่ละสัปดาห์ไม่ซ้ำกัน · กลุ่มลูกค้าที่เลือกมีผลกับแผน · ไอเดียที่กดใส่ในแผนมาก่อน"""
from datetime import date

from belka.models import ShopProfile
from belka.trust_engine import build_slots, fallback_task, pick_kinds

TODAY = date(2026, 11, 18)


def weeks(profile_kwargs: dict, n: int) -> list[list[str]]:
    hist: list[list[str]] = []
    for w in range(n):
        p = ShopProfile(**profile_kwargs, history=hist, week=w + 1)
        hist = hist + [pick_kinds(p)]
    return hist


def test_consecutive_weeks_do_not_repeat_tasks():
    h = weeks({"shop_type": "drink", "customer": "workers", "channels": ["line", "google_maps", "facebook"]}, 4)
    for a, b in zip(h, h[1:]):
        assert not set(a) & set(b), (a, b)
    assert all(len(set(w)) == 3 for w in h)


def test_setup_task_done_once_then_rotates():
    h = weeks({"shop_type": "food", "customer": "locals", "channels": ["none"]}, 3)
    assert h[0][0] == "maps_create" and "line_create" in h[0]
    assert "maps_create" not in h[1] and "line_create" not in h[1]
    assert not set(h[1]) & set(h[2])


def test_first_week_keeps_team_priority():
    p = ShopProfile(shop_type="drink", customer="workers", channels=["google_maps", "delivery"])
    assert pick_kinds(p)[:2] == ["maps_photos", "delivery_card"]


def test_persona_sets_post_time_and_why():
    p = ShopProfile(shop_type="drink", customer="workers", channels=["line"],
                    personas=[{"archetype": "พนักงานกะดึก", "likes": ["ใกล้ที่ทำงาน"], "post_time": "11:00–11:30"}])
    slots = build_slots(p, TODAY)
    assert {s.time_window for s in slots} == {"11:00–11:30"}
    assert "พนักงานกะดึก" in fallback_task(slots[0], p).why


def test_pinned_idea_goes_first_and_only_one_price_offer():
    p = ShopProfile(shop_type="drink", customer="students", channels=["line", "facebook"], pinned=["G3", "E1", "E2"])
    kinds = pick_kinds(p)
    assert kinds[0] == "lib:G3" and kinds.count("lib:E1") == 1 and "lib:E2" not in kinds
    task = fallback_task(build_slots(p, TODAY)[0], p)
    assert task.content_id == "G3" and task.redline.passed


def test_every_fallback_caption_passes_redline():
    for ch in (["line", "facebook", "google_maps", "delivery"], ["none"]):
        h = weeks({"shop_type": "bakery", "customer": "tourists", "channels": ch}, 5)
        p = ShopProfile(shop_type="bakery", customer="tourists", channels=ch)
        for w in h:
            for s in build_slots(ShopProfile(shop_type="bakery", customer="tourists", channels=ch, pinned=[]), TODAY):
                pass
        for k in {k for w in h for k in w}:
            from belka.models import Slot
            from belka.trust_engine import kind_spec
            sp = kind_spec(k)
            slot = Slot(slot=1, kind=k, channel=sp["channel"], goal=sp["goal"], date=TODAY, day_label="x",
                        time_window="x", minutes=sp["minutes"])
            assert fallback_task(slot, p).redline.passed, k
