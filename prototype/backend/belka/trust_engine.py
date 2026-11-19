"""Trust Engine: ส่วนที่ตัดสินใจด้วยโค้ดล้วน ตรวจสอบได้ และไม่เรียก AI.

หน้าที่:
1. build_slots  — เลือกช่องทาง วัน เวลา และเวลาที่ใช้ของงานทั้ง 3 งาน
2. fallback_task — เนื้อหาสำรองของแต่ละงาน ใช้เมื่อ AI ตอบไม่ได้ ช้าเกิน หรือไม่ผ่าน red-line
   ร้านจึงได้แผนทุกครั้ง (ความเสี่ยง R1 ใน Content Document)

ค่าเวลาและลำดับความสำคัญในไฟล์นี้เป็นค่าเริ่มต้นของทีม ต้องตรวจกับร้านจริงช่วง Pilot
"""
from __future__ import annotations

from datetime import date, timedelta

from .models import CHANNEL_TH, PlanTask, ShopProfile, Slot
from .redline import check_redline

DAY_OFFSETS = [0, 2, 4]  # งานแรกวันนี้ เว้นวันละหนึ่งวัน รวม 3 งานต่อสัปดาห์
WEEKDAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

# ช่วงเวลาที่ลูกค้าแต่ละกลุ่มมักว่างดูมือถือ (ค่าเริ่มต้น ตรวจช่วง Pilot)
TIME_WINDOW = {
    "workers": "11:00–12:00",
    "students": "15:00–17:00",
    "locals": "16:00–18:00",
    "tourists": "09:00–11:00",
}
MOMENT = {
    "workers": "ช่วงพักเที่ยง",
    "students": "หลังเลิกเรียน",
    "locals": "ทุกครั้งที่ผ่านหน้าร้าน",
    "tourists": "ระหว่างทางเที่ยว",
}
ITEM = {"drink": "เครื่องดื่ม", "bakery": "ขนม", "food": "อาหาร"}

# ประเภทงาน: ช่องทาง เป้าหมาย (ส่งให้ AI) และเวลาที่ใช้ (นาที)
KINDS: dict[str, dict] = {
    "maps_create": {"channel": "google_maps", "minutes": 10, "goal": "ร้านยังไม่มีหมุด ทำให้คนที่ค้นหาร้านแถวนี้เจอร้าน"},
    "maps_photos": {"channel": "google_maps", "minutes": 5, "goal": "ทำให้โปรไฟล์ร้านบน Google Maps ดูน่าแวะด้วยรูปใหม่"},
    "maps_reviews": {"channel": "google_maps", "minutes": 5, "goal": "ตอบรีวิวลูกค้าเพื่อแสดงว่าร้านใส่ใจ"},
    "maps_menu": {"channel": "google_maps", "minutes": 10, "goal": "ลงเมนูและราคาให้ชัดบน Google Maps ให้ลูกค้าตัดสินใจได้ก่อนมา"},
    "maps_faq": {"channel": "google_maps", "minutes": 5, "goal": "ใส่เวลาเปิดและข้อมูลที่ลูกค้าถามบ่อยบน Google Maps ให้ครบ"},
    "line_broadcast": {"channel": "line", "minutes": 5, "goal": "ชวนลูกค้าเดิมใน LINE OA ให้กลับมาร้านหรือสั่งตรง"},
    "line_create": {"channel": "line", "minutes": 10, "goal": "เปิด LINE OA เป็นช่องทางที่ร้านเป็นเจ้าของเอง"},
    "line_newmenu": {"channel": "line", "minutes": 5, "goal": "ให้ลูกค้าเดิมใน LINE ได้ลองเมนูใหม่หรือเมนูแนะนำก่อนคนอื่น"},
    "line_thanks": {"channel": "line", "minutes": 5, "goal": "ขอบคุณลูกค้าเดิมและขอความเห็นสั้น ๆ เพื่อปรับร้าน"},
    "line_poll": {"channel": "line", "minutes": 5, "goal": "ถามลูกค้าใน LINE ว่าอยากได้เมนูแบบไหน ให้ลูกค้ามีส่วนร่วม"},
    "fb_post": {"channel": "facebook", "minutes": 5, "goal": "โพสต์ให้คนในย่านเห็นร้านสม่ำเสมอ"},
    "fb_behind": {"channel": "facebook", "minutes": 10, "goal": "เล่าเบื้องหลังร้าน ให้ลูกค้าเห็นความตั้งใจและไว้ใจร้าน"},
    "fb_qa": {"channel": "facebook", "minutes": 10, "goal": "ตอบคำถามที่ลูกค้าถามบ่อยในโพสต์เดียว"},
    "fb_community": {"channel": "facebook", "minutes": 10, "goal": "แนะนำร้านในกลุ่ม Facebook ของชุมชนแถวร้าน"},
    "delivery_card": {"channel": "delivery", "minutes": 10, "goal": "ชวนลูกค้าจากแอปเดลิเวอรีให้มาหน้าร้านหรือสั่งตรงครั้งหน้า (ลดการพึ่งค่า GP)"},
    "delivery_menu": {"channel": "delivery", "minutes": 10, "goal": "อัปเดตรูปและคำอธิบายเมนูในแอปเดลิเวอรีให้น่าสั่ง"},
    "storefront_sign": {"channel": "storefront", "minutes": 10, "goal": "ให้คนที่เดินผ่านหน้าร้านตัดสินใจแวะง่ายขึ้น"},
    "storefront_staffpick": {"channel": "storefront", "minutes": 10, "goal": "ตั้งป้ายเมนูที่พนักงานแนะนำ ช่วยลูกค้าใหม่ที่เลือกไม่ถูก"},
}

