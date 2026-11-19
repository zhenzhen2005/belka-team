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


def test_middleware_is_wired():
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"
    assert client.post("/api/calc/discounts", content="x", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/calc/discounts", json={"items": [{"name": "a", "price": 10, "cost": 1}]},
                       headers={"origin": "https://evil.example"}).status_code == 403
    assert TestClient(app, base_url="http://evil.example").get("/api/health").status_code == 400
