"""Independent adversarial checks for the fixed local settings save boundary.

Synthetic settings only. The public API must preserve raw source identity,
author extensions and recovery evidence without broadening transaction targets.
Process crashes and Streamlit interactions are covered by the owner tests.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from copy import deepcopy

import pytest

from novel_ai import settings_commit as commit
from novel_ai.storage import ProjectStore

PROJECT = "SettingsReviewBook"
BIBLE = "memory/story_bible.json"
OUTLINE = "memory/outline.json"
REQUEST_A = "a" * 32
REQUEST_B = "b" * 32
BASE_BIBLE = {
    "title": "Synthetic settings review",
    "genre": "Synthetic old genre",
    "locked_facts": ["Synthetic bridge is closed"],
    "author_extension": {"notes": ["Preserve this synthetic author note"], "enabled": True},
}
BASE_OUTLINE = {
    "outline": "Synthetic old outline",
    "author_outline_extension": {"versions": [1, 2], "reviewed": False},
}


def raw_snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file() and path.name != ".store.lock"
    }


def seed(store, *, present=(True, True)):
    root = store.project_dir(PROJECT)
    for relative, value, exists in zip(
        (BIBLE, OUTLINE), (BASE_BIBLE, BASE_OUTLINE), present, strict=True,
    ):
        if exists:
            # Noncanonical whitespace is part of the optimistic source identity.
            (root / relative).write_text(json.dumps(value, indent=3) + "\n\n", encoding="utf-8")
    return root


def prepared(store, *, genre="Synthetic new genre", outline="Synthetic new outline"):
    snapshot = commit.load_settings_bundle(store, PROJECT)
    files = commit.prepare_settings_save(snapshot, bible={"genre": genre}, outline=outline)
    return snapshot, files


def publish(store, snapshot, files, *, request_id=REQUEST_A):
    return commit.commit_settings_bundle(
        store, PROJECT, files=files, expected_before=snapshot["sha256"], request_id=request_id,
    )


def leave_pending(store, monkeypatch, *, target=OUTLINE):
    snapshot, files = prepared(store)
    root = store.project_dir(PROJECT)
    original_write = store._write

    def interrupt(path, content, **kwargs):
        if path.relative_to(root).as_posix() == target:
            raise OSError("synthetic interrupted settings publication")
        return original_write(path, content, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_write", interrupt)
        with pytest.raises(OSError, match="synthetic interrupted"):
            publish(store, snapshot, files)
    assert (root / commit.INTENT_PATH).is_file()
    return root, snapshot, files


def receipts(root):
    return sorted((root / "memory/settings_commits").glob("settings-*.json"))


def test_public_scope_is_exactly_the_two_settings_files():
    assert commit.SETTINGS_PATHS == (BIBLE, OUTLINE)
    assert commit.INTENT_PATH == ".settings-commit-transaction.json"
    assert issubclass(commit.SettingsCommitError, ValueError)


@pytest.mark.parametrize("present", list(itertools.product([False, True], repeat=2)))
def test_load_accepts_independently_missing_files_without_migration(tmp_path, present):
    store = ProjectStore(tmp_path)
    root = seed(store, present=present)
    before = raw_snapshot(root)
    loaded = commit.load_settings_bundle(store, PROJECT)
    assert loaded["bible"] == (BASE_BIBLE if present[0] else {})
    assert loaded["outline"] == (BASE_OUTLINE if present[1] else {})
    assert loaded["sha256"] == {
        path: hashlib.sha256(before[path]).hexdigest() if exists else None
        for path, exists in zip((BIBLE, OUTLINE), present, strict=True)
    }
    assert raw_snapshot(root) == before
    # Returned nested structures are detached from future loads.
    loaded["bible"]["author_extension"] = {"caller": ["mutation"]}
    assert commit.load_settings_bundle(store, PROJECT)["bible"] == (BASE_BIBLE if present[0] else {})


@pytest.mark.parametrize("present", list(itertools.product([False, True], repeat=2)))
def test_save_from_independently_missing_files_preserves_available_extensions(tmp_path, present):
    store = ProjectStore(tmp_path)
    root = seed(store, present=present)
    snapshot, files = prepared(store)
    original_snapshot = deepcopy(snapshot)
    result = publish(store, snapshot, files)
    assert snapshot == original_snapshot
    assert result["historical"] is False
    assert result["current"]["bible"]["genre"] == "Synthetic new genre"
    assert result["current"]["outline"]["outline"] == "Synthetic new outline"
    if present[0]:
        assert result["current"]["bible"]["author_extension"] == BASE_BIBLE["author_extension"]
        assert result["current"]["bible"]["locked_facts"] == BASE_BIBLE["locked_facts"]
    if present[1]:
        assert result["current"]["outline"]["author_outline_extension"] == BASE_OUTLINE["author_outline_extension"]
    assert all((root / path).read_bytes() == text.encode("utf-8") for path, text in files.items())
    assert len(receipts(root)) == 1
    assert json.loads(receipts(root)[0].read_bytes()) == result["receipt"]
    assert not (root / commit.INTENT_PATH).exists()


def test_preparing_save_preserves_extensions_and_detaches_all_caller_values(tmp_path):
    store = ProjectStore(tmp_path)
    root = seed(store)
    before_disk = raw_snapshot(root)
    snapshot = commit.load_settings_bundle(store, PROJECT)
    before_snapshot = deepcopy(snapshot)
    edit = {"genre": "Synthetic edited genre", "locked_facts": ["Synthetic bridge reopened"]}
    before_edit = deepcopy(edit)
    files = commit.prepare_settings_save(snapshot, bible=edit, outline="Synthetic 新总纲")
    assert snapshot == before_snapshot and edit == before_edit
    assert raw_snapshot(root) == before_disk
    assert set(files) == {BIBLE, OUTLINE}
    assert json.loads(files[BIBLE]) == {**BASE_BIBLE, **edit}
    assert json.loads(files[OUTLINE]) == {**BASE_OUTLINE, "outline": "Synthetic 新总纲"}
    edit["locked_facts"].append("Later unconfirmed caller mutation")
    snapshot["bible"]["author_extension"]["notes"].append("Later caller mutation")
    result = publish(store, before_snapshot, files)
    assert result["current"]["bible"] == {**BASE_BIBLE, **before_edit}


@pytest.mark.parametrize("target", [BIBLE, OUTLINE])
@pytest.mark.parametrize("change", ["known_field", "unknown_field", "whitespace_only"])
def test_raw_cas_rejects_any_changed_source_without_writes(tmp_path, target, change):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    path = root / target
    if change == "whitespace_only":
        path.write_bytes(path.read_bytes() + b" \n")
    else:
        value = json.loads(path.read_bytes())
        key = "genre" if target == BIBLE else "outline"
        value[key if change == "known_field" else "new_external_extension"] = "Independent synthetic change"
        path.write_text(json.dumps(value), encoding="utf-8")
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("target", [BIBLE, OUTLINE])
@pytest.mark.parametrize("initially_missing", [True, False], ids=["missing-to-empty-object", "empty-object-to-missing"])
def test_missing_and_saved_empty_object_are_distinct_cas_sources(tmp_path, target, initially_missing):
    store = ProjectStore(tmp_path)
    root = store.project_dir(PROJECT)
    path = root / target
    if not initially_missing:
        path.write_text("{}", encoding="utf-8")
    snapshot, files = prepared(store)
    assert (snapshot["sha256"][target] is None) is initially_missing
    if initially_missing:
        path.write_text("{}", encoding="utf-8")
    else:
        path.unlink()
    current = commit.load_settings_bundle(store, PROJECT)
    assert current["bible"] == snapshot["bible"] == {}
    assert current["outline"] == snapshot["outline"] == {}
    assert current["sha256"][target] != snapshot["sha256"][target]
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("target", [BIBLE, OUTLINE])
@pytest.mark.parametrize("raw", [b"", b"null", b"[]", b"42", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'])
def test_invalid_stored_roots_or_json_preserve_both_original_files(tmp_path, target, raw):
    store = ProjectStore(tmp_path)
    root = seed(store)
    (root / target).write_bytes(raw)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.load_settings_bundle(store, PROJECT)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("tamper", ["extra_target", "missing_target", "alias_target", "null_bible", "null_outline", "duplicate_key", "nonfinite_extension", "nonstring_outline", "bytes_image"])
def test_invalid_after_images_never_create_intent_or_touch_settings(tmp_path, tamper):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    if tamper == "extra_target":
        files["chapters/unrelated.md"] = "Synthetic unrelated file"
    elif tamper == "missing_target":
        files.pop(OUTLINE)
    elif tamper == "alias_target":
        files["memory/./outline.json"] = files.pop(OUTLINE)
    elif tamper == "null_bible":
        files[BIBLE] = "null"
    elif tamper == "null_outline":
        files[OUTLINE] = "null"
    elif tamper == "duplicate_key":
        files[OUTLINE] = '{"outline":"one","outline":"two"}'
    elif tamper == "nonfinite_extension":
        files[BIBLE] = '{"title":"Synthetic","extension":Infinity}'
    elif tamper == "nonstring_outline":
        files[OUTLINE] = '{"outline":["not flat text"]}'
    else:
        files[BIBLE] = files[BIBLE].encode("utf-8")
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("tamper", ["missing_source", "extra_source", "canonical_instead_of_raw", "invalid_digest"])
def test_expected_before_must_name_both_exact_raw_sources(tmp_path, tamper):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    if tamper == "missing_source":
        snapshot["sha256"].pop(OUTLINE)
    elif tamper == "extra_source":
        snapshot["sha256"]["memory/characters.json"] = None
    elif tamper == "canonical_instead_of_raw":
        snapshot["sha256"][OUTLINE] = hashlib.sha256(json.dumps(BASE_OUTLINE).encode()).hexdigest()
    else:
        snapshot["sha256"][OUTLINE] = "g" * 64
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("request_id", [None, "", "A" * 32, "a" * 31, "a" * 33, True])
def test_request_id_is_explicit_and_strict_without_any_settings_writes(tmp_path, request_id):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files, request_id=request_id)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("change", ["payload", "baseline"])
def test_completed_request_id_cannot_be_rebound_to_other_content_or_sources(tmp_path, change):
    store = ProjectStore(tmp_path)
    root = seed(store)
    original, files = prepared(store)
    publish(store, original, files)
    altered_snapshot, altered_files = deepcopy((original, files))
    if change == "payload":
        altered_files[OUTLINE] = json.dumps({"outline": "Different synthetic request payload"})
    else:
        altered_snapshot["sha256"] = commit.load_settings_bundle(store, PROJECT)["sha256"]
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, altered_snapshot, altered_files)
    assert raw_snapshot(root) == before
    assert len(receipts(root)) == 1


def test_historical_exact_retry_returns_current_pair_without_rewriting_newer_files(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    root = seed(store)
    first_snapshot, first_files = prepared(store)
    first = publish(store, first_snapshot, first_files)
    newer_snapshot, newer_files = prepared(store, genre="Newer synthetic genre", outline="Newer synthetic outline")
    newer = publish(store, newer_snapshot, newer_files, request_id=REQUEST_B)
    before = raw_snapshot(root)
    monkeypatch.setattr(store, "_write", lambda *args, **kwargs: pytest.fail("historical retry rewrote data"))
    result = publish(store, first_snapshot, first_files)
    assert result["historical"] is True
    assert result["receipt"] == first["receipt"]
    assert result["current"] == newer["current"]
    assert raw_snapshot(root) == before
    assert len(receipts(root)) == 2


def test_new_request_with_identical_after_images_gets_its_own_receipt(tmp_path):
    store = ProjectStore(tmp_path)
    root = seed(store)
    original, files = prepared(store)
    first = publish(store, original, files)
    current = commit.load_settings_bundle(store, PROJECT)
    second = publish(store, current, files, request_id=REQUEST_B)
    assert second["historical"] is False
    assert second["receipt"] != first["receipt"]
    assert second["current"] == first["current"]
    assert len(receipts(root)) == 2


def test_pending_request_collision_retains_frozen_intent_and_partial_pair(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    seed(store)
    root, snapshot, files = leave_pending(store, monkeypatch)
    changed = {**files, OUTLINE: json.dumps({"outline": "Synthetic changed draft"})}
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, changed)
    assert raw_snapshot(root) == before
    result = publish(store, snapshot, files)
    assert result["current"]["outline"] == json.loads(files[OUTLINE])


@pytest.mark.parametrize("target", [BIBLE, OUTLINE])
def test_independently_changed_target_blocks_recovery_and_preserves_all_evidence(tmp_path, monkeypatch, target):
    store = ProjectStore(tmp_path)
    seed(store)
    root, _, _ = leave_pending(store, monkeypatch)
    (root / target).write_text('{"external_extension":"Independent synthetic update"}', encoding="utf-8")
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.recover_settings_commit(store, PROJECT)
    assert raw_snapshot(root) == before
    assert not receipts(root)


def test_recovery_rechecks_next_target_before_overwriting_external_change(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    seed(store)
    root, _, files = leave_pending(store, monkeypatch, target=BIBLE)
    intent_before = (root / commit.INTENT_PATH).read_bytes()
    external = b'{"outline":"Independent change during recovery"}\n'
    original_write = store._write

    def mutate_next_target(path, content, **kwargs):
        if path.relative_to(root).as_posix() == OUTLINE:
            pytest.fail("recovery overwrote an independently changed second target")
        result = original_write(path, content, **kwargs)
        if path.relative_to(root).as_posix() == BIBLE:
            (root / OUTLINE).write_bytes(external)
        return result

    monkeypatch.setattr(store, "_write", mutate_next_target)
    with pytest.raises(ValueError):
        commit.recover_settings_commit(store, PROJECT)
    assert (root / BIBLE).read_bytes() == files[BIBLE].encode("utf-8")
    assert (root / OUTLINE).read_bytes() == external
    assert (root / commit.INTENT_PATH).read_bytes() == intent_before
    assert not receipts(root)


def test_recovery_rechecks_completed_pair_before_publishing_success_receipt(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    seed(store)
    root, _, files = leave_pending(store, monkeypatch)
    intent_before = (root / commit.INTENT_PATH).read_bytes()
    external = b'{"genre":"Independent change after last publication"}\n'
    original_write = store._write

    def mutate_published_target(path, content, **kwargs):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("memory/settings_commits/"):
            pytest.fail("recovery published success for a changed pair")
        result = original_write(path, content, **kwargs)
        if relative == OUTLINE:
            (root / BIBLE).write_bytes(external)
        return result

    monkeypatch.setattr(store, "_write", mutate_published_target)
    with pytest.raises(ValueError):
        commit.recover_settings_commit(store, PROJECT)
    assert (root / BIBLE).read_bytes() == external
    assert (root / OUTLINE).read_bytes() == files[OUTLINE].encode("utf-8")
    assert (root / commit.INTENT_PATH).read_bytes() == intent_before
    assert not receipts(root)


@pytest.mark.parametrize("tamper", [
    "duplicate_key", "extra_target", "missing_target", "relative_alias",
    "before_bytes", "after_bytes", "foreign_project", "foreign_root", "receipt_identity",
])
def test_tampered_intent_never_publishes_remaining_target_or_removes_evidence(tmp_path, monkeypatch, tamper):
    store = ProjectStore(tmp_path)
    seed(store)
    root, _, _ = leave_pending(store, monkeypatch)
    path = root / commit.INTENT_PATH
    original = path.read_bytes()
    value = json.loads(original)
    if tamper == "duplicate_key":
        raw = ("{\"schema\":" + json.dumps(value["schema"]) + "," + original.decode().lstrip()[1:]).encode()
    else:
        if tamper == "extra_target":
            value["files"]["memory/characters.json"] = "[]"
        elif tamper == "missing_target":
            value["files"].pop(OUTLINE)
        elif tamper == "relative_alias":
            value["files"]["memory/./outline.json"] = value["files"].pop(OUTLINE)
        elif tamper == "before_bytes":
            value["before"][OUTLINE] += " \n"
        elif tamper == "after_bytes":
            value["files"][OUTLINE] += " \n"
        elif tamper == "foreign_project":
            value["receipt"]["project"] = "OtherSyntheticBook"
        elif tamper == "foreign_root":
            value["receipt"]["root"] = str(tmp_path / "different-source")
        else:
            value["receipt"]["operation_id"] = "settings-" + "0" * 64
        raw = json.dumps(value).encode("utf-8")
    path.write_bytes(raw)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.recover_settings_commit(store, PROJECT)
    assert raw_snapshot(root) == before
    assert not receipts(root)


@pytest.mark.parametrize("tamper", ["duplicate_key", "changed_after", "foreign_root"])
def test_tampered_published_receipt_blocks_exact_retry_without_rewriting_history(tmp_path, tamper):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    publish(store, snapshot, files)
    path = receipts(root)[0]
    original = path.read_bytes()
    value = json.loads(original)
    if tamper == "duplicate_key":
        raw = ("{\"schema\":" + json.dumps(value["schema"]) + "," + original.decode().lstrip()[1:]).encode()
    else:
        if tamper == "changed_after":
            value["after"][OUTLINE] = "0" * 64
        else:
            value["root"] = str(tmp_path / "foreign-root")
        raw = json.dumps(value).encode("utf-8")
    path.write_bytes(raw)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before


@pytest.mark.parametrize("other_intent", [".style-commit-transaction.json", ".memory-commit-transaction.json", ".extraction-transaction.json"])
def test_coexisting_intents_preserve_both_records_without_arbitrary_recovery_order(tmp_path, monkeypatch, other_intent):
    store = ProjectStore(tmp_path)
    seed(store)
    root, snapshot, files = leave_pending(store, monkeypatch)
    (root / other_intent).write_text('{"synthetic":"other pending operation"}', encoding="utf-8")
    before = raw_snapshot(root)
    for action in (
        lambda: commit.recover_settings_commit(store, PROJECT),
        lambda: publish(store, snapshot, files),
        lambda: store.read_json(PROJECT, BIBLE),
    ):
        with pytest.raises(ValueError):
            action()
        assert raw_snapshot(root) == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_target_aliases_are_rejected_without_detaching_or_overwriting_them(tmp_path, kind):
    store = ProjectStore(tmp_path)
    root = seed(store)
    snapshot, files = prepared(store)
    (root / OUTLINE).unlink()
    if kind == "symlink":
        (root / OUTLINE).symlink_to(root / BIBLE)
    else:
        os.link(root / BIBLE, root / OUTLINE)
    before = raw_snapshot(root)
    for action in (
        lambda: commit.load_settings_bundle(store, PROJECT),
        lambda: publish(store, snapshot, files),
    ):
        with pytest.raises(ValueError):
            action()
        assert raw_snapshot(root) == before
    assert os.path.samefile(root / BIBLE, root / OUTLINE)


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
@pytest.mark.parametrize("evidence", ["intent", "receipt"])
def test_recovery_rejects_evidence_aliased_to_a_settings_target(tmp_path, monkeypatch, kind, evidence):
    store = ProjectStore(tmp_path)
    seed(store)
    root, _, _ = leave_pending(store, monkeypatch)
    intent = root / commit.INTENT_PATH
    value = json.loads(intent.read_bytes())
    path = intent if evidence == "intent" else root / "memory/settings_commits" / (value["receipt"]["operation_id"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    if kind == "symlink":
        path.symlink_to(root / BIBLE)
    else:
        os.link(root / BIBLE, path)
    before = raw_snapshot(root)
    with pytest.raises(ValueError):
        commit.recover_settings_commit(store, PROJECT)
    assert raw_snapshot(root) == before
    assert os.path.samefile(path, root / BIBLE)


def test_receipt_directory_alias_cannot_redirect_publication_to_another_directory(tmp_path):
    store = ProjectStore(tmp_path / "store")
    root = seed(store)
    snapshot, files = prepared(store)
    outside = tmp_path / "other-receipts"
    outside.mkdir()
    (outside / "keep.json").write_bytes(b'{"synthetic":"unrelated evidence"}')
    (root / "memory/settings_commits").symlink_to(outside, target_is_directory=True)
    before, outside_before = raw_snapshot(root), raw_snapshot(outside)
    with pytest.raises(ValueError):
        publish(store, snapshot, files)
    assert raw_snapshot(root) == before
    assert raw_snapshot(outside) == outside_before


def test_internal_settings_intent_cannot_be_written_through_content_api(tmp_path):
    store = ProjectStore(tmp_path)
    root = seed(store)
    before = raw_snapshot(root)
    for relative in (commit.INTENT_PATH, commit.INTENT_PATH.upper()):
        with pytest.raises(ValueError):
            store.write_json(PROJECT, relative, {"synthetic": "untrusted content"})
        assert raw_snapshot(root) == before
