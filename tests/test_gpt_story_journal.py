"""Synthetic author-message fixtures; not real author acceptance or manuscripts."""
import copy
import itertools
from datetime import datetime, timezone
import pytest
from novel_ai import gpt_story_state as old
from novel_ai import gpt_story_journal as j
from novel_ai._vendor.eventsourcing_example import Aggregate, DomainEvent, aggregate_projector
COUNT = itertools.count()


def art(text, name="fixture", revision=1):
    return old.artifact(text, source_id=name, location="private://fixture/" + name, revision=revision)


def confirm(binding):
    return {**binding, "confirmed_by": "author", "confirmation_source": "synthetic-test://explicit-author-message"}


def migrated(state=None):
    state = old.create_state("test-book", "Synthetic only") if state is None else state
    source = art(state.model_dump_json(), "v1-state")
    return j.migrate_state(source, confirm({"scope": "migrate", "story_id": state.story_id,
                                          "origin_source_fingerprint": old.source_fingerprint(source)}))


def command(value, action, payload, operation_id=None):
    return dict(story_id=value.story_id, action=action, operation_id=operation_id or f"operation-{next(COUNT)}",
                expected_journal_sha256=j.journal_fingerprint(value), payload=payload)


def step(value, action, payload):
    return j.transition_journal(value, command(value, action, payload))


def story(value, action, payload):
    p = j.project_journal(value)
    checkpoint = None
    if p.requires_checkpoint or (action == "start_chapter" and p.story["progress"]["phase"] in {"awaiting_save", "awaiting_readback", "ready_next"}):
        checkpoint = {k: value.readback_receipt.get(k) for k in ("journal_sha256", "file_sha256", "location")}
    return step(value, "story", {"action": action, "payload": payload, "checkpoint": checkpoint,
        "context_confirmation": confirm(j.confirmation_binding(value, "story")) if action.startswith("accept_") else None})


def chapter_confirmation(value, scope):
    state = old.validate_state(j.project_journal(value).story)
    p = state.progress
    c = dict(confirmed_by="author", confirmation_source="synthetic-test://author", story_id=state.story_id,
             story_revision=p.base_story_revision, chapter_id=p.chapter_id, plan_revision=p.plan_revision,
             plan_source_fingerprint=old.source_fingerprint(p.plan))
    if scope in {"chapter", "memory"}:
        c.update(draft_revision=p.draft_revision, draft_source_fingerprint=old.source_fingerprint(p.draft))
    if scope == "memory":
        c["memory_update_id"] = p.memory_update_id
    return c


def finish_chapter(value, chapter_id="chapter-1"):
    value = story(value, "start_chapter", {"chapter_id": chapter_id})
    value = story(value, "set_plan", {"artifact": art("A person chooses a route", "plan-" + chapter_id).model_dump(mode="json")})
    value = story(value, "accept_plan", {"confirmation": chapter_confirmation(value, "plan")})
    value = story(value, "set_draft", {"artifact": art("The lamp remained lit.", "draft-" + chapter_id).model_dump(mode="json")})
    value = story(value, "review", {"draft_revision": 1, "issues": [], "source": art("No issues", "review-" + chapter_id).source.model_dump(mode="json")})
    value = story(value, "accept_chapter", {"confirmation": chapter_confirmation(value, "chapter")})
    value = story(value, "propose_memory", {"changes": []})
    value = story(value, "accept_memory", {"confirmation": chapter_confirmation(value, "memory")})
    return story(value, "apply_memory", {"memory_update_id": j.project_journal(value).story["progress"]["memory_update_id"]})


def propose(value, new=None):
    state = j.project_journal(value).story
    return step(value, "propose_amendment", {"reason": "Author changes future narrative distance",
        "changes": [{"path": "/style_profile", "old_value": state["style_profile"],
                     "new_value": {"distance": "close", "genre": "mystery"} if new is None else new}]})


def accept_proposal(value):
    return step(value, "accept_amendment", {"confirmation": confirm(j.confirmation_binding(value, "amendment"))})


def review(value, target, verdict="compatible"):
    item = j.project_journal(value).impacts[target]
    return step(value, "review_impact", {"target_id": target, "source_fingerprint": item["source_fingerprint"],
        "target_context_sha256": item["target_context_sha256"], "review_artifact": art("Read actual source and checked style/facts", "review-" + target).model_dump(mode="json"),
        "verdict": verdict, "issues": [] if verdict == "compatible" else ["Old text contradicts new rule"]})


def reconcile(value):
    for target in j.project_journal(value).impacts:
        value = review(value, target)
    return step(value, "resume_reconciled", {"confirmation": confirm(j.confirmation_binding(value, "resume"))})


