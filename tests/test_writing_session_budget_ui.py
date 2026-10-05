"""Real Streamlit writing-session budget checks over an offline HTTPX wire."""

import copy
import json
import pickle
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


class WireFixture:
    def __init__(self):
        self.calls = []
        self.review_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        system = payload["messages"][0]["content"]
        self.calls.append({"headers": dict(request.headers), "payload": payload})
        if "章节策划" in system:
            content = json.dumps({"chapter_title": "合成测试章", "scenes": []}, ensure_ascii=False)
        elif "严苛的网络小说章节编辑" in system:
            self.review_count += 1
            verdict = "revise" if self.review_count % 2 else "pass"
            content = json.dumps({"verdict": verdict, "issues": []}, ensure_ascii=False)
        elif "局部修订编辑" in system:
            content = "合成修订正文，不代表作者接受。"
        else:
            content = "合成正文，不代表作者接受。"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        )


def run_app(monkeypatch, tmp_path, wire: WireFixture):
    monkeypatch.chdir(tmp_path)
    real_client = httpx.Client

    def offline_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(wire)
        kwargs["trust_env"] = False
        return real_client(*args, **kwargs)

    # The provider, request serializer and HTTP response validation stay real.
    monkeypatch.setattr(httpx, "Client", offline_client)
    return AppTest.from_file(str(APP), default_timeout=30).run()


def configure_writer(at, *, mode="精修"):
    at.text_input(key="project_name").set_value("BudgetBook")
    at.text_input(key="chapter_id").set_value("001")
    at.text_area(key="chapter_goal").set_value("主角在雨夜核对一份账本。")
    at.radio[0].set_value(mode)
    for item in at.text_input:
        if item.label == "Base URL":
            item.set_value("http://wire.test")
        elif item.label == "Model":
            item.set_value("synthetic-model")
        elif item.label == "API Key（只在当前会话使用）":
            item.set_value("synthetic-secret")
    at.run()


def test_real_wire_budget_spans_plan_draft_oneshot_and_reruns(monkeypatch, tmp_path):
    wire = WireFixture()
    at = run_app(monkeypatch, tmp_path, wire)
    configure_writer(at)

    at.button(key="btn_plan").click().run()
    assert not at.exception
    budget = at.session_state["_writing_request_budget"]
    assert budget.snapshot()["requests_reserved"] == 1
    assert len(wire.calls) == 1

    at.button(key="btn_draft").click().run()
    assert not at.exception
    assert len(wire.calls) == 5  # draft, review, repair, re-review after the plan
    assert budget.snapshot()["requests_reserved"] == 5
    chapter = tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "001.md"
    assert chapter.exists()

    old_budget = budget
    at.button(key="btn_clear_plan").click().run()
    cleared_budget = at.session_state["_writing_request_budget"]
    assert old_budget.snapshot()["closed"] is True
    assert cleared_budget is not old_budget
    assert cleared_budget.snapshot()["requests_reserved"] == 0
    at.text_input(key="chapter_id").set_value("002").run()
    assert cleared_budget.snapshot()["closed"] is True
    new_budget = at.session_state["_writing_request_budget"]
    assert new_budget is not cleared_budget
    assert new_budget.snapshot()["requests_reserved"] == 0

    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    assert len(wire.calls) == 10  # one-shot plan, draft, review, repair, re-review
    assert new_budget.snapshot()["requests_reserved"] == 5
    assert (tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "002.md").exists()

    snapshot_text = json.dumps(new_budget.snapshot(), ensure_ascii=False)
    assert "wire.test" not in snapshot_text
    assert "synthetic-secret" not in snapshot_text
    assert "合成正文" not in snapshot_text
    with pytest.raises(TypeError):
        copy.deepcopy(new_budget)
    with pytest.raises(TypeError):
        pickle.dumps(new_budget)


def test_request_limit_stops_next_wire_and_explicit_new_session_recovers(monkeypatch, tmp_path):
    wire = WireFixture()
    at = run_app(monkeypatch, tmp_path, wire)
    configure_writer(at)
    at.number_input(key="writing_budget_max_requests").set_value(4)
    at.run()
    at.button(key="btn_clear_plan").click().run()
    configured = at.session_state["_writing_request_budget"]
    assert configured.limits.max_requests == 4

    at.button(key="btn_oneshot").click().run()
    assert len(wire.calls) == 4
    assert not (tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "001.md").exists()
    assert any("预算已耗尽" in item.value for item in at.error)
    at.run()
    assert len(wire.calls) == 4  # rerender cannot mint another allowance

    at.number_input(key="writing_budget_max_requests").set_value(8)
    at.button(key="btn_clear_plan").click().run()
    fresh = at.session_state["_writing_request_budget"]
    assert fresh.snapshot()["requests_reserved"] == 0
    assert fresh.limits.max_requests == 8

    at.radio[0].set_value("快速草稿").run()
    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    assert fresh.snapshot()["requests_reserved"] == 2
    assert (tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "001.md").exists()


def test_request_bytes_stop_before_wire_and_pending_config_waits_for_new_session(monkeypatch, tmp_path):
    wire = WireFixture()
    at = run_app(monkeypatch, tmp_path, wire)
    configure_writer(at, mode="快速草稿")
    at.number_input(key="writing_budget_max_request_bytes").set_value(1024)
    at.run()
    at.button(key="btn_clear_plan").click().run()

    at.button(key="btn_oneshot").click().run()
    assert len(wire.calls) == 0
    budget = at.session_state["_writing_request_budget"]
    assert budget.snapshot()["requests_reserved"] == 0
    assert any("预算已耗尽" in item.value for item in at.error)
    assert not (tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "001.md").exists()

    # Changing the control alone cannot replace a live budget.
    at.number_input(key="writing_budget_max_request_bytes").set_value(512 * 1024)
    at.run()
    assert at.session_state["_writing_request_budget"] is budget
    assert budget.limits.max_request_bytes == 1024

    at.button(key="btn_clear_plan").click().run()
    fresh = at.session_state["_writing_request_budget"]
    assert fresh is not budget
    assert fresh.limits.max_request_bytes == 512 * 1024
    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    assert len(wire.calls) == 2
    assert (tmp_path / "data" / "projects" / "BudgetBook" / "chapters" / "001.md").exists()
