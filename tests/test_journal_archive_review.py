"""Independent synthetic journal continuation ownership/readback review."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import httpx
import pytest

from novel_ai import accepted_writing as writing
from novel_ai import gpt_story_journal as journal
from novel_ai import gpt_story_state as state
from test_accepted_archive_writing import ready_archive, session, digest
from test_gpt_story_journal import migrated, propose, accept_proposal, reconcile, review, story, chapter_confirmation, art
from test_gpt_story_state import planned


def stable_hash(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@pytest.fixture
def saved_journal(tmp_path):
    original = ready_archive(tmp_path)
    value = migrated(state.load_state(original, expected_story_id="synthetic-story"))
    path = tmp_path / "synthetic.journal.json"
    saved = journal.save_journal(path, value)
    value = journal.load_journal(path, expected_story_id=value.story_id, expected_sha256=saved["sha256"])
    return path, value


def identity(value, path):
    projection = journal.project_journal(value)
    return {"expected_story_id": value.story_id, "expected_revision": projection.story["revision"],
        "expected_context_revision": projection.context_revision,
        "expected_journal_sha256": journal.journal_fingerprint(value), "expected_file_sha256": digest(path)}


def restore(path, value):
    return writing.restore_journal_source(path, **identity(value, path))


def save_load(path, value):
    journal.save_journal(path, value, expected_disk_sha256=digest(path))
    return journal.load_journal(path, expected_story_id=value.story_id, expected_sha256=digest(path))


@pytest.mark.parametrize("variant,expected", [
    ("history", "2ef44140a2e09fd8cb51c690216ba17df3502cc60e9939231e8dd33dedd0825a"),
    ("default", "2fa3076fb6dc779fecfc607dd6a9c2562bf828303dd536616c755f4c7be131c7"),
    ("omit", "835a2670444cdd9c72a811edc689139eada71d45465c39d3be7f4b5e25b34cb0"),
    ("no_auto", "5739e49489c4fd9e69c760ad2edc8678887f40d592a20119799574d279582e4d"),
    ("small", "a240c410396256170d69616baa2c2ff498b9426ad635e045fdb0d557896b40ec"),
])
def test_native_v1_matches_fixed_pr54_golden(tmp_path, variant, expected):
    # Values independently computed against frozen PR54 source 39d101330a11.
    # CI uses constants; it does not need another local checkout.
    value = state.load_state(ready_archive(tmp_path), expected_story_id="synthetic-story")
    if variant == "history":
        result = state.rebuild_accepted_history(value)
        result["readback_file_sha256"] = "NORMALIZED_FILE_SHA"
    else:
        options = {"include_current_draft": False} if variant == "omit" else {"history_source_limit": 0} if variant == "no_auto" else {}
        result = state.preflight_next_chapter_context(value, [], 1000 if variant == "small" else 200000, **options)
        result["accepted_history"]["readback_file_sha256"] = "NORMALIZED_FILE_SHA"
    assert stable_hash(result) == expected


@pytest.mark.parametrize("mode,expected", [
    ("history", "caba19ba2ec1ab0e6356275861f54593382a46bb5919a83e7f81fc5a87c96078"),
    ("preflight", "03464a085e5da14a307bef0ef7e3aacb761d9b220b6295a542844169e1b8869d"),
])
def test_native_revision_zero_default_matches_fixed_pr54_golden(mode, expected):
    value = planned()
    result = state.rebuild_accepted_history(value) if mode == "history" else state.preflight_next_chapter_context(value, [], 200000)
    assert stable_hash(result) == expected


@pytest.mark.parametrize("kind", ["dict", "json", "validate", "model_validate", "forged_public_receipt"])
def test_serialized_or_revalidated_observation_cannot_authorize_history(saved_journal, kind):
    path, value = saved_journal
    if kind == "dict": changed = value.model_dump(mode="json")
    elif kind == "json": changed = value.model_dump_json()
    elif kind == "validate": changed = journal.validate_journal(value)
    else:
        changed = journal.Journal.model_validate(value.model_dump())
        if kind == "forged_public_receipt": changed.readback_receipt = deepcopy(value.readback_receipt)
    with pytest.raises(ValueError, match="actual|observation|readback"):
        journal.rebuild_journal_accepted_history(changed, **identity(value, path))


@pytest.mark.parametrize("field", ["status", "journal_sha256", "file_sha256", "location"])
def test_private_observation_must_bind_current_envelope(saved_journal, field):
    path, value = saved_journal
    changed = deepcopy(value)
    changed._observed_readback[field] = "" if field == "location" else "f" * 64
    with pytest.raises(ValueError, match="actual|readback"):
        journal.rebuild_journal_accepted_history(changed, **identity(value, path))


@pytest.mark.parametrize("field,bad", [
    ("expected_story_id", "other"), ("expected_revision", 2), ("expected_revision", True),
    ("expected_context_revision", 1), ("expected_context_revision", False),
    ("expected_journal_sha256", "0" * 64), ("expected_file_sha256", "f" * 64),
])
def test_explicit_identity_mismatch_never_dispatches(saved_journal, monkeypatch, field, bad):
    path, value = saved_journal
    expected = identity(value, path); expected[field] = bad
    flow, calls = session(monkeypatch)
    with pytest.raises(ValueError):
        source = writing.restore_journal_source(path, **expected)
        flow.run_from_accepted_archive(source, current_chapter_id="ch-2")
    assert calls == []


@pytest.mark.parametrize("projection", ["owned_story", "public_projection", "handle_state"])
def test_public_state_never_loses_journal_ownership(saved_journal, tmp_path, projection):
    path, value = saved_journal
    source = restore(path, value)
    if projection == "owned_story": owned = journal.owned_story(value)
    elif projection == "public_projection": owned = state.validate_state(journal.project_journal(value).story)
    else: owned = source.state
    assert owned.journal_owner["journal_sha256"] == source.journal_sha256
    assert owned.write_receipt["status"] == owned.readback_receipt["status"] == "pending"
    with pytest.raises(ValueError, match="journal"): state.rebuild_accepted_history(owned)
    with pytest.raises(ValueError, match="journal"): state.preflight_next_chapter_context(owned, [], 200000)
    with pytest.raises(ValueError, match="journal"): state.save_state(tmp_path / "must-not-exist.json", owned)
    assert not (tmp_path / "must-not-exist.json").exists()


@pytest.mark.parametrize("phase", ["proposal", "accepted", "missing_derived", "requires_revision"])
def test_saved_but_unreconciled_amendments_stay_blocked(saved_journal, phase):
    path, value = saved_journal
    changed = propose(value)
    if phase != "proposal": changed = accept_proposal(changed)
    if phase == "missing_derived":
        for target in journal.project_journal(changed).impacts:
            if target != "derived_context": changed = review(changed, target)
    elif phase == "requires_revision":
        target = next(iter(journal.project_journal(changed).impacts))
        changed = review(changed, target, "requires_revision")
    changed = save_load(path, changed)
    with pytest.raises(ValueError, match="pending|reconciliation|impact"):
        restore(path, changed)


def test_reconciled_context_requires_its_current_actual_readback(saved_journal):
    path, old = saved_journal
    value = reconcile(accept_proposal(propose(old)))
    assert journal.project_journal(value).requires_checkpoint
    expected = identity(value, path)
    with pytest.raises(ValueError, match="readback"):
        journal.rebuild_journal_accepted_history(value, **expected)
    saved = journal.save_journal(path, value, expected_disk_sha256=digest(path))
    with pytest.raises(ValueError, match="readback"):
        journal.rebuild_journal_accepted_history(saved["journal"], **identity(saved["journal"], path))
    loaded = journal.load_journal(path, expected_story_id=value.story_id)
    result = journal.rebuild_journal_accepted_history(loaded, **identity(loaded, path))
    assert result["journal_binding"]["context_revision"] == 1
    assert journal.project_journal(loaded).requires_checkpoint  # Reading is not a transition.
    assert loaded.readback_receipt["status"] == "verified"
    assert journal.owned_story(loaded).readback_receipt["status"] == "pending"


def test_four_stage_owned_continuation_preserves_envelope_and_pending_acceptance(saved_journal, monkeypatch):
    path, value = saved_journal
    before = path.read_bytes(); source = restore(path, value)
    flow, calls = session(monkeypatch)
    result = flow.run_from_accepted_archive(source, current_chapter_id="ch-2", auto_repair=True)
    assert len(calls) == 4 and result.final_text
    for req in calls:
        assert source.journal_sha256 in req.content.decode()
        assert "AUTHOR JOURNAL IDENTITY DATA ONLY" in req.content.decode()
        assert "这句未接受草稿绝不进入历史" not in req.content.decode()
    assert path.read_bytes() == before
    assert source.state.progress.chapter_acceptance is None
    assert source.state.progress.memory_acceptance is None
    assert source.state.journal_owner["context_revision"] == 0
    assert result.report()["source"]["source_kind"] == "author_journal"


@pytest.mark.parametrize("kind", ["duplicate", "truncated", "altered_confirmation", "wrong_parent"])
def test_replay_corruption_is_rejected_before_transport(saved_journal, monkeypatch, kind):
    path, value = saved_journal
    # Add an authorized synthetic candidate-only event so the chain is nonempty.
    changed = story(value, "set_draft", {"artifact": art("未接受的新稿", "candidate").model_dump(mode="json")})
    changed = save_load(path, changed)
    payload = json.loads(path.read_text())
    if kind == "truncated": path.write_bytes(path.read_bytes()[:-9])
    else:
        if kind == "duplicate": payload["events"].append(deepcopy(payload["events"][0]))
        elif kind == "wrong_parent": payload["events"][0]["previous_event_sha256"] = "a" * 64
        else: payload["migration_confirmation"]["confirmed_by"] = "model"
        path.write_text(json.dumps(payload, ensure_ascii=False))
    flow, calls = session(monkeypatch)
    with pytest.raises(ValueError): restore(path, changed)
    assert calls == []


def test_journal_history_preserves_native_hash_and_derivation(saved_journal, tmp_path):
    path, value = saved_journal
    native = state.load_state(tmp_path / "private-story.json", expected_story_id=value.story_id)
    expected = state.rebuild_accepted_history(native)
    actual = journal.rebuild_journal_accepted_history(value, **identity(value, path))
    actual.pop("journal_binding"); actual.pop("readback_scope")
    actual["readback_file_sha256"] = expected["readback_file_sha256"]
    assert actual == expected


def test_candidate_event_keeps_history_hash_but_invalidates_prior_result(saved_journal, monkeypatch):
    path, value = saved_journal
    source = restore(path, value)
    old = journal.rebuild_journal_accepted_history(value, **identity(value, path))["accepted_history_sha256"]
    flow, calls = session(monkeypatch)
    result = flow.run_from_accepted_archive(source, current_chapter_id="ch-2", review=False)
    changed = story(value, "set_draft", {"artifact": art("第二版未接受候选", "new-candidate").model_dump(mode="json")})
    changed = save_load(path, changed)
    current = journal.rebuild_journal_accepted_history(changed, **identity(changed, path))
    assert current["accepted_history_sha256"] == old
    assert current["journal_binding"]["journal_sha256"] != source.journal_sha256
    with pytest.raises(ValueError): source.assert_current()
    with pytest.raises(ValueError): result.report()
    with pytest.raises(ValueError): _ = result.final_text
    assert len(calls) == 1


def test_context_reversal_cannot_reuse_old_journal_authority(saved_journal):
    path, value = saved_journal
    source = restore(path, value)
    previous = journal.rebuild_journal_accepted_history(value, **identity(value, path))
    initial_style = deepcopy(source.state.style_profile)
    changed = save_load(path, reconcile(accept_proposal(propose(value))))
    middle = journal.rebuild_journal_accepted_history(changed, **identity(changed, path))
    assert middle["accepted_history_sha256"] != previous["accepted_history_sha256"]
    reverted = save_load(path, reconcile(accept_proposal(propose(changed, initial_style))))
    current = journal.rebuild_journal_accepted_history(reverted, **identity(reverted, path))
    assert current["accepted_history_sha256"] == previous["accepted_history_sha256"]
    assert current["journal_binding"]["context_revision"] == 2
    assert current["journal_binding"]["journal_sha256"] != source.journal_sha256
    with pytest.raises(ValueError): source.assert_current()
    owned = restore(path, reverted).state
    assert owned.journal_owner["context_revision"] == 2
    assert owned.progress.plan_acceptance is None


def test_reconciled_context_requires_new_plan_and_context_confirmation(saved_journal, monkeypatch):
    path, value = saved_journal
    old_confirmation = deepcopy(journal.owned_story(value).progress.plan_acceptance.model_dump(mode="json"))
    plan = deepcopy(journal.owned_story(value).progress.plan.model_dump(mode="json"))
    changed = save_load(path, reconcile(accept_proposal(propose(value))))
    flow, calls = session(monkeypatch)
    with pytest.raises(ValueError, match="accepted plan|ready_to_draft"):
        flow.run_from_accepted_archive(restore(path, changed), current_chapter_id="ch-2")
    changed = story(changed, "set_plan", {"artifact": plan})
    with pytest.raises(ValueError): story(changed, "accept_plan", {"confirmation": old_confirmation})
    changed = story(changed, "accept_plan", {"confirmation": chapter_confirmation(changed, "plan")})
    changed = save_load(path, changed)
    result = flow.run_from_accepted_archive(restore(path, changed), current_chapter_id="ch-2", review=False)
    assert result.final_text and len(calls) == 1
    assert result.report()["source"]["context_revision"] == 1


@pytest.mark.parametrize("stage", [1, 2, 3, 4])
def test_changed_journal_body_stops_each_physical_stage(saved_journal, monkeypatch, stage):
    path, value = saved_journal
    source = restore(path, value)
    def change(request, count):
        if count == stage: path.write_bytes(path.read_bytes() + b" ")
    flow, calls = session(monkeypatch, change)
    with pytest.raises(ValueError, match="journal|archive"):
        flow.run_from_accepted_archive(source, current_chapter_id="ch-2", auto_repair=True)
    assert len(calls) == stage
    assert flow.budget_snapshot()["attempts"][-1]["status"] == "failed"


def test_changed_journal_on_format_error_blocks_internal_fallback(saved_journal, monkeypatch):
    path, value = saved_journal
    source = restore(path, value)
    def change(request, count):
        if count == 2:
            path.write_bytes(path.read_bytes() + b" ")
            return httpx.Response(400, json={"error": {"param": "response_format", "code": "unsupported_parameter"}})
    flow, calls = session(monkeypatch, change)
    with pytest.raises(ValueError, match="journal|archive"):
        flow.run_from_accepted_archive(source, current_chapter_id="ch-2", auto_repair=True)
    assert len(calls) == flow.budget_snapshot()["requests_reserved"] == 2


def test_journal_authority_budget_reserves_all_blocks_before_optional_recall(saved_journal):
    path, value = saved_journal
    source = restore(path, value)
    options = {"current_chapter_id": "ch-2", "history_source_limit": 0}
    initial = writing.prepare_accepted_context(source, **options)
    size = initial["preflight"]["used_bytes"]
    exact = writing.prepare_accepted_context(source, **options, budget_bytes=size, recall_chapter_ids=["ch-1"])
    assert exact["preflight"]["used_bytes"] == len(exact["preflight"]["context_text"].encode()) == size
    assert exact["preflight"]["journal_authority_bytes"] > 0
    assert exact["preflight"]["authority_binding_bytes"] > 0
    assert exact["preflight"]["dropped_sources"] and not exact["preflight"]["selected_sources"]
    with pytest.raises(ValueError): writing.prepare_accepted_context(source, **options, budget_bytes=size - 1)


@pytest.mark.parametrize("field", ["path", "state_sha256", "context_revision", "journal_sha256"])
def test_forged_handle_identity_never_dispatches(saved_journal, monkeypatch, field):
    path, value = saved_journal
    source = restore(path, value)
    replacement = str(path.parent / "missing.json") if field == "path" else 1 if field == "context_revision" else "f" * 64
    forged = replace(source, **{field: replacement})
    flow, calls = session(monkeypatch)
    with pytest.raises((ValueError, OSError)):
        flow.run_from_accepted_archive(forged, current_chapter_id="ch-2", review=False)
    assert calls == []


def test_direct_journal_preflight_does_not_invent_v1_receipts(saved_journal):
    path, value = saved_journal
    before = value.model_dump(mode="json")
    result = journal.preflight_journal_next_chapter_context(value, [], 200000, **identity(value, path))
    assert not result["blocked"]
    assert value.model_dump(mode="json") == before
    assert journal.project_journal(value).story["readback_receipt"]["status"] == "pending"
    assert result["journal_binding"]["file_sha256"] == digest(path)


def test_duplicate_json_keys_cannot_hide_journal_envelope_identity(saved_journal):
    path, value = saved_journal
    raw = path.read_text()
    assert '"engine_version":"gpt-author-journal-v1"' in raw
    path.write_text(raw.replace('"engine_version":"gpt-author-journal-v1"', '"engine_version":"fake","engine_version":"gpt-author-journal-v1"', 1))
    with pytest.raises(ValueError, match="duplicate"):
        restore(path, value)
