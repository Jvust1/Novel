"""Fault injection and memory-source interaction through fixed settings saves."""
from copy import deepcopy
from pathlib import Path

import pytest
from test_memory_proposals import TEXT
from test_memory_proposals import fixture as memory_fixture
from test_settings_commit_review import PROJECT, prepared, publish, raw_snapshot, seed

from novel_ai import settings_commit as commit
from novel_ai.memory_proposals import (
    apply_memory_proposal,
    assert_memory_source_current,
    capture_memory_source,
    make_memory_proposal,
    save_memory_proposal,
)
from novel_ai.models import ChapterPlan
from novel_ai.storage import ProjectStore


def assert_complete(store, snapshot, files):
    result = publish(store, snapshot, files)
    assert result["current"]["sha256"] == result["receipt"]["after"]
    assert not result["historical"]
    for path, content in files.items():
        assert (store.project_dir(PROJECT) / path).read_text() == content
    assert not (store.project_dir(PROJECT) / commit.INTENT_PATH).exists()
    return result


@pytest.mark.parametrize("target", ["intent", "bible", "outline", "receipt"])
@pytest.mark.parametrize("when", ["before", "after"])
def test_fault_at_each_atomic_publication_retries_the_same_complete_operation(tmp_path, monkeypatch, target, when):
    store = ProjectStore(tmp_path / "data")
    seed(store)
    snapshot, files = prepared(store)
    original = store._write

    def selected(path):
        return (path.name == commit.INTENT_PATH if target == "intent" else
                path.name == "story_bible.json" if target == "bible" else
                path.name == "outline.json" if target == "outline" else
                path.parent.name == "settings_commits")

    def interrupt(path, content, **kwargs):
        if selected(path) and when == "before":
            raise OSError("synthetic publication failure")
        original(path, content, **kwargs)
        if selected(path) and when == "after":
            raise OSError("synthetic publication failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write", interrupt)
        with pytest.raises(OSError, match="synthetic publication"):
            publish(store, snapshot, files)
    result = assert_complete(store, snapshot, files)
    before = raw_snapshot(store.root)
    assert publish(store, snapshot, files) == result
    assert raw_snapshot(store.root) == before


@pytest.mark.parametrize("sync_number", range(1, 8))
def test_directory_sync_failure_never_loses_exact_retry_or_replays_new_delta(tmp_path, monkeypatch, sync_number):
    store = ProjectStore(tmp_path / "data")
    seed(store)
    snapshot, files = prepared(store)
    original = commit.sync_directory
    calls = []

    def interrupt(path):
        calls.append(path)
        if len(calls) == sync_number:
            raise OSError("synthetic directory sync failure")
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(commit, "sync_directory", interrupt)
        with pytest.raises(OSError, match="synthetic directory"):
            publish(store, snapshot, files)
    assert len(calls) == sync_number
    assert_complete(store, snapshot, files)


@pytest.mark.parametrize("target", ["intent", "bible", "outline", "receipt"])
@pytest.mark.parametrize("fault", ["missing-readback", "changed-readback"])
def test_wrong_readback_never_reports_success_and_actual_bytes_can_recover(tmp_path, monkeypatch, target, fault):
    store = ProjectStore(tmp_path / "data")
    seed(store)
    snapshot, files = prepared(store)
    original_write, original_read = store._write, commit._read
    published = []

    def selected(path):
        return (path.name == commit.INTENT_PATH if target == "intent" else
                path.name == "story_bible.json" if target == "bible" else
                path.name == "outline.json" if target == "outline" else
                path.parent.name == "settings_commits")

    def write(path, content, **kwargs):
        original_write(path, content, **kwargs)
        if selected(path):
            published.append(path)

    def read(path):
        raw = original_read(path)
        if published and selected(path):
            return None if fault == "missing-readback" else b'{"synthetic_wrong_readback":true}'
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write", write)
        patch.setattr(commit, "_read", read)
        with pytest.raises(ValueError):
            publish(store, snapshot, files)
    assert published
    assert_complete(store, snapshot, files)


def test_intent_cleanup_failure_preserves_receipt_and_does_not_repeat_data_writes(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "data")
    seed(store)
    snapshot, files = prepared(store)
    original = Path.unlink

    def interrupt(path, *args, **kwargs):
        if path.name == commit.INTENT_PATH:
            raise OSError("synthetic cleanup failure")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupt)
        with pytest.raises(OSError, match="synthetic cleanup"):
            publish(store, snapshot, files)
    before = {path: (store.project_dir(PROJECT) / path).read_bytes() for path in commit.SETTINGS_PATHS}
    writes = []
    original_write = store._write

    def record(path, content, **kwargs):
        writes.append(path)
        return original_write(path, content, **kwargs)

    monkeypatch.setattr(store, "_write", record)
    assert_complete(store, snapshot, files)
    assert writes == []
    assert before == {path: (store.project_dir(PROJECT) / path).read_bytes() for path in commit.SETTINGS_PATHS}


@pytest.mark.parametrize("entry", ["capture", "assert-current"])
def test_pending_settings_block_raw_memory_source_reads_without_implicit_recovery(tmp_path, monkeypatch, entry):
    store, context, source, _ = memory_fixture(tmp_path)
    snapshot = commit.load_settings_bundle(store, "Book")
    files = commit.prepare_settings_save(snapshot, snapshot["bible"], "新的原创建议总纲")
    original = store._write

    def interrupt(path, content, **kwargs):
        if path.name in {"story_bible.json", "outline.json"}:
            raise OSError("synthetic settings intent only")
        return original(path, content, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write", interrupt)
        with pytest.raises(OSError):
            commit.commit_settings_bundle(store, "Book", files=files,
                expected_before=snapshot["sha256"], request_id="d" * 32)
    before = raw_snapshot(store.root)
    with pytest.raises(ValueError, match="pending"):
        if entry == "capture":
            capture_memory_source(store, "Book", "c1", final_text=TEXT,
                plan=ChapterPlan.model_validate(source.to_dict()["plan"]), context=context)
        else:
            assert_memory_source_current(store, source, context=context)
    assert raw_snapshot(store.root) == before


def test_completed_outline_only_save_invalidates_old_memory_confirmation(tmp_path):
    store, context, source, extraction = memory_fixture(tmp_path)
    proposal = make_memory_proposal(source, extraction)
    save_memory_proposal(store, proposal, context=context)
    snapshot = commit.load_settings_bundle(store, "Book")
    files = commit.prepare_settings_save(snapshot, snapshot["bible"], "另一个明确保存的总纲")
    commit.commit_settings_bundle(store, "Book", files=files,
        expected_before=snapshot["sha256"], request_id="e" * 32)
    before = raw_snapshot(store.root)
    with pytest.raises(ValueError):
        apply_memory_proposal(store, proposal, context=deepcopy(context), chapter_accepted=True,
            memory_accepted=True, confirmation_source="synthetic-only://prior-exact-confirmation")
    assert raw_snapshot(store.root) == before
    assert not (store.project_dir("Book") / "memory/memory_commits").exists()

