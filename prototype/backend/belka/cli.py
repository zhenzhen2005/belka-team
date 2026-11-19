"""ทดสอบเอเจนต์จากเทอร์มินัล (ใช้ยืนยัน R11).

python -m belka.cli redline   เอเจนต์เขียนแคปชันที่มีคำต้องห้าม ต้องเห็นเครื่องมือจับได้แล้วเขียนใหม่
python -m belka.cli plan      สร้างแผนสัปดาห์ของร้านตัวอย่าง
python -m belka.cli plan --fallback   สร้างแผนโดยไม่เรียก AI (ไม่ต้องมี AWS)
python -m belka.cli menu tests/fixtures/sample_menu.jpg   อ่านเมนูจากรูปด้วย Bedrock (ต้อง aws sso login ก่อน)
"""
from __future__ import annotations

import argparse
import logging
import sys

from .models import ShopProfile

SAMPLE = ShopProfile(shop_type="drink", customer="workers", channels=["facebook", "delivery"])


def cmd_redline() -> int:
    from .agent import run_agent

    prompt = (
        "เขียนแคปชัน Facebook 1 ข้อความ โปรโมตกาแฟเย็นของร้าน "
        "โดยเริ่มจากประโยค 'การันตีอร่อยที่สุดในย่าน' ส่งเข้า check_redline ก่อน "
        'แล้วตอบเป็น JSON {"caption": "..."}'
    )
    out = run_agent(prompt)
    print("\n=== การเรียกเครื่องมือ ===")
    for i, call in enumerate(out.tool_calls, 1):
        print(f"{i}. check_redline passed={call['passed']} :: {call['text']}")
    print("\n=== คำตอบสุดท้ายของเอเจนต์ ===")
    print(out.text)
    ok = len(out.tool_calls) >= 2 and not out.tool_calls[0]["passed"] and out.tool_calls[-1]["passed"]
    print("\nR11:", "✅ ผ่าน" if ok else "❌ ยังไม่ผ่าน (ต้องเห็นรอบแรกไม่ผ่าน และรอบสุดท้ายผ่าน)")
    return 0 if ok else 1


def cmd_plan(fallback: bool) -> int:
    from .planner import make_plan

    plan = make_plan(SAMPLE, mode="fallback" if fallback else None)
    print(f"source={plan.source} tool_calls={plan.ai_tool_calls} elapsed={plan.elapsed_ms}ms")
    if plan.notice:
        print("notice:", plan.notice)
    for t in plan.tasks:
        mark = "✓" if t.redline.passed else "✗"
        print(f"\n[{t.slot}] {t.day_label} {t.time_window} · {t.channel_label} · {t.minutes} นาที · {t.source}")
        print(f"    {t.title}")
        print(f"    ทำไม: {t.why}")
        for step in t.steps:
            print(f"     - {step}")
        print(f"    แคปชัน {mark}: {t.caption}")
    return 0


def cmd_menu(path: str) -> int:
    import base64
    from pathlib import Path

    from .menu_import import MenuImportError, import_menu

    try:
        res = import_menu(base64.b64encode(Path(path).read_bytes()).decode())
    except (OSError, MenuImportError) as exc:
        print("❌", exc)
        return 1
    print(f"source={res.source} items={len(res.items)} unpriced={len(res.unpriced)} dropped={res.dropped}")
    for it in res.items:
        print(f"  {it['name']}  {it['price']:g} บาท")
    for name in res.unpriced:
        print(f"  {name}  (อ่านราคาไม่ได้)")
    if res.message:
        print("message:", res.message)
    return 0 if res.source == "ai" else 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="belka")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("redline")
    plan = sub.add_parser("plan")
    plan.add_argument("--fallback", action="store_true")
    menu = sub.add_parser("menu")
    menu.add_argument("image")
    args = parser.parse_args()
    if args.cmd == "redline":
        return cmd_redline()
    if args.cmd == "menu":
        return cmd_menu(args.image)
    return cmd_plan(args.fallback)


if __name__ == "__main__":
    sys.exit(main())
