"""โครงสร้างข้อมูลของ Belka (ใช้ร่วมกันทั้ง API, Trust Engine และเอเจนต์)."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ShopType = Literal["drink", "bakery", "food"]
Customer = Literal["workers", "students", "locals", "tourists"]
Channel = Literal["line", "facebook", "google_maps", "delivery", "none"]
TaskChannel = Literal["line", "facebook", "google_maps", "delivery", "storefront", "instagram", "tiktok"]

SHOP_TYPE_TH = {"drink": "เครื่องดื่ม", "bakery": "เบเกอรี่", "food": "อาหาร"}
CUSTOMER_TH = {
    "workers": "คนทำงาน",
    "students": "นักศึกษา",
    "locals": "คนในย่าน",
    "tourists": "นักท่องเที่ยว",
}
CHANNEL_TH = {
    "line": "LINE",
    "facebook": "Facebook",
    "google_maps": "Google Maps",
    "delivery": "แอปเดลิเวอรี",
    "storefront": "หน้าร้าน",
    "instagram": "Instagram",
    "tiktok": "TikTok",
}


class PersonaPick(BaseModel):
    """กลุ่มลูกค้าจำลองที่เจ้าของร้านแตะเลือกก่อนรับแผน (มาจากการ์ดของ /api/personas)."""

    archetype: str = Field(min_length=1, max_length=60)
    segment: str = Field(default="", max_length=40)
    likes: list[str] = Field(default=[], max_length=4)
    objection: str = Field(default="", max_length=80)
    post_time: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}–\d{1,2}:\d{2}$")


class ShopProfile(BaseModel):
    """ข้อมูลจาก onboarding 3 ขั้น (แตะเลือกทั้งหมด ไม่มีช่องให้พิมพ์) + กลุ่มลูกค้าที่เลือก + ประวัติแผน."""

    shop_type: ShopType
    customer: Customer
    channels: list[Channel] = Field(min_length=1)
    personas: list[PersonaPick] = Field(default=[], max_length=3)
    # ประเภทงานของแผนสัปดาห์ก่อน ๆ (เก่าไปใหม่) ใช้กันไม่ให้งานซ้ำกับสัปดาห์ที่แล้ว
    history: list[list[str]] = Field(default=[], max_length=12)
    week: int = Field(default=1, ge=1, le=520)
    # ไอเดียที่เจ้าของร้านกด "ใส่ในแผน" จากแท็บไอเดีย (รหัสคลัง 34 แบบ เช่น G3)
    pinned: list[str] = Field(default=[], max_length=3)

    @field_validator("pinned")
    @classmethod
    def _clean_pinned(cls, value: list[str]) -> list[str]:
        return [v for v in dict.fromkeys(value) if re.fullmatch(r"[A-G]\d{1,2}", v)]

    @field_validator("channels")
    @classmethod
    def _clean_channels(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value))
        # "ยังไม่มี" ใช้ร่วมกับช่องทางอื่นไม่ได้
        if "none" in unique and len(unique) > 1:
            unique = [c for c in unique if c != "none"]
        return unique

    def has(self, channel: str) -> bool:
        return channel in self.channels


class RedlineIssue(BaseModel):
    term: str
    reason: str
    suggestion: str


class RedlineResult(BaseModel):
    passed: bool
    issues: list[RedlineIssue] = []


class Slot(BaseModel):
    """ช่องงานที่ Trust Engine กำหนดด้วยโค้ด: ช่องทาง วัน เวลา และเวลาที่ใช้."""

    slot: int
    kind: str
    channel: TaskChannel
    goal: str
    date: date
    day_label: str
    time_window: str
    minutes: int


class PlanTask(BaseModel):
    slot: int
    kind: str
    channel: TaskChannel
    channel_label: str
    date: date
    day_label: str
    time_window: str
    minutes: int
    title: str
    why: str
    steps: list[str]
    caption: str
    redline: RedlineResult
    source: Literal["ai", "fallback"]
    content_id: str = ""  # รหัสในคลัง 34 แบบ ใช้บันทึกความจำของร้าน


class WeeklyPlan(BaseModel):
    profile: ShopProfile
    week: int = 1
    tasks: list[PlanTask]
    source: Literal["ai", "fallback", "mixed"]
    notice: str | None = None
    ai_tool_calls: int = 0
    elapsed_ms: int = 0
