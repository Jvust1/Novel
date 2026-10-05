"""Synthetic adversarial boundaries for journal ownership and actual readback."""
from __future__ import annotations

import copy
import itertools
import json

import pytest

from novel_ai import gpt_story_journal as j
from novel_ai import gpt_story_state as v1

SEQ = itertools.count()
AUTHOR = "test-fixture://explicit-synthetic-author-message"


def source(text, name):
    return v1.artifact(text, source_id=name, location="private://synthetic/" + name, revision=1)


def legacy_step(state, action, payload):
    return v1.transition(state, {"story_id": state.story_id, "action": action,
        "base_story_revision": state.revision, "operation_id": "legacy-" + str(next(SEQ)),
        "expected_state_sha256": v1.state_fingerprint(state), "payload": payload})


def legacy_confirmation(state, scope):
    p = state.progress
    data = {"confirmed_by": "author", "confirmation_source": AUTHOR,
        "story_id": state.story_id, "story_revision": p.base_story_revision,
        "chapter_id": p.chapter_id, "plan_revision": p.plan_revision,
        "plan_source_fingerprint": v1.source_fingerprint(p.plan)}
    if scope in {"chapter", "memory"}:
        data.update(draft_revision=p.draft_revision, draft_source_fingerprint=v1.source_fingerprint(p.draft))
    if scope == "memory":
        data["memory_update_id"] = p.memory_update_id
    return data


def committed_state():
    state = v1.create_state("adversarial-story")
    state = legacy_step(state, "start_chapter", {"chapter_id": "ch-001"})
    state = legacy_step(state, "set_plan", {"artifact": source("Synthetic plan", "plan").model_dump(mode="json")})
    state = legacy_step(state, "accept_plan", {"confirmation": legacy_confirmation(state, "plan")})
    state = legacy_step(state, "set_draft", {"artifact": source("Synthetic scene", "draft").model_dump(mode="json")})
    state = legacy_step(state, "review", {"draft_revision": 1, "issues": [],
        "source": source("Synthetic review", "review").source.model_dump(mode="json")})
    state = legacy_step(state, "accept_chapter", {"confirmation": legacy_confirmation(state, "chapter")})
    state = legacy_step(state, "propose_memory", {"changes": []})
    state = legacy_step(state, "accept_memory", {"confirmation": legacy_confirmation(state, "memory")})
    return legacy_step(state, "apply_memory", {"memory_update_id": state.progress.memory_update_id})


def migrated(state=None):
    state = committed_state() if state is None else state
    origin = source(state.model_dump_json(), "origin")
    return j.migrate_state(origin, {"confirmed_by": "author", "confirmation_source": AUTHOR,
        "scope": "migrate", "story_id": state.story_id,
        "origin_source_fingerprint": v1.source_fingerprint(origin)})


def command(value, action, payload, operation_id=None):
    return {"story_id": value.story_id, "action": action,
        "operation_id": operation_id or "journal-" + str(next(SEQ)),
        "expected_journal_sha256": j.journal_fingerprint(value), "payload": payload}


def step(value, action, payload):
    return j.transition_journal(value, command(value, action, payload))


def explicit(value, scope):
    return {**j.confirmation_binding(value, scope), "confirmed_by": "author", "confirmation_source": AUTHOR}


def amend(value, style):
    old = j.project_journal(value).story["style_profile"]
    value = step(value, "propose_amendment", {"reason": "Synthetic style decision",
        "changes": [{"path": "/style_profile", "old_value": old, "new_value": style}]})
    return step(value, "accept_amendment", {"confirmation": explicit(value, "amendment")})


def review_payload(item, verdict="compatible"):
    return {"target_id": item["target_id"], "source_fingerprint": item["source_fingerprint"],
        "target_context_sha256": item["target_context_sha256"],
        "review_artifact": source("Synthetic compatibility review", "impact-review").model_dump(mode="json"),
        "verdict": verdict, "issues": [] if verdict == "compatible" else ["Requires historical prose repair"]}


def review_all(value):
    for item in list(j.project_journal(value).impacts.values()):
        value = step(value, "review_impact", review_payload(item))
    return value


def start_payload(chapter="ch-002", checkpoint=None):
    return {"action": "start_chapter", "payload": {"chapter_id": chapter},
            "context_confirmation": None, "checkpoint": checkpoint}


