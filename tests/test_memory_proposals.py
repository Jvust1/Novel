"""Synthetic memory proposals never imply author acceptance or Canon writes."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from novel_ai.author_workflow import save_chapter_plan, write_author_chapter
from novel_ai.memory import apply_extraction
from novel_ai.memory_proposals import (
    MemoryProposal, MemorySource, apply_memory_proposal, assert_memory_source_current,
    author_context, capture_memory_source, extract_memory_proposal, list_memory_proposals,
    load_memory_proposal, make_memory_proposal, save_memory_proposal,
)
from novel_ai.models import Character, ChapterPlan, MemoryExtraction
from novel_ai.storage import ProjectStore


TEXT = "舟把旧钥匙放在窗台上。对岸的船开走了，她决定等屋主回来。"


def fixture(tmp_path):
    store = ProjectStore(tmp_path / "data")
    plan = ChapterPlan.model_validate({"chapter_title": "等候", "chapter_promise": "留下来", "tension_curve": "上升",
        "scenes": [{"scene_no": 1, "pov": "舟", "objective": "归还钥匙", "opposition": "屋主不在",
                    "choice": "坐在门口等", "cost": "错过末班船", "state_change": "决定留下", "end_hook": "屋里传来响声"}]})
    cards = [{"name": "舟", "knows": [], "does_not_know": ["钥匙用途"],
              "custom_voice": {"register": "简洁"}, "aliases": ["小舟"]}]
    context = author_context(bible={"title": "合成测试"}, characters=cards, extra={"outline": "等候", "style": {"tone": "克制"}})
    store.write_json("Book", "memory/characters.json", cards)
    store.save_story_state("Book", {"facts": ["钥匙在窗台"], "timeline": [], "open_threads": [],
        "custom_ledger": {"keep": ["保留"]}, "foreshadowing": [{"id": "key", "description": "旧钥匙", "status": "resolved", "history": [], "lifecycle_warnings": []}]})
    store.write_json("Book", "memory/story_bible.json", context["bible"])
    write_author_chapter(store, "Book", "c1", TEXT)
    save_chapter_plan(store, "Book", "c1", plan, TEXT)
    source = capture_memory_source(store, "Book", "c1", final_text=TEXT, plan=plan, context=context)
    extraction = MemoryExtraction(chapter_id="c1", chapter_title="等候", summary="舟留下等候屋主。",
        new_facts=["舟错过末班船"], character_updates=[{"name": "舟", "knowledge_gained": ["钥匙用途"]}],
        foreshadowing=[{"id": "key", "description": "旧钥匙", "status": "planted"}])
    return store, context, source, extraction


def contents(store):
    return {p.relative_to(store.root).as_posix(): p.read_bytes() for p in store.root.rglob("*") if p.is_file()}


def test_pure_merge_detaches_every_input_and_preserves_author_extensions():
    char = Character(name="舟", knows=["旧知识"])
    state = {"facts": [], "timeline": [{"description": "old", "details": [1]}],
             "foreshadowing": [{"id": "x", "description": "hint", "status": "resolved", "lifecycle_warnings": []}],
             "unapplied_updates": [{"chapter_id": "old", "name": "other", "details": []}], "custom": {"keep": [1]}}
    before = deepcopy(state)
    chars, result = apply_extraction([char], state, MemoryExtraction(chapter_id="c", summary="s",
        foreshadowing=[{"id": "x", "description": "hint", "status": "planted"}]))
    assert state == before and result["custom"] == state["custom"]
    chars[0].knows.append("new")
    result["timeline"][0]["details"].append(2)
    result["custom"]["keep"].append(2)
    result["unapplied_updates"][0]["details"].append(2)
    assert char.knows == ["旧知识"] and state == before


def test_candidate_preview_and_restore_preserve_every_canonical_file(tmp_path):
    store, context, source, extraction = fixture(tmp_path)
    before = contents(store)
    proposal = make_memory_proposal(source, extraction)
    preview = proposal.preview()
    assert preview["phase"] == "awaiting_author_confirmation"
    assert preview["proposed_characters"][0]["custom_voice"] == {"register": "简洁"}
    assert preview["proposed_characters"][0]["aliases"] == ["小舟"]
    assert preview["proposed_story_state"]["custom_ledger"] == {"keep": ["保留"]}
    assert preview["proposed_characters"][0]["knows"] == ["钥匙用途"]
    assert contents(store) == before
    path = save_memory_proposal(store, proposal, context=context)
    after = contents(store)
    assert all(after[k] == v for k, v in before.items())
    assert set(after) - set(before) == {path.relative_to(store.root).as_posix()}
    assert save_memory_proposal(store, proposal, context=context) == path
    restored = load_memory_proposal(ProjectStore(store.root), "Book", proposal.proposal_id)
    assert restored == proposal and list_memory_proposals(store, "Book", "c1") == [proposal.proposal_id]
    assert list_memory_proposals(store, "Book", "c2") == []


@pytest.mark.parametrize("kind", ["draft", "plan", "characters", "story", "style", "new_summary", "context"])
def test_changes_during_model_extraction_refuse_without_candidate_or_canon_writes(tmp_path, kind):
    store, context, source, extraction = fixture(tmp_path)
    def mutate():
        if kind == "draft":
            store.write_chapter("Book", "c1", "作者的新版本")
        elif kind == "plan":
            path = next(store.project_dir("Book").glob("memory/chapter_plans/*.json")); path.write_text("{}")
        elif kind == "characters":
            store.write_json("Book", "memory/characters.json", [{"name": "舟", "knows": ["作者新增"]}])
        elif kind == "story":
            store.save_story_state("Book", {"facts": ["作者新增事实"]})
        elif kind == "style":
            store.write_json("Book", "styles/style_dna.json", {"tone": "new"})
        elif kind == "new_summary":
            store.save_extraction("Book", {"chapter_id": "other", "summary": "另一章"})
        else:
            context["extra"]["style"]["tone"] = "新基调"
    after_mutation = {}
    class Engine:
        def extract_memory(self, *args):
            mutate(); after_mutation.update(contents(store)); return extraction
    with pytest.raises(ValueError, match="changed"):
        extract_memory_proposal(store, source, Engine(), context=context)
    assert contents(store) == after_mutation
    assert not list(store.project_dir("Book").glob("memory/proposals/*"))


def test_live_context_reader_catches_replaced_ui_context(tmp_path):
    store, context, source, extraction = fixture(tmp_path)
    live = [context]
    class Engine:
        def extract_memory(self, *args):
            live[0] = deepcopy(context); live[0]["bible"]["title"] = "作者换了设定"; return extraction
    with pytest.raises(ValueError, match="author context changed"):
        extract_memory_proposal(store, source, Engine(), context=context, current_context=lambda: live[0])


@pytest.mark.parametrize("field", ["chapter", "timeline", "foreshadowing"])
def test_foreign_model_chapter_is_never_applied(tmp_path, field):
    store, context, source, extraction = fixture(tmp_path)
    raw = extraction.model_dump()
    if field == "chapter": raw["chapter_id"] = "foreign"
    elif field == "timeline": raw["timeline_events"] = [{"chapter_id": "foreign", "description": "wrong"}]
    else: raw["foreshadowing"][0]["chapter_id"] = "foreign"
    before = contents(store)
    with pytest.raises(ValueError, match="another chapter"):
        make_memory_proposal(source, MemoryExtraction.model_validate(raw))
    assert contents(store) == before


@pytest.mark.parametrize("field", ["unknown", "character", "timeline", "foreshadowing", "status"])
def test_unsupported_model_memory_fields_fail_instead_of_disappearing(field):
    raw = {"chapter_id": "c", "summary": "s"}
    if field == "unknown": raw["silently_drop_fact"] = "x"
    elif field == "character": raw["character_updates"] = [{"name": "a", "unknown_fact": "x"}]
    elif field == "timeline": raw["timeline_events"] = [{"description": "x", "unknown_fact": "x"}]
    elif field == "foreshadowing": raw["foreshadowing"] = [{"id": "x", "description": "x", "unknown_fact": "x"}]
    else: raw["foreshadowing"] = [{"id": "x", "description": "x", "status": "invented"}]
    with pytest.raises(ValidationError):
        MemoryExtraction.model_validate(raw)


@pytest.mark.parametrize("acceptance", [(False, False), (True, False), (False, True), ("yes", True), (True, 1)])
def test_pending_proposal_needs_two_explicit_boolean_decisions(tmp_path, acceptance):
    store, context, source, extraction = fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction); save_memory_proposal(store, proposal, context=context)
    before = contents(store)
    with pytest.raises(ValueError, match="explicit author acceptance"):
        apply_memory_proposal(store, proposal, context=context, chapter_accepted=acceptance[0],
                              memory_accepted=acceptance[1], confirmation_source="synthetic fixture author action")
    assert contents(store) == before


def test_model_error_or_bad_pending_publication_leaves_canon_unchanged(tmp_path, monkeypatch):
    store, context, source, extraction = fixture(tmp_path)
    before = contents(store)
    class Engine:
        def extract_memory(self, *args): raise ValueError("synthetic provider failure")
    with pytest.raises(ValueError):
        extract_memory_proposal(store, source, Engine(), context=context)
    proposal = make_memory_proposal(source, extraction)
    monkeypatch.setattr(store, "_write", lambda *a, **kw: (_ for _ in ()).throw(OSError("synthetic write failure")))
    with pytest.raises(OSError): save_memory_proposal(store, proposal, context=context)
    assert contents(store) == before


def test_proposal_mutation_and_cross_store_restore_are_refused(tmp_path):
    store, context, source, extraction = fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction)
    with pytest.raises(FrozenInstanceError): proposal._serialized = "{}"
    data = proposal.to_dict(); data["files"]["memory/story_state.json"] = "{}"
    with pytest.raises(ValueError): MemoryProposal(json.dumps(data)).preview()
    # Even recalculating the top hash cannot make arbitrary after-images valid.
    body = {k: v for k, v in data.items() if k != "proposal_id"}
    serialized = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    data["proposal_id"] = "memory-" + hashlib.sha256(serialized.encode()).hexdigest()
    with pytest.raises(ValueError, match="after-images"):
        MemoryProposal(json.dumps(data)).preview()
    with pytest.raises(ValueError):
        assert_memory_source_current(ProjectStore(tmp_path / "other"), source, context=context)


def commit(store, proposal, context):
    return apply_memory_proposal(store, proposal, context=context, chapter_accepted=True, memory_accepted=True,
                                 confirmation_source="synthetic fixture explicit author confirmation")


def test_explicit_acceptance_commits_actual_nine_files_without_editing_manuscript(tmp_path):
    from novel_ai.memory_commit import read_memory_commit_receipt
    store, context, source, extraction = fixture(tmp_path)
    original = (store.project_dir("Book") / "chapters/c1.md").read_bytes()
    proposal = make_memory_proposal(source, extraction); save_memory_proposal(store, proposal, context=context)
    receipt = commit(store, proposal, context)
    assert receipt["status"] == "committed"
    assert receipt == read_memory_commit_receipt(store, "Book", proposal.proposal_id)
    assert (store.project_dir("Book") / "chapters/c1.md").read_bytes() == original
    assert store.load_story_state("Book")["custom_ledger"] == {"keep": ["保留"]}
    assert store.read_json("Book", "memory/characters.json")[0]["knows"] == ["钥匙用途"]
    assert len(store.all_chapter_summaries("Book")) == 1
    after = contents(store)
    assert commit(store, proposal, context) == receipt
    assert contents(store) == after
    newer = store.load_story_state("Book"); newer["facts"].append("后续作者的新事实")
    store.save_story_state("Book", newer)
    after = contents(store)
    assert commit(store, proposal, context) == receipt
    assert contents(store) == after


@pytest.mark.parametrize("path", ["memory/characters.json", "memory/story_state.json", "memory/story_graph.json", "memory/longform_health.json"])
def test_pending_commit_recovery_uses_confirmed_images_without_reapplying_delta(tmp_path, monkeypatch, path):
    from novel_ai.memory_commit import INTENT_PATH
    store, context, source, extraction = fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction); save_memory_proposal(store, proposal, context=context)
    original = store._write
    def fail(target, *args, **kw):
        if target == store._path("Book", path):
            raise OSError("synthetic interrupted memory publication")
        return original(target, *args, **kw)
    monkeypatch.setattr(store, "_write", fail)
    with pytest.raises(OSError): commit(store, proposal, context)
    assert store._path("Book", INTENT_PATH, internal=True).exists()
    monkeypatch.setattr(store, "_write", original)
    # A fresh ordinary ProjectStore read recovers before exposing any memory.
    resumed = ProjectStore(store.root)
    assert resumed.read_json("Book", "memory/characters.json")[0]["knows"] == ["钥匙用途"]
    assert not resumed._path("Book", INTENT_PATH, internal=True).exists()
    assert len(resumed.all_chapter_summaries("Book")) == 1
    assert commit(resumed, load_memory_proposal(resumed, "Book", proposal.proposal_id), context)["status"] == "committed"


@pytest.mark.parametrize("kind", ["draft", "author_context", "disk_characters", "disk_state"])
def test_confirmation_cannot_reuse_previously_previewed_old_sources(tmp_path, kind):
    store, context, source, extraction = fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction); save_memory_proposal(store, proposal, context=context)
    if kind == "draft": store.write_chapter("Book", "c1", "作者的新稿")
    elif kind == "author_context": context["extra"]["outline"] = "作者的新方向"
    elif kind == "disk_characters": store.write_json("Book", "memory/characters.json", [{"name": "舟", "knows": ["新知识"]}])
    else: store.save_story_state("Book", {"facts": ["新事实"]})
    before = contents(store)
    with pytest.raises(ValueError, match="changed"):
        commit(store, proposal, context)
    assert contents(store) == before


def test_new_candidate_for_already_applied_chapter_requires_historical_reconciliation(tmp_path):
    store, context, source, extraction = fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction); save_memory_proposal(store, proposal, context=context)
    commit(store, proposal, context)
    context = deepcopy(context)
    context["characters"] = store.read_json("Book", "memory/characters.json")
    with pytest.raises(ValueError, match="historical reconciliation"):
        capture_memory_source(store, "Book", "c1", final_text=TEXT,
                              plan=ChapterPlan.model_validate(source.to_dict()["plan"]), context=context)


def test_blank_summary_is_not_a_complete_memory_candidate(tmp_path):
    store, context, source, extraction = fixture(tmp_path)
    extraction.summary = " \n"
    with pytest.raises(ValueError, match="must not be blank"):
        make_memory_proposal(source, extraction)