# ประเภทงานของแผนสัปดาห์ → รหัสคอนเทนต์ในคลัง 34 แบบ (ใช้บันทึกความจำและหลักฐาน)
KIND_CONTENT = {"maps_create": "C1", "maps_photos": "C1", "maps_reviews": "B1", "maps_menu": "A9", "maps_faq": "B3",
                "line_broadcast": "D1", "line_create": "D1", "line_newmenu": "D4", "line_thanks": "D3", "line_poll": "A8",
                "fb_post": "A2", "fb_behind": "A3", "fb_qa": "A6", "fb_community": "A4",
                "delivery_card": "C2", "delivery_menu": "C4", "storefront_sign": "C2", "storefront_staffpick": "A7"}

# งานแต่ละช่องทาง เรียงตามลำดับความสำคัญ สัปดาห์ถัดไปจะหมุนไปงานที่ยังไม่ได้ทำ (ไม่ซ้ำสัปดาห์ก่อน)
POOLS = {
    "google_maps": ["maps_photos", "maps_reviews", "maps_menu", "maps_faq"],
    "line": ["line_broadcast", "line_newmenu", "line_thanks", "line_poll"],
    "facebook": ["fb_post", "fb_behind", "fb_qa", "fb_community"],
    "delivery": ["delivery_card", "delivery_menu"],
    "storefront": ["storefront_sign", "storefront_staffpick"],
}
LIB_PREFIX = "lib:"  # งานที่มาจากไอเดียที่เจ้าของร้านเลือกเอง เช่น lib:G3
LIB_CHANNEL = {"LINE": "line", "Facebook": "facebook", "Google Maps": "google_maps", "Delivery app": "delivery",
               "Instagram": "instagram", "TikTok": "tiktok"}
CONTENT_KIND = {v: k for k, v in KIND_CONTENT.items() if k not in ("maps_create", "line_create", "storefront_sign")}


def _library() -> dict[str, dict]:
    from .strategy import library
    return {c["id"]: c for c in library()}


def kind_spec(kind: str) -> dict:
    if kind in KINDS:
        return KINDS[kind]
    if kind.startswith(LIB_PREFIX):
        c = _library()[kind[len(LIB_PREFIX):]]
        ch = next((LIB_CHANNEL[n] for n in c["channels"] if n in LIB_CHANNEL), "facebook")
        return {"channel": ch, "minutes": 5 + 5 * min(int(c["effort"]), 3), "goal": f"{c['name']}: {c['how']}"}
    raise ValueError(f"unknown kind: {kind}")


