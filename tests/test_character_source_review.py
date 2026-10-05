"""Independent offline AppTest regressions for character-source reconciliation.

All prose is synthetic. Requests use the real bounded provider over MockTransport;
no model service, browser, private manuscript, or remote storage is involved.
"""
import json
from copy import deepcopy

import httpx
import pytest
from test_author_ui import button, configure_provider, run_app
from test_memory_ui import accept
from test_memory_ui import fixture as memory_fixture

from novel_ai.author_workflow import load_character_source
from novel_ai.storage import ProjectStore

CARDS = [{
    "name": "闻舟", "speech": "只用短句核对事实", "locked": True,
    "knows": ["渡船已经靠岸"], "does_not_know": ["钥匙的来历"],
    "author_extension": {"voice": {"rhythm": ["停顿", "短句"]}, "keep": True},
}]
PLAN = {
    "chapter_title": "石阶边", "chapter_promise": "归还借来的钥匙",
    "scenes": [{"scene_no": 1, "pov": "闻舟", "objective": "归还钥匙",
                "opposition": "守船人已离开", "choice": "留在岸边等候",
                "cost": "错过末班船", "state_change": "取得新的约定"}],
}
PROSE = "闻舟把钥匙放在石阶上。守船人没有回来，他便坐下，任末班船越过河湾。"


def wire(monkeypatch, callback=None):
    calls = []
    original = httpx.Client

    def handle(request):
        payload = json.loads(request.content)
        calls.append(deepcopy(payload))
        response = callback(payload) if callback else None
        if response is not None:
            return response
        content = (json.dumps(PLAN, ensure_ascii=False)
                   if "章节策划" in payload["messages"][0]["content"] else PROSE)
        return httpx.Response(200, json={"choices": [{
            "message": {"content": content}, "finish_reason": "stop",
        }]})

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    return calls


def setup(monkeypatch, tmp_path, *, saved=True, callback=None):
    store = ProjectStore(tmp_path / "data")
    if saved:
        store.write_json("MyNovel", "memory/characters.json", deepcopy(CARDS))
    calls = wire(monkeypatch, callback)
    app = run_app(monkeypatch, tmp_path)
    assert not app.exception
    configure_provider(app)
    return app, store, calls


def add_unsaved(app):
    app.text_input(key="new_char_name").set_value("叶宁")
    app.text_input(key="new_char_speech").set_value("先问日期，再答问题")
    button(app, "添加人物").click().run()
    assert not app.exception
    assert app.session_state["characters"][-1]["name"] == "叶宁"


def changed_cards(version):
    cards = deepcopy(CARDS)
    cards[0]["speech"] = "当前独立保存版本" + version
    cards[0]["author_extension"]["voice"]["rhythm"].append(version)
    return cards


def cards_path(store):
    return store.project_dir("MyNovel") / "memory/characters.json"


def reload_checkbox(app, prefix="character_reload_"):
    return next(item for item in app.checkbox if str(item.key).startswith(prefix))


def choose_new_locks(app):
    next(item for item in app.multiselect if item.label.startswith("锁定人物")).set_value(["叶宁"])


@pytest.mark.parametrize("action", ["保存人物到本地", "应用锁定"], ids=["save", "lock"])
def test_stale_save_or_lock_preserves_session_and_newer_disk(monkeypatch, tmp_path, action):
    app, store, calls = setup(monkeypatch, tmp_path)
    baseline = app.session_state["characters_source_sha256"]
    add_unsaved(app)
    choose_new_locks(app)
    before = deepcopy(app.session_state["characters"])
    store.write_json("MyNovel", "memory/characters.json", changed_cards("B"))
    disk = cards_path(store).read_bytes()
    button(app, action).click().run()
    assert app.exception or app.error
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == baseline
    assert cards_path(store).read_bytes() == disk
    assert calls == []


@pytest.mark.parametrize("action", ["保存人物到本地", "应用锁定"], ids=["save", "lock"])
def test_interrupted_save_or_lock_does_not_publish_ui_changes(monkeypatch, tmp_path, action):
    app, store, calls = setup(monkeypatch, tmp_path)
    add_unsaved(app)
    choose_new_locks(app)
    before = deepcopy(app.session_state["characters"])
    digest = app.session_state["characters_source_sha256"]
    disk = cards_path(store).read_bytes()
    original = ProjectStore._write

    def interrupt(self, path, *args, **kwargs):
        if path.name == "characters.json":
            raise OSError("synthetic character write interruption before publication")
        return original(self, path, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "_write", interrupt)
    button(app, action).click().run()
    assert any("synthetic character write interruption before publication" in item.value for item in app.error)
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == digest
    assert cards_path(store).read_bytes() == disk
    assert calls == []


