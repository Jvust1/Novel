"""Independent offline regressions for local story-setting source conflicts.

Synthetic AppTest input and MockTransport only; no browser or real model calls.
The Bible and flat outline deliberately remain separate atomic publications.
"""
import json
from copy import deepcopy

import pytest
from test_author_ui import button, configure_provider
from test_character_source_review import setup

from novel_ai.author_workflow import load_story_bible_source
from novel_ai.storage import ProjectStore

BASE = {
    "title": "MyNovel", "genre": "现实都市旧设定", "locked_facts": ["桥尚未修复"],
    "author_extension": {"notes": ["保留作者原始备注"], "keep": True},
}


def seeded(monkeypatch, tmp_path):
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", "memory/story_bible.json", deepcopy(BASE))
    store.write_json("MyNovel", "memory/outline.json", {"outline": "原有总纲"})
    return setup(monkeypatch, tmp_path)


def paths(store):
    root = store.project_dir("MyNovel")
    return root / "memory/story_bible.json", root / "memory/outline.json"


def edit_settings(app):
    app.text_input(key="genre").set_value("本会话未保存的历史设定")
    app.text_area(key="locked_text").set_value("新锁定事实仍待核对")
    app.text_area(key="outline").set_value("本会话未保存的总纲")


def assert_edits(app):
    assert app.session_state["genre"] == "本会话未保存的历史设定"
    assert app.session_state["locked_text"] == "新锁定事实仍待核对"
    assert app.session_state["outline"] == "本会话未保存的总纲"


