"""เรดาร์เทรนด์: เทรนด์ภายนอก + ปฏิทินเทศกาล → คะแนน "จังหวะเวลา" และโบนัสเร่งด่วนของสูตรเลือกคอนเทนต์.

แหล่งข้อมูล
1. Google Trends "Trending Now" ประเทศไทย ผ่าน RSS สาธารณะ (ไม่ต้องใช้ key)
   https://trends.google.com/trending/rss?geo=TH — เป็นภาพ ณ ตอนนั้น ไม่มีประวัติ จึงดึงซ้ำทุก CACHE_MINUTES
2. ปฏิทินเทศกาลและฤดูกาล data/trend_calendar.json (ทีมแก้เองได้)

กฎความปลอดภัย (โค้ดล้วน)
- ตัดเทรนด์ข่าวการเมือง ภัยพิบัติ อาชญากรรม การเสียชีวิต การพนัน ทิ้งก่อนเสมอ (กรองเกินดีกว่ากรองขาด)
- ระบบไม่ส่งรายละเอียดข่าวให้ AI แต่ง ส่งแค่คำเทรนด์ที่ผ่านการกรองและเกี่ยวกับร้าน
"""
from __future__ import annotations

import json
import logging
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import PROJECT_DIR

log = logging.getLogger("belka.trends")

RSS_URL = "https://trends.google.com/trending/rss?geo=TH"
CACHE_MINUTES = 60
CACHE_FILE = PROJECT_DIR / "var" / "trends_cache.json"
CALENDAR_FILE = PROJECT_DIR / "data" / "trend_calendar.json"

BLOCKED = [
    "เสียชีวิต", "ตาย", "ศพ", "ฆ่า", "ยิง", "แทง", "อุบัติเหตุ", "ชน", "น้ำท่วม", "ไฟไหม้", "แผ่นดินไหว", "พายุ",
    "ระเบิด", "ข่มขืน", "ยาเสพติด", "การเมือง", "เลือกตั้ง", "นายก", "รัฐบาล", "พรรค", "ส.ส.", "ประท้วง", "สงคราม",
    "คดี", "จับกุม", "ตำรวจ", "ศาล", "หวย", "ลอตเตอรี่", "สลาก", "พนัน", "บาคาร่า", "สินบน", "โกง",
    "death", "dies", "killed", "shooting", "crash", "flood", "earthquake", "election", "police", "lottery",
]
FOOD_WORDS = {
    "drink": ["กาแฟ", "ชา", "ชานม", "ชาไทย", "มัทฉะ", "โกโก้", "น้ำปั่น", "สมูทตี้", "ลาเต้", "อเมริกาโน่", "บิงซู",
              "coffee", "tea", "matcha", "latte"],
    "bakery": ["ขนม", "เค้ก", "ครัวซองต์", "บราวนี่", "คุกกี้", "ขนมปัง", "ทาร์ต", "โดนัท", "ครอฟเฟิล", "cake", "croissant"],
    "food": ["ข้าว", "ก๋วยเตี๋ยว", "หมูกระทะ", "ส้มตำ", "ผัดกะเพรา", "ราเมง", "ชาบู", "ไก่ทอด", "สตรีทฟู้ด", "อาหาร", "food"],
}
GENERAL_WORDS = ["ร้อน", "ฝน", "หนาว", "วันหยุด", "เทศกาล", "คอนเสิร์ต", "ตลาดนัด", "ลดราคา", "โปร", "เปิดเทอม",
                 "เงินเดือน", "วันแม่", "วันพ่อ", "วาเลนไทน์", "ปีใหม่", "สงกรานต์", "ลอยกระทง", "คริสต์มาส", "ฮาโลวีน"]
