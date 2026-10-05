"""Offline UI recovery, source binding and cross-session settings regressions.

Real Streamlit reruns and bounded provider requests over MockTransport. All
content is synthetic; there is no browser, model service or remote publication.
"""
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from test_author_ui import button, configure_provider, run_app
from test_character_source_review import PROSE, setup
from test_story_settings_review import BASE, assert_edits, edit_settings, paths, seeded

from novel_ai import settings_ui
from novel_ai.settings_commit import (
    INTENT_PATH,
    SETTINGS_PATHS,
    commit_settings_bundle,
    load_settings_bundle,
    prepare_settings_save,
)
from novel_ai.storage import ProjectStore


def fail_outline(monkeypatch):
    original = ProjectStore._write

    def write(self, path, *args, **kwargs):
        if path.name == "outline.json":
            raise OSError("synthetic outline publication interrupted")
        return original(self, path, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "_write", write)
    return original


def raw_files(store, project="MyNovel"):
    root = store.project_dir(project)
    return {p: (root / p).read_bytes() if (root / p).exists() else None for p in SETTINGS_PATHS}


def receipts(store, project="MyNovel"):
    root = store.project_dir(project) / "memory/settings_commits"
    return {p.name: p.read_bytes() for p in root.glob("*.json")}


def assert_only_recovery_controls(app):
    assert not app.exception
    assert {item.label for item in app.button} == {"保存故事设定到本地", "重试这次故事设定保存"}
    assert len(app.get("download_button")) == 1
    assert app.get("download_button")[0].proto.label == "下载当前故事设定与总纲草案"


@pytest.mark.parametrize("action", ["btn_plan", "btn_draft", "btn_oneshot"])
def test_external_outline_only_update_blocks_lost_save_and_every_generation_entry(monkeypatch, tmp_path, action):
    app, store, calls = seeded(monkeypatch, tmp_path)
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 1
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    meta = deepcopy(app.session_state["pending_plan_meta"])
    plan = app.session_state["pending_plan_json"]
    bible_before = paths(store)[0].read_bytes()
    edit_settings(app)
    newer_outline = {"outline": "另一会话只改了总纲", "author_extension": {"keep": ["新总纲备注"]}}
    store.write_json("MyNovel", "memory/outline.json", newer_outline)
    before = raw_files(store)
    assert before[SETTINGS_PATHS[0]] == bible_before
    button(app, "保存故事设定到本地").click().run()
    assert app.error and not app.exception
    assert any("总纲已变化" in item.value for item in app.error)
    assert raw_files(store) == before
    assert app.session_state["settings_pending"] is None
    assert app.session_state["settings_snapshot"] == snapshot
    assert not (store.project_dir("MyNovel") / INTENT_PATH).exists()
    assert receipts(store) == {}
    assert_edits(app)
    app.button(key=action).click().run()
    assert app.exception and len(calls) == 1
    assert raw_files(store) == before
    assert app.session_state["pending_plan_json"] == plan
    assert app.session_state["pending_plan_meta"] == meta
    assert app.session_state["last_result"] is None
    assert not store.all_chapter_texts("MyNovel")
    assert_edits(app)