def test_projected_story_cannot_bypass_pending_reconciliation():
    value = amend(migrated(), {"tone": "quieter"})
    projection = j.project_journal(value)
    with pytest.raises(v1.StateError, match="journal"):
        legacy_step(v1.validate_state(projection.story), "start_chapter", {"chapter_id": "ch-002"})
    with pytest.raises(v1.StateError, match="journal"):
        v1.preflight_context(projection.story, [], 100000)


def test_imported_verified_receipt_is_not_a_current_actual_read(tmp_path):
    value = migrated()
    path = tmp_path / "story.journal.json"
    j.save_journal(path, value)
    loaded = j.load_journal(path, expected_story_id=value.story_id)
    checkpoint = {key: loaded.readback_receipt[key] for key in ("journal_sha256", "file_sha256", "location")}
    imported = json.loads(loaded.model_dump_json())
    cmd = command(loaded, "story", start_payload(checkpoint=checkpoint))
    with pytest.raises(j.JournalError, match="read|checkpoint"):
        j.transition_journal(imported, cmd)


def test_reconciled_context_requires_its_own_save_and_actual_readback():
    value = review_all(amend(migrated(), {"tone": "quieter"}))
    value = step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})
    with pytest.raises(j.JournalError, match="read|checkpoint|save"):
        step(value, "story", start_payload())


def test_superseding_blocked_amendment_preserves_history_and_reopens_all_reviews():
    value = amend(migrated(), {"tone": "quieter"})
    first = j.project_journal(value)
    item = first.impacts["chapter:ch-001"]
    value = step(value, "review_impact", review_payload(item, "requires_revision"))
    old_events = copy.deepcopy(value.events)
    old_history = copy.deepcopy(j.project_journal(value).story["accepted_chapters"])
    with pytest.raises(j.JournalError, match="compatible"):
        step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})
    value = amend(value, {})
    final = j.project_journal(value)
    assert value.events[:len(old_events)] == old_events
    assert final.story["accepted_chapters"] == old_history
    assert final.context_revision == first.context_revision + 1
    assert set(final.impacts) == set(first.impacts)
    assert all(item["status"] == "pending" for item in final.impacts.values())
    assert final.story["style_profile"] == {}


def test_source_mismatch_and_omitted_derived_context_cannot_resume():
    value = amend(migrated(), {"tone": "quieter"})
    projection = j.project_journal(value)
    payload = review_payload(projection.impacts["chapter:ch-001"])
    payload["source_fingerprint"] = "0" * 64
    before = value.model_dump_json()
    with pytest.raises(j.JournalError, match="source"):
        step(value, "review_impact", payload)
    assert value.model_dump_json() == before
    value = step(value, "review_impact", review_payload(projection.impacts["chapter:ch-001"]))
    with pytest.raises(j.JournalError, match="derived context"):
        step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})


def test_preflight_does_not_call_unsaved_reconciliation_ready(tmp_path):
    value = review_all(amend(migrated(), {"tone": "quieter"}))
    value = step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})
    assert j.preflight_journal(value, [], 100000)["blocked"] is True
    path = tmp_path / "reconciled.journal.json"
    saved = j.save_journal(path, value)
    assert j.preflight_journal(saved["journal"], [], 100000)["blocked"] is True
    loaded = j.load_journal(path, expected_story_id=value.story_id)
    assert j.preflight_journal(loaded, [], 100000)["blocked"] is False
    imported = json.loads(loaded.model_dump_json())
    assert j.preflight_journal(imported, [], 100000)["blocked"] is True


def test_actual_readback_checkpoint_can_resume_and_replay_without_new_read_claim(tmp_path):
    value = review_all(amend(migrated(), {"tone": "quieter"}))
    value = step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})
    path = tmp_path / "reconciled.journal.json"
    j.save_journal(path, value)
    loaded = j.load_journal(path, expected_story_id=value.story_id)
    checkpoint = {key: loaded.readback_receipt[key] for key in ("journal_sha256", "file_sha256", "location")}
    cmd = command(loaded, "story", start_payload(checkpoint=checkpoint))
    continued = j.transition_journal(loaded, cmd)
    assert j.project_journal(continued).story["progress"]["chapter_id"] == "ch-002"
    restored = j.validate_journal(continued.model_dump_json())
    assert j.project_journal(restored) == j.project_journal(continued)
    assert restored.readback_receipt["status"] == "pending"
    assert j.project_journal(restored).story["readback_receipt"]["status"] == "pending"
    assert j.transition_journal(restored, cmd).model_dump(mode="json") == restored.model_dump(mode="json")


