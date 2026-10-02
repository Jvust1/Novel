"""Offline, synthetic request admission and actual shared writer execution."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import hashlib
import json

import httpx
import pytest

from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.models import ChapterPlan, StoryBible, StyleFingerprint
from novel_ai.orchestration import ProviderRouter, RouterConfig
from novel_ai.output_policy import OutputPolicy, OutputValidationError
from novel_ai.provider import LiteLLMConfig, OpenAICompatibleProvider, ProviderConfig
from novel_ai.request_budget import (
    RequestBudget, RequestBudgetExceeded, RequestBudgetLimits, bounded_request_bytes,
)


MESSAGES = [{"role": "user", "content": "合成资料，不含真实小说"}]
PLAN = {"chapter_title": "雨后", "chapter_promise": "作出选择", "tension_curve": "上升",
        "scenes": [{"scene_no": 1, "pov": "舟", "objective": "找钥匙", "opposition": "门锁住了",
                    "choice": "等屋主回来", "cost": "错过末班船", "state_change": "决定留下", "end_hook": "灯亮了"}]}
PROSE = "屋檐不再滴水。他把湿鞋放到门外，坐在台阶上等。"
REVISED = "雨已经停了。他脱下湿鞋放在门外，坐到台阶最干的一块，等屋里的人点灯。"


def envelope(text=PROSE):
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(handler)))


def provider(monkeypatch, handler, limits=None):
    transport(monkeypatch, handler)
    budget = RequestBudget(limits)
    return OpenAICompatibleProvider(ProviderConfig("https://example.invalid/v1", "synthetic", api_key="synthetic-test-credential"), request_budget=budget), budget


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "10", None])
@pytest.mark.parametrize("field", ["max_requests", "max_request_bytes", "max_total_request_bytes", "max_reserved_output_tokens"])
def test_invalid_limits_are_never_coerced(field, value):
    with pytest.raises(ValueError):
        RequestBudgetLimits(**{field: value})


def test_limits_and_snapshot_do_not_expose_mutable_ledger():
    b = RequestBudget()
    with pytest.raises(FrozenInstanceError):
        b.limits.max_requests = 100
    t = b.admit(b"{}", max_tokens=2)
    b.finish(t, succeeded=True)
    snapshot = b.snapshot()
    snapshot["attempts"][0]["status"] = "edited"
    snapshot["limits"]["max_requests"] = 1000
    assert b.snapshot()["attempts"][0]["status"] == "succeeded"
    assert b.limits.max_requests == 8
    assert b.snapshot()["actual_cost"] is None and b.snapshot()["actual_tokens"] is None


def test_utf8_body_is_exact_complete_and_not_clipped():
    payload = {"messages": MESSAGES, "model": "模型", "max_tokens": 3, "temperature": .5}
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    assert bounded_request_bytes(payload, max_bytes=len(raw)) == raw
    with pytest.raises(RequestBudgetExceeded):
        bounded_request_bytes(payload, max_bytes=len(raw) - 1)
    assert payload["messages"] == MESSAGES


@pytest.mark.parametrize("messages", [None, [], {}, [{"role": "tool", "content": "x"}],
    [{"role": "user", "content": [{"text": "x"}]}], [{"role": "user", "content": "x", "name": "n"}],
    [{"role": "user"}], [None], [{"role": [], "content": "x"}]])
def test_unsupported_message_shapes_rejected(messages):
    with pytest.raises((ValueError, TypeError)):
        bounded_request_bytes({"messages": messages}, max_bytes=10000)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object(), "\ud800"])
def test_nonfinite_unsupported_unicode_fields_rejected_without_echo(bad):
    with pytest.raises(ValueError) as exc:
        bounded_request_bytes({"messages": MESSAGES, "extra": bad}, max_bytes=10000)
    assert MESSAGES[0]["content"] not in str(exc.value)


def test_direct_invalid_caps_do_not_spend_admission():
    b = RequestBudget()
    for value in (0, False, -1, 1.5):
        with pytest.raises(ValueError):
            b.admit(b"{}", max_tokens=value)
    assert b.snapshot()["requests_reserved"] == 0


def test_no_wire_call_when_complete_body_does_not_fit(monkeypatch):
    calls = []
    p, b = provider(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, json=envelope()),
                    RequestBudgetLimits(max_request_bytes=10))
    with pytest.raises(RequestBudgetExceeded):
        p.chat(MESSAGES)
    assert calls == [] and b.snapshot()["requests_reserved"] == 0


def test_sent_bytes_equal_admitted_digest_and_headers_are_not_recorded(monkeypatch):
    calls = []
    p, b = provider(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    assert p.chat(MESSAGES, max_tokens=10) == PROSE
    snap = b.snapshot()
    assert snap["attempts"][0]["request_sha256"] == hashlib.sha256(calls[0].content).hexdigest()
    assert snap["request_bytes_reserved"] == len(calls[0].content)
    assert snap["output_tokens_reserved"] == 10
    assert json.loads(calls[0].content)["messages"] == MESSAGES
    assert all(x not in json.dumps(snap, ensure_ascii=False) for x in
               ("synthetic-test-credential", "example.invalid", MESSAGES[0]["content"], PROSE))


@pytest.mark.parametrize("cap", [1, 2])
def test_format_fallback_is_a_second_fully_reserved_wire_attempt(monkeypatch, cap):
    calls = []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(400, json={"error": {"param": "response_format", "code": "unsupported_parameter"}})
        return httpx.Response(200, json=envelope())
    p, b = provider(monkeypatch, handler, RequestBudgetLimits(max_requests=cap))
    if cap == 1:
        with pytest.raises(RequestBudgetExceeded):
            p.chat(MESSAGES, max_tokens=10, response_format={"type": "json_object"})
    else:
        assert p.chat(MESSAGES, max_tokens=10, response_format={"type": "json_object"}) == PROSE
        assert "response_format" not in json.loads(calls[1].content)
    assert len(calls) == cap and b.snapshot()["requests_reserved"] == cap
    assert b.snapshot()["output_tokens_reserved"] == cap * 10
    assert b.snapshot()["attempts"][0]["status"] == "failed"


@pytest.mark.parametrize("failure", ["transport", "500", "invalid", "partial"])
def test_sent_failures_never_refund_or_reset_allowance(monkeypatch, failure):
    calls = []
    def handler(req):
        calls.append(req)
        if failure == "transport":
            raise httpx.ConnectError("offline synthetic", request=req)
        if failure == "500":
            return httpx.Response(500)
        if failure == "invalid":
            return httpx.Response(200, content=b"invalid")
        data = envelope(); data["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=data)
    p, b = provider(monkeypatch, handler, RequestBudgetLimits(max_requests=1))
    with pytest.raises((httpx.HTTPError, OutputValidationError)):
        p.chat(MESSAGES, max_tokens=10)
    with pytest.raises(RequestBudgetExceeded):
        p.chat(MESSAGES, max_tokens=10)
    assert len(calls) == 1 and b.snapshot()["output_tokens_reserved"] == 10
    assert b.snapshot()["attempts"][0]["status"] == "failed"


def test_output_reservation_is_worst_case_and_rejects_before_next_call(monkeypatch):
    calls = []
    p, b = provider(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, json=envelope("短")),
                    RequestBudgetLimits(max_reserved_output_tokens=20))
    p.chat(MESSAGES, max_tokens=20)
    with pytest.raises(RequestBudgetExceeded):
        p.chat(MESSAGES, max_tokens=1)
    assert len(calls) == 1 and b.snapshot()["output_tokens_reserved"] == 20


def test_total_byte_reservation_and_closed_budget():
    b = RequestBudget(RequestBudgetLimits(max_request_bytes=3, max_total_request_bytes=5))
    t = b.admit(b"abc", max_tokens=1); b.finish(t, succeeded=True)
    with pytest.raises(RequestBudgetExceeded):
        b.admit(b"abc", max_tokens=1)
    t = b.admit(b"ab", max_tokens=1); b.finish(t, succeeded=False)
    b.close()
    with pytest.raises(RequestBudgetExceeded):
        b.admit(b"a", max_tokens=1)
    assert b.snapshot()["request_bytes_reserved"] == 5


def test_concurrent_admission_reserves_once_under_shared_cap():
    b = RequestBudget(RequestBudgetLimits(max_requests=3))
    def run(_):
        try:
            t = b.admit(b"{}", max_tokens=3)
            b.finish(t, succeeded=True)
            return True
        except RequestBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(run, range(30))) == 3
    assert b.snapshot()["output_tokens_reserved"] == 9


def session_transport(monkeypatch, limits=None, output_policy=None, override=None):
    calls = []
    def handler(req):
        payload = json.loads(req.content)
        sys = payload["messages"][0]["content"]
        stage = ("plan" if "章节策划" in sys else "review" if "严苛的网络小说章节编辑" in sys else
                 "repair" if "局部修订编辑" in sys else "memory" if "连续性记录员" in sys else
                 "style" if "文体分析师" in sys else "draft")
        calls.append({"stage": stage, "payload": payload, "bytes": len(req.content), "host": req.url.host})
        if override:
            custom = override(stage, len(calls))
            if custom is not None:
                return custom
        text = (json.dumps(PLAN, ensure_ascii=False) if stage == "plan" else
                json.dumps({"verdict": "revise" if len([x for x in calls if x['stage'] == 'review']) == 1 else "pass", "issues": []}) if stage == "review" else
                json.dumps({"summary": "等待屋主", "chapter_id": "c"}) if stage == "memory" else
                "{}" if stage == "style" else REVISED if stage == "repair" else PROSE)
        return httpx.Response(200, json=envelope(text))
    transport(monkeypatch, handler)
    cfg = RouterConfig(local=ProviderConfig("https://writer.invalid/v1", "writer"),
                       reviewer=ProviderConfig("https://reviewer.invalid/v1", "reviewer"))
    return BudgetedWritingSession(cfg, limits=limits, output_policy=output_policy), calls


def options():
    return {"bible": StoryBible(title="合成测试"), "characters": [], "outline": "等屋主回来",
            "chapter_goal": "选择留下", "auto_repair": True, "extra_context": "LOCKED_SYNTHETIC_FACT"}


def test_actual_five_stage_writer_roles_share_one_ledger_and_do_not_accept(monkeypatch):
    s, calls = session_transport(monkeypatch)
    result = s.run(**options())
    assert result.final_text == REVISED
    assert [x["stage"] for x in calls] == ["plan", "draft", "review", "repair", "review"]
    assert [x["host"] for x in calls] == ["writer.invalid", "writer.invalid", "reviewer.invalid", "writer.invalid", "reviewer.invalid"]
    assert all("LOCKED_SYNTHETIC_FACT" in json.dumps(x["payload"]) for x in calls)
    snap = s.budget_snapshot()
    assert snap["requests_reserved"] == 5
    assert snap["request_bytes_reserved"] == sum(x["bytes"] for x in calls)
    assert snap["output_tokens_reserved"] == sum(x["payload"]["max_tokens"] for x in calls)
    assert result.final_report["author_acceptance"] == "pending"


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_whole_flow_call_limit_stops_exactly_before_next_stage(monkeypatch, count):
    s, calls = session_transport(monkeypatch, RequestBudgetLimits(max_requests=count))
    with pytest.raises(RequestBudgetExceeded):
        s.run(**options())
    assert len(calls) == count
    with pytest.raises(RequestBudgetExceeded):
        s.run(**options())
    assert len(calls) == count


def test_confirmed_plan_uses_four_calls_without_replanning(monkeypatch):
    s, calls = session_transport(monkeypatch)
    kw = options(); kw.pop("outline"); kw.pop("chapter_goal")
    result = s.run_from_plan(plan=ChapterPlan.model_validate(PLAN), **kw)
    assert result.final_text == REVISED
    assert [x["stage"] for x in calls] == ["draft", "review", "repair", "review"]


def test_memory_candidate_shares_remaining_budget_and_cannot_reset_it(monkeypatch):
    s, calls = session_transport(monkeypatch, RequestBudgetLimits(max_requests=6))
    s.run(**options())
    memory = s.extract_memory(StoryBible(), [], "c", PROSE)
    assert memory.chapter_id == "c" and len(calls) == 6
    with pytest.raises(RequestBudgetExceeded):
        s.extract_memory(StoryBible(), [], "c", PROSE)
    assert len(calls) == 6


def test_opaque_sdk_and_execution_paths_are_rejected_before_calls(monkeypatch):
    calls = []
    transport(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    with pytest.raises(ValueError, match="opaque"):
        BudgetedWritingSession(RouterConfig(litellm=LiteLLMConfig(("m",))))
    with pytest.raises(TypeError):
        BudgetedWritingSession(None)
    s = BudgetedWritingSession(RouterConfig(local=ProviderConfig("https://example.invalid", "m")))
    for key in ("reviewer", "external_review_hooks", "structured_extractor"):
        with pytest.raises(ValueError):
            s.run(**options(), **{key: None})
    assert calls == []


@pytest.mark.parametrize("stop_at", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("kind", ["total_bytes", "reserved_tokens"])
def test_whole_flow_accumulated_allowance_stops_before_exact_wire_call(monkeypatch, stop_at, kind):
    with monkeypatch.context() as patch:
        s, baseline = session_transport(patch)
        s.run(**options())
    if kind == "total_bytes":
        cap = sum(x["bytes"] for x in baseline[:stop_at]) - 1
        limits = RequestBudgetLimits(max_total_request_bytes=cap)
    else:
        cap = sum(x["payload"]["max_tokens"] for x in baseline[:stop_at]) - 1
        limits = RequestBudgetLimits(max_reserved_output_tokens=cap)
    with monkeypatch.context() as patch:
        s, calls = session_transport(patch, limits)
        with pytest.raises(RequestBudgetExceeded):
            s.run(**options())
        assert len(calls) == stop_at - 1


def test_style_and_memory_use_same_session_and_close_does_not_refund(monkeypatch):
    s, calls = session_transport(monkeypatch)
    style = s.enrich_style("原创合成高层文体示例", StyleFingerprint())
    assert isinstance(style, StyleFingerprint) and calls[0]["stage"] == "style"
    s.extract_memory(StoryBible(), [], "c", PROSE)
    before = s.budget_snapshot()
    s.close()
    with pytest.raises(RequestBudgetExceeded):
        s.enrich_style("原创示例", StyleFingerprint())
    assert len(calls) == 2
    assert s.budget_snapshot()["output_tokens_reserved"] == before["output_tokens_reserved"]


def test_inherited_process_ledger_is_refused_before_acquiring_lock(monkeypatch):
    import os
    b = RequestBudget()
    original_pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: original_pid + 1)
    b._lock.acquire()
    try:
        for action in (lambda: b.admit(b"{}", max_tokens=1), b.snapshot, b.close,
                       lambda: b.finish(1, succeeded=True), lambda: b.limits):
            with pytest.raises(RequestBudgetExceeded, match="another process"):
                action()
    finally:
        b._lock.release()


def test_source_port_is_pinned_complete_and_executed(monkeypatch):
    from pathlib import Path
    from novel_ai._vendor.pydantic_ai_usage import UsageLimits
    root = Path(__file__).resolve().parents[1]
    provenance = json.loads((root / "third_party/pydantic-ai-usage-limits/provenance.json").read_text())
    assert provenance["observed_stars"] >= 1000 and provenance["source_port"] is True
    for item in provenance["files"]:
        raw = (root / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["git_blob"]
    hits = []
    before = UsageLimits.check_before_request
    tokens = UsageLimits.check_tokens
    monkeypatch.setattr(UsageLimits, "check_before_request", lambda self, u: hits.append("request") or before(self, u))
    monkeypatch.setattr(UsageLimits, "check_tokens", lambda self, u: hits.append("reservation") or tokens(self, u))
    b = RequestBudget()
    b.admit(b"{}", max_tokens=1)
    assert hits == ["request", "reservation"]