def _last_used(history: list[list[str]]) -> dict[str, int]:
    used: dict[str, int] = {}
    for i, week in enumerate(history):
        for k in week:
            used[k] = i
    return used


def _rotate(pool: list[str], used: dict[str, int], taken: list[str]) -> str:
    """งานในช่องทางนี้ที่ยังไม่เคยทำก่อน ถ้าทำครบแล้วเลือกงานที่ทำนานที่สุด"""
    free = [k for k in pool if k not in taken]
    return min(free, key=lambda k: (k in used, used.get(k, -1), pool.index(k)))


def _pinned_kind(cid: str, profile: ShopProfile, lib: dict[str, dict]) -> str | None:
    if cid not in lib:
        return None
    k = CONTENT_KIND.get(cid)
    if k and (profile.has(KINDS[k]["channel"]) or KINDS[k]["channel"] == "storefront"):
        return k
    return LIB_PREFIX + cid


def pick_kinds(profile: ShopProfile) -> list[str]:
    """เลือกงาน 3 ประเภท (สูตรตัดสินใจ: Google Maps และ LINE มาก่อน)

    - ไอเดียที่ร้านกด "ใส่ในแผน" มาก่อน (ข้อเสนอราคาได้ไม่เกิน 1 งาน)
    - แต่ละช่องทางหมุนงานที่ยังไม่ได้ทำ จึงไม่ซ้ำกับสัปดาห์ก่อน
    - งานตั้งค่าครั้งเดียว (ปักหมุด / เปิด LINE OA) ทำแล้วไม่ทำซ้ำ ถือว่าร้านมีช่องทางนั้นแล้ว
    """
    used = _last_used(profile.history)
    order: list[str] = []
    if profile.pinned:
        lib = _library()
        price = 0
        for cid in profile.pinned:
            k = _pinned_kind(cid, profile, lib)
            if not k or k in order:
                continue
            if lib[cid]["is_price_offer"]:
                if price:
                    continue
                price += 1
            order.append(k)
    has_maps = profile.has("google_maps") or "maps_create" in used
    has_line = profile.has("line") or "line_create" in used
    chans = {kind_spec(k)["channel"] for k in order}

    def add(ch: str) -> None:
        if len(order) < 3 and ch not in chans:
            order.append(_rotate(POOLS[ch], used, order))
            chans.add(ch)

    if len(order) < 3 and "google_maps" not in chans:
        if has_maps:
            add("google_maps")
        else:
            order.append("maps_create")
            chans.add("google_maps")
    if profile.has("delivery"):
        add("delivery")
    if has_line:
        add("line")
    elif profile.has("facebook"):
        add("facebook")
    elif len(order) < 3:
        order.append("line_create")
        chans.add("line")
    if profile.has("facebook"):
        add("facebook")
    add("storefront")
    if has_maps:  # ยังไม่ครบ 3 งาน ใช้งาน Google Maps อีกงานที่ยังไม่ได้ทำ
        while len(order) < 3:
            order.append(_rotate(POOLS["google_maps"], used, order))
    while len(order) < 3:
        order.append(_rotate(POOLS["storefront"] + POOLS["google_maps"], used, order))
    return order[:3]


def day_label(d: date) -> str:
    return f"{WEEKDAY_TH[d.weekday()]} {d.day} {MONTH_TH[d.month - 1]}"


def time_window(profile: ShopProfile) -> str:
    """เวลาโพสต์: ใช้ของกลุ่มลูกค้าจำลองที่ร้านเลือก ถ้าไม่ได้เลือกใช้ค่าเริ่มต้นของกลุ่มลูกค้า"""
    for p in profile.personas:
        if p.post_time:
            return p.post_time
    return TIME_WINDOW[profile.customer]


def build_slots(profile: ShopProfile, today: date | None = None) -> list[Slot]:
    today = today or date.today()
    slots = []
    last: date | None = None
    for i, kind in enumerate(pick_kinds(profile)):
        spec = kind_spec(kind)
        d = today + timedelta(days=DAY_OFFSETS[i])
        # ร้านที่ลูกค้าเป็นคนทำงาน เลี่ยงเสาร์–อาทิตย์ (ยกเว้นงานแรกที่เป็นวันนี้)
        while i > 0 and profile.customer == "workers" and d.weekday() >= 5:
            d += timedelta(days=1)
        if last and d <= last:
            d = last + timedelta(days=1)
        last = d
        slots.append(
            Slot(
                slot=i + 1,
                kind=kind,
                channel=spec["channel"],
                goal=spec["goal"],
                date=d,
                day_label=day_label(d),
                time_window=time_window(profile),
                minutes=spec["minutes"],
            )
        )
    return slots