def test_migration_preserves_bytes_and_needs_explicit_binding():
    state = old.create_state("test-book")
    original = state.model_dump_json(indent=2)
    source = art(original, "original-state")
    binding = {"scope": "migrate", "story_id": state.story_id, "origin_source_fingerprint": old.source_fingerprint(source)}
    value = j.migrate_state(source, confirm(binding))
    assert value.origin.text == original
    assert j.project_journal(value).version == 0
    with pytest.raises(ValueError):
        j.migrate_state(source, confirm({**binding, "origin_source_fingerprint": "f" * 64}))
    assert j.validate_journal(value.model_dump_json()) == value


def test_complete_amend_review_resume_restore_next_chapter(tmp_path):
    value = finish_chapter(migrated())
    history = copy.deepcopy(j.project_journal(value).story["accepted_chapters"])
    value = accept_proposal(propose(value))
    p = j.project_journal(value)
    assert p.context_revision == 1 and p.story["revision"] == 1
    assert set(p.impacts) == {"chapter:chapter-1", "derived_context"}
    assert p.story["accepted_chapters"] == history
    assert j.preflight_journal(value, [], 100000)["blocked"]
    with pytest.raises(ValueError):
        story(value, "start_chapter", {"chapter_id": "chapter-2"})
    value = reconcile(value)
    assert j.preflight_journal(value, [], 100000)["blocked"]
    path = tmp_path / "private-journal.json"
    saved = j.save_journal(path, value)
    value = j.load_journal(path, expected_story_id="test-book", expected_sha256=saved["sha256"])
    assert value.readback_receipt["status"] == "verified"
    assert not j.preflight_journal(value, [], 100000)["blocked"]
    value = finish_chapter(value, "chapter-2")
    assert j.project_journal(value).story["revision"] == 2
    assert j.project_journal(value).story["accepted_chapters"][:1] == history
    j.save_journal(path, value, expected_disk_sha256=saved["sha256"])
    restored = j.load_journal(path, expected_story_id="test-book")
    assert j.journal_fingerprint(restored) == j.journal_fingerprint(value)


def test_unchanged_v1_guard_and_pending_draft_archive(tmp_path):
    value = story(migrated(), "start_chapter", {"chapter_id": "chapter-1"})
    value = story(value, "set_plan", {"artifact": art("A person chooses", "plan").model_dump(mode="json")})
    old_confirmation = chapter_confirmation(value, "plan")
    value = story(value, "accept_plan", {"confirmation": old_confirmation})
    value = accept_proposal(propose(value))
    p = j.project_journal(value)
    assert p.archived_progress[-1]["progress"]["plan_acceptance"] == old.Confirmation.model_validate(old_confirmation).model_dump(mode="json")
    assert p.story["progress"]["plan"] is None and p.story["progress"]["plan_revision"] == 1
    value = reconcile(value)
    j.save_journal(tmp_path / "mid.json", value)
    value = j.load_journal(tmp_path / "mid.json", expected_story_id="test-book")
    value = story(value, "set_plan", {"artifact": art("A person chooses", "plan").model_dump(mode="json")})
    assert j.project_journal(value).story["progress"]["plan_revision"] == 2
    with pytest.raises(ValueError):
        story(value, "accept_plan", {"confirmation": old_confirmation})
    owned = j.owned_story(value)
    with pytest.raises(ValueError, match="journal"):
        old.preflight_context(owned, [], 100000)
    with pytest.raises(ValueError, match="journal"):
        old.transition(owned, {})


def test_missing_and_incompatible_review_block_resume():
    value = accept_proposal(propose(finish_chapter(migrated())))
    value = review(value, "chapter:chapter-1")
    with pytest.raises(ValueError, match="all accepted chapters"):
        step(value, "resume_reconciled", {"confirmation": confirm(j.confirmation_binding(value, "resume"))})
    value = review(value, "derived_context", "requires_revision")
    with pytest.raises(ValueError):
        review(value, "derived_context")
    with pytest.raises(ValueError):
        step(value, "resume_reconciled", {"confirmation": confirm(j.confirmation_binding(value, "resume"))})
    value = accept_proposal(propose(value, {}))
    assert j.project_journal(value).context_revision == 2
    assert any(e.action == "review_impact" and e.payload["verdict"] == "requires_revision" for e in value.events)
    value = reconcile(value)
    assert j.preflight_journal(value, [], 100000)["blocked"]  # still needs actual save/readback


