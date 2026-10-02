"""Independent synthetic review of accepted-only export and save boundaries."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from novel_ai import accepted_export as export
from novel_ai import author_workflow as workflow
from novel_ai import gpt_story_journal as journal
from novel_ai import gpt_story_state as state
from novel_ai.accepted_writing import restore_journal_source
from novel_ai.market_eval import MARKET_RUBRIC, MarketChapter, MarketCorpus, MarketScore
from novel_ai.release_pack import MarketProfile, build_release_pack
from novel_ai.storage import ProjectStore
import test_accepted_export as fixtures
from test_accepted_export import build, profile, source_archive, unpack
from test_accepted_archive_writing import digest
from test_gpt_story_journal import accept_proposal, propose, reconcile


@pytest.mark.parametrize("component", ["root", "root_parent"])
def test_export_rechecks_store_root_ancestry_after_construction(tmp_path, component):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    parent = tmp_path / "container"
    store = ProjectStore(parent / "out")
    external = tmp_path / "other-destination"
    external.mkdir()
    replaced = store.root if component == "root" else parent
    replaced.rename(tmp_path / "original-directory")
    replaced.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert list(external.iterdir()) == []


@pytest.mark.parametrize("component", ["project", "exports", "target", "source"])
def test_persistent_symlink_is_not_followed(tmp_path, component):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    raw = bundle.bundle_bytes
    store = ProjectStore(tmp_path / "out")
    project = store.project_dir(source.story_id)
    target = project / "exports" / ("release-" + hashlib.sha256(raw).hexdigest() + ".zip")
    external = tmp_path / "external"
    external.mkdir()
    if component == "source":
        path = Path(source.path)
        copied = external / "source.json"
        path.rename(copied)
        path.symlink_to(copied)
    elif component == "target":
        copied = external / "artifact.zip"
        copied.write_bytes(raw)
        target.symlink_to(copied)
    else:
        path = project if component == "project" else project / "exports"
        path.rename(external / "original")
        path.symlink_to(external / "original", target_is_directory=True)
    before = {str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert before == {str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()}


@pytest.mark.parametrize("story_id", ["padded ", "two words", "book/child", "con"])
def test_story_name_alias_cannot_choose_a_different_storage_project(tmp_path, story_id):
    source, _ = source_archive(tmp_path, story_id=story_id)
    bundle = build(source)
    store = ProjectStore(tmp_path / "out")
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, story_id, bundle)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, store.slugify(story_id), bundle)
    assert not (store.root / "projects").exists()


@pytest.mark.parametrize("kind", ["v1", "journal"])
def test_ready_next_exports_without_a_new_plan_or_state_transition(tmp_path, kind, monkeypatch):
    source, texts = source_archive(tmp_path, kind=kind, pending=False)
    before = Path(source.path).read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError("export must not change an author decision or invoke recovery")
    monkeypatch.setattr(state, "transition", forbidden)
    monkeypatch.setattr(journal, "transition_journal", forbidden)
    monkeypatch.setattr(ProjectStore, "_guard", forbidden)
    bundle = build(source)
    assert len(source.state.accepted_chapters) == 3
    if kind == "journal":
        assert "journal_owner" in source.state.model_dump()
    store = ProjectStore(tmp_path / "out")
    root = store.project_dir(source.story_id)
    for name in (".memory-commit-transaction.json", ".extraction-transaction.json"):
        (root / name).write_bytes(b"synthetic pending intent remains untouched")
    (root / "memory" / "characters.json").write_bytes(b"synthetic canonical evidence")
    evidence = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    saved = export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert unpack(saved.read_bytes())["chapters/003.md"] == texts["ch-3"]
    assert Path(source.path).read_bytes() == before
    assert all(p.read_bytes() == raw for p, raw in evidence.items())


def test_same_text_same_revision_distinct_confirmation_evidence_is_bound(tmp_path, monkeypatch):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    a, _ = source_archive(left, same_text=True)
    monkeypatch.setattr(fixtures, "CHAT", "another synthetic author message reference")
    b, _ = source_archive(right, same_text=True)
    first, second = unpack(build(a)), unpack(build(b))
    x, y = (json.loads(files["accepted_source.json"]) for files in (first, second))
    assert json.loads(first["manifest.json"])["corpus_sha256"] == json.loads(second["manifest.json"])["corpus_sha256"]
    for row_a, row_b in zip(x["chapters"], y["chapters"]):
        assert row_a["text_sha256"] == row_b["text_sha256"]
        assert row_a["draft_revision"] == row_b["draft_revision"]
        assert row_a["draft_source_fingerprint"] == row_b["draft_source_fingerprint"]
        assert row_a["acceptance_records_sha256"] != row_b["acceptance_records_sha256"]
    assert fixtures.CHAT.encode() not in b"".join(second.values())


@pytest.mark.parametrize("method", ["constructor", "replace", "report", "subclass"])
def test_unobserved_or_non_native_bundle_is_not_a_save_capability(tmp_path, method):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    if method == "constructor":
        changed = export.AcceptedReviewBundle(bundle._source, bundle._spec_json, bundle._bundle_bytes)
    elif method == "replace":
        changed = replace(bundle)
    elif method == "report":
        changed = bundle.report()
    else:
        class ForeignBundle(export.AcceptedReviewBundle):
            pass
        changed = ForeignBundle(bundle._source, bundle._spec_json, bundle._bundle_bytes)
    store = ProjectStore(tmp_path / "out")
    with pytest.raises((ValueError, TypeError)):
        export.save_accepted_review_bundle(store, source.story_id, changed)
    assert not (store.root / "projects").exists()


@pytest.mark.parametrize("field", ["_source", "_spec_json", "_bundle_bytes", "_observed_digest"])
def test_mutated_handle_cannot_reuse_existing_historical_artifact(tmp_path, field):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    store = ProjectStore(tmp_path / "out")
    path = export.save_accepted_review_bundle(store, source.story_id, bundle)
    before = path.read_bytes()
    changed = {"_source": replace(source, state_sha256="0" * 64),
               "_spec_json": bundle._spec_json + b" ", "_bundle_bytes": before + b" ",
               "_observed_digest": "0" * 64}[field]
    object.__setattr__(bundle, field, changed)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert path.read_bytes() == before


def test_rebound_observation_digest_does_not_skip_rebuilding_actual_source(tmp_path):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    object.__setattr__(bundle, "_bundle_bytes", bundle._bundle_bytes + b"forged suffix")
    object.__setattr__(bundle, "_observed_digest", bundle._identity())
    with pytest.raises(ValueError, match="actual accepted source"):
        bundle.report()


def test_metadata_preview_and_report_are_detached_from_live_bundle(tmp_path):
    source, _ = source_archive(tmp_path)
    chosen_profile = profile()
    tags = ["original tag"]
    bundle = build(source, profile=chosen_profile, tags=tags)
    before = bundle.bundle_bytes
    chosen_profile.genre = "changed genre"
    tags.append("later tag")
    view = export.preview_accepted_corpus(source, chapter_ids=["ch-1", "ch-2", "ch-3"],
                                          stage="opening_3", profile=profile())
    view.chapters[0].text = "unaccepted replacement"
    report = bundle.report()
    report["source"]["chapters"][0]["text_sha256"] = "f" * 64
    report["publishability_verdict"] = "approved"
    assert bundle.bundle_bytes == before
    assert bundle.report()["publishability_verdict"] is None


@pytest.mark.parametrize("phase", ["build_release_pack", "release_bundle_bytes", "_add_authority"])
def test_source_change_at_each_packaging_stage_refuses_a_bundle(tmp_path, monkeypatch, phase):
    source, _ = source_archive(tmp_path)
    owner = workflow if phase == "release_bundle_bytes" else export
    original = getattr(owner, phase)
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        Path(source.path).write_bytes(Path(source.path).read_bytes() + b" ")
        return result
    monkeypatch.setattr(owner, phase, change)
    with pytest.raises(ValueError):
        build(source)


@pytest.mark.parametrize("when", ["fsync", "new_readback", "existing_readback", "racing_link"])
def test_source_change_across_save_paths_never_returns_success(tmp_path, monkeypatch, when):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    raw = bundle.bundle_bytes
    store = ProjectStore(tmp_path / "out")
    if when == "existing_readback":
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    def change_source():
        Path(source.path).write_bytes(Path(source.path).read_bytes() + b" ")
    if when == "fsync":
        original = workflow.os.fsync
        def fsync(fd):
            original(fd)
            change_source()
        monkeypatch.setattr(workflow.os, "fsync", fsync)
    elif when == "racing_link":
        def race(src, dst):
            Path(dst).write_bytes(Path(src).read_bytes())
            change_source()
            raise FileExistsError("synthetic identical winner with changed source")
        monkeypatch.setattr(workflow.os, "link", race)
    else:
        original = workflow._read_bytes
        def read(path):
            result = original(path)
            if path.name.startswith("release-"):
                change_source()
            return result
        monkeypatch.setattr(workflow, "_read_bytes", read)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    artifacts = list(store.root.rglob("release-*.zip"))
    assert len(artifacts) == (0 if when == "fsync" else 1)
    assert all(p.read_bytes() == raw for p in artifacts)
    assert not list(store.root.rglob(".release-*"))


@pytest.mark.parametrize("phase", ["proposal", "accepted", "reconciled"])
def test_owned_journal_change_invalidates_old_export_and_preserves_review_gates(tmp_path, phase):
    source, _ = source_archive(tmp_path, kind="journal", pending=False)
    bundle = build(source)
    changed = propose(source.journal)
    if phase != "proposal":
        changed = accept_proposal(changed)
    if phase == "reconciled":
        changed = reconcile(changed)
    journal.save_journal(source.path, changed, expected_disk_sha256=source.file_sha256)
    with pytest.raises(ValueError):
        bundle.report()
    options = dict(expected_story_id=source.story_id, expected_revision=source.revision,
                   expected_context_revision=journal.project_journal(changed).context_revision,
                   expected_journal_sha256=journal.journal_fingerprint(changed),
                   expected_file_sha256=digest(Path(source.path)))
    if phase != "reconciled":
        with pytest.raises(ValueError):
            restore_journal_source(source.path, **options)
    else:
        fresh = restore_journal_source(source.path, **options)
        proof = build(fresh).report()["source"]
        assert proof["context_revision"] == 1
        assert "journal_owner" in fresh.state.model_dump()
        assert journal.project_journal(fresh.journal).requires_checkpoint


@pytest.mark.parametrize("when", ["before_link", "after_readback"])
def test_mid_save_root_redirection_is_rejected_without_deleting_foreign_files(tmp_path, monkeypatch, when):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    raw = bundle.bundle_bytes
    store = ProjectStore(tmp_path / "out")
    backup = tmp_path / "original-output"
    external = tmp_path / "foreign-output"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_bytes(b"foreign evidence must remain")
    def redirect():
        store.root.rename(backup)
        store.root.symlink_to(external, target_is_directory=True)
    if when == "before_link":
        original = workflow.tempfile.NamedTemporaryFile
        @contextmanager
        def staged_file(*args, **kwargs):
            with original(*args, **kwargs) as handle:
                yield handle
            assert handle.closed
            redirect()
        monkeypatch.setattr(workflow.tempfile, "NamedTemporaryFile", staged_file)
    else:
        original = workflow._read_bytes
        def read(path):
            result = original(path)
            if path.name.startswith("release-"):
                redirect()
            return result
        monkeypatch.setattr(workflow, "_read_bytes", read)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert list(external.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"foreign evidence must remain"
    artifacts = list(backup.rglob("release-*.zip"))
    assert len(artifacts) == (0 if when == "before_link" else 1)
    assert all(path.read_bytes() == raw for path in artifacts)


@pytest.mark.parametrize("failure", ["fsync", "link", "readback", "cleanup"])
def test_io_failures_report_failure_and_retry_complete_bytes(tmp_path, monkeypatch, failure):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    raw = bundle.bundle_bytes
    store = ProjectStore(tmp_path / "out")
    def fail(*args, **kwargs):
        raise OSError("synthetic " + failure + " failure")
    with monkeypatch.context() as patch:
        if failure == "fsync":
            patch.setattr(workflow.os, "fsync", fail)
        elif failure == "link":
            patch.setattr(workflow.os, "link", fail)
        elif failure == "readback":
            original = workflow._read_bytes
            def read(path):
                if path.name.startswith("release-"):
                    fail()
                return original(path)
            patch.setattr(workflow, "_read_bytes", read)
        else:
            original = Path.unlink
            def unlink(path, *args, **kwargs):
                if path.name.startswith(".release-"):
                    fail()
                return original(path, *args, **kwargs)
            patch.setattr(Path, "unlink", unlink)
        with pytest.raises(OSError):
            export.save_accepted_review_bundle(store, source.story_id, bundle)
    artifacts = list(store.root.rglob("release-*.zip"))
    assert len(artifacts) == (0 if failure in {"fsync", "link"} else 1)
    assert all(path.read_bytes() == raw for path in artifacts)
    saved = export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert saved.read_bytes() == raw
    assert len(list(store.root.rglob("release-*.zip"))) == 1


def test_replaced_temporary_file_is_neither_published_nor_deleted(tmp_path, monkeypatch):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    store = ProjectStore(tmp_path / "out")
    original = workflow.tempfile.NamedTemporaryFile
    replacements = []
    @contextmanager
    def replace_temporary(*args, **kwargs):
        with original(*args, **kwargs) as handle:
            yield handle
        assert handle.closed
        temporary = Path(handle.name)
        temporary.rename(tmp_path / "original-staged-bytes")
        temporary.write_bytes(b"foreign replacement must not be deleted or published")
        replacements.append(temporary)
    monkeypatch.setattr(workflow.tempfile, "NamedTemporaryFile", replace_temporary)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert len(replacements) == 1
    assert replacements[0].read_bytes() == b"foreign replacement must not be deleted or published"
    assert not list(store.root.rglob("release-*.zip"))


def test_changed_bytes_on_owned_staging_inode_cannot_be_published(tmp_path, monkeypatch):
    source, _ = source_archive(tmp_path)
    bundle = build(source)
    store = ProjectStore(tmp_path / "out")
    original = workflow.os.fsync
    def corrupt_temporary(fd):
        original(fd)
        temporary, = store.root.rglob(".release-*")
        inode = temporary.stat().st_ino
        temporary.write_bytes(b"changed bytes on the original inode")
        assert temporary.stat().st_ino == inode
    monkeypatch.setattr(workflow.os, "fsync", corrupt_temporary)
    with pytest.raises(ValueError):
        export.save_accepted_review_bundle(store, source.story_id, bundle)
    assert not list(store.root.rglob("release-*.zip"))


@pytest.mark.parametrize("corruption", ["duplicate", "extra", "missing", "text", "path", "approval"])
def test_packager_membership_and_text_corruption_cannot_gain_acceptance_proof(tmp_path, monkeypatch, corruption):
    source, _ = source_archive(tmp_path)
    original = workflow.release_bundle_bytes
    def corrupt(*args, **kwargs):
        raw = original(*args, **kwargs)
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as old, zipfile.ZipFile(output, "w") as new:
            for entry in old.infolist():
                if corruption == "missing" and entry.filename == "chapters/001.md":
                    continue
                data = old.read(entry.filename)
                if corruption == "text" and entry.filename == "chapters/001.md":
                    data = b"unaccepted replacement"
                if entry.filename == "manifest.json" and corruption in {"path", "approval"}:
                    manifest = json.loads(data)
                    if corruption == "path":
                        manifest["chapters"][0]["path"] = "../private-plan.txt"
                    else:
                        manifest["publishability_verdict"] = "approved"
                    data = json.dumps(manifest).encode()
                new.writestr(entry, data)
            if corruption == "duplicate":
                with pytest.warns(UserWarning, match="Duplicate"):
                    new.writestr("chapters/001.md", b"duplicate")
            elif corruption == "extra":
                new.writestr("private-canon.json", b"synthetic private secret")
        return output.getvalue()
    monkeypatch.setattr(workflow, "release_bundle_bytes", corrupt)
    with pytest.raises(ValueError):
        build(source)


def test_scores_bind_preview_corpus_and_do_not_become_publication_approval(tmp_path):
    source, _ = source_archive(tmp_path)
    args = dict(chapter_ids=["ch-1", "ch-2", "ch-3"], stage="opening_3", profile=profile())
    corpus = export.preview_accepted_corpus(source, **args)
    scores = [MarketScore(project=corpus.project, stage=corpus.stage,
        corpus_sha256=corpus.fingerprint(), reviewer_id="synthetic-reader",
        dimension=dimension, score=4, note="synthetic review") for dimension, _, _ in MARKET_RUBRIC]
    bundle = build(source, scores=scores)
    before = bundle.bundle_bytes
    scores[0].note = "later mutable review note"
    assert bundle.bundle_bytes == before
    assert bundle.report()["human_review_status"] == "human_review_recorded"
    assert bundle.report()["publishability_verdict"] is None
    corpus.chapters[0].text = "unaccepted draft to misbind scores"
    for row in scores:
        row.corpus_sha256 = corpus.fingerprint()
    with pytest.raises(ValueError):
        build(source, scores=scores)


@pytest.mark.parametrize("field", ["story_id", "revision", "file_sha256", "state_sha256",
                                  "context_revision", "journal_sha256"])
def test_forged_journal_source_identity_cannot_build_export(tmp_path, field):
    source, _ = source_archive(tmp_path, kind="journal")
    replacement = {"story_id": "other-story", "revision": 4, "file_sha256": "0" * 64,
                   "state_sha256": "0" * 64, "context_revision": 1,
                   "journal_sha256": "0" * 64}[field]
    with pytest.raises(ValueError):
        build(replace(source, **{field: replacement}))


@pytest.mark.parametrize("failure", ["unknown_field", "bad_profile", "duplicate_key", "wrong_source", "linked_metadata"])
def test_cli_failure_logs_do_not_echo_private_metadata_or_create_export(tmp_path, failure):
    source, _ = source_archive(tmp_path)
    secret = "SYNTHETIC_PRIVATE_METADATA_NEVER_ECHO"
    metadata = {"profile": profile().model_dump(), **fixtures.COPY}
    if failure == "unknown_field":
        metadata["outline"] = secret
    elif failure == "bad_profile":
        metadata["profile"]["genre"] = {"private": secret}
    content = json.dumps(metadata)
    if failure == "duplicate_key":
        content = '{"title": "' + secret + '", ' + content[1:]
    path = tmp_path / "metadata.json"
    path.write_text(content)
    if failure == "linked_metadata":
        original = tmp_path / "metadata-original.json"
        path.rename(original)
        path.symlink_to(original)
    out = tmp_path / "cli-out"
    args = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/export_accepted_review.py"),
        source.path, str(path), "--story-id", source.story_id, "--revision", str(source.revision),
        "--sha256", "0" * 64 if failure == "wrong_source" else source.file_sha256,
        "--stage", "opening_3", "--out-root", str(out)]
    for chapter_id in ["ch-1", "ch-2", "ch-3"]:
        args.extend(["--chapter-id", chapter_id])
    done = subprocess.run(args, capture_output=True, text=True)
    assert done.returncode != 0
    assert "accepted export refused" in done.stderr
    assert secret not in done.stdout + done.stderr
    assert fixtures.CHAT not in done.stdout + done.stderr
    assert not list(out.rglob("release-*.zip"))


# Recorded from the frozen c8c6d27 tree. CI does not read a sibling checkout.
LEGACY_SHA256 = {
    (3, False): "8926e5adebb98d24dfd96bddf1b9f25983f9be0be9d025cbec496bd8416c1902",
    (3, True): "5c8b3eba3347887ce51e3868176da4cffea407ad76f3f555685d1393482d0e60",
    (20, False): "5caac3436906f1aab7c54815c5eadcef66da3eaee9129c93e5bf3c0f96cd2cb9",
    (20, True): "1761918074513a4e413775785ff6111697e1891c649aa774b79abce3861ccd1a",
}


@pytest.mark.parametrize("count,scored", LEGACY_SHA256)
def test_legacy_review_zip_matches_frozen_whole_byte_golden(count, scored):
    stage = "opening_3" if count == 3 else "retention_20"
    corpus = MarketCorpus(project="golden-review", stage=stage, audience="adult synthetic readers",
        genre="fiction", review_note="Original offline golden", chapters=[MarketChapter(
            number=i, title="Synthetic " + str(i), text="\ufeff  灯 " + str(i) + "\r\nraw  \n")
            for i in range(1, count + 1)])
    pack = build_release_pack(corpus, MarketProfile(genre=corpus.genre, audience=corpus.audience),
        title="Original test title", one_line_hook="A choice", short_blurb="The lamp remains",
        tags=["night", "choice"])
    scores = [MarketScore(project=corpus.project, stage=stage, corpus_sha256=corpus.fingerprint(),
        reviewer_id="synthetic-human", dimension=dimension, score=3, note="Synthetic review")
        for dimension, _, _ in MARKET_RUBRIC] if scored else None
    raw = workflow.release_bundle_bytes(corpus, pack,
        chapter_ids=["id-" + str(i) for i in range(1, count + 1)], scores=scores)
    assert hashlib.sha256(raw).hexdigest() == LEGACY_SHA256[count, scored]
