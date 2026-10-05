"""Actual offline HTTP stages reject a changed saved story Bible."""
import json

import httpx
import pytest
from test_author_ui import configure_provider, run_app
from test_character_source_bindings import PLAN, PROSE

from novel_ai.storage import ProjectStore

OLD = {"title": "归尺", "genre": "历史纪实", "locked_facts": ["没有超自然能力"],
       "custom_rule": {"author": ["保留这份原始设定"]}}
NEW = {"title": "归尺", "genre": "太空科幻", "locked_facts": ["全部场景在轨道站"],
       "custom_rule": {"author": ["另一会话的新设定"]}}


def workspace(monkeypatch, tmp_path, changed_stage=None):
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", "memory/story_bible.json", OLD)
    calls = []
    reviews = []
    original = httpx.Client

    def serve(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == changed_stage:
            store.write_json("MyNovel", "memory/story_bible.json", NEW)
        system = payload["messages"][0]["content"]
        if "章节策划" in system:
            text = json.dumps(PLAN, ensure_ascii=False)
        elif "严苛的网络小说章节编辑" in system:
            reviews.append(payload)
            text = json.dumps({"verdict": "revise" if len(reviews) == 1 else "pass", "issues": []})
        else:
            text = PROSE
        return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}]})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(serve)))
    app = run_app(monkeypatch, tmp_path)
    configure_provider(app)
    app.radio[0].set_value("精修")
    return app, store, calls


@pytest.mark.parametrize("stage", [1, 2, 3, 4, 5], ids=["plan", "draft", "review", "repair", "rereview"])
def test_saved_story_change_stops_each_actual_http_stage(monkeypatch, tmp_path, stage):
    app, store, calls = workspace(monkeypatch, tmp_path, stage)
    app.button(key="btn_oneshot").click().run()
    assert app.exception or app.error
    assert len(calls) == stage
    assert not store.all_chapter_texts("MyNovel")
    assert store.read_json("MyNovel", "memory/story_bible.json") == NEW
    assert app.session_state["genre"] == OLD["genre"]
    assert app.session_state["memory_source_bible"] == OLD
    assert app.session_state["last_result"] is None


def test_final_candidate_publication_rechecks_saved_story(monkeypatch, tmp_path):
    import novel_ai.longform_tools as longform

    app, store, calls = workspace(monkeypatch, tmp_path)
    original = longform.near_duplicate_chapters

    def changed_after_result(*args, **kwargs):
        result = original(*args, **kwargs)
        store.write_json("MyNovel", "memory/story_bible.json", NEW)
        return result

    monkeypatch.setattr(longform, "near_duplicate_chapters", changed_after_result)
    app.button(key="btn_oneshot").click().run()
    assert len(calls) == 5
    assert app.exception or app.error
    assert not store.all_chapter_texts("MyNovel")
    assert app.session_state["last_result"] is None
    assert app.session_state["memory_source_bible"] == OLD


@pytest.mark.parametrize("button_key", ["btn_plan", "btn_oneshot"])
def test_changed_saved_genre_stops_before_any_dispatch(monkeypatch, tmp_path, button_key):
    app, store, calls = workspace(monkeypatch, tmp_path)
    store.write_json("MyNovel", "memory/story_bible.json", NEW)
    app.button(key=button_key).click().run()
    assert app.exception or app.error
    assert calls == []
    assert not store.all_chapter_texts("MyNovel")
    assert app.session_state["memory_source_bible"] == OLD
