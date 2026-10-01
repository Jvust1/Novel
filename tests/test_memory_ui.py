"""Real AppTest buttons, original fixtures, no actual model endpoint."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from novel_ai.author_workflow import save_chapter_plan, write_author_chapter
from novel_ai.engine import ChapterResult
from novel_ai.models import ChapterPlan, ChapterReview
from novel_ai.provider import OpenAICompatibleProvider
from novel_ai.storage import ProjectStore

APP = Path(__file__).resolve().parents[1] / "app.py"
TEXT = "舟把旧钥匙留在窗台上，没有赶末班船。她现在知道了钥匙的用途。"


def fixture(monkeypatch, tmp_path, *, output=None, callback=None, wire=False):
    monkeypatch.chdir(tmp_path)
    store = ProjectStore(tmp_path / "data")
    cards = [{"name": "舟", "knows": [], "does_not_know": ["钥匙用途"], "voice_extension": {"keep": True}}]
    store.write_json("MyNovel", "memory/characters.json", cards)
    store.write_json("MyNovel", "memory/story_bible.json", {"title": "MyNovel", "audience": "测试读者", "custom_rule": {"preserve": True}})
    store.save_story_state("MyNovel", {"facts": ["旧钥匙在窗台"], "custom_ledger": {"keep": True}})
    plan = ChapterPlan(chapter_title="等候")
    write_author_chapter(store, "MyNovel", "001", TEXT)
    save_chapter_plan(store, "MyNovel", "001", plan, TEXT)
    calls = []
    payload = output or {"chapter_id": "001", "summary": "舟留下来，得知钥匙用途。", "character_updates": [{"name": "舟", "knowledge_gained": ["钥匙用途"]}]}
    def chat(self, messages, **kwargs):
        calls.append({"messages": deepcopy(messages), "limits": self.request_budget.limits})
        if callback:
            callback(store)
        return json.dumps(payload, ensure_ascii=False)
    if wire:
        original = httpx.Client
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}, "finish_reason": "stop"}]})
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    else:
        monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.session_state["last_result"] = ChapterResult(plan=plan, draft=TEXT, review=ChapterReview(verdict="pass"), ai_flavor={})
    app.session_state["last_result_meta"] = {"project": "MyNovel", "chapter_id": "001", "text_sha256": hashlib.sha256((TEXT + "\n").encode()).hexdigest()}
    app.run()
    next(x for x in app.text_input if x.label == "Base URL").set_value("https://synthetic.invalid/v1")
    next(x for x in app.text_input if x.label == "Model").set_value("synthetic")
    app.run()
    assert not app.exception
    return app, store, calls, cards


def canon(store):
    return {p.relative_to(store.root).as_posix(): p.read_bytes() for p in store.root.rglob("*")
            if p.is_file() and "/proposals/" not in p.as_posix()}


def accept(app):
    next(x for x in app.checkbox if x.label == "我接受这一版正文作为记忆来源").check().run()
    next(x for x in app.checkbox if x.label == "我已查看并接受这份记忆变更").check().run()
    app.button(key="btn_memory_apply").click().run()


def test_actual_wire_prepare_preview_two_decisions_commit_and_repeated_rerun(monkeypatch, tmp_path):
    app, store, calls, cards = fixture(monkeypatch, tmp_path, wire=True)
    before = canon(store)
    app.button(key="btn_memory_propose").click().run()
    assert not app.exception and len(calls) == 1
    assert "测试读者" in json.dumps(calls[0], ensure_ascii=False)
    assert calls[0]["max_tokens"] == 8192
    assert canon(store) == before and app.session_state["characters"] == cards
    assert app.button(key="btn_memory_apply").disabled
    next(x for x in app.checkbox if x.label == "我接受这一版正文作为记忆来源").check().run()
    assert app.button(key="btn_memory_apply").disabled
    next(x for x in app.checkbox if x.label == "我已查看并接受这份记忆变更").check().run()
    assert not app.button(key="btn_memory_apply").disabled
    app.button(key="btn_memory_apply").click().run()
    assert not app.exception
    assert store.read_json("MyNovel", "memory/characters.json")[0]["knows"] == ["钥匙用途"]
    assert store.read_json("MyNovel", "memory/characters.json")[0]["voice_extension"] == {"keep": True}
    assert store.read_json("MyNovel", "memory/story_bible.json")["custom_rule"] == {"preserve": True}
    assert store.load_story_state("MyNovel")["custom_ledger"] == {"keep": True}
    after = canon(store)
    app.run(); app.run()
    assert app.button(key="btn_memory_apply").disabled and canon(store) == after
    assert len(calls) == 1


def test_pending_proposal_restores_after_app_restart_without_reextracting(monkeypatch, tmp_path):
    app, store, calls, cards = fixture(monkeypatch, tmp_path)
    before = canon(store)
    app.button(key="btn_memory_propose").click().run()
    assert not app.exception and canon(store) == before
    restarted = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not restarted.exception
    assert restarted.session_state["last_result"] is None
    restarted.button(key="btn_memory_load").click().run()
    assert not restarted.exception and len(calls) == 1
    assert restarted.button(key="btn_memory_apply").disabled
    accept(restarted)
    assert not restarted.exception and len(calls) == 1
    assert restarted.session_state["characters"][0]["knows"] == ["钥匙用途"]


@pytest.mark.parametrize("kind", ["chapter", "cards", "context"])
def test_after_preview_changed_source_or_author_context_cannot_commit(monkeypatch, tmp_path, kind):
    app, store, calls, cards = fixture(monkeypatch, tmp_path)
    app.button(key="btn_memory_propose").click().run()
    assert not app.exception
    if kind == "chapter": store.write_chapter("MyNovel", "001", "作者的新版本正文。")
    elif kind == "cards": store.write_json("MyNovel", "memory/characters.json", [{"name": "舟", "knows": ["作者新增"]}])
    else: app.text_area(key="premise").set_value("作者的新核心设定").run()
    before = canon(store)
    accept(app)
    assert app.exception and canon(store) == before and len(calls) == 1
    assert app.session_state["characters"] == cards


@pytest.mark.parametrize("kind", ["chapter", "cards"])
def test_model_completion_rechecks_sources_before_even_saving_candidate(monkeypatch, tmp_path, kind):
    changed = []
    def change(store):
        if kind == "chapter": store.write_chapter("MyNovel", "001", "作者已换稿。")
        else: store.write_json("MyNovel", "memory/characters.json", [{"name": "舟", "knows": ["作者新增"]}])
        changed.append(canon(store))
    app, store, calls, cards = fixture(monkeypatch, tmp_path, callback=change)
    app.button(key="btn_memory_propose").click().run()
    assert app.exception and len(calls) == 1
    assert canon(store) == changed[0]
    assert not list(store.project_dir("MyNovel").glob("memory/proposals/*/*.json"))
    assert app.session_state["characters"] == cards


def test_foreign_model_chapter_never_writes_other_chapter_or_canon(monkeypatch, tmp_path):
    app, store, calls, cards = fixture(monkeypatch, tmp_path, output={"chapter_id": "elsewhere", "summary": "不属于本章"})
    before = canon(store)
    app.button(key="btn_memory_propose").click().run()
    assert app.exception and canon(store) == before and len(calls) == 1
    assert not store._path("MyNovel", "memory/extractions/elsewhere.json").exists()


def test_project_switch_keeps_pending_candidates_with_their_own_book(monkeypatch, tmp_path):
    app, store, calls, cards = fixture(monkeypatch, tmp_path)
    app.button(key="btn_memory_propose").click().run()
    saved = app.session_state["memory_candidate_json"]
    project_input = app.text_input(key="project_name")
    project_input.set_value("OtherBook").run()
    assert not app.exception and app.session_state["memory_candidate_json"] is None
    assert not list(store.project_dir("OtherBook").glob("memory/proposals/*/*.json"))
    app.text_input(key="project_name").set_value("MyNovel").run()
    assert not app.exception and app.session_state["memory_candidate_json"] == saved
    assert len(calls) == 1 and app.button(key="btn_memory_apply").disabled


def test_commit_failure_does_not_publish_ui_then_restart_recovers_existing_confirmation(monkeypatch, tmp_path):
    from novel_ai.memory_commit import INTENT_PATH
    app, store, calls, cards = fixture(monkeypatch, tmp_path)
    app.button(key="btn_memory_propose").click().run()
    original = ProjectStore._write
    def fail(self, path, *a, **kw):
        if path.name == "story_state.json":
            raise OSError("synthetic interrupted batch")
        return original(self, path, *a, **kw)
    monkeypatch.setattr(ProjectStore, "_write", fail)
    accept(app)
    assert app.exception and app.session_state["characters"] == cards
    assert not app.session_state["last_memory_commit"]
    assert store._path("MyNovel", INTENT_PATH, internal=True).exists()
    monkeypatch.setattr(ProjectStore, "_write", original)
    restarted = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not restarted.exception and restarted.session_state["characters"][0]["knows"] == ["钥匙用途"]
    restarted.button(key="btn_memory_load").click().run()
    assert not restarted.exception and restarted.button(key="btn_memory_apply").disabled
    assert len(calls) == 1
