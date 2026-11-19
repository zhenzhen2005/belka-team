"""อ่านค่าตั้งจาก environment หรือไฟล์ backend/.env (ไม่ต้องติดตั้งแพ็กเกจเพิ่ม)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


# กฎบัญชีทีม (.kiro/steering/aws.md และ requirements 12.1–12.2 ของ spec weekly-plan)
ALLOWED_REGION = "ap-southeast-1"
ALLOWED_MODEL_ID = "anthropic.claude-sonnet-5"


@dataclass(frozen=True)
class Settings:
    mode: str  # "ai" = ใช้เอเจนต์บน Bedrock, "fallback" = ใช้ Trust Engine อย่างเดียว
    region: str
    model_id: str
    ai_timeout_s: float
    ai_attempts: int


def get_settings() -> Settings:
    return Settings(
        mode=os.getenv("BELKA_MODE", "ai").lower(),
        region=os.getenv("BELKA_REGION", ALLOWED_REGION),
        model_id=os.getenv("BELKA_MODEL_ID", ALLOWED_MODEL_ID),
        ai_timeout_s=float(os.getenv("BELKA_AI_TIMEOUT", "8")),
        ai_attempts=int(os.getenv("BELKA_AI_ATTEMPTS", "2")),
    )


def config_refused(settings: Settings) -> str | None:
    """คืนเหตุผลถ้าค่าตั้งผิดกฎบัญชีทีม (ห้ามเรียก Bedrock) หรือ None ถ้าใช้ได้."""
    if settings.model_id.startswith(("global.", "apac.")):
        return f"model ID {settings.model_id} ส่งไปรีเจียนอื่น บัญชีทีมจะปฏิเสธ"
    if settings.model_id != ALLOWED_MODEL_ID:
        return f"model ID ต้องเป็น {ALLOWED_MODEL_ID}"
    if settings.region != ALLOWED_REGION:
        return f"รีเจียนต้องเป็น {ALLOWED_REGION}"
    return None