def test_stale_save_preserves_newer_files_and_all_session_edits(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    baseline = app.session_state["story_bible_source_sha256"]
    source = deepcopy(app.session_state["memory_source_bible"])
    edit_settings(app)
    newer = {**BASE, "genre": "另一会话的新科幻设定", "locked_facts": ["桥已拆除"],
             "new_custom_field": {"preserve": ["另一会话作者备注"]}}
    store.write_json("MyNovel", "memory/story_bible.json", newer)
    store.write_json("MyNovel", "memory/outline.json", {"outline": "另一会话的新总纲", "custom": "保留"})
    before = [path.read_bytes() for path in paths(store)]
    for _ in range(2):
        button(app, "保存故事设定到本地").click().run()
        assert app.error and not app.exception
        assert any("已变化" in item.value for item in app.error)
        assert [path.read_bytes() for path in paths(store)] == before
        assert app.session_state["story_bible_source_sha256"] == baseline
        assert app.session_state["memory_source_bible"] == source
        assert_edits(app)
    assert calls == []


@pytest.mark.parametrize("initially_missing", [True, False], ids=["missing-to-empty", "empty-to-missing"])
def test_missing_file_and_saved_empty_object_have_distinct_sources(monkeypatch, tmp_path, initially_missing):
    store = ProjectStore(tmp_path / "data")
    if not initially_missing:
        store.write_json("MyNovel", "memory/story_bible.json", {})
    app, store, calls = setup(monkeypatch, tmp_path)
    baseline = app.session_state["story_bible_source_sha256"]
    assert (baseline is None) is initially_missing
    bible_path, outline_path = paths(store)
    if initially_missing:
        store.write_json("MyNovel", "memory/story_bible.json", {})
    else:
        bible_path.unlink()
    actual = load_story_bible_source(store, "MyNovel")
    assert actual["bible"] == {} and actual["sha256"] != baseline
    edit_settings(app)
    button(app, "保存故事设定到本地").click().run()
    assert app.error and not app.exception
    assert app.session_state["story_bible_source_sha256"] == baseline
    assert bible_path.exists() is initially_missing
    if initially_missing:
        assert json.loads(bible_path.read_text()) == {}
    assert not outline_path.exists()
    assert_edits(app)
    app.button(key="btn_plan").click().run()
    assert app.exception and calls == []


def test_own_save_preserves_extensions_invalidates_old_plan_and_allows_replan(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 1
    old_plan = app.session_state["pending_plan_json"]
    old_meta = deepcopy(app.session_state["pending_plan_meta"])
    edit_settings(app)
    button(app, "保存故事设定到本地").click().run()
    assert not app.exception and not app.error
    saved = store.read_json("MyNovel", "memory/story_bible.json")
    assert saved["author_extension"] == BASE["author_extension"]
    assert saved["genre"] == "本会话未保存的历史设定"
    assert saved["locked_facts"] == ["新锁定事实仍待核对"]
    assert app.session_state["memory_source_bible"] == saved
    assert app.session_state["story_bible_source_sha256"] == load_story_bible_source(store, "MyNovel")["sha256"]
    assert app.session_state["story_bible_source_sha256"] != old_meta["story_bible_source_sha256"]
    app.button(key="btn_draft").click().run()
    assert app.exception and len(calls) == 1
    assert app.session_state["pending_plan_json"] == old_plan
    assert app.session_state["pending_plan_meta"] == old_meta
    assert store.all_chapter_texts("MyNovel") == []
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 2
    assert app.session_state["pending_plan_meta"]["story_bible_source_sha256"] == app.session_state["story_bible_source_sha256"]
    app.button(key="btn_draft").click().run()
    assert not app.exception and len(calls) == 3
    assert "本会话未保存的历史设定" in json.dumps(calls[-1], ensure_ascii=False)
    assert len(store.all_chapter_texts("MyNovel")) == 1
    assert not (store.project_dir("MyNovel") / "memory/memory_commits").exists()


@pytest.mark.parametrize("failure", ["bible-write", "outline-write", "readback-error", "readback-mismatch"])
def test_failed_save_keeps_old_ui_source_and_preserves_partial_publication_boundary(monkeypatch, tmp_path, failure):
    app, store, calls = seeded(monkeypatch, tmp_path)
    baseline = app.session_state["story_bible_source_sha256"]
    source = deepcopy(app.session_state["memory_source_bible"])
    bible_path, outline_path = paths(store)
    before_bible, before_outline = bible_path.read_bytes(), outline_path.read_bytes()
    edit_settings(app)
    original_write, original_read = ProjectStore._write, ProjectStore.read_json
    bible_published = []

    def write(self, path, *args, **kwargs):
        if (failure == "bible-write" and path.name == "story_bible.json"
                or failure == "outline-write" and path.name == "outline.json"):
            raise OSError("synthetic settings publication interrupted: " + failure)
        result = original_write(self, path, *args, **kwargs)
        if path.name == "story_bible.json":
            bible_published.append(path.read_bytes())
        return result

    def read(self, project, relative, *args, **kwargs):
        value = original_read(self, project, relative, *args, **kwargs)
        if relative == "memory/story_bible.json" and bible_published:
            if failure == "readback-error":
                raise OSError("synthetic settings readback unavailable")
            if failure == "readback-mismatch":
                return {**value, "genre": "synthetic inconsistent readback"}
        return value

    monkeypatch.setattr(ProjectStore, "_write", write)
    monkeypatch.setattr(ProjectStore, "read_json", read)
    button(app, "保存故事设定到本地").click().run()
    assert app.error and not app.exception
    assert not any("已保存并读回本地故事设定" in item.value for item in app.success)
    assert app.session_state["story_bible_source_sha256"] == baseline
    assert app.session_state["memory_source_bible"] == source
    assert_edits(app)
    assert calls == []
    monkeypatch.setattr(ProjectStore, "_write", original_write)
    monkeypatch.setattr(ProjectStore, "read_json", original_read)
    if failure == "bible-write":
        assert bible_path.read_bytes() == before_bible
        assert outline_path.read_bytes() == before_outline
        assert bible_published == []
    else:
        assert len(bible_published) == 1 and bible_path.read_bytes() == bible_published[0]
        assert bible_path.read_bytes() != before_bible
        assert json.loads(bible_path.read_bytes())["author_extension"] == BASE["author_extension"]
        if failure == "outline-write":
            assert outline_path.read_bytes() == before_outline
        else:
            assert json.loads(outline_path.read_bytes()) == {"outline": "本会话未保存的总纲"}
        app.button(key="btn_plan").click().run()
        assert app.exception and calls == []
        assert store.all_chapter_texts("MyNovel") == []
        assert app.session_state["story_bible_source_sha256"] == baseline
        assert_edits(app)


def test_project_switch_retains_cached_baseline_and_blocks_stale_saved_settings(monkeypatch, tmp_path):
    app, store, calls = seeded(monkeypatch, tmp_path)
    baseline = app.session_state["story_bible_source_sha256"]
    edit_settings(app)
    app.run()
    other = {"title": "OtherBook", "genre": "乙书科幻", "author_extension": "乙书备注"}
    store.write_json("OtherBook", "memory/story_bible.json", other)
    app.text_input(key="project_name").set_value("OtherBook").run()
    assert not app.exception
    assert app.session_state["genre"] == other["genre"]
    assert app.session_state["story_bible_source_sha256"] == load_story_bible_source(store, "OtherBook")["sha256"]
    newer = {**BASE, "genre": "甲书另一会话的新设定", "new_extension": ["保留"]}
    store.write_json("MyNovel", "memory/story_bible.json", newer)
    store.write_json("MyNovel", "memory/outline.json", {"outline": "甲书新总纲"})
    before = [path.read_bytes() for path in paths(store)]
    app.text_input(key="project_name").set_value("MyNovel").run()
    assert not app.exception
    assert app.session_state["story_bible_source_sha256"] == baseline
    assert app.session_state["memory_source_bible"] == BASE
    assert_edits(app)
    configure_provider(app)
    button(app, "保存故事设定到本地").click().run()
    assert app.error and not app.exception
    app.button(key="btn_plan").click().run()
    assert app.exception and calls == []
    assert [path.read_bytes() for path in paths(store)] == before
    assert store.read_json("OtherBook", "memory/story_bible.json") == other
    assert_edits(app)
