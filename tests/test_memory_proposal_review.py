"""Independent synthetic review of the optional memory confirmation boundary."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_ai.author_workflow import save_chapter_plan, write_author_chapter
from novel_ai.memory_proposals import (
    apply_memory_proposal, author_context, capture_memory_source, extract_memory_proposal,
    load_memory_proposal, make_memory_proposal, save_memory_proposal,
)
from novel_ai.memory_ui import render_memory_proposals, workbench_memory_context
from novel_ai.models import ChapterPlan, MemoryExtraction, StoryBible
from novel_ai.project_session import switch_project
from novel_ai.storage import ProjectStore


TEXT = "薛遥把借来的铜铃交回，决定留在渡口等消息。"


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class UI:
    """Runs the actual view function; decisions are explicit test actions."""
    def __init__(self, state, *, actions=(), on_button=None):
        self.session_state = state
        self.actions = set(actions)
        self.on_button = on_button
        self.errors = []
        self.successes = []
        self.warnings = []
        self.jsons = []
        self.buttons = {}
        self.downloads = {}

    def download_button(self, label, data, *, key, **kwargs):
        self.downloads[key] = data
        return False

    def button(self, label, *, key, disabled=False, **kwargs):
        self.buttons[key] = disabled
        selected = key in self.actions and not disabled
        if selected and self.on_button:
            self.on_button(key)
        return selected

    def checkbox(self, label, *, key, value=False, **kwargs):
        return self.session_state.get(key, value)

    def selectbox(self, label, options, **kwargs): return options[0]
    def expander(self, *args, **kwargs): return nullcontext()
    def exception(self, error): self.errors.append(error)
    def success(self, message): self.successes.append(message)
    def warning(self, message): self.warnings.append(message)
    def json(self, value): self.jsons.append(deepcopy(value))
    def divider(self): pass
    def subheader(self, *args): pass
    def caption(self, *args): pass
    def info(self, *args): pass


@pytest.fixture
def scenario(tmp_path):
    store = ProjectStore(tmp_path / "data")
    bible = StoryBible(title="边界测试", premise="归还铜铃").model_dump()
    cards = [{"name": "薛遥", "knows": [], "custom": {"voice": ["简短"]}}]
    store.write_json("River", "memory/story_bible.json", bible)
    store.write_json("River", "memory/characters.json", cards)
    store.save_story_state("River", {"facts": [], "custom": {"retain": [1]}})
    plan = ChapterPlan(chapter_title="渡口", scenes=[])
    write_author_chapter(store, "River", "c01", TEXT)
    save_chapter_plan(store, "River", "c01", plan, TEXT)
    state = State(project_name="River", chapter_id="c01")
    switch_project(state, store, "River")
    state.chapter_id = "c01"
    result = SimpleNamespace(final_text=TEXT, plan=plan)
    state.last_result = result
    state.last_result_meta = {"project": "River", "chapter_id": "c01", "text_sha256": hashlib.sha256((TEXT + "\n").encode()).hexdigest()}
    context = workbench_memory_context(state)
    source = capture_memory_source(store, "River", "c01", final_text=TEXT, plan=plan, context=context)
    extraction = MemoryExtraction(chapter_id="c01", chapter_title="渡口", summary="薛遥交还铜铃。", new_facts=["铜铃已经交还"], character_updates=[{"name": "薛遥", "knowledge_gained": ["船夫已离开"]}])
    return store, state, result, context, source, extraction


def canonical_bytes(store):
    root = store.project_dir("River")
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != ".store.lock" and "proposals" not in p.parts}


def pending(scenario):
    store, state, result, context, source, extraction = scenario
    proposal = make_memory_proposal(source, extraction)
    save_memory_proposal(store, proposal, context=context)
    state.memory_candidate_json = proposal._serialized
    state["memory_text_" + proposal.proposal_id] = True
    state["memory_changes_" + proposal.proposal_id] = True
    return proposal


@pytest.mark.parametrize("changed", ["project", "chapter", "draft"])
def test_view_source_switch_during_model_cannot_publish_old_candidate(scenario, changed):
    store, state, result, context, source, extraction = scenario
    before = canonical_bytes(store)
    class Engine:
        def extract_memory(self, *args):
            if changed == "project": state.project_name = "Other"
            elif changed == "chapter": state.chapter_id = "c02"
            else: state.last_result = SimpleNamespace(final_text="另一版正文", plan=result.plan)
            return extraction
    ui = UI(state, actions={"btn_memory_propose"})
    render_memory_proposals(ui, store, "River", "c01", result, Engine)
    assert canonical_bytes(store) == before
    assert not list(store.project_dir("River").glob("memory/proposals/*/*.json")), "a switched source was accepted after extraction"
    assert not state.get("memory_candidate_json")


@pytest.mark.parametrize("changed", ["project", "chapter", "draft"])
def test_view_source_switch_at_confirmation_does_not_commit_or_publish_to_new_view(scenario, changed):
    store, state, result, context, source, extraction = scenario
    pending(scenario)
    before = canonical_bytes(store)
    def switch(key):
        if key != "btn_memory_apply": return
        if changed == "project": state.project_name = "Other"
        elif changed == "chapter": state.chapter_id = "c02"
        else: state.last_result = SimpleNamespace(final_text="另一版正文", plan=result.plan)
    ui = UI(state, actions={"btn_memory_apply"}, on_button=switch)
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert canonical_bytes(store) == before, "old source was committed after the live view changed"
    assert not state.get("last_memory_commit")


def test_displayed_newer_result_cannot_confirm_saved_older_candidate(scenario):
    store, state, result, context, source, extraction = scenario
    pending(scenario)
    state.last_result = SimpleNamespace(final_text="薛遥没有交还铜铃，转身上船。", plan=result.plan)
    before = canonical_bytes(store)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", state.last_result, lambda: None)
    assert canonical_bytes(store) == before, "apply ignored the displayed-versus-saved revision warning"
    assert not state.get("last_memory_commit")


def test_committed_receipt_retry_finishes_ui_readback_after_transient_read_error(scenario, monkeypatch):
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    old_cards = deepcopy(state.characters)
    original = store.read_json
    def fail_once(project, path, *args, **kwargs):
        if path == "memory/characters.json": raise OSError("synthetic UI readback unavailable")
        return original(project, path, *args, **kwargs)
    monkeypatch.setattr(store, "read_json", fail_once)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert ui.errors and not ui.successes
    assert state.characters == old_cards and not state.get("last_memory_commit")
    monkeypatch.setattr(store, "read_json", original)
    expected = original("River", "memory/characters.json")
    assert expected != old_cards
    resumed = UI(state)
    render_memory_proposals(resumed, store, "River", "c01", result, lambda: None)
    assert not resumed.errors
    assert state.characters == expected, "historical receipt marked the view done without completing current Canon readback"
    assert state.last_memory_commit["proposal_id"] == proposal.proposal_id


def test_rebound_saved_proposal_does_not_inherit_another_candidates_checkbox_acceptance(scenario):
    store, state, result, context, source, extraction = scenario
    old = pending(scenario)
    newer = extraction.model_copy(deep=True)
    newer.summary = "作者选择查看第二份摘要候选。"
    new = make_memory_proposal(source, newer)
    save_memory_proposal(store, new, context=context)
    state.memory_candidate_json = new._serialized
    before = canonical_bytes(store)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert not ui.errors and ui.buttons["btn_memory_apply"]
    assert canonical_bytes(store) == before
    assert old.proposal_id != new.proposal_id


@pytest.mark.parametrize("change", ["custom_card", "native_card", "bible", "outline", "style", "hierarchy", "reference"])
def test_unsaved_author_change_after_preview_blocks_confirmation(scenario, change):
    store, state, result, context, source, extraction = scenario
    pending(scenario)
    if change == "custom_card": state.characters[0]["custom"]["voice"].append("新的语调")
    elif change == "native_card": state.characters[0]["knows"].append("作者新决定")
    elif change == "bible": state.premise = "换设定"
    elif change == "outline": state.outline = "换总纲"
    elif change == "style": state.style = {"tone": "换文风"}
    elif change == "hierarchy": state.hierarchy_data = {"new": "层级"}
    else: state.reference_hashes.add("changed-reference")
    before = canonical_bytes(store)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert ui.errors and not ui.successes
    assert canonical_bytes(store) == before


def test_saved_pending_reload_is_read_only_and_has_no_inherited_acceptance(scenario):
    store, state, result, context, source, extraction = scenario
    pending(scenario)
    fresh = State(project_name="River", chapter_id="c01")
    switch_project(fresh, store, "River")
    fresh.chapter_id = "c01"
    before = canonical_bytes(store)
    ui = UI(fresh, actions={"btn_memory_load", "btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", None, lambda: (_ for _ in ()).throw(AssertionError("model not allowed")))
    assert fresh.memory_candidate_json
    assert ui.buttons["btn_memory_apply"]
    assert not fresh.get("last_memory_commit")
    assert not ui.errors
    assert canonical_bytes(store) == before


@pytest.mark.parametrize("kind", ["custom_card", "native_card"])
def test_capture_refuses_unsaved_cards_instead_of_silently_rebasing(scenario, kind):
    store, state, result, context, source, extraction = scenario
    if kind == "custom_card": state.characters[0]["custom"]["voice"].append("changed")
    else: state.characters[0]["knows"].append("changed")
    before = canonical_bytes(store)
    with pytest.raises(ValueError, match="saved Canon"):
        capture_memory_source(store, "River", "c01", final_text=TEXT, plan=result.plan, context=workbench_memory_context(state))
    assert canonical_bytes(store) == before


def test_source_and_candidate_are_detached_from_all_mutable_models(scenario):
    store, state, result, context, source, extraction = scenario
    proposal = make_memory_proposal(source, extraction)
    original_source = source.to_dict()
    original_proposal = proposal.to_dict()
    context["characters"][0]["custom"]["voice"].append("context mutation")
    result.plan.chapter_title = "plan mutation"
    extraction.new_facts.append("extraction mutation")
    public_source = source.to_dict(); public_source["plan"]["chapter_title"] = "snapshot mutation"
    preview = proposal.preview(); preview["proposed_characters"][0]["custom"]["voice"].append("preview mutation")
    assert source.to_dict() == original_source
    assert proposal.to_dict() == original_proposal


def test_historical_receipt_never_replays_old_after_images_over_newer_canon(scenario):
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    receipt = apply_memory_proposal(store, proposal, context=context, chapter_accepted=True, memory_accepted=True,
                                    confirmation_source="explicit-workbench-memory-confirmation:" + proposal.proposal_id)
    newer = store.read_json("River", "memory/characters.json")
    newer[0]["knows"].append("后续作者新知识")
    store.write_json("River", "memory/characters.json", newer)
    store.write_chapter("River", "c01", "后续作者另存的修订")
    state.characters[0]["custom"]["voice"].append("尚未保存的新编辑")
    unsaved = deepcopy(state.characters)
    before = canonical_bytes(store)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert not ui.errors and ui.buttons["btn_memory_apply"]
    assert state.characters == unsaved
    assert json.loads(ui.downloads["download_memory_character_session"]) == unsaved
    assert ui.buttons["btn_memory_reload_cards"]
    assert canonical_bytes(store) == before
    assert state.last_memory_commit == receipt


def test_real_textarea_cannot_confirm_a_different_visible_draft(scenario, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from novel_ai.engine import ChapterResult, NovelEngine
    store, state, result, context, source, extraction = scenario
    monkeypatch.chdir(tmp_path)
    received = []
    def extract(self, bible, cards, cid, text):
        received.append(text)
        return extraction
    monkeypatch.setattr(NovelEngine, "extract_memory", extract)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.text_input(key="project_name").set_value("River").run()
    app.text_input(key="chapter_id").set_value("c01")
    app.session_state["last_result"] = ChapterResult(plan=result.plan, draft=TEXT, review=None, ai_flavor={})
    app.session_state["last_result_meta"] = state.last_result_meta
    for control in app.text_input:
        if control.label == "Base URL": control.set_value("http://unused.invalid")
        if control.label == "Model": control.set_value("synthetic-model")
    app.run()
    assert not app.exception
    prose = next(area for area in app.text_area if area.label == "正文")
    if prose.disabled:
        return  # A display-only source does not offer an unbound edit path.
    prose.set_value("薛遥没有还铃，登上了渡船。").run()
    assert next(area for area in app.text_area if area.label == "正文").value != TEXT
    app.button(key="btn_memory_propose").click().run()
    assert not received, "the model extracted the old result while the author was shown different prose"
    assert not list(store.project_dir("River").glob("memory/proposals/*/*.json"))


def test_context_assembler_observes_one_epoch_while_confirmed_commit_waits(scenario, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from novel_ai.context import ContextAssembler
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    read_state, started, done = Event(), Event(), Event()
    original = store.load_story_state
    def paused(project):
        old = original(project)
        read_state.set()
        assert started.wait(2)
        assert not done.wait(.15), "commit passed the ContextAssembler snapshot lock"
        return old
    monkeypatch.setattr(store, "load_story_state", paused)
    def writer():
        assert read_state.wait(2)
        started.set()
        result = apply_memory_proposal(store, proposal, context=context,
            chapter_accepted=True, memory_accepted=True, confirmation_source="synthetic explicit author action")
        done.set()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        commit = pool.submit(writer)
        assembled = ContextAssembler(store, "River").assemble()
        assert commit.result(timeout=5)["status"] == "committed"
    assert assembled.recent_summaries == []
    assert "铜铃已经交还" not in assembled.canon_block
    assert store.all_chapter_summaries("River")[0]["summary"] == extraction.summary


@pytest.mark.parametrize("field", ["timeline", "foreshadowing", "state", "custom"])
def test_merge_outputs_cannot_alias_nested_source_records(scenario, field):
    from novel_ai.memory import apply_extraction
    from novel_ai.models import Character
    old = {"facts": [], "timeline": [{"description": "earlier", "evidence": {"keep": [1]}}],
           "foreshadowing": [{"id": "bell", "description": "sound", "status": "resolved", "history": [{"chapter_id": "old", "extra": [1]}], "lifecycle_warnings": []}],
           "unapplied_updates": [{"name": "unknown", "chapter_id": "old", "reason": "locked", "extra": [1]}],
           "custom": {"map": [1]}}
    before = deepcopy(old)
    card = Character(name="薛遥", status={"location": "渡口"}, knows=["旧知识"])
    extraction = MemoryExtraction(chapter_id="c01", summary="新摘要", foreshadowing=[{"id": "bell", "description": "sound", "status": "planted"}])
    chars, changed = apply_extraction([card], old, extraction)
    assert old == before
    if field == "timeline": changed["timeline"][0]["evidence"]["keep"].append(2)
    elif field == "foreshadowing": changed["foreshadowing"][0]["history"][0]["extra"].append(2)
    elif field == "state": changed["unapplied_updates"][0]["extra"].append(2)
    else: changed["custom"]["map"].append(2)
    chars[0].status["location"] = "船上"
    assert old == before and card.status["location"] == "渡口"


def test_cached_ui_receipt_cannot_fabricate_completed_author_acceptance(scenario):
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    state.last_memory_commit = {"proposal_id": proposal.proposal_id, "status": "committed"}
    before = canonical_bytes(store)
    ui = UI(state)
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert not ui.successes, "an unverified session dictionary claimed that memory was already committed"
    assert not ui.buttons["btn_memory_apply"]
    assert canonical_bytes(store) == before


@pytest.mark.parametrize("field", ["before_sha256", "after_sha256", "input_sha256"])
def test_completed_receipt_must_match_the_previewed_proposal_operation(scenario, field):
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    receipt = apply_memory_proposal(store, proposal, context=context, chapter_accepted=True, memory_accepted=True,
                                    confirmation_source="explicit-workbench-memory-confirmation:" + proposal.proposal_id)
    # A structurally intact but rebound receipt must not make this candidate
    # look applied. This is consistency validation, not a signature/auth claim.
    if field == "input_sha256":
        receipt[field]["memory/story_bible.json"] = "f" * 64
    else:
        receipt[field]["memory/characters.json"] = "f" * 64
    body = {key: value for key, value in receipt.items() if key != "commit_sha256"}
    receipt["commit_sha256"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    path = store.project_dir("River") / "memory/memory_commits" / (proposal.proposal_id + ".json")
    path.write_text(json.dumps(receipt, ensure_ascii=False))
    ui = UI(state)
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert ui.errors, "the receipt's operation hashes differ from this exact immutable proposal"
    assert not ui.successes


def test_author_edits_during_commit_are_not_overwritten_by_readback(scenario, monkeypatch):
    store, state, result, context, source, extraction = scenario
    pending(scenario)
    original = store._write
    edited = []
    def edit(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path.name == "story_state.json":
            state.characters[0]["custom"]["voice"].append("作者正在修改的声线")
            edited[:] = deepcopy(state.characters)
        return value
    monkeypatch.setattr(store, "_write", edit)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert not ui.errors
    assert state.characters == edited
    assert store.read_json("River", "memory/characters.json")[0]["knows"] == ["船夫已离开"]
    assert ui.warnings
    resumed = UI(state)
    render_memory_proposals(resumed, store, "River", "c01", result, lambda: None)
    assert state.characters == edited and resumed.warnings


@pytest.mark.parametrize("selection", ["project", "chapter"])
def test_selection_switch_after_confirmed_write_never_receives_old_ui_state(scenario, monkeypatch, selection):
    from novel_ai.memory_commit import read_memory_commit_receipt
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    original = store._write
    old_cards = deepcopy(state.characters)
    def switch(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path.name == "story_state.json":
            if selection == "project": state.project_name = "Other"
            else: state.chapter_id = "c02"
        return value
    monkeypatch.setattr(store, "_write", switch)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert read_memory_commit_receipt(store, "River", proposal.proposal_id)["status"] == "committed"
    assert state.characters == old_cards
    assert not state.get("last_memory_commit")
    assert ui.errors and not ui.successes


@pytest.mark.parametrize("target", ["memory/story_state.json", "memory/longform_health.json"])
def test_confirmed_pending_retry_finishes_without_model_or_duplicate_delta(scenario, monkeypatch, target):
    store, state, result, context, source, extraction = scenario
    proposal = pending(scenario)
    original = store._write
    def fail(path, *args, **kwargs):
        if path == store._path("River", target): raise OSError("synthetic batch interruption")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(store, "_write", fail)
    ui = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(ui, store, "River", "c01", result, lambda: None)
    assert ui.errors and not ui.successes and not state.get("last_memory_commit")
    assert store._path("River", ".memory-commit-transaction.json", internal=True).exists()
    monkeypatch.setattr(store, "_write", original)
    retry = UI(state, actions={"btn_memory_apply"})
    render_memory_proposals(retry, store, "River", "c01", result, lambda: (_ for _ in ()).throw(AssertionError("no model retry")))
    assert not retry.errors
    assert state.last_memory_commit["proposal_id"] == proposal.proposal_id
    assert state.characters[0]["knows"] == ["船夫已离开"]
    assert len(store.all_chapter_summaries("River")) == 1