def test_exact_retry_stale_context_and_mutated_operation():
    value = migrated()
    cmd = command(value, "propose_amendment", {"reason": "Change distance", "changes": [{"path": "/style_profile", "old_value": {}, "new_value": {"distance": "close"}}]})
    updated = j.transition_journal(value, cmd)
    assert j.transition_journal(updated, cmd) == updated
    cancelled = step(updated, "cancel_amendment", {"proposal_id": j.project_journal(updated).proposal["proposal_id"]})
    assert j.transition_journal(cancelled, cmd) == cancelled
    altered = copy.deepcopy(cmd)
    altered["payload"]["reason"] = "Different"
    with pytest.raises(ValueError):
        j.transition_journal(cancelled, altered)
    cmd["operation_id"] = "new"
    with pytest.raises(ValueError, match="stale"):
        j.transition_journal(cancelled, cmd)


def test_tampering_and_actual_readback(tmp_path):
    value = finish_chapter(migrated())
    with pytest.raises(ValueError, match="readback"):
        story(value, "start_chapter", {"chapter_id": "chapter-2"})
    path = tmp_path / "book.json"
    saved = j.save_journal(path, value)
    assert j.project_journal(saved["journal"]).story["progress"]["phase"] == "awaiting_save"
    with pytest.raises(ValueError, match="readback"):
        story(saved["journal"], "start_chapter", {"chapter_id": "chapter-2"})
    loaded = j.load_journal(path, expected_story_id="test-book")
    value = story(loaded, "start_chapter", {"chapter_id": "chapter-2"})
    assert j.project_journal(value).story["progress"]["phase"] == "planning"
    for mutate in (lambda d: d["events"].reverse(), lambda d: d["events"].pop(0),
                   lambda d: d["events"][0].update(originator_id="other-book"),
                   lambda d: d["events"][0].update(originator_version=5)):
        data = value.model_dump(mode="json")
        mutate(data)
        with pytest.raises(ValueError):
            j.validate_journal(data)
    with pytest.raises(ValueError):
        j.save_journal(path, migrated(), expected_disk_sha256=saved["sha256"])
    with pytest.raises(ValueError):
        j.load_journal(path, expected_story_id="other-book")


def test_upstream_projector_guards_are_used():
    now = datetime.now(timezone.utc)
    p = Aggregate(id="book", version=0, created_on=now, modified_on=now)
    def mutate(event, previous):
        return Aggregate(id=event.originator_id, version=event.originator_version, created_on=now, modified_on=now)
    replay = aggregate_projector(mutate)
    event = DomainEvent(originator_id="book", originator_version=1, timestamp=now)
    assert replay(p, [event]).version == 1
    for bad in (DomainEvent(originator_id="other", originator_version=1, timestamp=now),
                DomainEvent(originator_id="book", originator_version=2, timestamp=now)):
        with pytest.raises(ValueError):
            replay(p, [bad])


@pytest.mark.parametrize("path", ["/canon/reader_reveal_ledger", "/accepted_chapters", "/active/current_time", "/canon/characters/0", "/write_receipt"])
def test_unsupported_amendment_paths(path):
    with pytest.raises(ValueError):
        step(migrated(), "propose_amendment", {"reason": "Synthetic request", "changes": [{"path": path, "old_value": None, "new_value": []}]})


def test_review_source_identity_and_context_binding():
    value = accept_proposal(propose(finish_chapter(migrated())))
    item = j.project_journal(value).impacts["chapter:chapter-1"]
    payload = {"target_id": "chapter:chapter-1", "source_fingerprint": item["source_fingerprint"],
        "target_context_sha256": item["target_context_sha256"], "review_artifact": art("Review fixture", "review").model_dump(mode="json"),
        "verdict": "compatible", "issues": []}
    for key in ("source_fingerprint", "target_context_sha256"):
        with pytest.raises(ValueError):
            step(value, "review_impact", {**payload, key: "f" * 64})
    with pytest.raises(ValueError):
        step(value, "review_impact", {**payload, "issues": ["A known unresolved issue"]})
    bad = copy.deepcopy(payload)
    bad["review_artifact"]["text"] = "Changed review without hash update"
    with pytest.raises(ValueError):
        step(value, "review_impact", bad)


def test_journal_partial_duplicate_and_conflicting_parent(tmp_path):
    value = propose(migrated())
    path = tmp_path / "private.json"
    saved = j.save_journal(path, value)
    raw = path.read_bytes()
    with pytest.raises(ValueError):
        j.validate_journal(raw[:-9])
    for change in (lambda d: d["events"].append(d["events"][0]),
                   lambda d: d["events"][0].update(previous_event_sha256="f" * 64)):
        data = value.model_dump(mode="json")
        change(data)
        with pytest.raises(ValueError):
            j.validate_journal(data)
    with pytest.raises(ValueError):
        j.save_journal(path, value, expected_disk_sha256="f" * 64)
    assert path.read_bytes() == raw
    unchanged = j.save_journal(path, value, expected_disk_sha256=saved["sha256"])
    assert unchanged["changed"] is False and path.read_bytes() == raw


