from datetime import date
from itertools import combinations

import pytest

from belka.models import ShopProfile
from belka.redline import check_redline
from belka.trust_engine import build_slots, fallback_task, pick_kinds

TODAY = date(2026, 11, 18)  # วันพุธ
CHANNELS = ["line", "facebook", "google_maps", "delivery"]


def all_profiles():
    channel_sets = [["none"]] + [list(c) for n in range(1, 5) for c in combinations(CHANNELS, n)]
    for shop in ["drink", "bakery", "food"]:
        for customer in ["workers", "students", "locals", "tourists"]:
            for chans in channel_sets:
                yield ShopProfile(shop_type=shop, customer=customer, channels=chans)


@pytest.mark.parametrize("profile", list(all_profiles()))
def test_every_profile_gets_three_safe_tasks(profile):
    """ร้านทุกแบบต้องได้แผน 3 งาน ไม่ซ้ำ ไม่เกิน 10 นาที และแคปชันผ่าน red-line"""
    slots = build_slots(profile, TODAY)
    assert len(slots) == 3
    assert len({s.kind for s in slots}) == 3
    for slot in slots:
        task = fallback_task(slot, profile)
        assert 1 <= task.minutes <= 10
        assert task.redline.passed, task.caption
        assert check_redline(" ".join([task.title, task.why, *task.steps])).passed
        assert 2 <= len(task.steps) <= 3


def test_first_task_is_today_and_spaced():
    profile = ShopProfile(shop_type="drink", customer="workers", channels=["facebook"])
    slots = build_slots(profile, TODAY)
    assert [s.date.day for s in slots] == [18, 20, 23]  # อาทิตย์ 22 เลื่อนเป็นจันทร์ 23
    assert slots[0].day_label == "พุธ 18 พ.ย."
    locals_profile = ShopProfile(shop_type="drink", customer="locals", channels=["facebook"])
    assert [s.date.day for s in build_slots(locals_profile, TODAY)] == [18, 20, 22]


def test_google_maps_comes_first():
    profile = ShopProfile(shop_type="food", customer="locals", channels=["none"])
    assert pick_kinds(profile)[0] == "maps_create"
    profile = ShopProfile(shop_type="food", customer="locals", channels=["google_maps"])
    assert pick_kinds(profile)[0] == "maps_photos"


def test_delivery_shops_get_direct_order_task():
    profile = ShopProfile(shop_type="food", customer="workers", channels=["delivery"])
    assert "delivery_card" in pick_kinds(profile)


def test_none_is_dropped_when_other_channels_chosen():
    profile = ShopProfile(shop_type="bakery", customer="students", channels=["none", "line"])
    assert profile.channels == ["line"]
