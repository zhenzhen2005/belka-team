import pytest

from belka.redline import check_redline


@pytest.mark.parametrize(
    "text",
    [
        "เติมความสดชื่นด้วยเครื่องดื่มจากร้านเรา แวะมาได้ช่วงพักเที่ยง ☕",
        "สวัสดีจากร้านเรา สัปดาห์นี้มีขนมรอคุณอยู่",
        "ขอบคุณที่สั่งจากร้านเรา 🙏 ครั้งหน้าแวะมาที่ร้านได้นะ",
        "ร้านเปิดมา 5 ปีแล้ว",  # ตัวเลขข้อเท็จจริง ไม่ใช่ตัวเลขผลลัพธ์
    ],
)
def test_safe_text_passes(text):
    assert check_redline(text).passed


@pytest.mark.parametrize(
    "text,term",
    [
        ("การันตีอร่อยที่สุดในย่าน", "การันตี"),
        ("กาแฟอร่อยที่สุดในย่าน", "ที่สุด"),
        ("ร้านอันดับ 1 ของซอย", "อันดับ 1"),
        ("อร่อย 100% ไม่อร่อยยินดีคืนเงิน", "100%"),
        ("ชาสูตรนี้ช่วยลดน้ำหนัก", "ลดน้ำหนัก"),
    ],
)
def test_banned_terms_fail(text, term):
    result = check_redline(text)
    assert not result.passed
    assert term in [i.term for i in result.issues]
    assert all(i.suggestion for i in result.issues)


def test_result_claim_fails():
    result = check_redline("ใช้แล้วยอดขายเพิ่ม 50% ภายในเดือนเดียว")
    assert not result.passed
    assert any("ตัวเลขผลลัพธ์" in i.reason for i in result.issues)


def test_fake_scarcity_fails():
    assert not check_redline("รีบเลย เหลือเพียง 3 แก้วสุดท้าย").passed


def test_empty_fails():
    assert not check_redline("   ").passed
