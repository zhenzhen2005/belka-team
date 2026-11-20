"""Belka API — backend ตัวเดียวที่ใช้ร่วมกันทั้ง web app และแอปมือถือ.

รัน (จากโฟลเดอร์ prototype/backend):
    uv run --with fastapi --with uvicorn uvicorn belka.api:app --host 127.0.0.1 --port 8000
web app: http://127.0.0.1:8000
ทีมกำหนดให้รันเฉพาะ 127.0.0.1 (spec weekly-plan D1) อย่าเปลี่ยนเป็น 0.0.0.0 ถ้าทีมยังไม่อนุมัติ

ส่วนที่ใช้ AI (Bedrock): /api/plan (เขียนแผนและแคปชัน), /api/ask (ถาม Belka), /api/menu/import (อ่านเมนูจากรูป)
ส่วนที่เป็นโค้ดล้วน: /api/calc/*, /api/personas, /api/ideas, /api/trends, /api/memory, /api/redline
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import calc, memory, menu_import, personas, strategy, trends
from .config import PROJECT_DIR, config_refused, get_settings
from .models import RedlineResult, ShopProfile, WeeklyPlan
from .planner import _call_with_deadline, make_plan
from .redline import check_redline
from .security import SecurityMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("belka.api")

r2_ = calc.r2

app = FastAPI(title="Belka API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
                   allow_methods=["*"], allow_headers=["*"])
# ชั้นป้องกัน (Host/Origin/ขนาด/จำกัดครั้ง/header) — เพิ่มทีหลัง CORS จึงอยู่นอกสุด ตรวจก่อนทุกอย่าง
app.add_middleware(SecurityMiddleware)


class ShopContext(BaseModel):
    """ข้อมูลร้านสำหรับ persona / ไอเดีย / ถาม Belka (ทุกช่องนอกจาก 3 ข้อแรกไม่บังคับ)"""
    shop_type: Literal["drink", "bakery", "food"]
    customer: Literal["workers", "students", "locals", "tourists"]
    channels: list[str] = []
    shop_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    avg_price: float | None = None
    area: dict | None = None
    menu: list[str] = []
    tags: list[str] = []
    flags: list[str] = []
    goals: list[str] = []
    has_costs: bool = False
    consented_contacts: int = 0
    regular_customers: int = 0
    has_partner: bool = False
    nearby_office: bool = False
    leftover_pct: float = 0
    full_capacity: bool = False
    owner_time_level: int = 2


class RedlineRequest(BaseModel):
    text: str = Field(max_length=1000)


class MenuRow(BaseModel):
    name: str = Field(max_length=60)
    price: float = Field(gt=0)
    cost: float | None = Field(default=None, ge=0)


class MenuCalcRequest(BaseModel):
    items: list[MenuRow] = Field(min_length=1, max_length=50)
    gp_rates: dict[str, float] = {"หน้าร้าน": 0.0, "Grab": 0.30, "LINE MAN": 0.30}
    monthly_sales: float | None = None
    platform_share_before: float | None = None
    platform_share_after: float | None = None


class PromoRequest(BaseModel):
    name: str = "เมนู"
    price: float = Field(gt=0)
    cost: float = Field(ge=0)
    commission_rate: float = Field(default=0, ge=0, lt=1)
    expected_lift: float = Field(default=0.3, gt=0, le=3)
    base_units_per_day: float = Field(default=20, gt=0)


class MemoryEvent(BaseModel):
    type: Literal["done", "skip", "result", "save_idea", "swipe", "search", "note"]
    content_id: str | None = None
    outcome: Literal["above", "within", "below"] | None = None
    score: float | None = None
    archetype: str | None = None
    answer: Literal["not_my_shop", "similar", "exactly"] | None = None
    text: str | None = Field(default=None, max_length=200)
    channel: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    shop: ShopContext


def _shop_dict(shop: ShopContext) -> dict:
    return shop.model_dump()


def _memory_summary(shop_id: str | None) -> dict:
    return memory.summarize(memory.load(shop_id)) if shop_id else memory.summarize([])


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "mode": s.mode, "model": s.model_id, "region": s.region, "config_refused": config_refused(s)}


@app.post("/api/plan", response_model=WeeklyPlan)
def create_plan(profile: ShopProfile) -> WeeklyPlan:
    return make_plan(profile)


@app.post("/api/redline", response_model=RedlineResult)
def redline(body: RedlineRequest) -> RedlineResult:
    """ใช้ตรวจแคปชันที่เจ้าของร้านแก้เอง ข้อความที่แก้แล้วต้องผ่าน gate เหมือนกัน"""
    return check_redline(body.text)


@app.post("/api/personas")
def match_personas(shop: ShopContext) -> dict:
    swipes = _memory_summary(shop.shop_id)["swipes"]
    return personas.match_shop(_shop_dict(shop), swipes=swipes)


@app.get("/api/trends")
def get_trends(shop_type: Literal["drink", "bakery", "food"] = "drink", menu: str = "") -> dict:
    return trends.trend_signals(shop_type, [m for m in menu.split(",") if m])


@app.post("/api/ideas")
def ideas(shop: ShopContext) -> dict:
    d = _shop_dict(shop)
    mem = _memory_summary(shop.shop_id)
    cards = personas.match_shop(d, swipes=mem["swipes"])["cards"]
    sig = trends.trend_signals(shop.shop_type, shop.menu)
    ranked = strategy.score_all(d, cards, mem, trends.timing_scores(sig["signals"]))
    return {"week": strategy.pick_week(ranked), "ranked": ranked, "personas": cards,
            "trends": sig, "memory": {k: mem[k] for k in ("done", "skipped", "events", "interests")}}


@app.post("/api/calc/menu")
def calc_menu(body: MenuCalcRequest) -> dict:
    rows = []
    for it in body.items:
        if it.cost is None:
            rows.append({"name": it.name, "price": it.price, "cost": None, "note": "ยังไม่มีต้นทุน แสดงเฉพาะราคา"})
            continue
        by_ch = calc.profit_by_channel(it.price, it.cost, body.gp_rates)
        rows.append({"name": it.name, "price": it.price, "cost": it.cost, "by_channel": by_ch,
                     "loss_channels": [c for c, v in by_ch.items() if v["loss"]],
                     "low_margin_channels": [c for c, v in by_ch.items() if v["margin"] < calc.MIN_MARGIN_FOR_PROMO]})
    out = {"items": rows}
    if body.monthly_sales and body.platform_share_before is not None and body.platform_share_after is not None:
        gp = max((r for r in body.gp_rates.values()), default=0.3)
        out["gp_savings"] = calc.gp_savings(body.monthly_sales, body.platform_share_before,
                                            body.platform_share_after, gp)
    return out


@app.post("/api/calc/promo")
def calc_promo(body: PromoRequest) -> dict:
    try:
        item = calc.Item(body.name, body.price, body.cost, commission_rate=body.commission_rate)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    rec = calc.recommend_discount(item, body.expected_lift)
    if not rec["eligible"]:
        return {"recommendation": rec}
    sims = calc.simulate_units(rec["unit_profit_before"], rec["discount_baht"], body.base_units_per_day,
                               body.expected_lift)
    return {"recommendation": rec, "scenarios": sims,
            "delivery_promo_allowed": calc.delivery_promo_allowed(item)}


class DiscountRequest(BaseModel):
    items: list[MenuRow] = Field(min_length=1, max_length=50)
    expected_lift: float = Field(default=0.3, gt=0, le=3)
    # อัตรา GP ต่อช่องทาง (สัดส่วน 0–<1) ใช้หักก่อนคิดว่าลดได้เท่าไหร่ ช่องแรกคือช่องหลักที่ใช้ใน "recommendation"
    gp_rates: dict[str, float] = {"หน้าร้าน": 0.0}

    @field_validator("gp_rates")
    @classmethod
    def _check_rates(cls, v: dict[str, float]) -> dict[str, float]:
        if not v or len(v) > 8:
            raise ValueError("ใส่ช่องทางได้ 1–8 ช่องทาง")
        if any(not 0 <= r < 1 for r in v.values()):
            raise ValueError("GP ต้องอยู่ระหว่าง 0% ถึงต่ำกว่า 100%")
        return v


@app.post("/api/calc/discounts")
def calc_discounts(body: DiscountRequest) -> dict:
    """ส่งเมนู ราคา ต้นทุน ทีเดียว ได้คำแนะนำส่วนลดรายเมนู แยกตามช่องทาง (หัก GP ก่อน) ไม่มีส่วนลดเหมารวม"""
    rows, first = [], next(iter(body.gp_rates))
    for it in body.items:
        if it.cost is None:
            rows.append({"name": it.name, "price": it.price, "cost": None, "recommendation": None, "by_channel": {},
                         "note": "ยังไม่มีต้นทุน จึงยังคำนวณส่วนลดไม่ได้"})
            continue
        by_channel = {}
        try:
            for ch, rate in body.gp_rates.items():
                item = calc.Item(it.name, it.price, it.cost, commission_rate=rate)
                by_channel[ch] = {**calc.recommend_discount(item, body.expected_lift), "gp_rate": rate,
                                  "unit_profit_before_gp": r2_(it.price - it.cost)}
        except ValueError as exc:
            rows.append({"name": it.name, "price": it.price, "cost": it.cost, "recommendation": None,
                         "by_channel": {}, "note": str(exc)})
            continue
        rows.append({"name": it.name, "price": it.price, "cost": it.cost, "recommendation": by_channel[first],
                     "by_channel": by_channel})
    ok = sum(1 for r in rows if any(c["eligible"] for c in r["by_channel"].values()))
    return {"items": rows, "channels": list(body.gp_rates), "eligible_count": ok}


class AdBudgetRequest(BaseModel):
    monthly_sales: float = Field(gt=0, le=100_000_000)
    platform_share_before: float = Field(ge=0, le=1)
    platform_share_after: float = Field(ge=0, le=1)
    gp_rate: float = Field(ge=0, lt=1)


@app.post("/api/calc/ad-budget")
def calc_ad_budget(body: AdBudgetRequest) -> dict:
    """งบโฆษณา = ส่วนหนึ่ง (30% ตามสูตรทีม) ของ GP ที่ประหยัดได้เมื่อลดสัดส่วนออเดอร์ผ่านแอป
    ถ้าไม่ได้ลดสัดส่วน (ไม่มี GP ที่ประหยัด) งบเป็น 0 ไม่แนะนำให้ควักเพิ่ม"""
    r = calc.gp_savings(body.monthly_sales, body.platform_share_before, body.platform_share_after, body.gp_rate)
    saving = r["saved_per_month"] > 0
    budget = r["marketing_budget"] if saving else 0.0
    return {**r, "marketing_budget": budget, "weekly_budget": calc.r2(budget * 12 / 52), "has_saving": saving,
            "share_of_saved": calc.MARKETING_SHARE_OF_GP_SAVED}


@app.get("/api/memory/{shop_id}")
def get_memory(shop_id: str) -> dict:
    try:
        return memory.summarize(memory.load(shop_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/memory/{shop_id}")
def add_memory(shop_id: str, event: MemoryEvent) -> dict:
    try:
        memory.record(shop_id, event.model_dump(exclude_none=True))
        return memory.summarize(memory.load(shop_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _fallback_answer(question: str, shop: dict) -> str:
    picks = strategy.pick_week(strategy.score_all(shop, []))
    names = " · ".join(p["name"] for p in picks)
    if any(w in question for w in ("ลด", "โปร", "ส่วนลด", "ราคา")):
        return ("เรื่องส่วนลดให้ใช้ตัวคำนวณโปรในแท็บวิเคราะห์ กรอกราคากับต้นทุนเมนู 1 รายการ "
                "Belka จะบอกราคาโปรที่ยังคุ้มและยอดที่ต้องขายเพิ่ม")
    return f"สัปดาห์นี้ลองเริ่มจาก: {names} ดูรายละเอียดและเหตุผลได้ในแท็บไอเดีย"


@app.post("/api/ask")
def ask(body: AskRequest) -> dict:
    shop = _shop_dict(body.shop)
    settings = get_settings()
    if settings.mode == "ai" and not config_refused(settings):
        from .agent import run_ask

        out = _call_with_deadline(lambda q: run_ask(q, shop), body.question, settings.ai_timeout_s * 2)
        if out is not None:
            gate = check_redline(out.text)
            if gate.passed:
                return {"answer": out.text, "source": "ai", "tool_calls": out.tool_calls}
            log.warning("คำตอบถาม Belka ไม่ผ่าน red-line ใช้คำตอบมาตรฐาน")
    return {"answer": _fallback_answer(body.question, shop), "source": "fallback", "tool_calls": []}


class MenuImportRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=5_000_000)


@app.post("/api/menu/import")
def import_menu_from_photo(body: MenuImportRequest) -> dict:
    """อ่านรายการเมนูจากรูปถ่าย (ไม่เก็บรูป). เจ้าของร้านต้องตรวจและแก้ก่อนใช้."""
    try:
        res = menu_import.import_menu(body.image_base64)
    except menu_import.MenuImportError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"items": res.items, "unpriced": res.unpriced, "dropped": res.dropped,
            "source": res.source, "message": res.message}


# เสิร์ฟโลโก้ มาสคอต และ web app (ต้องอยู่หลัง route ของ /api)
app.mount("/brand", StaticFiles(directory=PROJECT_DIR / "brand"), name="brand")
app.mount("/", StaticFiles(directory=PROJECT_DIR / "web", html=True), name="web")