def test_write_interruption_does_not_change_old_bytes(tmp_path, monkeypatch):
    value = migrated()
    path = tmp_path / "private.json"
    saved = j.save_journal(path, value)
    raw = path.read_bytes()
    updated = propose(value)
    def fail(*args):
        raise OSError("synthetic interruption before replace")
    monkeypatch.setattr(j.os, "replace", fail)
    with pytest.raises(OSError):
        j.save_journal(path, updated, expected_disk_sha256=saved["sha256"])
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


def test_no_clobber_and_symlink_destination(tmp_path, monkeypatch):
    path = tmp_path / "private.json"
    original_link = j.os.link
    def race(source, target):
        path.write_text("another writer")
        return original_link(source, target)
    monkeypatch.setattr(j.os, "link", race)
    with pytest.raises(FileExistsError):
        j.save_journal(path, migrated())
    assert path.read_text() == "another writer"
    link = tmp_path / "alias.json"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        j.save_journal(link, migrated())


def test_new_migration_does_not_overwrite_v1_file(tmp_path):
    state = old.create_state("test-book")
    path = tmp_path / "v1.json"
    saved = old.save_state(path, state)
    raw = path.read_bytes()
    source = art(raw.decode("utf-8"), "v1-state")
    value = j.migrate_state(source, confirm({"scope": "migrate", "story_id": "test-book", "origin_source_fingerprint": old.source_fingerprint(source)}))
    with pytest.raises(ValueError):
        j.save_journal(path, value, expected_disk_sha256=saved.sha256)
    assert path.read_bytes() == raw


def test_owner_guard_save_and_legacy_default_fingerprint(tmp_path):
    value = migrated()
    with pytest.raises(ValueError, match="journal"):
        old.save_state(tmp_path / "bypass.json", j.project_journal(value).story)
    assert not (tmp_path / "bypass.json").exists()
    state = old.create_state("test-book")
    assert "journal_owner" not in state.model_dump()


def test_cli_real_migrate_inspect_apply_idempotence(tmp_path):
    import subprocess
    import sys
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "v1.json"
    source.write_text(old.create_state("test-book").model_dump_json(), encoding="utf-8")
    src = old.artifact(source.read_bytes().decode(), source_id="source", location=str(source), revision="1")
    decision = tmp_path / "confirmation.json"
    decision.write_text(json.dumps(confirm({"scope": "migrate", "story_id": "test-book", "origin_source_fingerprint": old.source_fingerprint(src)})))
    target = tmp_path / "journal.json"
    def run(*args):
        result = subprocess.run([sys.executable, str(root / "scripts/story_journal.py"), *map(str,args)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    run("migrate", source, target, "--source-id", "source", "--source-revision", "1", "--confirmation", decision)
    output = run("inspect", target, "--story-id", "test-book")
    assert output["readback_receipt"]["status"] == "verified"
    current = j.load_journal(target, expected_story_id="test-book")
    cmd = command(current, "propose_amendment", {"reason": "Fixture change", "changes": [{"path": "/style_profile", "old_value": {}, "new_value": {"distance": "close"}}]})
    command_file = tmp_path / "command.json"
    command_file.write_text(json.dumps(cmd))
    assert run("apply", target, command_file)["changed"] is True
    raw = target.read_bytes()
    assert run("apply", target, command_file)["changed"] is False
    assert target.read_bytes() == raw


def test_license_provenance_and_entry_integration():
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    pins = json.loads((root / "third_party/eventsourcing/provenance.json").read_text())
    assert pins["observed_stars"] >= 1000 and pins["license"] == "BSD-3-Clause"
    for row in [pins["license_file"], *pins["files"], pins["adaptation"]]:
        assert hashlib.sha256((root / row["local_path"]).read_bytes()).hexdigest() == row["sha256"]
    assert "GPT_AUTHOR_AMENDMENTS.md" in (root / "docs/GPT_WRITING_ENTRY.md").read_text()
    assert "aggregate_projector(_reduce)" in (root / "novel_ai/gpt_story_journal.py").read_text()
    assert hashlib.sha256((root / "writing_demos/plugin-first-chapter-20261001/chapter-001.md").read_bytes()).hexdigest() == "b6d9e0d26c21658e1be0c9ab30117ca0ce53f7067c941fef8bad969d014c432e"