def test_same_bible_failed_outline_stops_all_later_tabs_and_retains_hidden_edits(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    # First normalize the legacy JSON to the exact UI payload. The failing
    # operation below really changes only the outline, including its raw bytes.
    button(app, "保存故事设定到本地").click().run()
    assert not app.error and not app.exception
    app.button(key="btn_plan").click().run()
    assert len(calls) == 1 and not app.exception
    before = raw_files(store)
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    plan = app.session_state["pending_plan_json"]
    meta = deepcopy(app.session_state["pending_plan_meta"])
    edited_plan = json.loads(app.text_area(key="plan_editor").value)
    edited_plan["scenes"][0]["choice"] = "作者尚未保存的独立场景选择"
    hidden = {
        "new_char_name": "新人物待核对", "hierarchy_markdown": "# 未保存的层级大纲",
        "chapter_goal": "未保存的章节目标", "chapter_notes": "未保存的写作要求",
        "release_hook": "未保存的发布看点", "plan_editor": json.dumps(edited_plan, ensure_ascii=False),
    }
    for key, value in hidden.items():
        widgets = app.text_input if key in {"new_char_name", "release_hook"} else app.text_area
        widgets(key=key).set_value(value)
    app.text_area(key="outline").set_value("只改总纲，故事设定完全相同")
    original = fail_outline(monkeypatch)
    button(app, "保存故事设定到本地").click().run()
    assert app.error
    assert_only_recovery_controls(app)
    pending = deepcopy(app.session_state["settings_pending"])
    assert pending["files"][SETTINGS_PATHS[0]].encode() == before[SETTINGS_PATHS[0]]
    assert pending["files"][SETTINGS_PATHS[1]].encode() != before[SETTINGS_PATHS[1]]
    assert raw_files(store) == before
    assert app.session_state["settings_snapshot"] == snapshot
    assert app.session_state["pending_plan_json"] == plan
    assert app.session_state["pending_plan_meta"] == meta
    for _ in range(2):
        app.run()
        assert_only_recovery_controls(app)
        assert app.session_state["settings_pending"] == pending
        assert app.session_state["settings_snapshot"] == snapshot
        assert {key: app.session_state[key] for key in hidden} == hidden
        assert raw_files(store) == before
        assert len(calls) == 1
    monkeypatch.setattr(ProjectStore, "_write", original)
    app.button(key="retry_settings_save").click().run()
    assert not app.error and not app.exception
    assert app.session_state["settings_pending"] is None
    assert {key: app.session_state[key] for key in hidden} == hidden
    assert raw_files(store) == {p: value.encode() for p, value in pending["files"].items()}
    app.button(key="btn_draft").click().run()
    assert app.exception and len(calls) == 1
    assert not store.all_chapter_texts("MyNovel")


def test_changed_displayed_input_refuses_retry_without_replacing_frozen_operation(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    edit_settings(app)
    original = fail_outline(monkeypatch)
    button(app, "保存故事设定到本地").click().run()
    pending = deepcopy(app.session_state["settings_pending"])
    before = raw_files(store)
    intent_path = store.project_dir("MyNovel") / INTENT_PATH
    intent = intent_path.read_bytes()
    monkeypatch.setattr(ProjectStore, "_write", original)
    app.text_area(key="outline").set_value("失败以后继续写的新总纲，不是原操作")
    for _ in range(2):
        app.button(key="retry_settings_save").click().run()
        assert app.error and not app.exception
        assert any("输入不一致" in item.value for item in app.error)
        assert_only_recovery_controls(app)
        assert app.session_state["settings_pending"] == pending
        assert app.session_state["settings_snapshot"] == snapshot
        assert app.session_state["outline"] == "失败以后继续写的新总纲，不是原操作"
        assert raw_files(store) == before
        assert intent_path.read_bytes() == intent
        assert receipts(store) == {}
    app.text_area(key="outline").set_value("本会话未保存的总纲")
    app.button(key="retry_settings_save").click().run()
    assert not app.error and not app.exception
    assert app.session_state["settings_pending"] is None
    assert raw_files(store) == {p: value.encode() for p, value in pending["files"].items()}
    assert_edits(app)
    assert calls == []


def test_fresh_session_recovers_complete_pair_before_exposing_settings_or_generation(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    edit_settings(app)
    original = fail_outline(monkeypatch)
    button(app, "保存故事设定到本地").click().run()
    pending = deepcopy(app.session_state["settings_pending"])
    stale_snapshot = deepcopy(app.session_state["settings_snapshot"])
    assert raw_files(store)[SETTINGS_PATHS[0]] == pending["files"][SETTINGS_PATHS[0]].encode()
    assert raw_files(store)[SETTINGS_PATHS[1]] != pending["files"][SETTINGS_PATHS[1]].encode()
    monkeypatch.setattr(ProjectStore, "_write", original)
    fresh = run_app(monkeypatch, tmp_path)
    assert not fresh.exception and not fresh.error
    assert fresh.session_state["settings_pending"] is None
    current = load_settings_bundle(store, "MyNovel")
    assert fresh.session_state["settings_snapshot"] == current
    assert fresh.session_state["memory_source_bible"] == current["bible"]
    assert current["bible"]["author_extension"] == BASE["author_extension"]
    assert_edits(fresh)
    assert raw_files(store) == {p: value.encode() for p, value in pending["files"].items()}
    assert not (store.project_dir("MyNovel") / INTENT_PATH).exists()
    saved = list(receipts(store).values())
    assert len(saved) == 1 and json.loads(saved[0])["request_id"] == pending["request_id"]
    # A different session's recovery does not silently authorize the old UI.
    app.run()
    assert_only_recovery_controls(app)
    assert app.session_state["settings_pending"] == pending
    assert app.session_state["settings_snapshot"] == stale_snapshot
    configure_provider(fresh)
    fresh.button(key="btn_plan").click().run()
    assert not fresh.exception and len(calls) == 1
    assert fresh.session_state["pending_plan_meta"]["settings_source_sha256"] == current["sha256"]
    assert "本会话未保存的总纲" in json.dumps(calls[0], ensure_ascii=False)


@pytest.mark.parametrize("fault_on_return", [False, True], ids=["recovered-on-return", "fault-still-active"])
def test_cached_project_switch_keeps_pending_request_baseline_and_edits_until_exact_retry(monkeypatch, tmp_path, fault_on_return):
    app, store, calls = seeded(monkeypatch, tmp_path)
    other_bible = {"title": "OtherBook", "genre": "乙书设定"}
    store.write_json("OtherBook", SETTINGS_PATHS[0], other_bible)
    store.write_json("OtherBook", SETTINGS_PATHS[1], {"outline": "乙书总纲"})
    other_before = raw_files(store, "OtherBook")
    edit_settings(app)
    original = fail_outline(monkeypatch)
    button(app, "保存故事设定到本地").click().run()
    pending = deepcopy(app.session_state["settings_pending"])
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    if not fault_on_return:
        monkeypatch.setattr(ProjectStore, "_write", original)
    app.text_input(key="project_name").set_value("OtherBook").run()
    assert not app.exception and app.session_state["settings_pending"] is None
    assert app.session_state["genre"] == "乙书设定"
    assert app.session_state["outline"] == "乙书总纲"
    app.text_input(key="project_name").set_value("MyNovel").run()
    if fault_on_return:
        # A failed automatic recovery must not replace the source book's cache
        # with the target book or with Streamlit's partially cleaned-up widgets.
        assert app.exception
        assert app.session_state["seeded_project"] == "OtherBook"
        cached = app.session_state["_project_drafts"]["MyNovel"]
        assert cached["settings_pending"] == pending
        assert cached["settings_snapshot"] == snapshot
        assert cached["genre"] == "本会话未保存的历史设定"
        assert cached["locked_text"] == "新锁定事实仍待核对"
        assert cached["outline"] == "本会话未保存的总纲"
        assert raw_files(store, "OtherBook") == other_before
        monkeypatch.setattr(ProjectStore, "_write", original)
        app.run()
    assert_only_recovery_controls(app)
    assert app.session_state["settings_pending"] == pending
    assert app.session_state["settings_snapshot"] == snapshot
    assert_edits(app)
    app.run()
    assert_only_recovery_controls(app)
    assert app.session_state["settings_pending"] == pending
    assert app.session_state["settings_snapshot"] == snapshot
    app.button(key="retry_settings_save").click().run()
    assert not app.exception and not app.error
    assert app.session_state["settings_pending"] is None
    assert app.session_state["settings_snapshot"] == load_settings_bundle(store, "MyNovel")
    assert raw_files(store) == {p: value.encode() for p, value in pending["files"].items()}
    assert raw_files(store, "OtherBook") == other_before
    assert len(receipts(store)) == 1
    assert_edits(app)
    assert calls == []


def test_historical_retry_preserves_new_complete_pair_without_rebasing_old_ui(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    original = settings_ui.save_workbench_story_settings

    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("synthetic response lost after durable settings receipt")

    monkeypatch.setattr(settings_ui, "save_workbench_story_settings", lose_response)
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    edit_settings(app)
    button(app, "保存故事设定到本地").click().run()
    assert app.error
    pending = deepcopy(app.session_state["settings_pending"])
    original_receipts = receipts(store)
    assert len(original_receipts) == 1
    monkeypatch.setattr(settings_ui, "save_workbench_story_settings", original)
    recovered = load_settings_bundle(store, "MyNovel")
    newer = {**recovered["bible"], "genre": "另一会话的新完整设定", "new_author_field": ["应保留"]}
    files = prepare_settings_save(recovered, newer, "另一会话的新完整总纲")
    result = commit_settings_bundle(store, "MyNovel", files=files, expected_before=recovered["sha256"], request_id=uuid4().hex)
    before = raw_files(store)
    before_receipts = receipts(store)
    assert not result["historical"] and len(before_receipts) == 2
    assert all(before_receipts[name] == raw for name, raw in original_receipts.items())
    for _ in range(2):
        app.button(key="retry_settings_save").click().run()
        assert app.error and any("已有回执" in item.value for item in app.error)
        assert_only_recovery_controls(app)
        assert raw_files(store) == before
        assert receipts(store) == before_receipts
        assert app.session_state["settings_pending"] == pending
        assert app.session_state["settings_snapshot"] == snapshot
        assert app.session_state["memory_source_bible"] == snapshot["bible"]
        assert_edits(app)
    fresh = run_app(monkeypatch, tmp_path)
    assert not fresh.error and not fresh.exception
    assert fresh.session_state["settings_pending"] is None
    assert fresh.session_state["genre"] == newer["genre"]
    assert fresh.session_state["outline"] == "另一会话的新完整总纲"
    assert fresh.session_state["settings_snapshot"] == result["current"]
    assert calls == []


def test_own_outline_only_save_invalidates_plan_until_replan_uses_new_pair(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    button(app, "保存故事设定到本地").click().run()
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 1
    snapshot = deepcopy(app.session_state["settings_snapshot"])
    meta = deepcopy(app.session_state["pending_plan_meta"])
    old_plan = app.session_state["pending_plan_json"]
    app.text_area(key="outline").set_value("仅本会话新保存的总纲")
    button(app, "保存故事设定到本地").click().run()
    assert not app.error and not app.exception
    current = app.session_state["settings_snapshot"]
    assert current["sha256"][SETTINGS_PATHS[0]] == snapshot["sha256"][SETTINGS_PATHS[0]]
    assert current["sha256"][SETTINGS_PATHS[1]] != snapshot["sha256"][SETTINGS_PATHS[1]]
    assert app.session_state["story_bible_source_sha256"] == meta["story_bible_source_sha256"]
    assert app.session_state["pending_plan_meta"] == meta
    app.button(key="btn_draft").click().run()
    assert app.exception and len(calls) == 1
    assert app.session_state["pending_plan_json"] == old_plan
    assert not store.all_chapter_texts("MyNovel")
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 2
    assert app.session_state["pending_plan_meta"]["settings_source_sha256"] == current["sha256"]
    assert "仅本会话新保存的总纲" in json.dumps(calls[-1], ensure_ascii=False)
    app.button(key="btn_draft").click().run()
    assert not app.exception and len(calls) == 3
    assert len(store.all_chapter_texts("MyNovel")) == 1


@pytest.mark.parametrize("phase", ["fallback", "plan-response", "draft-response", "oneshot-response"])
def test_outline_only_mutation_during_http_blocks_next_request_and_result_publication(monkeypatch, tmp_path, phase):
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", SETTINGS_PATHS[0], deepcopy(BASE))
    store.write_json("MyNovel", SETTINGS_PATHS[1], {"outline": "原有总纲"})
    responses = []

    def mutate(payload):
        is_plan = "章节策划" in payload["messages"][0]["content"]
        if phase in {"fallback", "plan-response"} or not is_plan:
            store.write_json("MyNovel", SETTINGS_PATHS[1], {"outline": "HTTP 期间外部修改总纲"})
            responses.append(deepcopy(payload))
            if phase == "fallback":
                return httpx.Response(400, json={"error": {
                    "message": "response_format is not supported", "param": "response_format",
                    "code": "unsupported_parameter",
                }})
            if not is_plan:
                return httpx.Response(200, json={"choices": [{"message": {"content": PROSE}, "finish_reason": "stop"}]})
        return None

    app, store, calls = setup(monkeypatch, tmp_path, callback=mutate)
    if phase == "draft-response":
        app.button(key="btn_plan").click().run()
        assert not app.exception and len(calls) == 1
    plan = app.session_state["pending_plan_json"]
    meta = deepcopy(app.session_state["pending_plan_meta"])
    action = "btn_draft" if phase == "draft-response" else ("btn_plan" if phase == "plan-response" else "btn_oneshot")
    app.button(key=action).click().run()
    assert app.exception or app.error
    assert len(responses) == 1
    assert len(calls) == (2 if phase in {"draft-response", "oneshot-response"} else 1)
    assert app.session_state["pending_plan_json"] == plan
    assert app.session_state["pending_plan_meta"] == meta
    assert app.session_state["last_result"] is None
    assert not store.all_chapter_texts("MyNovel")
    assert not list((store.project_dir("MyNovel") / "memory/plans").glob("*.json"))
