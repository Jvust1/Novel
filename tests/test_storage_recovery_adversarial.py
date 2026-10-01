"""Independent synthetic-file probes for the bounded local storage contract."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from novel_ai import eval as evaluation
from novel_ai import storage_guard
from novel_ai.storage import ProjectStore, StorageIntegrityError


@pytest.mark.parametrize("folder,loader", [
    ("voice_dna", "load_voice_dna_history"),
    ("story_dna", "load_story_dna_history"),
    ("chapter_analytics", "load_chapter_analytics_history"),
])
def test_history_rejects_link_before_enumerating_directory(tmp_path, monkeypatch, folder, loader):
    store = ProjectStore(tmp_path / "data")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = store.project_dir("P") / "memory" / folder
    linked.symlink_to(outside, target_is_directory=True)
    enumerated = []
    original = Path.glob

    def observe(path, pattern):
        enumerated.append(path)
        return original(path, pattern)

    monkeypatch.setattr(Path, "glob", observe)
    with pytest.raises(ValueError):
        getattr(store, loader)("P")
    assert linked not in enumerated
    assert not list(outside.iterdir())


@pytest.mark.skipif(os.name != "posix", reason="Native POSIX reentry probe")
def test_native_lock_reentry_normalizes_dotdot_alias(tmp_path, monkeypatch):
    import fcntl

    (tmp_path / "alias").mkdir()
    native = fcntl.flock
    acquisitions = []

    def bounded_flock(descriptor, operation):
        if operation == fcntl.LOCK_EX:
            acquisitions.append(descriptor)
            # Fail rather than hang when a second open-description lock is tried.
            assert len(acquisitions) == 1, "same-inode alias bypassed reentry registry"
        return native(descriptor, operation)

    monkeypatch.setattr(fcntl, "flock", bounded_flock)
    with storage_guard.project_lock(tmp_path / ".lock"):
        with storage_guard.project_lock(tmp_path / "alias" / ".." / ".lock"):
            pass
    assert len(acquisitions) == 1


def _pending_before_publication(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    store.save_extraction("P", {"chapter_id": "c", "summary": "old"})
    store.save_extraction("P", {"chapter_id": "neighbor", "summary": "keep"})
    root = store.project_dir("P")
    targets = [root / "memory/extractions/c.json", root / "memory/chapter_summaries.jsonl"]
    before = [path.read_bytes() for path in targets]
    original = store._write

    def fail_before_first_target(path, content, **kwargs):
        if path == targets[0]:
            raise OSError("synthetic interruption before either target")
        return original(path, content, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write", fail_before_first_target)
        with pytest.raises(OSError):
            store.save_extraction("P", {"chapter_id": "c", "summary": "new"})
    return root, targets, before


def _set_content(item, content):
    item["content"] = content
    item["after_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("corruption", [
    "three_targets", "reversed_targets", "different_project", "bool_version",
    "null_document", "non_object_record", "non_string_content", "digest_container",
    "invalid_extraction_json", "invalid_summary_json", "summary_not_object",
    "missing_summary", "duplicate_summary", "summary_disagrees", "chapter_path_disagrees",
])
def test_corrupt_intent_never_publishes_either_target(tmp_path, monkeypatch, corruption):
    root, targets, before = _pending_before_publication(tmp_path, monkeypatch)
    intent = root / ".extraction-transaction.json"
    data = json.loads(intent.read_text(encoding="utf-8"))
    if corruption == "three_targets":
        data["files"].append(dict(data["files"][0]))
    elif corruption == "reversed_targets":
        data["files"].reverse()
    elif corruption == "different_project":
        data["project"] = "Q"
    elif corruption == "bool_version":
        data["version"] = True
    elif corruption == "null_document":
        data = None
    elif corruption == "non_object_record":
        data["files"][0] = 12
    elif corruption == "non_string_content":
        data["files"][0]["content"] = {}
    elif corruption == "digest_container":
        data["files"][0]["before_sha256"] = []
    elif corruption == "invalid_extraction_json":
        _set_content(data["files"][0], "{")
    elif corruption == "invalid_summary_json":
        _set_content(data["files"][1], "{\n")
    elif corruption == "summary_not_object":
        _set_content(data["files"][1], "[]\n")
    elif corruption == "missing_summary":
        _set_content(data["files"][1], "")
    elif corruption == "duplicate_summary":
        _set_content(data["files"][1], data["files"][1]["content"] * 2)
    elif corruption == "summary_disagrees":
        rows = [json.loads(line) for line in data["files"][1]["content"].splitlines()]
        rows[0]["summary"] = "unrelated"
        _set_content(data["files"][1], "".join(json.dumps(row) + "\n" for row in rows))
    elif corruption == "chapter_path_disagrees":
        data["files"][0]["path"] = "memory/extractions/different.json"
        data["files"][0]["before_sha256"] = None
    intent.write_text(json.dumps(data), encoding="utf-8")
    corrupted = intent.read_bytes()

    with pytest.raises(StorageIntegrityError):
        ProjectStore(tmp_path).all_chapter_summaries("P")
    assert [path.read_bytes() for path in targets] == before
    assert intent.read_bytes() == corrupted
    assert not (root / "memory/extractions/different.json").exists()


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize("target_index", [0, 1])
def test_digest_consistent_nonfinite_recovery_content_is_rejected(tmp_path, monkeypatch, token, target_index):
    root, targets, before = _pending_before_publication(tmp_path, monkeypatch)
    intent = root / ".extraction-transaction.json"
    data = json.loads(intent.read_text(encoding="utf-8"))
    item = data["files"][target_index]
    if target_index == 0:
        content = item["content"].rstrip()[:-1] + ', "numeric_value": ' + token + "}"
    else:
        # Use an otherwise unrelated row, preserving the matching c summary.
        lines = item["content"].splitlines()
        lines[-1] = lines[-1].rstrip()[:-1] + ', "numeric_value": ' + token + "}"
        content = "\n".join(lines) + "\n"
    _set_content(item, content)
    intent.write_text(json.dumps(data), encoding="utf-8")
    corrupted = intent.read_bytes()

    with pytest.raises(StorageIntegrityError):
        ProjectStore(tmp_path).all_chapter_summaries("P")
    assert [path.read_bytes() for path in targets] == before
    assert intent.read_bytes() == corrupted


@pytest.mark.parametrize("conflicted_index", [0, 1])
def test_conflict_on_either_target_preserves_other_pending_old_target(tmp_path, monkeypatch, conflicted_index):
    root, targets, before = _pending_before_publication(tmp_path, monkeypatch)
    targets[conflicted_index].write_bytes(b"synthetic independent edit")
    before[conflicted_index] = b"synthetic independent edit"
    with pytest.raises(StorageIntegrityError):
        ProjectStore(tmp_path).read_json("P", "memory/unrelated.json")
    assert [path.read_bytes() for path in targets] == before
    assert (root / ".extraction-transaction.json").is_file()


def test_recovery_after_intent_unlink_failure_is_idempotent(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    store.save_extraction("P", {"chapter_id": "c", "summary": "old"})
    original = Path.unlink

    def fail_intent_unlink(path, *args, **kwargs):
        if path.name == ".extraction-transaction.json":
            raise OSError("synthetic interruption after both targets")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_intent_unlink)
        with pytest.raises(OSError):
            store.save_extraction("P", {"chapter_id": "c", "summary": "new"})
    root = store.project_dir("P")
    paths = [root / "memory/extractions/c.json", root / "memory/chapter_summaries.jsonl"]
    published = [path.read_bytes() for path in paths]
    fresh = ProjectStore(tmp_path)
    assert fresh.all_chapter_summaries("P")[0]["summary"] == "new"
    assert [path.read_bytes() for path in paths] == published
    assert not (root / ".extraction-transaction.json").exists()


@pytest.mark.parametrize("checkpoint", [".extraction-transaction.json", "c.json", "chapter_summaries.jsonl"])
def test_fresh_process_recovers_actual_process_exit_at_each_publication(tmp_path, checkpoint):
    script = '''
import os
import sys
from novel_ai.storage import ProjectStore
store = ProjectStore(sys.argv[1])
store.save_extraction("P", {"chapter_id": "c", "summary": "old"})
original = store._write
def exit_after_publication(path, content, **kwargs):
    original(path, content, **kwargs)
    if path.name == sys.argv[2]:
        os._exit(23)
store._write = exit_after_publication
store.save_extraction("P", {"chapter_id": "c", "summary": "new"})
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), checkpoint],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 23, result.stderr
    store = ProjectStore(tmp_path)
    root = store.project_dir("P")
    assert (root / ".extraction-transaction.json").is_file()
    assert store.read_json("P", "memory/extractions/c.json")["summary"] == "new"
    assert store.all_chapter_summaries("P") == [
        {"chapter_id": "c", "chapter_title": "", "summary": "new"}
    ]
    assert not (root / ".extraction-transaction.json").exists()


def test_encoding_failure_preserves_previous_chapter_and_cleans_part(tmp_path):
    store = ProjectStore(tmp_path)
    chapter = store.write_chapter("P", "c", "old draft")
    before = chapter.read_bytes()
    with pytest.raises(UnicodeEncodeError):
        store.write_chapter("P", "c", "\ud800")
    assert chapter.read_bytes() == before
    assert not list(chapter.parent.glob(".novel-*.tmp"))


def test_score_file_created_during_publication_is_not_clobbered(tmp_path, monkeypatch):
    score = tmp_path / "scoring_sheet.csv"
    original = os.link

    def competing_publication(source, destination, *args, **kwargs):
        if Path(destination) == score:
            score.write_bytes(b"human scores arrived concurrently")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", competing_publication)
    with pytest.raises(FileExistsError):
        evaluation.make_scoring_sheet({"run_id": "synthetic", "cases": []}, score)
    assert score.read_bytes() == b"human scores arrived concurrently"
    assert not list(tmp_path.glob(".novel-*.tmp"))
