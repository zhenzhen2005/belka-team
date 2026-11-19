"""ชั้นป้องกันของ Belka API (ASGI ล้วน ไม่ต้องติดตั้งแพ็กเกจเพิ่ม).

แอปนี้รันเฉพาะ 127.0.0.1 ตาม D1 และไม่มีระบบล็อกอิน จึงต้องกันสิ่งที่ยังเข้าถึงเครื่องเราได้ผ่านเบราว์เซอร์:
1. Host ต้องเป็น 127.0.0.1 / localhost / [::1]            กัน DNS rebinding (เว็บอื่นหลอกให้เบราว์เซอร์ยิงเข้าเครื่องเรา)
2. คำขอที่เปลี่ยนข้อมูล (POST ฯลฯ) ต้องมี Origin ตรงกับ Host  กัน CSRF จากเว็บอื่น
3. POST ต้องเป็น application/json                         กัน "simple request" ที่ไม่ผ่าน preflight
4. จำกัดขนาด body                                           กันส่งก้อนใหญ่จนเครื่อง/ค่า AI พัง
5. จำกัดจำนวนครั้งเรียก AI ต่อนาทีและต่อวัน                  กันค่า Bedrock ของบัญชีทีมบวม
6. security headers (CSP ฯลฯ)                                จำกัดว่าหน้าเว็บส่งข้อมูลไปไหนได้ ลดผลของ XSS
ทุกการปฏิเสธคืนข้อความไทยสั้น ๆ ที่ไม่เผยรายละเอียดภายใน
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from typing import Callable

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
AI_PATHS = frozenset({"/api/plan", "/api/ask", "/api/menu/import"})
MAX_BODY_BYTES = 6_000_000    # รูปเมนูย่อแล้วไม่เกิน ~3.5 MB (base64 ~4.7 MB) + ส่วนอื่น

# Google Fonts เป็นภายนอกอย่างเดียวที่หน้าเว็บโหลด ที่เหลือต้องมาจากเซิร์ฟเวอร์เราเท่านั้น
# 'unsafe-inline' ของ script จำเป็นเพราะหน้าเว็บเป็นไฟล์เดียวที่มีสคริปต์ฝังอยู่ (ข้อจำกัดที่รู้ ดูเอกสารอธิบาย)
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
SECURITY_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(self), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
]


class SlidingLimiter:
    """นับครั้งในช่วงเวลาหนึ่ง (หน่วยความจำในโปรเซสเดียว พอสำหรับแอปบนเครื่องเดียว)."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: deque[float] = deque()

    def allow(self) -> tuple[bool, int]:
        """คืน (ผ่านไหม, วินาทีที่ต้องรอถ้าไม่ผ่าน). ครั้งที่ถูกปฏิเสธไม่ถูกนับ."""
        now = self.clock()
        while self._hits and now - self._hits[0] >= self.window_s:
            self._hits.popleft()
        if len(self._hits) >= self.limit:
            return False, max(1, int(self.window_s - (now - self._hits[0])) + 1)
        self._hits.append(now)
        return True, 0


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, default)))
    except ValueError:
        return default


def host_of(value: str) -> str:
    """ตัดพอร์ตออกจากค่า Host (รองรับ IPv6 แบบ [::1]:8000)."""
    value = value.strip().lower()
    if value.startswith("["):
        return value[: value.find("]") + 1] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class _TooLarge(Exception):
    pass


class SecurityMiddleware:
    def __init__(self, app, max_body: int = MAX_BODY_BYTES, ai_per_min: int | None = None,
                 ai_per_day: int | None = None, other_per_min: int | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.app, self.max_body = app, max_body
        self.ai_min = SlidingLimiter(ai_per_min or _env_int("BELKA_AI_PER_MIN", 12), 60, clock)
        self.ai_day = SlidingLimiter(ai_per_day or _env_int("BELKA_AI_PER_DAY", 300), 86_400, clock)
        self.other_min = SlidingLimiter(other_per_min or _env_int("BELKA_API_PER_MIN", 240), 60, clock)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":      # แอปนี้ไม่ใช้ websocket
                await send({"type": "websocket.close", "code": 1008})
            else:
                await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        method, path = scope["method"], scope["path"]

        deny = self._check(headers, method, path)
        if deny:
            status, message, extra = deny
            await self._respond(send, status, message, path, extra)
            return

        started = False
        seen = 0

        async def guarded_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_body:
                    raise _TooLarge
            return message

        async def guarded_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message = dict(message)
                message["headers"] = _with_headers(message.get("headers", []), path)
            await send(message)

        try:
            await self.app(scope, guarded_receive, guarded_send)
        except _TooLarge:
            if not started:
                await self._respond(send, 413, "ข้อมูลที่ส่งมาใหญ่เกินไป", path, [])

    # ---- ตรวจคำขอ คืน None ถ้าผ่าน หรือ (สถานะ, ข้อความ, header เพิ่ม) ----
    def _check(self, headers: dict, method: str, path: str):
        if host_of(headers.get("host", "")) not in ALLOWED_HOSTS:
            return 400, "ไม่อนุญาตให้เข้าด้วยชื่อโฮสต์นี้", []
        if method not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None:
                o = origin.lower()
                if not (o.startswith("http://") and o[len("http://"):] == headers.get("host", "").lower()):
                    return 403, "คำขอนี้มาจากหน้าเว็บอื่น ไม่อนุญาต", []
            if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
                return 403, "คำขอนี้มาจากหน้าเว็บอื่น ไม่อนุญาต", []
            if path.startswith("/api/") and not headers.get("content-type", "").lower().startswith("application/json"):
                return 415, "ต้องส่งข้อมูลเป็น JSON", []
        try:
            if int(headers.get("content-length", "0") or 0) > self.max_body:
                return 413, "ข้อมูลที่ส่งมาใหญ่เกินไป", []
        except ValueError:
            return 400, "คำขอไม่ถูกต้อง", []
        if path.startswith("/api/"):
            if path in AI_PATHS:
                ok, wait = self.ai_min.allow()
                if not ok:
                    return 429, "เรียก AI ถี่เกินไป รอสักครู่แล้วลองใหม่", [(b"retry-after", str(wait).encode())]
                ok, wait = self.ai_day.allow()
                if not ok:
                    return 429, "ใช้โควตา AI ของวันนี้ครบแล้ว", [(b"retry-after", str(wait).encode())]
            else:
                ok, wait = self.other_min.allow()
                if not ok:
                    return 429, "ส่งคำขอถี่เกินไป รอสักครู่แล้วลองใหม่", [(b"retry-after", str(wait).encode())]
        return None

    async def _respond(self, send, status: int, message: str, path: str, extra: list):
        body = json.dumps({"detail": message}, ensure_ascii=False).encode()
        headers = _with_headers([(b"content-type", b"application/json; charset=utf-8"),
                                 (b"content-length", str(len(body)).encode()), *extra], path)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def _with_headers(existing: list, path: str) -> list:
    have = {k.lower() for k, _ in existing}
    out = list(existing) + [(k, v) for k, v in SECURITY_HEADERS if k not in have]
    if path.startswith("/api/") and b"cache-control" not in have:
        out.append((b"cache-control", b"no-store"))
    return out
