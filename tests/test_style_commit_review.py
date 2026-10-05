"""Independent adversarial tests for the fixed Style Lab persistence boundary.

Synthetic profiles only. These tests intentionally exercise the public style
commit API and publication failures, without assuming private receipt fields.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from novel_ai import style_commit as commit
from novel_ai.models import StyleFingerprint
from novel_ai.storage import ProjectStore
from novel_ai.style_engine import blend_styles

PROJECT = "ReviewBook"
_REQUEST_SEQUENCE = itertools.count(1)
_REQUESTS = {}
_REQUEST_LOCK = threading.Lock()


def profile(name="Synthetic A", weight=1.0):
    return {
        "name": name,
        "weight": weight,
        "fingerprint": StyleFingerprint(
            name=name, avg_sentence_chars=12.0, avg_paragraph_chars=45.0,
            custom_notes=["Synthetic high-level rhythm only"],
        ).model_dump(),
        "decoding": None,
    }


def library_files(profiles=None, *, extra_style=None):
    profiles = [profile()] if profiles is None else profiles
    style = blend_styles(
        [(StyleFingerprint.model_validate(p["fingerprint"]), p["weight"]) for p in profiles],
        name="Novel-Composite",
    ).model_dump() if profiles else None
    if extra_style:
        style.update(extra_style)
    values = [profiles, style, {"hashes": ["a" * 20] if profiles else [], "shingle_chars": 18}]
    return dict(zip(commit.STYLE_PATHS, values, strict=True))


def raw_snapshot(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*") if p.is_file() and p.name != ".store.lock"
    }


def seed_legacy(store, *, profiles=None, extra_style=None):
    values = library_files(profiles, extra_style=extra_style)
    root = store.project_dir(PROJECT)
    for relative, value in values.items():
        # Deliberately noncanonical whitespace. A read must not migrate bytes.
        raw = json.dumps(value, ensure_ascii=False, indent=3) + "\n\n"
        (root / relative).write_text(raw, encoding="utf-8")
    return values


def prepared(store, name="Synthetic B", hash_char="b"):
    snapshot = commit.load_style_bundle(store, PROJECT)
    files = commit.prepare_style_addition(snapshot, profile(name), {hash_char * 20})
    return snapshot, files


def publish(store, snapshot, files, *, request_id=None):
    # A freshly prepared dict represents a new intentional action. Reusing the
    # same frozen dict, including after failure, reuses its request nonce.
    if request_id is None:
        with _REQUEST_LOCK:
            key = id(files)
            if key not in _REQUESTS:
                _REQUESTS[key] = (files, f"{next(_REQUEST_SEQUENCE):032x}")
            request_id = _REQUESTS[key][1]
    return commit.commit_style_bundle(
        store, PROJECT, files=files, expected_before=snapshot["sha256"],
        request_id=request_id,
    )


def assert_after_images(store, files):
    root = store.project_dir(PROJECT)
    assert all((root / path).read_bytes() == text.encode("utf-8") for path, text in files.items())


def test_empty_library_load_creates_no_style_or_receipt_files(tmp_path):
    store = ProjectStore(tmp_path)
    bundle = commit.load_style_bundle(store, PROJECT)
    assert bundle["profiles"] == [] and bundle["style"] is None
    assert bundle["signature"] == {"hashes": [], "shingle_chars": 18}
    assert bundle["sha256"] == dict.fromkeys(commit.STYLE_PATHS)
    assert raw_snapshot(store.project_dir(PROJECT)) == {}


def test_complete_legacy_load_preserves_raw_bytes_omitted_defaults_and_extensions(tmp_path):
    store = ProjectStore(tmp_path)
    old = profile()
    old.pop("decoding")
    old["fingerprint"] = {"name": old["name"], "avg_sentence_chars": 12.0}
    old["legacy_provenance"] = {"source": "synthetic private fixture"}
    original = seed_legacy(store, profiles=[old], extra_style={"custom_dimension": {"pace": "steady"}})
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    loaded = commit.load_style_bundle(store, PROJECT)
    assert loaded["profiles"] == original[commit.STYLE_PATHS[0]]
    assert loaded["style"] == original[commit.STYLE_PATHS[1]]
    assert loaded["signature"] == original[commit.STYLE_PATHS[2]]
    assert loaded["sha256"] == {p: hashlib.sha256(before[p]).hexdigest() for p in commit.STYLE_PATHS}
    assert raw_snapshot(root) == before
    # Returned containers do not become a mutable cache inside the store.
    loaded["style"]["custom_dimension"]["pace"] = "caller mutation"
    assert commit.load_style_bundle(store, PROJECT)["style"] == original[commit.STYLE_PATHS[1]]


@pytest.mark.parametrize("present", [bits for bits in itertools.product([False, True], repeat=3) if 0 < sum(bits) < 3])
def test_every_incomplete_legacy_triplet_fails_without_inventing_or_removing_files(tmp_path, present):
    store = ProjectStore(tmp_path)
    values = library_files()
    root = store.project_dir(PROJECT)
    for path, exists in zip(commit.STYLE_PATHS, present, strict=True):
        if exists:
            (root / path).write_text(json.dumps(values[path]), encoding="utf-8")
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.load_style_bundle(store, PROJECT)
    assert raw_snapshot(root) == before


def test_legacy_manual_known_override_loads_but_add_refuses_and_explicit_clear_works(tmp_path):
    store = ProjectStore(tmp_path)
    seed_legacy(store, extra_style={"diction": "Author-locked synthetic diction", "custom_dimension": "retained"})
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    snapshot = commit.load_style_bundle(store, PROJECT)
    assert snapshot["style"]["diction"] == "Author-locked synthetic diction"
    with pytest.raises(ValueError):
        commit.prepare_style_addition(snapshot, profile("B"), {"b" * 20})
    assert raw_snapshot(root) == before
    files = commit.prepare_style_clear(snapshot)
    result = publish(store, snapshot, files)
    assert result["current"]["profiles"] == []
    assert result["current"]["style"] is None
    assert result["current"]["signature"]["hashes"] == []
    assert commit.load_style_bundle(ProjectStore(tmp_path), PROJECT)["profiles"] == []


def test_new_addition_preserves_legacy_profile_and_unknown_composite_fields(tmp_path):
    store = ProjectStore(tmp_path)
    old = profile()
    old["private_extension"] = {"category": "synthetic"}
    seed_legacy(store, profiles=[old], extra_style={"custom_dimension": {"cadence": ["short", "long"]}})
    snapshot, files = prepared(store)
    before = deepcopy(snapshot)
    after_profiles = json.loads(files[commit.STYLE_PATHS[0]])
    after_style = json.loads(files[commit.STYLE_PATHS[1]])
    assert after_profiles[0] == old
    assert after_style["custom_dimension"] == snapshot["style"]["custom_dimension"]
    assert snapshot == before
    publish(store, snapshot, files)
    assert commit.load_style_bundle(store, PROJECT)["style"]["custom_dimension"] == after_style["custom_dimension"]


@pytest.mark.parametrize("weight", [0, -1, True, False, float("nan"), float("inf"), -float("inf"), "1.0"])
def test_addition_refuses_nonpositive_nonfinite_or_coerced_weights_without_mutation(tmp_path, weight):
    store = ProjectStore(tmp_path)
    snapshot = commit.load_style_bundle(store, PROJECT)
    before = deepcopy(snapshot)
    with pytest.raises(ValueError):
        commit.prepare_style_addition(snapshot, profile(weight=weight), {"b" * 20})
    assert snapshot == before
    assert raw_snapshot(store.project_dir(PROJECT)) == {}


@pytest.mark.parametrize("bad_hash", ["", "b" * 19, "b" * 21, "b" * 64, "B" * 20, "z" * 20, 42])
def test_shingle_signatures_require_current_20_lowercase_hex_format(tmp_path, bad_hash):
    store = ProjectStore(tmp_path)
    snapshot = commit.load_style_bundle(store, PROJECT)
    with pytest.raises(ValueError):
        commit.prepare_style_addition(snapshot, profile(), {bad_hash})
    assert raw_snapshot(store.project_dir(PROJECT)) == {}


def test_stale_session_cannot_replace_a_newer_saved_library(tmp_path):
    store = ProjectStore(tmp_path)
    old, files_a = prepared(store, "A", "a")
    files_b = commit.prepare_style_addition(old, profile("B"), {"b" * 20})
    publish(store, old, files_a)
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(ProjectStore(tmp_path), old, files_b)
    assert raw_snapshot(root) == before
    assert [row["name"] for row in commit.load_style_bundle(store, PROJECT)["profiles"]] == ["A"]


def test_exact_retry_after_newer_add_and_clear_is_historical_and_never_rewrites(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    snapshot_a, files_a = prepared(store, "A", "a")
    first = publish(store, snapshot_a, files_a)
    snapshot_b, files_b = prepared(store, "B", "b")
    publish(store, snapshot_b, files_b)
    newest = commit.load_style_bundle(store, PROJECT)
    publish(store, newest, commit.prepare_style_clear(newest))
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    monkeypatch.setattr(store, "_write", lambda *args, **kwargs: pytest.fail("historical retry rewrote a file"))
    result = publish(store, snapshot_a, files_a)
    assert result["receipt"] == first["receipt"]
    assert result["historical"] is True
    assert result["current"]["profiles"] == [] and result["current"]["style"] is None
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_stale_sessions_commit_once_or_share_exact_retry(tmp_path, same_request):
    store = ProjectStore(tmp_path)
    snapshot, first_files = prepared(store, "A", "a")
    second_files = first_files if same_request else commit.prepare_style_addition(snapshot, profile("B"), {"b" * 20})
    barrier = threading.Barrier(2)

    def attempt(files):
        barrier.wait(timeout=10)
        try:
            return publish(ProjectStore(tmp_path), snapshot, files)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, [first_files, second_files]))
    assert sum(result is not None for result in outcomes) == (2 if same_request else 1)
    if same_request:
        assert outcomes[0]["receipt"] == outcomes[1]["receipt"]
    assert len(commit.load_style_bundle(store, PROJECT)["profiles"]) == 1


@pytest.mark.parametrize("target_index", [0, 1, 2])
@pytest.mark.parametrize("after_publication", [False, True])
def test_failure_before_or_after_each_target_publication_recovers_exact_frozen_images(
    tmp_path, monkeypatch, target_index, after_publication,
):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    snapshot, files = prepared(store)
    original_write = store._write
    target = commit.STYLE_PATHS[target_index]
    root = store.project_dir(PROJECT)

    def failing_write(path, content, **kwargs):
        matches = path.relative_to(root).as_posix() == target
        if matches and not after_publication:
            raise OSError("synthetic before target publication")
        result = original_write(path, content, **kwargs)
        if matches:
            raise OSError("synthetic after target publication")
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", failing_write)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    assert (root / commit.INTENT_PATH).exists()
    # A fresh reader must recover the complete batch before returning state.
    recovered = commit.load_style_bundle(ProjectStore(tmp_path), PROJECT)
    assert recovered["profiles"] == json.loads(files[commit.STYLE_PATHS[0]])
    assert recovered["style"] == json.loads(files[commit.STYLE_PATHS[1]])
    assert recovered["signature"] == json.loads(files[commit.STYLE_PATHS[2]])
    assert_after_images(store, files)
    assert not (root / commit.INTENT_PATH).exists()
    result = publish(store, snapshot, files)
    assert result["current"] == recovered


def leave_pending(store, monkeypatch):
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    original_write = store._write

    def stop_on_second_target(path, content, **kwargs):
        if path.relative_to(root).as_posix() == commit.STYLE_PATHS[1]:
            raise OSError("synthetic pending style commit")
        return original_write(path, content, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", stop_on_second_target)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    return root, snapshot, files


def test_independently_changed_target_blocks_all_remaining_recovery_writes(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    root, _, _ = leave_pending(store, monkeypatch)
    (root / commit.STYLE_PATHS[2]).write_text('{"hashes":["cccccccccccccccccccc"],"shingle_chars":18}\n')
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.recover_style_commit(store, PROJECT)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("fault", ["duplicate_key", "array_root", "empty_object", "invalid_utf8", "nonfinite", "foreign_project"])
def test_corrupt_recovery_intent_is_preserved_and_never_publishes_more_targets(tmp_path, monkeypatch, fault):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    root, _, _ = leave_pending(store, monkeypatch)
    path = root / commit.INTENT_PATH
    original = path.read_bytes()
    value = json.loads(original)
    if fault == "duplicate_key":
        key = next(iter(value))
        extra = json.dumps(key) + ":" + json.dumps(value[key])
        bad = ("{" + extra + "," + original.decode("utf-8").lstrip()[1:]).encode("utf-8")
    elif fault == "array_root":
        bad = b"[]"
    elif fault == "empty_object":
        bad = b"{}"
    elif fault == "invalid_utf8":
        bad = b"\xff"
    elif fault == "nonfinite":
        bad = b'{"value":1e999}'
    else:
        value["receipt"]["project"] = "ForeignBook"
        bad = json.dumps(value).encode("utf-8")
    path.write_bytes(bad)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.load_style_bundle(store, PROJECT)
    assert raw_snapshot(root) == before


def test_reported_success_without_exact_intent_readback_cannot_publish_targets(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    original_write = store._write

    def omit_intent(path, content, **kwargs):
        if path.name == commit.INTENT_PATH:
            return None
        return original_write(path, content, **kwargs)

    monkeypatch.setattr(store, "_write", omit_intent)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


def test_prepared_files_detach_caller_profile_and_hash_container(tmp_path):
    store = ProjectStore(tmp_path)
    snapshot = commit.load_style_bundle(store, PROJECT)
    row, hashes = profile(), {"a" * 20}
    files = commit.prepare_style_addition(snapshot, row, hashes)
    row["fingerprint"]["custom_notes"].append("unconfirmed caller mutation")
    hashes.add("b" * 20)
    publish(store, snapshot, files)
    loaded = commit.load_style_bundle(store, PROJECT)
    assert loaded["profiles"][0]["fingerprint"]["custom_notes"] == ["Synthetic high-level rhythm only"]
    assert loaded["signature"]["hashes"] == ["a" * 20]


@pytest.mark.parametrize("coerced_nonfinite", ["NaN", "Infinity", "1e999"])
def test_legacy_style_cannot_hide_nonfinite_values_behind_pydantic_string_coercion(tmp_path, coerced_nonfinite):
    store = ProjectStore(tmp_path)
    seed_legacy(store, extra_style={"avg_sentence_chars": coerced_nonfinite})
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.load_style_bundle(store, PROJECT)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("after_publication", [False, True])
def test_intent_publication_error_never_claims_rollback_or_loses_recovery(tmp_path, monkeypatch, after_publication):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    before = raw_snapshot(root)
    original_write = store._write

    def fail_intent(path, content, **kwargs):
        if path.name != commit.INTENT_PATH:
            return original_write(path, content, **kwargs)
        if after_publication:
            original_write(path, content, **kwargs)
        raise OSError("synthetic intent publication error")

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", fail_intent)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    after = raw_snapshot(root)
    assert {p: after[p] for p in commit.STYLE_PATHS} == {p: before[p] for p in commit.STYLE_PATHS}
    assert (root / commit.INTENT_PATH).exists() is after_publication
    if after_publication:
        commit.load_style_bundle(ProjectStore(tmp_path), PROJECT)
        assert_after_images(store, files)
    else:
        assert after == before


@pytest.mark.parametrize("after_publication", [False, True])
def test_receipt_publication_failure_retains_exact_retry_identity(tmp_path, monkeypatch, after_publication):
    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    original_write = store._write
    receipt_paths = []

    def fail_receipt(path, content, **kwargs):
        relative = path.relative_to(root).as_posix()
        if relative in commit.STYLE_PATHS or relative == commit.INTENT_PATH:
            return original_write(path, content, **kwargs)
        receipt_paths.append(path)
        if after_publication:
            original_write(path, content, **kwargs)
        raise OSError("synthetic receipt publication error")

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", fail_receipt)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    assert len(receipt_paths) == 1
    assert (root / commit.INTENT_PATH).exists()
    assert_after_images(store, files)
    result = publish(store, snapshot, files)
    before = raw_snapshot(root)
    assert result["current"]["profiles"] == json.loads(files[commit.STYLE_PATHS[0]])
    assert publish(store, snapshot, files)["receipt"] == result["receipt"]
    assert raw_snapshot(root) == before


def test_receipt_already_published_recovery_only_cleans_up_and_retains_newer_state(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    original_write = store._write

    def fail_after_receipt(path, content, **kwargs):
        result = original_write(path, content, **kwargs)
        relative = path.relative_to(root).as_posix()
        if relative not in commit.STYLE_PATHS and relative != commit.INTENT_PATH:
            raise OSError("synthetic receipt was already published")
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", fail_after_receipt)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    # Simulate later valid author state outside the still-pending cleanup.
    seed_legacy(store, profiles=[profile("Newer accepted synthetic source")])
    before = raw_snapshot(root)
    monkeypatch.setattr(store, "_write", lambda *args, **kwargs: pytest.fail("receipt cleanup replayed old state"))
    result = publish(store, snapshot, files)
    assert result["historical"] is True
    assert result["current"]["profiles"][0]["name"] == "Newer accepted synthetic source"
    before.pop(commit.INTENT_PATH)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("tamper", ["extra_path", "missing_path", "composite_mismatch", "wrong_shingle_width", "duplicate_hashes", "nonfinite", "duplicate_json_key"])
def test_malformed_new_batch_is_rejected_before_intent_or_canonical_publication(tmp_path, tamper):
    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    if tamper == "extra_path":
        files["chapters/unrelated.md"] = "This may not be a style transaction target"
    elif tamper == "missing_path":
        files.pop(commit.STYLE_PATHS[2])
    elif tamper == "composite_mismatch":
        value = json.loads(files[commit.STYLE_PATHS[1]])
        value["avg_sentence_chars"] += 7
        files[commit.STYLE_PATHS[1]] = json.dumps(value)
    elif tamper == "wrong_shingle_width":
        value = json.loads(files[commit.STYLE_PATHS[2]])
        value["shingle_chars"] = 19
        files[commit.STYLE_PATHS[2]] = json.dumps(value)
    elif tamper == "duplicate_hashes":
        value = json.loads(files[commit.STYLE_PATHS[2]])
        value["hashes"] *= 2
        files[commit.STYLE_PATHS[2]] = json.dumps(value)
    elif tamper == "nonfinite":
        files[commit.STYLE_PATHS[1]] = '{"avg_sentence_chars":1e999}'
    else:
        value = files[commit.STYLE_PATHS[2]]
        files[commit.STYLE_PATHS[2]] = '{"shingle_chars":18,' + value.lstrip()[1:]
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


def test_intentional_readd_after_clear_is_not_misclassified_as_historical_retry(tmp_path):
    store = ProjectStore(tmp_path)
    empty = commit.load_style_bundle(store, PROJECT)
    publish(store, empty, commit.prepare_style_clear(empty))
    first_snapshot, first_files = prepared(store, "Same intentional source", "a")
    publish(store, first_snapshot, first_files)
    full = commit.load_style_bundle(store, PROJECT)
    publish(store, full, commit.prepare_style_clear(full))
    second_snapshot, second_files = prepared(store, "Same intentional source", "a")
    # Identical content has returned, but this is a new explicit add action.
    assert second_snapshot["sha256"] == first_snapshot["sha256"]
    assert second_files == first_files
    result = publish(store, second_snapshot, second_files)
    assert result["historical"] is False
    assert [p["name"] for p in result["current"]["profiles"]] == ["Same intentional source"]
    old_retry = publish(store, first_snapshot, first_files)
    # The earlier operation is still exactly-once, even though a newer explicit
    # operation has returned the canonical bytes to its historical after-image.
    assert old_retry["receipt"] != result["receipt"]
    assert old_retry["current"] == result["current"]


@pytest.mark.parametrize("request_id", ["", "a" * 31, "a" * 33, "a" * 64, "A" * 32, "z" * 32, True, 123])
def test_request_nonce_must_be_explicit_32_lowercase_hex_without_writes(tmp_path, request_id):
    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    before = raw_snapshot(store.project_dir(PROJECT))
    with pytest.raises(ValueError):
        publish(store, snapshot, files, request_id=request_id)
    assert raw_snapshot(store.project_dir(PROJECT)) == before


def test_cached_project_return_refreshes_saved_style_and_keeps_unsaved_writing_draft(tmp_path):
    from novel_ai.project_session import switch_project

    store = ProjectStore(tmp_path)
    state = {}
    switch_project(state, store, PROJECT)
    state.update(characters=[{"name": "Unsaved synthetic character"}], chapter_goal="Unsaved chapter goal")
    switch_project(state, store, "OtherBook")
    snapshot, files = prepared(store)
    publish(store, snapshot, files)
    switch_project(state, store, PROJECT)
    assert state["characters"] == [{"name": "Unsaved synthetic character"}]
    assert state["chapter_goal"] == "Unsaved chapter goal"
    assert state["style_profiles"] == json.loads(files[commit.STYLE_PATHS[0]])
    assert state["style_snapshot"] == commit.load_style_bundle(store, PROJECT)


@pytest.mark.parametrize("other_intent", [".memory-commit-transaction.json", ".extraction-transaction.json"])
def test_coexisting_transaction_intents_block_without_arbitrary_recovery_order(tmp_path, monkeypatch, other_intent):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    root, _, _ = leave_pending(store, monkeypatch)
    (root / other_intent).write_text('{"synthetic":"other pending operation"}')
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        store.read_json(PROJECT, "memory/story_bible.json", {})
    assert raw_snapshot(root) == before


def test_memory_source_capture_cannot_consume_a_partial_style_transaction(tmp_path, monkeypatch):
    from novel_ai.memory_proposals import capture_memory_source
    from novel_ai.models import ChapterPlan

    store = ProjectStore(tmp_path)
    seed_legacy(store)
    root, _, _ = leave_pending(store, monkeypatch)
    before = raw_snapshot(root)
    with pytest.raises(ValueError, match="pending"):
        capture_memory_source(
            store, PROJECT, "c", final_text="Synthetic unaccepted draft",
            plan=ChapterPlan(chapter_id="c", chapter_title="Synthetic", chapter_goal="Synthetic"),
            context={"bible": {"title": "Synthetic"}, "characters": [], "extra": {}},
        )
    assert raw_snapshot(root) == before


def test_ui_frozen_request_survives_failure_without_mutating_live_style_then_retries(tmp_path, monkeypatch):
    from novel_ai.style_ui import (
        apply_style_snapshot,
        commit_pending_style,
        freeze_style_request,
    )

    store = ProjectStore(tmp_path)
    seed_legacy(store)
    snapshot, files = prepared(store)
    state = {}
    apply_style_snapshot(state, snapshot)
    old_fields = deepcopy(state)
    freeze_style_request(state, store, PROJECT, files=files, expected_before=snapshot["sha256"], binding="synthetic-input", kind="add")
    frozen = deepcopy(state["style_pending"])
    root = store.project_dir(PROJECT)
    original_write = store._write

    def fail(path, content, **kwargs):
        if path.relative_to(root).as_posix() == commit.STYLE_PATHS[1]:
            raise OSError("synthetic late UI save failure")
        return original_write(path, content, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", fail)
        with pytest.raises(OSError):
            commit_pending_style(state, store, PROJECT, binding="synthetic-input")
    assert {key: state[key] for key in old_fields} == old_fields
    assert state["style_pending"] == frozen
    result = commit_pending_style(state, ProjectStore(tmp_path), PROJECT, binding="synthetic-input")
    assert state["style_pending"] is None
    assert state["style_snapshot"] == result["current"]
    assert len(state["style_profiles"]) == 2


@pytest.mark.parametrize("field,value", [
    ("source", "changed-source"), ("name", "changed-name"), ("weight", 2.0),
    ("encoding", "gb18030"), ("semantic", True), ("notes", "changed notes"),
])
def test_changed_visible_inputs_cannot_reuse_a_frozen_style_request(tmp_path, field, value):
    from novel_ai.style_ui import (
        apply_style_snapshot,
        commit_pending_style,
        freeze_style_request,
        style_input_binding,
    )

    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    state = {}
    apply_style_snapshot(state, snapshot)
    inputs = {"project": PROJECT, "source": "original-source", "name": "Original name", "weight": 1.0,
              "encoding": "utf-8", "semantic": False, "notes": "Original notes"}
    original_binding = style_input_binding(**inputs)
    freeze_style_request(state, store, PROJECT, files=files, expected_before=snapshot["sha256"], binding=original_binding, kind="add")
    before_state = deepcopy(state)
    before_disk = raw_snapshot(store.project_dir(PROJECT))
    inputs[field] = value
    with pytest.raises(ValueError):
        commit_pending_style(state, store, PROJECT, binding=style_input_binding(**inputs))
    assert state == before_state
    assert raw_snapshot(store.project_dir(PROJECT)) == before_disk


def test_preanalysis_style_check_refuses_stale_session_without_overwriting_draft(tmp_path):
    from novel_ai.style_ui import apply_style_snapshot, require_current_style

    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    state = {"chapter_goal": "Unsaved synthetic goal"}
    apply_style_snapshot(state, snapshot)
    publish(store, snapshot, files)
    before = deepcopy(state)
    with pytest.raises(ValueError):
        require_current_style(state, store, PROJECT)
    assert state == before


def test_reused_request_nonce_cannot_rebind_another_payload_or_baseline(tmp_path):
    store = ProjectStore(tmp_path)
    original, files = prepared(store, "Original", "a")
    nonce = "d" * 32
    publish(store, original, files, request_id=nonce)
    current, changed = prepared(store, "Changed", "b")
    before = raw_snapshot(store.project_dir(PROJECT))
    with pytest.raises(ValueError):
        publish(store, current, changed, request_id=nonce)
    assert raw_snapshot(store.project_dir(PROJECT)) == before


def test_actual_failed_style_save_does_not_fall_through_to_later_tab_storage_reads(tmp_path, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30).run()
    next(c for c in at.checkbox if c.label == "使用当前模型做语义文体分析").uncheck()
    next(t for t in at.text_area if t.label == "或粘贴参考文本").set_value(
        "原创测试样本。林舟把纸条放在桌上，转身去核对门锁。楼下传来脚步声，他停了一会儿。" * 20,
    )
    failed = [False]
    later_reads = []
    original_write = ProjectStore._write
    original_history = ProjectStore._load_history

    def fail(self, path, content, **kwargs):
        if path.name == "style_dna.json":
            failed[0] = True
            raise OSError("synthetic continuing style-storage failure")
        return original_write(self, path, content, **kwargs)

    def record(self, *args, **kwargs):
        if failed[0]:
            later_reads.append(args)
        return original_history(self, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "_write", fail)
    monkeypatch.setattr(ProjectStore, "_load_history", record)
    next(b for b in at.button if b.label == "分析并加入风格库").click().run()
    assert failed[0] and at.error
    assert at.session_state["style_pending"] is not None
    assert not later_reads
    assert not at.exception


def test_actual_stale_style_session_cannot_dispatch_chapter_generation_with_old_style(tmp_path, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from novel_ai.engine import NovelEngine

    monkeypatch.chdir(tmp_path)
    app = Path(__file__).resolve().parents[1] / "app.py"
    first = AppTest.from_file(str(app), default_timeout=30).run()
    stale = AppTest.from_file(str(app), default_timeout=30).run()
    next(c for c in first.checkbox if c.label == "使用当前模型做语义文体分析").uncheck()
    next(t for t in first.text_area if t.label == "或粘贴参考文本").set_value(
        "原创测试样本。林舟把纸条放在桌上，转身去核对门锁。楼下传来脚步声，他停了一会儿。" * 20,
    )
    next(b for b in first.button if b.label == "分析并加入风格库").click().run()
    calls = []

    def model_must_not_run(*args, **kwargs):
        calls.append(True)
        raise AssertionError("stale style reached model dispatch")

    monkeypatch.setattr(NovelEngine, "run", model_must_not_run)
    next(t for t in stale.text_input if t.label == "Base URL").set_value("http://synthetic.invalid/v1")
    next(t for t in stale.text_input if t.label == "Model").set_value("synthetic-no-network")
    stale.button(key="btn_oneshot").click().run()
    assert not calls
    assert stale.error or stale.exception
    assert stale.session_state["style_profiles"] == []


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
@pytest.mark.parametrize("path_index", [0, 1, 2])
def test_legacy_json_must_be_utf8_even_when_json_parser_can_autodetect_other_encoding(tmp_path, encoding, path_index):
    store = ProjectStore(tmp_path)
    seed_legacy(store)
    root = store.project_dir(PROJECT)
    path = root / commit.STYLE_PATHS[path_index]
    path.write_bytes(path.read_text(encoding="utf-8").encode(encoding))
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.load_style_bundle(store, PROJECT)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("after_unlink", [False, True])
def test_intent_cleanup_error_can_retry_without_republishing_saved_style(tmp_path, monkeypatch, after_unlink):
    from pathlib import Path

    store = ProjectStore(tmp_path)
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    intent_path = root / commit.INTENT_PATH
    original_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path != intent_path:
            return original_unlink(path, *args, **kwargs)
        if after_unlink:
            original_unlink(path, *args, **kwargs)
        raise OSError("synthetic intent cleanup error")

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(OSError):
            publish(store, snapshot, files)
    assert_after_images(store, files)
    monkeypatch.setattr(store, "_write", lambda *args, **kwargs: pytest.fail("cleanup retry republished saved state"))
    result = publish(store, snapshot, files)
    assert result["current"]["profiles"] == json.loads(files[commit.STYLE_PATHS[0]])
    assert not intent_path.exists()
