"""ทดสอบ /api/calc/discounts และการต่อ SecurityMiddleware เข้ากับแอปจริง (ต้องมี fastapi + httpx)"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from belka.api import app  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_discounts_per_item():
    r = client.post("/api/calc/discounts", json={"items": [
        {"name": "ชาไทย", "price": 60, "cost": 20},
        {"name": "ข้าวมันไก่", "price": 50, "cost": 45},     # มาร์จิ้นต่ำ ห้ามลด
        {"name": "เค้ก", "price": 90},                         # ยังไม่มีต้นทุน
    ]})
    assert r.status_code == 200
    a, b, c = r.json()["items"]
    assert a["recommendation"]["eligible"] and a["recommendation"]["promo_price"] < 60
    assert not b["recommendation"]["eligible"] and "ไม่ควรลดราคา" in b["recommendation"]["reason"]
    assert c["recommendation"] is None and "ต้นทุน" in c["note"]
    assert r.json()["eligible_count"] == 1


def test_discounts_validation():
    assert client.post("/api/calc/discounts", json={"items": []}).status_code == 422
    assert client.post("/api/calc/discounts", json={"items": [{"name": "x", "price": 0, "cost": 1}]}).status_code == 422


def test_discounts_account_for_gp_per_channel():
    r = client.post("/api/calc/discounts", json={"items": [
        {"name": "ชาไทย", "price": 60, "cost": 20},
        {"name": "ข้าวกล่อง", "price": 45, "cost": 25}],
        "gp_rates": {"หน้าร้าน": 0, "Grab": 0.30}})
    assert r.status_code == 200
    tea, box = r.json()["items"]
    # หัก GP แล้วกำไรต่อชิ้นน้อยลง ส่วนลดที่ลดได้ก็น้อยลงตาม
    assert tea["by_channel"]["Grab"]["unit_profit_before"] < tea["by_channel"]["หน้าร้าน"]["unit_profit_before"]
    assert tea["by_channel"]["Grab"]["discount_baht"] <= tea["by_channel"]["หน้าร้าน"]["discount_baht"]
    # หน้าร้านมาร์จิ้นพอ แต่ผ่านแอปหลังหัก GP ต่ำกว่า 20% ห้ามทำโปรในแอป
    assert box["by_channel"]["หน้าร้าน"]["eligible"] and not box["by_channel"]["Grab"]["eligible"]
    assert box["recommendation"]["eligible"]          # recommendation = ช่องแรก (หน้าร้าน)


def test_discounts_reject_bad_gp():
    item = {"items": [{"name": "x", "price": 50, "cost": 10}]}
    for bad in [{"Grab": 1.0}, {"Grab": -0.1}, {}]:
        assert client.post("/api/calc/discounts", json={**item, "gp_rates": bad}).status_code == 422


def test_ad_budget_from_gp_saved():
    r = client.post("/api/calc/ad-budget", json={"monthly_sales": 20000, "platform_share_before": 0.8,
                                                 "platform_share_after": 0.5, "gp_rate": 0.3})
    assert r.status_code == 200
    j = r.json()
    assert j["gp_before"] == 4800 and j["gp_after"] == 3000 and j["saved_per_month"] == 1800
    assert j["marketing_budget"] == 540 and j["has_saving"]          # 30% ของ GP ที่ประหยัดได้
    assert j["weekly_budget"] == round(540 * 12 / 52, 2)


def test_ad_budget_zero_when_no_gp_saved():
    r = client.post("/api/calc/ad-budget", json={"monthly_sales": 20000, "platform_share_before": 0.5,
                                                 "platform_share_after": 0.7, "gp_rate": 0.3})
    assert r.json()["marketing_budget"] == 0 and not r.json()["has_saving"]
    assert client.post("/api/calc/ad-budget", json={"monthly_sales": 0, "platform_share_before": 0.5,
                                                    "platform_share_after": 0.4, "gp_rate": 0.3}).status_code == 422


def test_middleware_is_wired():
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"
    assert client.post("/api/calc/discounts", content="x", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/calc/discounts", json={"items": [{"name": "a", "price": 10, "cost": 1}]},
                       headers={"origin": "https://evil.example"}).status_code == 403
    assert TestClient(app, base_url="http://evil.example").get("/api/health").status_code == 400
