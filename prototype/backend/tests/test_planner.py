"""ทดสอบ planner ด้วยเอเจนต์จำลอง จึงไม่ต้องมี AWS."""
import json
import time
from datetime import date

from belka.agent import AgentOutput
from belka.models import ShopProfile
from belka.planner import extract_json, make_plan

TODAY = date(2026, 11, 18)
PROFILE = ShopProfile(shop_type="drink", customer="workers", channels=["facebook", "delivery"])


def good_task(slot, caption="ร้อนแบบนี้ แวะมาเติมความสดชื่นที่ร้านเราได้ช่วงพักเที่ยง ☕"):
    return {
        "slot": slot,
        "title": "โพสต์รูปกาแฟเย็นลง Facebook",
        "why": "ช่วงเที่ยงคนทำงานเลื่อนมือถือหาที่พัก โพสต์ตอนนี้ช่วยให้เห็นร้านก่อนตัดสินใจ",
        "steps": ["ถ่ายรูปกาแฟเย็น 1 รูป", "วางแคปชันแล้วกดโพสต์"],
        "caption": caption,
    }


def runner_returning(payload, tool_calls=None):
    def _run(prompt):
        assert "ช่องงาน" in prompt
        return AgentOutput(text=payload, tool_calls=tool_calls or [])

    return _run


def test_ai_plan_used_when_valid():
    text = "```json\n" + json.dumps({"tasks": [good_task(1), good_task(2), good_task(3)]}, ensure_ascii=False) + "\n```"
    calls = [{"tool": "check_redline", "text": "x", "passed": True}] * 3
    plan = make_plan(PROFILE, TODAY, runner_returning(text, calls), mode="ai")
    assert plan.source == "ai"
    assert plan.ai_tool_calls == 3
    assert len(plan.tasks) == 3
    # ช่องทาง วัน เวลา และนาทีมาจากโค้ด ไม่ใช่ AI
    assert [t.date.day for t in plan.tasks] == [18, 20, 23]
    assert all(t.redline.passed for t in plan.tasks)


def test_redline_failure_replaced_by_fallback():
    tasks = [good_task(1), good_task(2, caption="การันตีอร่อยที่สุดในย่าน"), good_task(3)]
    plan = make_plan(PROFILE, TODAY, runner_returning(json.dumps({"tasks": tasks}, ensure_ascii=False)), mode="ai")
    assert plan.source == "mixed"
    assert plan.tasks[1].source == "fallback"
    assert all(t.redline.passed for t in plan.tasks)


def test_missing_slot_filled_by_fallback():
    plan = make_plan(PROFILE, TODAY, runner_returning(json.dumps({"tasks": [good_task(1)]}, ensure_ascii=False)), mode="ai")
    assert [t.source for t in plan.tasks] == ["ai", "fallback", "fallback"]


def test_garbage_output_gives_full_fallback():
    plan = make_plan(PROFILE, TODAY, runner_returning("ขอโทษครับ ไม่เข้าใจ"), mode="ai")
    assert plan.source == "fallback"
    assert plan.notice
    assert len(plan.tasks) == 3


def test_agent_error_gives_fallback():
    def boom(prompt):
        raise RuntimeError("bedrock down")

    plan = make_plan(PROFILE, TODAY, boom, mode="ai")
    assert plan.source == "fallback" and len(plan.tasks) == 3


def test_slow_agent_times_out(monkeypatch):
    monkeypatch.setenv("BELKA_AI_TIMEOUT", "0.3")

    def slow(prompt):
        time.sleep(2)
        return AgentOutput(text="{}")

    started = time.monotonic()
    plan = make_plan(PROFILE, TODAY, slow, mode="ai")
    assert time.monotonic() - started < 1.5
    assert plan.source == "fallback"


def test_fallback_mode_never_calls_agent():
    def never(prompt):
        raise AssertionError("ไม่ควรถูกเรียก")

    plan = make_plan(PROFILE, TODAY, never, mode="fallback")
    assert plan.source == "fallback" and plan.notice is None


def test_extract_json():
    assert extract_json('ok {"a": 1} end') == {"a": 1}
    assert extract_json("no json") is None


def test_config_refused_for_apac_model(monkeypatch):
    """โมเดล apac./global. หรือรีเจียนอื่นต้องไม่เรียก Bedrock และใช้แผนสำรอง (spec 12.2)"""
    import belka.agent as agent_mod

    def must_not_run(prompt):
        raise AssertionError("ไม่ควรเรียก Bedrock")

    monkeypatch.setattr(agent_mod, "run_agent", must_not_run)
    for env in [{"BELKA_MODEL_ID": "apac.anthropic.claude-sonnet-5"},
                {"BELKA_MODEL_ID": "global.anthropic.claude-sonnet-5"},
                {"BELKA_REGION": "us-west-2"}]:
        monkeypatch.delenv("BELKA_MODEL_ID", raising=False)
        monkeypatch.delenv("BELKA_REGION", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        plan = make_plan(PROFILE, TODAY, mode="ai")
        assert plan.source == "fallback" and len(plan.tasks) == 3


def test_default_settings_follow_team_rules(monkeypatch):
    from belka.config import config_refused, get_settings

    monkeypatch.delenv("BELKA_MODEL_ID", raising=False)
    monkeypatch.delenv("BELKA_REGION", raising=False)
    s = get_settings()
    assert s.model_id == "anthropic.claude-sonnet-5" and s.region == "ap-southeast-1"
    assert s.ai_timeout_s == 8
    assert config_refused(s) is None