def test_unsaved_additions_can_plan_draft_and_save_all_nested_author_fields(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path)
    add_unsaved(app)
    unsaved = deepcopy(app.session_state["characters"])
    assert store.read_json("MyNovel", "memory/characters.json") == CARDS
    app.button(key="btn_plan").click().run()
    assert not app.exception
    app.button(key="btn_draft").click().run()
    assert not app.exception and len(calls) == 2
    assert all("先问日期，再答问题" in json.dumps(call, ensure_ascii=False) for call in calls)
    assert len(store.all_chapter_texts("MyNovel")) == 1
    assert store.read_json("MyNovel", "memory/characters.json") == CARDS
    button(app, "保存人物到本地").click().run()
    assert not app.exception
    assert store.read_json("MyNovel", "memory/characters.json") == unsaved
    assert app.session_state["characters"] == unsaved
    assert app.session_state["characters_source_sha256"] == load_character_source(store, "MyNovel")["sha256"]
    assert len(calls) == 2


def test_return_to_cached_book_retains_old_source_and_blocks_generation(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path)
    add_unsaved(app)
    before = deepcopy(app.session_state["characters"])
    digest = app.session_state["characters_source_sha256"]
    app.text_input(key="project_name").set_value("OtherBook").run()
    assert not app.exception and app.session_state["characters"] == []
    store.write_json("MyNovel", "memory/characters.json", changed_cards("B"))
    app.text_input(key="project_name").set_value("MyNovel").run()
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == digest
    configure_provider(app)
    app.button(key="btn_oneshot").click().run()
    assert app.exception or app.error
    assert calls == [] and not store.all_chapter_texts("MyNovel")
    assert app.session_state["characters"] == before


def test_reload_consent_for_b_cannot_discard_edits_for_unseen_c(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path)
    add_unsaved(app)
    before = deepcopy(app.session_state["characters"])
    digest = app.session_state["characters_source_sha256"]
    store.write_json("MyNovel", "memory/characters.json", changed_cards("B"))
    app.run()
    assert app.button(key="btn_reload_characters").disabled
    b_key = reload_checkbox(app).key
    reload_checkbox(app).check().run()
    assert not app.button(key="btn_reload_characters").disabled
    store.write_json("MyNovel", "memory/characters.json", changed_cards("C"))
    app.button(key="btn_reload_characters").click().run()
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == digest
    assert reload_checkbox(app).key != b_key and not reload_checkbox(app).value
    assert app.button(key="btn_reload_characters").disabled
    reload_checkbox(app).check().run()
    app.button(key="btn_reload_characters").click().run()
    assert not app.exception and app.session_state["characters"] == changed_cards("C")
    assert app.session_state["characters_source_sha256"] == load_character_source(store, "MyNovel")["sha256"]
    assert calls == []


def test_current_reload_keeps_old_plan_but_only_replanning_allows_new_prose(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path)
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 1
    plan = app.session_state["pending_plan_json"]
    meta = deepcopy(app.session_state["pending_plan_meta"])
    store.write_json("MyNovel", "memory/characters.json", changed_cards("B"))
    app.run()
    reload_checkbox(app).check().run()
    app.button(key="btn_reload_characters").click().run()
    assert not app.exception
    assert app.session_state["pending_plan_json"] == plan
    assert app.session_state["pending_plan_meta"] == meta
    app.button(key="btn_draft").click().run()
    assert app.exception or app.error
    assert len(calls) == 1 and not store.all_chapter_texts("MyNovel")
    app.button(key="btn_plan").click().run()
    assert not app.exception and len(calls) == 2
    assert "当前独立保存版本B" in json.dumps(calls[-1], ensure_ascii=False)
    app.button(key="btn_draft").click().run()
    assert not app.exception and len(calls) == 3
    assert "当前独立保存版本B" in json.dumps(calls[-1], ensure_ascii=False)
    assert len(store.all_chapter_texts("MyNovel")) == 1


def test_absent_source_is_not_equivalent_to_a_saved_empty_list(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path, saved=False)
    assert app.session_state["characters_source_sha256"] is None
    assert not cards_path(store).exists()
    store.write_json("MyNovel", "memory/characters.json", [])
    app.button(key="btn_oneshot").click().run()
    assert app.exception or app.error
    assert calls == [] and not store.all_chapter_texts("MyNovel")
    assert app.session_state["characters_source_sha256"] is None
    assert load_character_source(store, "MyNovel")["sha256"] is not None


