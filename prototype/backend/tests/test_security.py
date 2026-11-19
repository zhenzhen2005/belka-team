"""เทสต์ชั้นป้องกัน ไม่ต้องใช้ fastapi/AWS: เรียก ASGI ตรง ๆ"""
import asyncio
import json

from belka.security import AI_PATHS, SecurityMiddleware, SlidingLimiter, host_of


async def inner_app(scope, receive, send):
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": json.dumps({"n": len(body)}).encode()})


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def call(mw, method="GET", path="/", headers=None, body=b"", chunks=None):
    h = {"host": "127.0.0.1:8000"}
    h.update(headers or {})
    if method != "GET" and path.startswith("/api/") and "content-type" not in h:
        h["content-type"] = "application/json"
    scope = {"type": "http", "method": method, "path": path, "headers": [(k.encode(), v.encode()) for k, v in h.items()]}
    parts = chunks if chunks is not None else [body]
    queue = [{"type": "http.request", "body": c, "more_body": i < len(parts) - 1} for i, c in enumerate(parts)]
    out = []

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(m): out.append(m)

    asyncio.run(mw(scope, receive, send))
    start = next(m for m in out if m["type"] == "http.response.start")
    hdrs = {k.decode(): v.decode() for k, v in start["headers"]}
    body_out = b"".join(m.get("body", b"") for m in out if m["type"] == "http.response.body")
    return start["status"], hdrs, body_out


def mk(**kw):
    return SecurityMiddleware(inner_app, **kw)


# ---------- Host ----------
def test_host_parsing():
    assert host_of("127.0.0.1:8000") == "127.0.0.1"
    assert host_of("LocalHost:8001") == "localhost"
    assert host_of("[::1]:8000") == "[::1]"
    assert host_of("evil.example") == "evil.example"


def test_allowed_hosts_pass_and_others_rejected():
    for host in ["127.0.0.1:8000", "localhost:8001", "[::1]:8000", "127.0.0.1"]:
        assert call(mk(), headers={"host": host})[0] == 200
    for host in ["evil.example", "evil.example:8000", "127.0.0.1.evil.example", "", "10.0.0.5:8000"]:
        assert call(mk(), headers={"host": host})[0] == 400


# ---------- Origin / CSRF ----------
def test_same_origin_post_ok_and_no_origin_ok():
    mw = mk()
    assert call(mw, "POST", "/api/redline", {"origin": "http://127.0.0.1:8000"}, b"{}")[0] == 200
    assert call(mw, "POST", "/api/redline", {}, b"{}")[0] == 200   # curl / สคริปต์ ไม่ส่ง Origin


def test_cross_origin_post_blocked():
    mw = mk()
    for origin in ["https://evil.example", "http://evil.example", "http://127.0.0.1:9999", "null", "https://127.0.0.1:8000"]:
        assert call(mw, "POST", "/api/redline", {"origin": origin}, b"{}")[0] == 403, origin
    assert call(mw, "POST", "/api/redline", {"sec-fetch-site": "cross-site"}, b"{}")[0] == 403


def test_post_must_be_json():
    mw = mk()
    assert call(mw, "POST", "/api/redline", {"content-type": "text/plain"}, b"{}")[0] == 415
    assert call(mw, "POST", "/api/redline", {"content-type": "application/x-www-form-urlencoded"}, b"a=b")[0] == 415
    assert call(mw, "POST", "/api/redline", {"content-type": "application/json; charset=utf-8"}, b"{}")[0] == 200


# ---------- ขนาด ----------
def test_body_size_limits():
    mw = mk(max_body=100)
    assert call(mw, "POST", "/api/redline", body=b"x" * 100)[0] == 200
    assert call(mw, "POST", "/api/redline", {"content-length": "101"}, b"x")[0] == 413          # บอกขนาดตรง ๆ
    assert call(mw, "POST", "/api/redline", chunks=[b"x" * 60, b"x" * 60])[0] == 413             # ส่งทีละชิ้น
    assert call(mw, "POST", "/api/redline", {"content-length": "abc"}, b"x")[0] == 400


# ---------- จำกัดจำนวนครั้ง ----------
def test_sliding_limiter_window():
    c = Clock()
    lim = SlidingLimiter(2, 60, c)
    assert lim.allow() == (True, 0) and lim.allow() == (True, 0)
    ok, wait = lim.allow()
    assert not ok and 1 <= wait <= 61
    assert not lim.allow()[0]          # ครั้งที่ถูกปฏิเสธไม่ถูกนับ ไม่ทำให้ติดนานขึ้น
    c.t += 61
    assert lim.allow()[0]


def test_ai_per_minute_limit_and_reset():
    c = Clock()
    mw = mk(ai_per_min=3, ai_per_day=100, clock=c)
    for _ in range(3):
        assert call(mw, "POST", "/api/ask", body=b"{}")[0] == 200
    status, hdrs, body = call(mw, "POST", "/api/ask", body=b"{}")
    assert status == 429 and "retry-after" in hdrs and "ถี่เกินไป" in json.loads(body)["detail"]
    c.t += 61
    assert call(mw, "POST", "/api/ask", body=b"{}")[0] == 200


def test_ai_daily_cap():
    c = Clock()
    mw = mk(ai_per_min=50, ai_per_day=4, clock=c)
    for i in range(4):
        assert call(mw, "POST", "/api/plan", body=b"{}")[0] == 200
        c.t += 61
    status, _, body = call(mw, "POST", "/api/plan", body=b"{}")
    assert status == 429 and "ครบแล้ว" in json.loads(body)["detail"]
    c.t += 86_400
    assert call(mw, "POST", "/api/plan", body=b"{}")[0] == 200


def test_ai_limit_does_not_block_calculators_or_static():
    mw = mk(ai_per_min=1, ai_per_day=1, other_per_min=1000)
    assert call(mw, "POST", "/api/ask", body=b"{}")[0] == 200
    assert call(mw, "POST", "/api/ask", body=b"{}")[0] == 429
    assert call(mw, "POST", "/api/calc/menu", body=b"{}")[0] == 200
    assert call(mw, "GET", "/")[0] == 200
    assert {"/api/plan", "/api/ask", "/api/menu/import"} == set(AI_PATHS)


def test_rejected_requests_do_not_spend_ai_quota():
    mw = mk(ai_per_min=2, ai_per_day=100)
    for _ in range(5):
        call(mw, "POST", "/api/ask", {"origin": "https://evil.example"}, b"{}")      # 403 ก่อนถึงตัวนับ
        call(mw, "POST", "/api/ask", {"host": "evil.example"}, b"{}")                # 400 ก่อนถึงตัวนับ
    assert call(mw, "POST", "/api/ask", body=b"{}")[0] == 200


# ---------- header ----------
def test_security_headers_on_all_responses():
    mw = mk()
    for res in [call(mw, "GET", "/"), call(mw, "GET", "/api/health"), call(mw, "GET", "/", {"host": "evil.example"})]:
        h = res[1]
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "connect-src 'self'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and "camera=(self)" in h["permissions-policy"]
    assert call(mw, "GET", "/api/health")[1]["cache-control"] == "no-store"
    assert "cache-control" not in call(mw, "GET", "/")[1]


def test_websocket_closed():
    out = []
    async def send(m): out.append(m)
    async def receive(): return {}
    asyncio.run(mk()({"type": "websocket", "path": "/", "headers": []}, receive, send))
    assert out == [{"type": "websocket.close", "code": 1008}]
