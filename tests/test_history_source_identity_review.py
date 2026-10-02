"""Independent offline regression review of accepted-history source collisions.

Synthetic confirmation messages are explicitly labeled fixtures. Public transitions
and actual save/load produce the accepted archives; no author identities, receipts,
or acceptance records are patched. HTTPX MockTransport never uses the network.
"""
import hashlib
import itertools
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from novel_ai import accepted_writing as writing
from novel_ai import gpt_story_journal as journal
from novel_ai import gpt_story_state as state
from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.orchestration import RouterConfig
from novel_ai.provider import ProviderConfig

ROOT = Path(state.__file__).resolve().parents[1]
COUNT = itertools.count()
BUDGET = 100000
PLAN = {
    "chapter_title": "Synthetic door", "chapter_promise": "Choose a route", "tension_curve": "rising",
    "scenes": [{"scene_no": 1, "pov": "Mara", "objective": "Reach the room", "opposition": "The door is locked",
                "choice": "Wait for the keeper", "cost": "Miss the boat", "state_change": "Mara stays", "end_hook": "A lamp lights"}],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path, text, source_id, *, revision=1, file_id=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return state.artifact(path.read_bytes().decode("utf-8"), source_id=source_id,
                          location=str(path), revision=revision, file_id=file_id)


def step(value, action, payload):
    return state.transition(value, {"action": action, "story_id": value.story_id,
        "base_story_revision": value.revision, "operation_id": f"history-identity-review-{next(COUNT)}",
        "expected_state_sha256": state.state_fingerprint(value), "payload": payload})


def simulated_confirmation(value, scope):
    p = value.progress
    result = {"confirmed_by": "author", "confirmation_source": "test-fixture://explicitly-simulated-author-message",
        "story_id": value.story_id, "story_revision": p.base_story_revision, "chapter_id": p.chapter_id,
        "plan_revision": p.plan_revision, "plan_source_fingerprint": state.source_fingerprint(p.plan)}
    if scope != "plan":
        result.update(draft_revision=p.draft_revision, draft_source_fingerprint=state.source_fingerprint(p.draft))
    if scope == "memory":
        result["memory_update_id"] = p.memory_update_id
    return result


def archive(tmp_path, *, count=1, exact_reuse=False):
    path = tmp_path / "synthetic-story.json"
    value = state.create_state("synthetic-history-source-review")
    first_draft = None
    for number in range(1, count + 1):
        chapter = f"ch-{number}"
        value = step(value, "start_chapter", {"chapter_id": chapter})
        plan = artifact(tmp_path / chapter / "plan.json", json.dumps(PLAN), "plan-" + chapter)
        value = step(value, "set_plan", {"artifact": plan.model_dump(mode="json")})
        value = step(value, "accept_plan", {"confirmation": simulated_confirmation(value, "plan")})
        draft = first_draft if exact_reuse and first_draft else artifact(
            tmp_path / chapter / "draft.txt", f"ACCEPTED_CHAPTER_{number}_PROSE. Mara put the bronze key down.", "draft")
        first_draft = draft if first_draft is None else first_draft
        value = step(value, "set_draft", {"artifact": draft.model_dump(mode="json")})
        review = artifact(tmp_path / chapter / "review.txt", "Synthetic clean review", "review-" + chapter)
        value = step(value, "review", {"draft_revision": 1, "issues": [], "source": review.source.model_dump(mode="json")})
        value = step(value, "accept_chapter", {"confirmation": simulated_confirmation(value, "chapter")})
        value = step(value, "propose_memory", {"changes": []})
        value = step(value, "accept_memory", {"confirmation": simulated_confirmation(value, "memory")})
        value = step(value, "apply_memory", {"memory_update_id": value.progress.memory_update_id})
        options = {"expected_disk_revision": number - 1, "expected_disk_sha256": digest(path)} if path.exists() else {}
        saved = state.save_state(path, value, **options)
        value = state.load_state(path, expected_story_id=value.story_id, expected_revision=number, expected_sha256=saved.sha256)
    value = step(value, "start_chapter", {"chapter_id": f"ch-{count + 1}"})
    current = artifact(tmp_path / "current-plan.json", json.dumps(PLAN), "current-plan")
    value = step(value, "set_plan", {"artifact": current.model_dump(mode="json")})
    value = step(value, "accept_plan", {"confirmation": simulated_confirmation(value, "plan")})
    saved = state.save_state(path, value, expected_disk_revision=count, expected_disk_sha256=digest(path))
    return path, state.load_state(path, expected_story_id=value.story_id, expected_revision=count, expected_sha256=saved.sha256)


def supplied_shadow(value, tmp_path, field="text"):
    original = state.Artifact.model_validate(value.accepted_chapters[0]["draft"])
    source = original.source
    if field == "text":
        # The supplied bytes are genuinely read from the same named source after
        # a local edit. The immutable accepted archive snapshot stays untouched.
        return artifact(Path(source.location), "UNACCEPTED_SOURCE_PROSE. Mara dropped the key in the lake.", source.source_id)
    if field == "location":
        return artifact(tmp_path / "relocated.txt", original.text, source.source_id)
    if field == "file_id":
        return artifact(Path(source.location), original.text, source.source_id, file_id="synthetic-distinct-file-id")
    if field == "revision_type":
        return artifact(Path(source.location), original.text, source.source_id, revision="1")
    raise AssertionError(field)


def row(value, **options):
    return {"artifact": value.model_dump(mode="json"), "required": False, "priority": 0, **options}


def restore(path, value):
    return writing.restore_source(path, expected_story_id=value.story_id, expected_revision=value.revision,
                                  expected_sha256=digest(path))


def mocked_session(monkeypatch):
    calls = []
    original = httpx.Client
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Mara waited at the door. The keeper returned before dawn."}, "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return BudgetedWritingSession(RouterConfig(local=ProviderConfig("https://synthetic.invalid/v1", "synthetic-writer"))), calls


def owning_journal(path, value):
    origin_path = path.with_name("migration-origin.json")
    origin = artifact(origin_path, value.model_dump_json(), "synthetic-actual-origin")
    migrated = journal.migrate_state(origin, {"confirmed_by": "author",
        "confirmation_source": "test-fixture://explicitly-simulated-migration-message", "scope": "migrate",
        "story_id": value.story_id, "origin_source_fingerprint": state.source_fingerprint(origin)})
    journal_path = path.with_name("synthetic-owned-journal.json")
    saved = journal.save_journal(journal_path, migrated)
    loaded = journal.load_journal(journal_path, expected_story_id=value.story_id, expected_sha256=saved["sha256"])
    projection = journal.project_journal(loaded)
    identity = {"expected_story_id": loaded.story_id, "expected_revision": projection.story["revision"],
        "expected_context_revision": projection.context_revision,
        "expected_journal_sha256": journal.journal_fingerprint(loaded), "expected_file_sha256": digest(journal_path)}
    return journal_path, loaded, identity


@pytest.mark.parametrize("field", ["text", "location", "file_id", "revision_type"])
@pytest.mark.parametrize("budget", [1, BUDGET])
def test_supplied_collision_refused_before_budget_or_formatting(tmp_path, field, budget):
    path, value = archive(tmp_path)
    before = path.read_bytes()
    original_state = deepcopy(value.model_dump(mode="json"))
    shadow = supplied_shadow(value, tmp_path, field)
    assert state.source_fingerprint(shadow) != state.source_fingerprint(value.accepted_chapters[0]["draft"])
    history = state.rebuild_accepted_history(value)["accepted_history_sha256"]
    with pytest.raises(state.StateError, match="source"):
        state.preflight_next_chapter_context(value, [row(shadow)], budget,
            expected_story_id=value.story_id, expected_history_sha256=history)
    assert path.read_bytes() == before and value.model_dump(mode="json") == original_state


@pytest.mark.parametrize("budget", [1, BUDGET])
def test_two_accepted_colliding_sources_refused_even_with_tiny_budget(tmp_path, budget):
    path, value = archive(tmp_path, count=2)
    before = path.read_bytes()
    with pytest.raises(state.StateError, match="source"):
        state.preflight_next_chapter_context(value, [], budget)
    assert path.read_bytes() == before


def test_real_cli_refuses_conflicting_supplied_source_and_emits_no_context(tmp_path):
    path, value = archive(tmp_path)
    before = path.read_bytes()
    supplied = tmp_path / "sources.json"
    supplied.write_text(json.dumps([row(supplied_shadow(value, tmp_path))]), encoding="utf-8")
    history = state.rebuild_accepted_history(value)["accepted_history_sha256"]
    result = subprocess.run([sys.executable, str(ROOT / "scripts/story_state.py"), "next-preflight", str(path),
        "--story-id", value.story_id, "--revision", "1", "--sha256", digest(path), "--sources", str(supplied),
        "--budget-bytes", str(BUDGET), "--expected-history-sha256", history], capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 2
    assert result.stdout == "" and "source" in json.loads(result.stderr)["error"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("owned", [False, True], ids=["v1", "journal"])
def test_actual_source_bound_collision_never_reserves_or_dispatches(tmp_path, monkeypatch, owned):
    path, value = archive(tmp_path, count=2)
    if owned:
        path, _, identity = owning_journal(path, value)
        source = writing.restore_journal_source(path, **identity)
    else:
        source = restore(path, value)
    before = path.read_bytes()
    flow, calls = mocked_session(monkeypatch)
    with pytest.raises(state.StateError, match="source"):
        flow.run_from_accepted_archive(source, current_chapter_id="ch-3", review=False)
    assert calls == [] and flow.budget_snapshot()["requests_reserved"] == 0
    assert path.read_bytes() == before


def test_owning_journal_direct_preflight_refuses_supplied_collision(tmp_path):
    path, value = archive(tmp_path)
    path, loaded, identity = owning_journal(path, value)
    before = path.read_bytes()
    shadow = supplied_shadow(value, tmp_path, "location")
    with pytest.raises(state.StateError, match="source"):
        journal.preflight_journal_next_chapter_context(loaded, [row(shadow)], BUDGET, **identity)
    assert path.read_bytes() == before


def test_exact_supplied_accepted_artifact_is_reused_once(tmp_path):
    _, value = archive(tmp_path)
    accepted = state.Artifact.model_validate(value.accepted_chapters[0]["draft"])
    result = state.preflight_next_chapter_context(value, [row(accepted, required=True, priority=27)], BUDGET)
    assert not result["blocked"]
    assert result["selected_sources"].count(accepted.model_dump(mode="json")) == 1
    assert not any(x["kind"] == "draft" for x in result["automatic_history_sources"])
    assert result["dropped_sources"] == []


@pytest.mark.parametrize("owned", [False, True], ids=["v1", "journal"])
def test_identical_accepted_source_can_be_reused_by_two_chapters_and_dispatch(tmp_path, monkeypatch, owned):
    path, value = archive(tmp_path, count=2, exact_reuse=True)
    if owned:
        path, _, identity = owning_journal(path, value)
        source = writing.restore_journal_source(path, **identity)
    else:
        source = restore(path, value)
    before = path.read_bytes()
    preview = writing.prepare_accepted_context(source, current_chapter_id="ch-3")
    assert preview["history"]["history_chapter_ids"] == ["ch-1", "ch-2"]
    drafts = [x for x in preview["preflight"]["selected_sources"] if x["source"]["source_id"] == "draft"]
    assert len(drafts) == 1 and "ACCEPTED_CHAPTER_1_PROSE" in drafts[0]["text"]
    flow, calls = mocked_session(monkeypatch)
    candidate = flow.run_from_accepted_archive(source, current_chapter_id="ch-3", review=False)
    assert candidate.final_text and len(calls) == 1
    assert path.read_bytes() == before


@pytest.mark.parametrize("limit", [0, 1])
def test_history_source_limit_checks_only_actually_admitted_automatic_sources(tmp_path, limit):
    path, value = archive(tmp_path, count=2)
    before = path.read_bytes()
    result = state.preflight_next_chapter_context(value, [], BUDGET, history_source_limit=limit)
    assert not result["blocked"]
    assert result["accepted_history"]["history_chapter_ids"] == ["ch-1", "ch-2"]
    drafts = [x for x in result["selected_sources"] if x["source"]["source_id"] == "draft"]
    assert len(drafts) == limit
    if limit:
        assert "ACCEPTED_CHAPTER_2_PROSE" in drafts[0]["text"]
    assert path.read_bytes() == before


def test_source_outside_recent_window_still_conflicts_when_explicitly_supplied(tmp_path):
    _, value = archive(tmp_path, count=2)
    older = state.Artifact.model_validate(value.accepted_chapters[0]["draft"])
    with pytest.raises(state.StateError, match="source"):
        state.preflight_next_chapter_context(value, [row(older)], BUDGET, history_source_limit=1)


def test_zero_automatic_source_limit_does_not_add_global_accepted_identity_guard(tmp_path):
    _, value = archive(tmp_path)
    shadow = supplied_shadow(value, tmp_path)
    result = state.preflight_next_chapter_context(value, [row(shadow)], BUDGET, history_source_limit=0)
    assert not result["blocked"] and result["automatic_history_sources"] == []
    assert result["selected_sources"] == [shadow.model_dump(mode="json")]


@pytest.mark.parametrize("limit", [0, 4])
def test_explicit_duplicate_supplied_list_keeps_existing_refusal(tmp_path, limit):
    _, value = archive(tmp_path)
    accepted = state.Artifact.model_validate(value.accepted_chapters[0]["draft"])
    with pytest.raises(state.StateError, match="duplicate source ID/revision"):
        state.preflight_next_chapter_context(value, [row(accepted), row(accepted)], BUDGET, history_source_limit=limit)


@pytest.mark.parametrize("limit", [0, 4])
def test_explicit_both_chapters_still_refused_before_source_bound_dispatch(tmp_path, monkeypatch, limit):
    path, value = archive(tmp_path, count=2)
    flow, calls = mocked_session(monkeypatch)
    with pytest.raises(state.StateError, match="source"):
        flow.run_from_accepted_archive(restore(path, value), current_chapter_id="ch-3", review=False,
            required_chapter_ids=["ch-1", "ch-2"], history_source_limit=limit)
    assert calls == [] and flow.budget_snapshot()["requests_reserved"] == 0


def test_required_full_identity_still_blocks_with_automatic_history_disabled(tmp_path):
    _, value = archive(tmp_path)
    original = value.accepted_chapters[0]["draft"]["source"]
    required = {key: original[key] for key in ("source_id", "revision", "location", "file_id", "sha256", "sha256_method")}
    result = state.preflight_next_chapter_context(value, [row(supplied_shadow(value, tmp_path))], BUDGET,
        required_sources=[required], history_source_limit=0)
    assert result["blocked"]
    assert any("required source identity mismatch" in reason for reason in result["reasons"])


def test_nonconflicting_tiny_budget_preserves_normal_blocked_result(tmp_path):
    _, value = archive(tmp_path)
    result = state.preflight_next_chapter_context(value, [], 1)
    assert result["blocked"] and result["dropped_sources"]
    assert any("budget" in reason or "do not draft" in reason for reason in result["reasons"])


def test_checked_supplied_snapshot_cannot_change_before_formatting(tmp_path, monkeypatch):
    """A cooperative caller callback changes its own dict during admission.

    This checks a single-call detached input snapshot, not hostile-process or
    threaded memory isolation. The originally admitted bytes must be formatted.
    """
    _, value = archive(tmp_path)
    original = artifact(tmp_path / "supplement.txt", "ORIGINAL_SUPPLEMENT_PROSE", "supplement")
    replacement = artifact(tmp_path / "replacement.txt", "CHANGED_SUPPLEMENT_PROSE", "supplement")
    supplied = [row(original, required=True, priority=73)]
    expected = state.preflight_next_chapter_context(value, supplied, BUDGET)
    validate = state.ContextSource.model_validate
    changed = []
    def mutate_external_after_check(cls, item, *args, **kwargs):
        parsed = validate(item, *args, **kwargs)
        if parsed.artifact.source.source_id == "supplement" and not changed:
            supplied[0]["artifact"] = replacement.model_dump(mode="json")
            supplied[0]["required"] = False
            supplied[0]["priority"] = -999
            changed.append(True)
        return parsed
    monkeypatch.setattr(state.ContextSource, "model_validate", classmethod(mutate_external_after_check))
    actual = state.preflight_next_chapter_context(value, supplied, BUDGET)
    assert actual == expected
    assert supplied[0]["artifact"] == replacement.model_dump(mode="json")
    assert changed == [True]