def test_unrelated_supersession_cannot_clear_known_historical_repair():
    value = amend(migrated(), {"tone": "quieter"})
    item = j.project_journal(value).impacts["chapter:ch-001"]
    value = step(value, "review_impact", review_payload(item, "requires_revision"))
    before = value.model_dump_json()
    with pytest.raises(j.JournalError, match="exact context reversal"):
        amend(value, {"tone": "even quieter"})
    assert value.model_dump_json() == before
    assert j.project_journal(value).impacts["chapter:ch-001"]["status"] == "requires_revision"


def test_active_plan_draft_counters_and_old_evidence_survive_amendment(tmp_path):
    state = v1.create_state("adversarial-story")
    state = legacy_step(state, "start_chapter", {"chapter_id": "ch-active"})
    plan = source("Unchanged candidate plan", "plan").model_dump(mode="json")
    draft = source("Unchanged candidate draft", "draft").model_dump(mode="json")
    state = legacy_step(state, "set_plan", {"artifact": plan})
    old_confirmation = legacy_confirmation(state, "plan")
    state = legacy_step(state, "accept_plan", {"confirmation": old_confirmation})
    state = legacy_step(state, "set_draft", {"artifact": draft})
    value = amend(migrated(state), {"tone": "quieter"})
    p = j.project_journal(value)
    archived = p.archived_progress[-1]["progress"]
    assert archived["plan"] == plan and archived["draft"] == draft
    assert archived["plan_acceptance"] == v1.Confirmation.model_validate(old_confirmation).model_dump(mode="json")
    assert p.story["progress"]["plan_revision"] == 1
    assert p.story["progress"]["draft_revision"] == 1
    assert p.story["progress"]["plan_acceptance"] is None
    value = review_all(value)
    value = step(value, "resume_reconciled", {"confirmation": explicit(value, "resume")})
    path = tmp_path / "active.journal.json"
    j.save_journal(path, value)
    loaded = j.load_journal(path, expected_story_id=value.story_id)
    checkpoint = {key: loaded.readback_receipt[key] for key in ("journal_sha256", "file_sha256", "location")}
    value = step(loaded, "story", {"action": "set_plan", "payload": {"artifact": plan},
        "context_confirmation": None, "checkpoint": checkpoint})
    assert j.project_journal(value).story["progress"]["plan_revision"] == 2
    with pytest.raises(v1.StateError, match="confirmation"):
        step(value, "story", {"action": "accept_plan", "payload": {"confirmation": old_confirmation},
            "context_confirmation": explicit(value, "story"), "checkpoint": None})


@pytest.mark.parametrize("after_replace", [False, True])
def test_interrupted_journal_replace_recovers_without_duplicate_event(tmp_path, monkeypatch, after_replace):
    value = migrated()
    path = tmp_path / "interrupt.journal.json"
    original = j.save_journal(path, value)
    old_bytes = path.read_bytes()
    cmd = command(value, "propose_amendment", {"reason": "Synthetic new tone",
        "changes": [{"path": "/style_profile", "old_value": {}, "new_value": {"tone": "quieter"}}]})
    changed = j.transition_journal(value, cmd)
    real_replace = j.os.replace

    def interrupt(source_path, destination_path):
        if after_replace:
            real_replace(source_path, destination_path)
        raise OSError("synthetic process interruption")

    monkeypatch.setattr(j.os, "replace", interrupt)
    with pytest.raises(OSError, match="synthetic process interruption"):
        j.save_journal(path, changed, expected_disk_sha256=original["sha256"])
    monkeypatch.setattr(j.os, "replace", real_replace)
    loaded = j.load_journal(path, expected_story_id=value.story_id)
    if after_replace:
        assert path.read_bytes() != old_bytes
        assert len(loaded.events) == 1
        retried = j.transition_journal(loaded, cmd)
        assert len(retried.events) == 1
        no_change = j.save_journal(path, retried, expected_disk_sha256=loaded.readback_receipt["file_sha256"])
        assert no_change["changed"] is False
    else:
        assert path.read_bytes() == old_bytes
        assert len(loaded.events) == 0
        retried = j.transition_journal(loaded, cmd)
        saved = j.save_journal(path, retried, expected_disk_sha256=original["sha256"])
        assert saved["changed"] is True
        assert len(j.load_journal(path, expected_story_id=value.story_id).events) == 1
    assert not list(tmp_path.glob("*.tmp"))