def test_response_format_fallback_stops_after_character_mutation(monkeypatch, tmp_path):
    store = ProjectStore(tmp_path / "data")

    def mutate(_payload):
        store.write_json("MyNovel", "memory/characters.json", changed_cards("B"))
        return httpx.Response(400, json={"error": {
            "message": "response_format is not supported", "param": "response_format",
            "code": "unsupported_parameter",
        }})

    app, store, calls = setup(monkeypatch, tmp_path, callback=mutate)
    before = deepcopy(app.session_state["characters"])
    plan = app.session_state["pending_plan_json"]
    app.button(key="btn_oneshot").click().run()
    assert app.exception or app.error
    assert len(calls) == 1 and "response_format" in calls[0]
    assert app.session_state["characters"] == before
    assert app.session_state["pending_plan_json"] == plan
    assert app.session_state["last_result"] is None
    assert not store.all_chapter_texts("MyNovel")


@pytest.mark.parametrize("stale", [False, True], ids=["current-consent", "stale-consent"])
def test_memory_readback_and_explicit_reload_bind_exact_compared_cards(monkeypatch, tmp_path, stale):
    app, store, calls, _cards = memory_fixture(monkeypatch, tmp_path, wire=True)
    app.button(key="btn_memory_propose").click().run()
    assert not app.exception
    accept(app)
    assert not app.exception and len(calls) == 1
    accepted = load_character_source(store, "MyNovel")
    assert app.session_state["characters"] == accepted["cards"]
    assert app.session_state["characters_source_sha256"] == accepted["sha256"]
    add_unsaved(app)
    before = deepcopy(app.session_state["characters"])
    assert app.button(key="btn_memory_reload_cards").disabled
    prefix = "memory_character_reload_"
    old_key = reload_checkbox(app, prefix).key
    reload_checkbox(app, prefix).check().run()
    if stale:
        current = deepcopy(accepted["cards"])
        current[0]["voice_extension"]["new_version"] = "C"
        store.write_json("MyNovel", "memory/characters.json", current)
    app.button(key="btn_memory_reload_cards").click().run()
    if stale:
        assert app.session_state["characters"] == before
        assert app.session_state["characters_source_sha256"] == accepted["sha256"]
        assert reload_checkbox(app, prefix).key != old_key
        assert not reload_checkbox(app, prefix).value
        assert app.button(key="btn_memory_reload_cards").disabled
        reload_checkbox(app, prefix).check().run()
        app.button(key="btn_memory_reload_cards").click().run()
    assert not app.exception
    current = load_character_source(store, "MyNovel")
    assert app.session_state["characters"] == current["cards"]
    assert app.session_state["characters_source_sha256"] == current["sha256"]
    assert len(calls) == 1


def test_published_lock_with_failed_readback_preserves_ui_until_explicit_reload(monkeypatch, tmp_path):
    app, store, calls = setup(monkeypatch, tmp_path)
    add_unsaved(app)
    choose_new_locks(app)
    before = deepcopy(app.session_state["characters"])
    digest = app.session_state["characters_source_sha256"]
    expected = deepcopy(before)
    for card in expected:
        card["locked"] = card["name"] == "叶宁"
    original_write = ProjectStore._write
    original_read = ProjectStore.read_json
    publications = []
    fail_readback = [True]

    def publish(self, path, *args, **kwargs):
        value = original_write(self, path, *args, **kwargs)
        if path.name == "characters.json":
            publications.append(path.read_bytes())
        return value

    def read(self, project, relative, *args, **kwargs):
        if relative == "memory/characters.json" and publications and fail_readback[0]:
            raise OSError("synthetic readback failure after complete character publication")
        return original_read(self, project, relative, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "_write", publish)
    monkeypatch.setattr(ProjectStore, "read_json", read)
    button(app, "应用锁定").click().run()
    assert any("synthetic readback failure after complete character publication" in item.value for item in app.error)
    assert len(publications) == 1
    assert json.loads(cards_path(store).read_bytes()) == expected
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == digest
    fail_readback[0] = False
    button(app, "保存人物到本地").click().run()
    assert app.exception or app.error
    assert len(publications) == 1 and cards_path(store).read_bytes() == publications[0]
    assert app.session_state["characters"] == before
    assert app.session_state["characters_source_sha256"] == digest
    reload_checkbox(app).check().run()
    app.button(key="btn_reload_characters").click().run()
    assert not app.exception
    assert app.session_state["characters"] == expected
    assert app.session_state["characters_source_sha256"] == load_character_source(store, "MyNovel")["sha256"]
    assert len(publications) == 1 and calls == []
