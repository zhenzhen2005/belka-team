"""ความจำของร้าน: เรียนรู้จากสิ่งที่ร้านทำซ้ำ ๆ บันทึก และค้นหา — โค้ดล้วน เก็บเป็นไฟล์ในเครื่อง.

เหตุการณ์ที่เก็บ (event.type)
- done / skip      : ร้านทำหรือข้ามงานของคอนเทนต์ content_id
- result           : ผลที่วัดได้ outcome = above | within | below (เทียบกับที่จำลองไว้) หรือ score 0–100
- save_idea        : บันทึกไอเดียไว้
- swipe            : ปัดการ์ดลูกค้าจำลอง archetype + answer = not_my_shop | similar | exactly
- search / note    : คำค้นหรือโน้ตของเจ้าของร้าน (ใช้เป็นความสนใจ)

ผลที่ส่งให้สูตรเลือกคอนเทนต์
- หลักฐาน = (n × ผลเฉลี่ย + 3 × 50) ÷ (n + 3) เริ่มที่ 50 (สูตรของทีม)
- ตัวคูณความสนใจต่อคอนเทนต์ (assumption): ข้ามแต่ละครั้ง ×0.85 ทำแต่ละครั้ง ×1.05 บันทึกไว้ ×1.1 ขอบ 0.5–1.5
- ตัวคูณการปัด persona ×0.5 / ×1.2 / ×1.5 ขอบ 0.2–2.0 (สูตรของทีม)
ไม่เก็บข้อมูลส่วนบุคคลของลูกค้าจริง
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from .config import PROJECT_DIR
from .personas import apply_swipe

MEMORY_DIR = PROJECT_DIR / "var" / "memory"
OUTCOME_SCORE = {"above": 90, "within": 60, "below": 25}
VALID_TYPES = {"done", "skip", "result", "save_idea", "swipe", "search", "note"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _path(shop_id: str) -> Path:
    if not _SAFE_ID.match(shop_id):
        raise ValueError("shop_id ใช้ได้เฉพาะ A-Z a-z 0-9 _ -")
    return MEMORY_DIR / f"{shop_id}.json"


def load(shop_id: str) -> list[dict]:
    p = _path(shop_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))["events"]
    except (OSError, json.JSONDecodeError, KeyError):
        return []


def record(shop_id: str, event: dict) -> dict:
    if event.get("type") not in VALID_TYPES:
        raise ValueError(f"type ต้องเป็นหนึ่งใน {sorted(VALID_TYPES)}")
    event = {k: v for k, v in event.items() if k in {"type", "content_id", "outcome", "score", "archetype",
                                                     "answer", "text", "channel"}}
    if "text" in event:
        event["text"] = str(event["text"])[:200]
    event["ts"] = time.time()
    events = load(shop_id) + [event]
    p = _path(shop_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"shop_id": shop_id, "events": events[-2000:]}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)  # เขียนแบบ atomic
    return event


def evidence(n: int, avg: float) -> float:
    return (n * avg + 3 * 50) / (n + 3)


def summarize(events: list[dict]) -> dict:
    results: dict[str, list[float]] = defaultdict(list)
    interest: dict[str, float] = defaultdict(lambda: 1.0)
    swipes: dict[str, float] = {}
    channels: Counter = Counter()
    words: Counter = Counter()
    done = skip = 0
    for e in events:
        cid, t = e.get("content_id"), e["type"]
        if t == "result" and cid:
            score = e.get("score")
            if score is None:
                score = OUTCOME_SCORE.get(e.get("outcome", ""), None)
            if score is not None:
                results[cid].append(float(max(0, min(100, score))))
        elif t == "done" and cid:
            done += 1
            interest[cid] = min(1.5, interest[cid] * 1.05)
        elif t == "skip" and cid:
            skip += 1
            interest[cid] = max(0.5, interest[cid] * 0.85)
        elif t == "save_idea" and cid:
            interest[cid] = min(1.5, interest[cid] * 1.1)
        elif t == "swipe" and e.get("archetype") and e.get("answer"):
            swipes[e["archetype"]] = apply_swipe(swipes.get(e["archetype"], 1.0), e["answer"])
        if e.get("channel"):
            channels[e["channel"]] += 1
        if t in ("search", "note") and e.get("text"):
            words.update(w for w in re.split(r"\s+", e["text"]) if len(w) > 1)
    ev = {cid: {"n": len(v), "avg": round(sum(v) / len(v), 1), "evidence": round(evidence(len(v), sum(v) / len(v)), 1)}
          for cid, v in results.items()}
    return {"evidence": ev, "interest": dict(interest), "swipes": swipes, "done": done, "skipped": skip,
            "top_channels": [c for c, _ in channels.most_common(3)],
            "interests": [w for w, _ in words.most_common(10)], "events": len(events)}
