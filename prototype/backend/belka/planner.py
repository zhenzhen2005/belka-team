"""สร้างแผนสัปดาห์: Trust Engine กำหนดช่องงาน → เอเจนต์เขียนเนื้อหา → ตรวจทุกข้อ → แผนสำรองถ้าจำเป็น.

ลำดับการทำงาน
1. build_slots: โค้ดเลือกช่องทาง วัน เวลา เวลาที่ใช้ (AI ไม่ยุ่งกับตัวเลข)
2. เรียกเอเจนต์ภายในเวลาที่กำหนด ลองใหม่ได้ถ้าตอบผิดรูปแบบ
3. ตรวจรูปแบบและ red-line ทุกงานซ้ำด้วยโค้ด
4. งานที่ไม่ผ่าน ใช้เนื้อหาสำรองจาก Trust Engine แทน ร้านได้แผนครบ 3 งานเสมอ
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from typing import Callable

from .agent import AgentOutput, build_user_prompt
from .config import config_refused, get_settings
from .models import CHANNEL_TH, PlanTask, ShopProfile, Slot, WeeklyPlan
from .redline import check_redline
from .trust_engine import build_slots, content_id, fallback_task

log = logging.getLogger("belka.planner")
_executor = ThreadPoolExecutor(max_workers=4)

Runner = Callable[[str], AgentOutput]


def extract_json(text: str) -> dict | None:
    """ดึง JSON ก้อนแรกจากคำตอบของโมเดล (รองรับกรณีห่อด้วย ```json)."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _valid_item(item: dict) -> bool:
    try:
        steps = item["steps"]
        return (
            isinstance(item["title"], str) and 0 < len(item["title"].strip()) <= 80
            and isinstance(item["why"], str) and 0 < len(item["why"].strip()) <= 300
            and isinstance(item["caption"], str) and 0 < len(item["caption"].strip()) <= 300
            and isinstance(steps, list) and 1 <= len(steps) <= 4
            and all(isinstance(s, str) and s.strip() for s in steps)
        )
    except (KeyError, TypeError):
        return False


def merge_ai_tasks(data: dict | None, slots: list[Slot], profile: ShopProfile) -> list[PlanTask]:
    """รวมคำตอบของ AI เข้ากับช่องงาน ช่องไหนไม่ผ่านใช้แผนสำรองแทน."""
    by_slot: dict[int, dict] = {}
    if data and isinstance(data.get("tasks"), list):
        for item in data["tasks"]:
            if isinstance(item, dict) and isinstance(item.get("slot"), int):
                by_slot.setdefault(item["slot"], item)

    tasks: list[PlanTask] = []
    for slot in slots:
        item = by_slot.get(slot.slot)
        if item and _valid_item(item):
            text_to_check = " ".join([item["title"], item["why"], item["caption"], *item["steps"]])
            if check_redline(text_to_check).passed:
                tasks.append(
                    PlanTask(
                        slot=slot.slot,
                        kind=slot.kind,
                        channel=slot.channel,
                        channel_label=CHANNEL_TH[slot.channel],
                        date=slot.date,
                        day_label=slot.day_label,
                        time_window=slot.time_window,
                        minutes=slot.minutes,
                        title=item["title"].strip(),
                        why=item["why"].strip(),
                        steps=[s.strip() for s in item["steps"]][:3],
                        caption=item["caption"].strip(),
                        redline=check_redline(item["caption"]),
                        source="ai",
                        content_id=content_id(slot.kind),
                    )
                )
                continue
            log.warning("slot %s ไม่ผ่าน red-line ใช้แผนสำรอง", slot.slot)
        tasks.append(fallback_task(slot, profile))
    return tasks


def _call_with_deadline(runner: Runner, prompt: str, timeout_s: float) -> AgentOutput | None:
    future = _executor.submit(runner, prompt)
    try:
        return future.result(timeout=max(timeout_s, 0.1))
    except FutureTimeout:
        log.warning("เอเจนต์ตอบช้าเกิน %.1f วินาที ใช้แผนสำรอง", timeout_s)
    except Exception as exc:  # noqa: BLE001 - ร้านต้องได้แผนเสมอ
        log.warning("เรียกเอเจนต์ไม่สำเร็จ: %s", exc)
    return None


def make_plan(
    profile: ShopProfile,
    today: date | None = None,
    runner: Runner | None = None,
    mode: str | None = None,
) -> WeeklyPlan:
    settings = get_settings()
    mode = mode or settings.mode
    started = time.monotonic()
    slots = build_slots(profile, today)

    tool_calls: list[dict] = []
    tasks: list[PlanTask] | None = None
    notice = None

    if mode == "ai" and runner is None:
        refused = config_refused(settings)
        if refused:
            log.warning("cause=config_refused %s ไม่เรียก Bedrock ใช้แผนสำรอง", refused)
            mode_refused = True
        else:
            from .agent import run_agent

            runner = run_agent
            mode_refused = False
    else:
        mode_refused = False

    if mode == "ai" and not mode_refused:
        prompt = build_user_prompt(profile, slots)
        deadline = started + settings.ai_timeout_s
        for attempt in range(1, settings.ai_attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            output = _call_with_deadline(runner, prompt, remaining)
            if output is None:
                break
            tool_calls += output.tool_calls
            data = extract_json(output.text)
            if data is None:
                log.warning("รอบที่ %s: คำตอบไม่ใช่ JSON", attempt)
                continue
            tasks = merge_ai_tasks(data, slots, profile)
            break

    if tasks is None:
        tasks = [fallback_task(s, profile) for s in slots]
        if mode == "ai":
            notice = "ตอนนี้ใช้แผนมาตรฐานของ Belka ไปก่อน แผนเฉพาะร้านจะกลับมาเมื่อระบบพร้อม"

    sources = {t.source for t in tasks}
    source = sources.pop() if len(sources) == 1 else "mixed"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info("plan source=%s tool_calls=%s elapsed=%sms", source, len(tool_calls), elapsed_ms)
    return WeeklyPlan(
        profile=profile,
        week=profile.week,
        tasks=tasks,
        source=source,
        notice=notice,
        ai_tool_calls=len(tool_calls),
        elapsed_ms=elapsed_ms,
    )