def _fallback_content(kind: str, profile: ShopProfile) -> tuple[str, str, list[str], str]:
    item = ITEM[profile.shop_type]
    moment = MOMENT[profile.customer]
    hook = {
        "drink": "เติมความสดชื่นด้วยเครื่องดื่มจากร้านเรา",
        "bakery": "มีขนมรอให้เลือกที่ร้านเรา",
        "food": "หิวเมื่อไรแวะมาทานที่ร้านเรา",
    }[profile.shop_type]
    emoji = {"drink": "☕", "bakery": "🍰", "food": "🍜"}[profile.shop_type]

    if kind == "maps_create":
        return (
            "ปักหมุดร้านบน Google Maps",
            "ถ้าร้านไม่มีหมุด คนที่ค้นหาร้านแถวนี้จะไม่เจอร้านคุณ ทำครั้งเดียวใช้ได้ตลอด",
            [
                "เปิด Google Maps แล้วค้นหาชื่อร้าน",
                "ถ้าไม่เจอ ให้สมัคร Google Business Profile ด้วยบัญชี Google ของคุณ",
                "ใส่ประเภทร้าน เวลาเปิด และรูปหน้าร้าน 1 รูป แล้ววางคำอธิบายด้านล่าง",
            ],
            f"ร้าน{item}ที่รอต้อนรับคุณ แวะมาได้{moment} {emoji}",
        )
    if kind == "maps_photos":
        return (
            f"อัปรูป{item}ใหม่ 3 รูปบน Google Maps",
            "ลูกค้าหลายคนดูรูปบน Google Maps ก่อนตัดสินใจมาร้าน รูปใหม่ที่ชัดช่วยให้ตัดสินใจง่ายขึ้น",
            [
                f"ถ่ายรูป{item} 3 รูปใกล้หน้าต่าง ให้ได้แสงธรรมชาติ",
                "เปิด Google Maps แล้วเข้าโปรไฟล์ร้านของคุณ",
                "กด 'เพิ่มรูปภาพ' แล้ววางคำอธิบายด้านล่าง",
            ],
            f"{hook} แวะมาได้{moment} {emoji}",
        )
    if kind == "maps_reviews":
        return (
            "ตอบรีวิวลูกค้าล่าสุด 3 รีวิว",
            "การตอบรีวิวแสดงว่าร้านใส่ใจลูกค้า และลูกค้าใหม่ที่อ่านรีวิวจะเห็นด้วย",
            [
                "เปิด Google Maps แล้วไปที่รีวิวของร้าน",
                "เลือกรีวิวล่าสุด 3 รีวิว",
                "วางข้อความด้านล่าง แล้วแก้ให้เข้ากับแต่ละรีวิว",
            ],
            "ขอบคุณที่แวะมาอุดหนุนร้านเรา ดีใจที่ชอบ ไว้แวะมาใหม่นะ 🙏",
        )
    if kind == "line_broadcast":
        return (
            "ส่งข้อความหาลูกค้าใน LINE ชวนแวะมาร้าน",
            "ลูกค้าใน LINE เคยมาร้านแล้ว ชวนให้กลับมาง่ายกว่าหาลูกค้าใหม่ และร้านไม่เสียค่า GP",
            [
                "เปิดแอป LINE Official Account",
                "เลือก 'บรอดแคสต์' แล้ววางข้อความด้านล่าง",
                f"แนบรูป{item} 1 รูป แล้วกดส่ง",
            ],
            f"สวัสดีจากร้านเรา 👋 สัปดาห์นี้มี{item}รอคุณอยู่ แวะมาได้{moment} หรือทักแชตสั่งล่วงหน้าได้เลย {emoji}",
        )
    if kind == "line_create":
        return (
            "เปิด LINE OA ของร้าน",
            "LINE OA เป็นช่องทางที่ร้านเป็นเจ้าของเอง ส่งข่าวถึงลูกค้าประจำได้โดยไม่เสียค่า GP",
            [
                "ดาวน์โหลดแอป LINE Official Account แล้วสมัครด้วยบัญชี LINE ของคุณ",
                "ตั้งชื่อร้านและรูปโปรไฟล์",
                "พิมพ์ QR code ของร้าน ตั้งไว้ที่เคาน์เตอร์พร้อมข้อความด้านล่าง",
            ],
            "สแกนเพื่อเป็นเพื่อนกับร้าน รับข่าวเมนูใหม่และโปรของร้าน 📲",
        )
    if kind == "fb_post":
        return (
            f"โพสต์รูป{item}ลง Facebook",
            "โพสต์สม่ำเสมอช่วยให้คนในย่านเห็นร้านบ่อยขึ้น และช่วงเวลาที่แนะนำตรงกับตอนที่ลูกค้าของคุณว่าง",
            [
                f"ถ่ายรูป{item} 1 รูป",
                "เปิดเพจร้านแล้วกด 'สร้างโพสต์'",
                "วางแคปชันด้านล่าง แล้วกดโพสต์",
            ],
            f"{hook} แวะมาได้{moment} {emoji}",
        )
    if kind == "delivery_card":
        tail = (
            "ครั้งหน้าทักสั่งตรงทาง LINE ของร้านได้เลย สแกน QR ด้านล่าง"
            if profile.has("line")
            else "ครั้งหน้าแวะมาที่ร้านได้นะ"
        )
        return (
            "แนบการ์ดชวนสั่งตรงในถุงเดลิเวอรี",
            "ลูกค้าจากแอปเดลิเวอรีรู้จักร้านแล้ว ถ้าครั้งหน้าเขามาที่ร้านหรือสั่งตรง ร้านไม่เสียค่า GP ในออเดอร์นั้น",
            [
                "เขียนหรือพิมพ์ข้อความด้านล่างลงการ์ดใบเล็ก",
                "ถ้ามี LINE OA ให้แปะ QR ของร้านบนการ์ดด้วย",
                "ใส่การ์ดในถุงทุกออเดอร์ของสัปดาห์นี้",
            ],
            f"ขอบคุณที่สั่งจากร้านเรา 🙏 {tail}",
        )
    if kind == "storefront_sign":
        return (
            "ตั้งป้ายแนะนำเมนูหน้าร้าน",
            "คนที่เดินผ่านตัดสินใจเร็ว ป้ายที่บอกเมนูชัดช่วยให้แวะง่ายขึ้น",
            [
                f"เลือก{item}ที่ลูกค้าสั่งบ่อย 1 อย่าง",
                "เขียนชื่อเมนูและราคาตัวใหญ่ลงป้าย",
                "ตั้งป้ายให้มองเห็นจากทางเดิน",
            ],
            f"เมนูแนะนำของร้านวันนี้ {emoji} แวะมาลองได้{moment}",
        )
    if kind == "maps_menu":
        return (
            f"ลงเมนู{item}พร้อมราคาบน Google Maps",
            "ลูกค้าที่เห็นเมนูและราคาก่อนมา ตัดสินใจแวะได้ง่ายขึ้น และถามน้อยลง",
            [
                f"ถ่ายรูปป้ายเมนูหรือ{item}ขายดี 3 อย่าง",
                "เปิดโปรไฟล์ร้านบน Google Maps แล้วเข้า 'เมนู' หรือ 'ผลิตภัณฑ์'",
                "ใส่ชื่อ ราคาปกติ และวางคำอธิบายด้านล่าง",
            ],
            f"เมนูของร้านพร้อมราคา ดูก่อนแวะมาได้เลย {emoji}",
        )
    if kind == "maps_faq":
        return (
            "อัปเดตเวลาเปิดและข้อมูลร้านบน Google Maps",
            "ลูกค้ามักดูเวลาเปิด ที่จอดรถ และช่องทางจ่ายเงินก่อนมา ข้อมูลครบช่วยให้ไม่เสียลูกค้าที่มาแล้วร้านปิด",
            [
                "เปิดโปรไฟล์ร้านบน Google Maps แล้วกด 'แก้ไขโปรไฟล์'",
                "ตรวจเวลาเปิด–ปิด วันหยุด และช่องทางจ่ายเงิน",
                "เพิ่มคำอธิบายร้านด้านล่าง แล้วบันทึก",
            ],
            f"ร้าน{item}ของเราเปิดทุกวันตามเวลาในโปรไฟล์ แวะมาได้{moment} {emoji}",
        )
    if kind == "line_newmenu":
        return (
            f"ชวนลูกค้าใน LINE ลอง{item}แนะนำก่อนใคร",
            "ลูกค้าเดิมชอบรู้สึกว่าได้รู้ก่อน ชวนลองเมนูแนะนำเป็นเหตุผลให้กลับมาโดยไม่ต้องลดราคา",
            [
                f"เลือก{item}ที่อยากให้ลอง 1 อย่าง แล้วถ่ายรูป",
                "เปิด LINE OA เลือก 'บรอดแคสต์'",
                "แนบรูปพร้อมข้อความด้านล่าง แล้วกดส่ง",
            ],
            f"บอกเพื่อนใน LINE ก่อนใคร 👋 สัปดาห์นี้ร้านมี{item}แนะนำ แวะมาลองได้{moment} {emoji}",
        )
    if kind == "line_thanks":
        return (
            "ขอบคุณลูกค้าใน LINE และขอความเห็น 1 ข้อ",
            "คำขอบคุณทำให้ลูกค้าจำร้านได้ และความเห็นสั้น ๆ ช่วยให้รู้ว่าควรปรับอะไร",
            [
                "เปิด LINE OA เลือก 'บรอดแคสต์'",
                "วางข้อความด้านล่าง",
                "จดคำตอบที่ได้ไว้ ใช้คิดเมนูหรือโพสต์สัปดาห์หน้า",
            ],
            f"ขอบคุณที่อุดหนุนร้านเรานะ 🙏 อยากให้ร้านมี{item}แบบไหนเพิ่ม ตอบกลับมาบอกกันได้เลย",
        )
    if kind == "line_poll":
        return (
            f"ถามลูกค้าใน LINE ว่าอยากได้{item}แบบไหน",
            "ให้ลูกค้าโหวตเมนู ทำให้เขามีส่วนร่วม และร้านรู้ว่าควรทำอะไรต่อ",
            [
                f"เลือก{item} 2 แบบที่ร้านทำได้",
                "เปิด LINE OA สร้าง 'แบบสอบถาม' หรือส่งข้อความให้ตอบ A หรือ B",
                "วางข้อความด้านล่าง แล้วกดส่ง",
            ],
            f"ช่วยร้านเลือกหน่อย 🙌 สัปดาห์หน้าอยากได้{item}แบบ A หรือ B ตอบกลับมาได้เลย",
        )
    if kind == "fb_behind":
        return (
            "โพสต์เบื้องหลังร้าน 3 รูป",
            "ลูกค้าไว้ใจร้านมากขึ้นเมื่อเห็นการเตรียมของและคนทำจริง",
            [
                "ถ่าย 3 รูป: ตอนเตรียมของ ตอนทำ และตอนเปิดร้าน",
                "เปิดเพจร้าน กด 'สร้างโพสต์' แล้วใส่รูปทั้ง 3",
                "วางแคปชันด้านล่าง แล้วกดโพสต์",
            ],
            f"เช้านี้ที่ร้านเรา เตรียมของ ทำ{item} แล้วเปิดร้านรอคุณ แวะมาได้{moment} {emoji}",
        )
    if kind == "fb_qa":
        return (
            "โพสต์ตอบคำถามที่ลูกค้าถามบ่อย",
            "คำถามที่ถามซ้ำ เช่น เวลาเปิด ที่จอดรถ สั่งล่วงหน้าได้ไหม ตอบครั้งเดียวในโพสต์ช่วยประหยัดเวลาตอบแชต",
            [
                "จดคำถามที่ลูกค้าถามบ่อย 3 ข้อ",
                "เปิดเพจร้าน กด 'สร้างโพสต์'",
                "วางแคปชันด้านล่าง แล้วเติมคำตอบของร้าน",
            ],
            "ลูกค้าถามบ่อย ร้านตอบตรงนี้เลย 🙋 เวลาเปิด · ที่จอดรถ · สั่งล่วงหน้า",
        )
    if kind == "fb_community":
        return (
            "แนะนำร้านในกลุ่ม Facebook ของย่าน",
            "คนในกลุ่มชุมชนอยู่ใกล้ร้าน และเชื่อคำแนะนำจากคนในย่าน",
            [
                "ค้นหากลุ่ม Facebook ของย่านหรือหมู่บ้านใกล้ร้าน",
                "อ่านกฎกลุ่มว่าโพสต์แนะนำร้านได้ไหม",
                f"โพสต์รูป{item} 1 รูปพร้อมแคปชันด้านล่าง",
            ],
            f"สวัสดีเพื่อนบ้าน 👋 ร้าน{item}ของเราอยู่แถวนี้ แวะมาได้{moment} {emoji}",
        )
    if kind == "delivery_menu":
        return (
            "อัปเดตรูปและคำอธิบายเมนูในแอปเดลิเวอรี",
            "รูปชัดและคำอธิบายสั้นช่วยให้คนที่เลื่อนดูในแอปกดสั่งง่ายขึ้น",
            [
                f"ถ่ายรูป{item}ขายดี 2 เมนู แสงธรรมชาติ",
                "เปิดแอปร้านค้าของ Grab หรือ LINE MAN แล้วแก้เมนู",
                "เปลี่ยนรูป แล้ววางคำอธิบายด้านล่าง",
            ],
            f"ทำใหม่ทุกออเดอร์ {emoji} ส่วนผสมสำคัญ: ใส่ของร้านคุณ",
        )
    if kind == "storefront_staffpick":
        return (
            "ตั้งป้าย 'เมนูที่พนักงานแนะนำ'",
            "ลูกค้าใหม่มักเลือกไม่ถูก ป้ายเมนูที่คนในร้านแนะนำช่วยให้ตัดสินใจเร็วขึ้น",
            [
                f"เลือก{item}ที่คนในร้านชอบ 1 อย่าง",
                "เขียนชื่อเมนู ราคา และเหตุผลสั้น ๆ ลงป้าย",
                "ตั้งป้ายไว้ข้างเคาน์เตอร์",
            ],
            f"เมนูที่พนักงานแนะนำวันนี้ {emoji} ลองดูได้{moment}",
        )
    if kind.startswith(LIB_PREFIX):
        c = _library()[kind[len(LIB_PREFIX):]]
        return (
            c["name"],
            f"ไอเดียที่คุณเลือกจากแท็บไอเดีย ({c['group_name']})",
            [f"เตรียม: {c['how']}", f"ลงช่องทางที่ร้านใช้ ช่วงเวลาที่แนะนำ", f"วัดผล: {c['measure']}"],
            f"{hook} แวะมาได้{moment} {emoji}",
        )
    raise ValueError(f"unknown kind: {kind}")


def fallback_task(slot: Slot, profile: ShopProfile) -> PlanTask:
    title, why, steps, caption = _fallback_content(slot.kind, profile)
    if profile.personas:
        p = profile.personas[0]
        why += f" · เหมาะกับลูกค้ากลุ่ม{p.archetype}" + (f" ที่ชอบ{p.likes[0]}" if p.likes else "")
    return PlanTask(
        slot=slot.slot,
        kind=slot.kind,
        channel=slot.channel,
        channel_label=CHANNEL_TH[slot.channel],
        date=slot.date,
        day_label=slot.day_label,
        time_window=slot.time_window,
        minutes=slot.minutes,
        title=title,
        why=why,
        steps=steps,
        caption=caption,
        redline=check_redline(caption),
        source="fallback",
        content_id=content_id(slot.kind),
    )


def content_id(kind: str) -> str:
    return kind[len(LIB_PREFIX):] if kind.startswith(LIB_PREFIX) else KIND_CONTENT.get(kind, "")