# เทรนด์แต่ละแบบเหมาะกับคอนเทนต์อะไร (รหัสจากคลัง 34 แบบ)
KIND_TO_CONTENT = {
    "food": ["A2", "A5", "A1", "A7"],
    "festival": ["G3", "A5"],  # G1 ประกาศวันหยุด ใช้เมื่อร้านบอกว่าจะปิดร้านเท่านั้น
    "season": ["A5", "A2", "G3"],
    "payday": ["E2", "D1", "A2"],
    "event": ["A5", "A4", "F2"],
    "general": ["A5"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("​", "")
    return " ".join(s.split()).casefold()


def is_blocked(text: str) -> bool:
    t = _norm(text)
    return any(_norm(w) in t for w in BLOCKED)


def classify(title: str, shop_type: str, menu_names: list[str]) -> tuple[str, float]:
    """คืน (ชนิดเทรนด์, ความเกี่ยวกับร้าน 0–1)"""
    t = _norm(title)
    if any(_norm(m) in t for m in menu_names if m):
        return "food", 1.0
    if any(_norm(w) in t for w in FOOD_WORDS.get(shop_type, [])):
        return "food", 0.9
    if any(_norm(w) in t for ws in FOOD_WORDS.values() for w in ws):
        return "food", 0.5
    if any(_norm(w) in t for w in GENERAL_WORDS):
        return "event", 0.5
    return "general", 0.15


# ---------- Google Trends RSS ----------
def parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter():
        if not item.tag.endswith("item"):
            continue
        row = {"title": "", "traffic": "", "published": "", "news": []}
        for child in item:
            tag = child.tag.split("}")[-1]
            if tag == "title":
                row["title"] = (child.text or "").strip()
            elif tag == "approx_traffic":
                row["traffic"] = (child.text or "").strip()
            elif tag == "pubDate":
                row["published"] = (child.text or "").strip()
            elif tag == "news_item":
                for n in child:
                    if n.tag.split("}")[-1] == "news_item_title" and n.text:
                        row["news"].append(n.text.strip())
        if row["title"]:
            items.append(row)
    return items


def fetch_google_trends(timeout: float = 5.0) -> list[dict]:
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Belka-prototype/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_rss(resp.read().decode("utf-8", errors="ignore"))


def get_external_trends(now: float | None = None, fetcher=fetch_google_trends) -> dict:
    """อ่านจากแคช ถ้าเก่ากว่า CACHE_MINUTES ให้ดึงใหม่ ถ้าดึงไม่ได้ใช้ของเดิมและบอกสถานะ"""
    now = now or time.time()
    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    if cache and now - cache.get("fetched_at", 0) < CACHE_MINUTES * 60:
        return {**cache, "status": "cache"}
    try:
        items = fetcher()
        cache = {"fetched_at": now, "source": RSS_URL, "items": items}
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return {**cache, "status": "fresh"}
    except Exception as exc:  # noqa: BLE001 - ไม่มีเน็ตก็ต้องใช้ต่อได้
        log.warning("ดึง Google Trends ไม่ได้: %s", exc)
        return {**cache, "items": cache.get("items", []), "status": "offline"}


# ---------- ปฏิทินเทศกาล ----------
def load_calendar() -> list[dict]:
    try:
        return json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))["events"]
    except (OSError, json.JSONDecodeError, KeyError):
        return []


def calendar_signals(today: date, events: list[dict] | None = None, horizon_days: int = 14) -> list[dict]:
    """เทศกาล/ฤดูกาลที่อยู่ในช่วงหรือกำลังจะมาภายใน horizon_days"""
    out = []
    if today.day >= 25 or today.day <= 2:  # เงินเดือนออก ทุกเดือน
        out.append({"title": "เงินเดือนออก", "kind": "payday", "start": "", "end": "", "days_to_start": 0,
                    "relevance": 0.6, "source": "calendar", "urgent": False})
    for ev in events if events is not None else load_calendar():
        for start_s, end_s in _occurrences(ev, today):
            start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
            if start - timedelta(days=horizon_days) <= today <= end:
                days_to = max(0, (start - today).days)
                rel = 1.0 if days_to <= 3 else (0.8 if days_to <= 7 else 0.5)
                if ev.get("kind") == "season":
                    rel = min(rel, 0.6)  # ฤดูกาลยาวหลายเดือน ไม่เร่งเท่าเทศกาล
                out.append({"title": ev["name"], "kind": ev.get("kind", "festival"), "start": start_s, "end": end_s,
                            "days_to_start": days_to, "relevance": rel, "source": "calendar",
                            "urgent": ev.get("kind") == "festival" and days_to <= 3})
                break
    return out


def _occurrences(ev: dict, today: date):
    if "dates" in ev:  # วันที่ระบุรายปี เช่น เทศกาลตามจันทรคติ
        for d in ev["dates"]:
            yield d["start"], d["end"]
    else:  # เดือน-วัน ซ้ำทุกปี
        for y in (today.year, today.year + 1):
            s = f"{y}-{ev['start']}"
            e_year = y + 1 if ev["end"] < ev["start"] else y
            yield s, f"{e_year}-{ev['end']}"


# ---------- รวมเป็นสัญญาณให้สูตรเลือกคอนเทนต์ ----------
def trend_signals(shop_type: str, menu_names: list[str] | None = None, today: date | None = None,
                  external: dict | None = None) -> dict:
    today = today or date.today()
    menu_names = menu_names or []
    ext = external if external is not None else get_external_trends()
    signals, blocked = [], 0
    for it in ext.get("items", []):
        text = " ".join([it["title"], *it.get("news", [])])
        if is_blocked(text):
            blocked += 1
            continue
        kind, rel = classify(it["title"], shop_type, menu_names)
        signals.append({"title": it["title"], "kind": kind, "relevance": rel, "traffic": it.get("traffic", ""),
                        "source": "google_trends", "urgent": False})
    signals += calendar_signals(today)
    signals.sort(key=lambda s: -s["relevance"])
    return {"signals": signals, "blocked_count": blocked, "external_status": ext.get("status", "none"),
            "fetched_at": ext.get("fetched_at"), "source": RSS_URL}


def timing_scores(signals: list[dict]) -> tuple[dict[str, float], dict[str, str], set[str]]:
    """คะแนนจังหวะเวลา 0–100 ต่อรหัสคอนเทนต์ + เทรนด์ที่ทำให้ได้คะแนน + รหัสที่ได้โบนัสเร่งด่วน"""
    scores: dict[str, float] = {}
    because: dict[str, str] = {}
    urgent: set[str] = set()
    for s in signals:
        for cid in KIND_TO_CONTENT.get(s["kind"], []):
            val = 100 * s["relevance"]
            if val > scores.get(cid, 0) or (val == scores.get(cid, 0) and s.get("urgent")):
                scores[cid], because[cid] = val, s["title"]
            if s.get("urgent") and cid == "G3":
                urgent.add(cid)
    return scores, because, urgent
