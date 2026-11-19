"""ตรวจความพร้อมของเครื่องนี้สำหรับ R1 และ R10 (ใช้กฎบัญชีทีม: anthropic.claude-sonnet-5 @ ap-southeast-1)

    cd prototype && uv run --with fastapi --with uvicorn python scripts/check_setup.py

ไม่แก้ไฟล์ใด ๆ แค่ตรวจ
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    print("=== R1 · เครื่องมือพัฒนา ===")
    check("Python 3.11 ขึ้นไป", sys.version_info >= (3, 11), sys.version.split()[0])
    for pkg in ["fastapi", "uvicorn", "pydantic", "boto3", "strands", "pytest"]:
        try:
            importlib.import_module(pkg)
            check(f"แพ็กเกจ {pkg}", True)
        except ImportError:
            check(f"แพ็กเกจ {pkg}", False, "รันผ่าน uv: uv run --with fastapi --with uvicorn ...")
    check("โฟลเดอร์ .kiro/steering ของทีม", (ROOT.parent / ".kiro" / "steering" / "product.md").exists())
    print("ℹ️  Kiro IDE: ตรวจด้วยมือ — เปิดโฟลเดอร์นี้ใน Kiro, กด Trust, แล้วถามในแชตให้สรุป steering")

    print("\n=== R10 · AWS และ Bedrock ===")
    if shutil.which("aws"):
        print("✅ AWS CLI")
    else:
        print("⚠️  ไม่พบ AWS CLI (ไม่บังคับ แต่ใช้ตั้งค่าได้ง่าย: aws configure หรือ aws sso login)")

    try:
        import boto3
    except ImportError:
        check("boto3", False)
        return summary()

    from belka.config import ALLOWED_MODEL_ID, ALLOWED_REGION, config_refused, get_settings

    settings = get_settings()
    refused = config_refused(settings)
    if not check("ค่าตั้งตรงกฎบัญชีทีม", refused is None, refused or f"{settings.model_id} @ {settings.region}"):
        print(f"   แก้ backend/.env ให้ใช้ BELKA_MODEL_ID={ALLOWED_MODEL_ID} และ BELKA_REGION={ALLOWED_REGION}")
        return summary()

    session = boto3.Session()
    try:
        ident = session.client("sts", region_name=settings.region).get_caller_identity()
        check("ล็อกอิน AWS (SSO)", True, ident["Arn"])
    except Exception as exc:  # noqa: BLE001
        check("ล็อกอิน AWS (SSO)", False, f"{type(exc).__name__}: รัน aws sso login")
        return summary()

    try:
        resp = session.client("bedrock-runtime", region_name=settings.region).converse(
            modelId=settings.model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the word READY only."}]}],
            inferenceConfig={"maxTokens": 10},
        )
        text = resp["output"]["message"]["content"][0]["text"].strip()
        check("เรียกโมเดลได้", True, f"{settings.model_id} ตอบว่า {text!r}")
    except Exception as exc:  # noqa: BLE001
        check("เรียกโมเดลได้", False, f"{type(exc).__name__}: {str(exc)[:160]}")
    return summary()


def summary() -> int:
    failed = [n for n, ok, _ in results if not ok]
    print("\n=== สรุป ===")
    print("✅ เครื่องนี้พร้อม" if not failed else "❌ ยังไม่พร้อม: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
