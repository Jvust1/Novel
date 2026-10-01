"""Optional private author-amendment journal, reusing the v1 writing reducer.

Caller-supplied author/review references are evidence, not authentication. Replay
is pure; only save_journal/load_journal perform local I/O. No network/model calls.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, PrivateAttr

from novel_ai import gpt_story_state as v1
from novel_ai._vendor.eventsourcing_example import Aggregate, DomainEvent, aggregate_projector

OWNER = "gpt-author-journal-v1"
ZERO = "0" * 64
ALLOWED_PATHS = {"/canon/story_bible", "/canon/world_rules", "/canon/locked_facts",
                 "/canon/outline", "/canon/characters", "/style_profile"}
ACTIONS = Literal["story", "propose_amendment", "cancel_amendment", "accept_amendment",
                  "review_impact", "resume_reconciled"]


def _json(value: Any) -> bytes:
    return v1._json(value)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JournalError(v1.StateError):
    pass


class JournalEvent(DomainEvent):
    action: ACTIONS
    operation_id: str = Field(min_length=1)
    expected_journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any]
    previous_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class JournalCommand(v1.Record):
    story_id: str = Field(min_length=1)
    action: ACTIONS
    operation_id: str = Field(min_length=1)
    expected_journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any] = Field(default_factory=dict)


class Journal(v1.Record):
    _observed_readback: dict[str, Any] | None = PrivateAttr(default=None)
    engine_version: Literal["gpt-author-journal-v1"] = OWNER
    story_id: str
    origin: v1.Artifact
    migration_confirmation: dict[str, Any]
    created_at: datetime
    events: list[JournalEvent] = Field(default_factory=list)
    write_receipt: dict[str, Any] = Field(default_factory=lambda: {"status": "pending"})
    readback_receipt: dict[str, Any] = Field(default_factory=lambda: {"status": "pending"})


class Projection(Aggregate):
    story: dict[str, Any]
    context_revision: int = 0
    requires_checkpoint: bool = False
    proposal: dict[str, Any] | None = None
    amendment: dict[str, Any] | None = None
    impacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    archived_progress: list[dict[str, Any]] = Field(default_factory=list)
    operations: dict[str, str] = Field(default_factory=dict)
    origin_fingerprint: str
    migration_fingerprint: str
    head_sha256: str = ZERO


def _token(projection: Projection) -> str:
    return _hash({"story_id": projection.id, "version": projection.version,
                  "context_revision": projection.context_revision,
                  "origin": projection.origin_fingerprint,
                  "migration": projection.migration_fingerprint, "head": projection.head_sha256})


def _command_digest(action, operation_id, expected, payload):
    return _hash({"action": action, "operation_id": operation_id,
                  "expected_journal_sha256": expected, "payload": payload})


def _keys(value: dict, keys: set[str]) -> None:
    if set(value) != keys:
        raise JournalError("payload keys must be exactly: " + ", ".join(sorted(keys)))


def _confirmation(value, expected):
    if not isinstance(value, dict):
        raise JournalError("explicit author confirmation required")
    _keys(value, set(expected) | {"confirmed_by", "confirmation_source"})
    if value.get("confirmed_by") != "author" or not isinstance(value.get("confirmation_source"), str) or not value["confirmation_source"].strip():
        raise JournalError("explicit author message reference required; code cannot authenticate it")
    for key, actual in expected.items():
        if _json(value[key]) != _json(actual):
            raise JournalError("author confirmation differs from current " + key)


def _story(projection: Projection) -> v1.StoryState:
    return v1.validate_state(projection.story)


def _context(state: v1.StoryState) -> str:
    return v1._base_context_digest(state)


def _origin(journal: Journal) -> Projection:
    state = v1.validate_state(journal.origin.text)
    if not state.story_id or state.story_id != journal.story_id or getattr(state, "journal_owner", None):
        raise JournalError("migration needs an initialized, unowned v1 story with matching identity")
    if state.write_receipt.get("status") == "success" and (
        state.write_receipt.get("story_revision") != state.revision or
        state.write_receipt.get("content_sha256") != v1._content_digest(state)
    ):
        raise JournalError("v1 saved origin differs from its original write receipt")
    origin_fp = v1.source_fingerprint(journal.origin)
    _confirmation(journal.migration_confirmation,
                  {"scope": "migrate", "story_id": state.story_id, "origin_source_fingerprint": origin_fp})
    # Historical receipts remain in the archived origin bytes, never a fresh read.
    state.write_receipt = {"status": "pending"}
    state.readback_receipt = {"status": "pending"}
    return Projection(id=state.story_id, version=0, created_on=journal.created_at,
                      modified_on=journal.created_at, story=state.model_dump(mode="json"),
                      origin_fingerprint=origin_fp,
                      migration_fingerprint=_hash({"confirmation": journal.migration_confirmation, "created_at": journal.created_at.isoformat()}))


def _amendment_binding(p: Projection, proposal: dict) -> dict:
    return {"scope": "amendment", "story_id": p.id, "context_revision": p.context_revision,
            "proposal_id": proposal["proposal_id"], "target_context_sha256": proposal["target_context_sha256"]}


def _resume_binding(p: Projection) -> dict:
    if p.amendment is None:
        raise JournalError("no amendment awaits reconciliation")
    return {"scope": "resume", "story_id": p.id, "context_revision": p.context_revision,
            "proposal_id": p.amendment["proposal_id"], "target_context_sha256": _context(_story(p)),
            "reviews_sha256": _hash(p.impacts)}


def confirmation_binding(journal: Journal | dict, scope: Literal["amendment", "resume", "story"]) -> dict:
    """Binding fields only: never fabricate confirmed_by or author-message evidence."""
    p = _project_journal(journal)
    if scope == "amendment":
        if p.proposal is None:
            raise JournalError("no pending amendment")
        return _amendment_binding(p, p.proposal)
    if scope == "resume":
        return _resume_binding(p)
    return {"scope": "story", "story_id": p.id, "context_revision": p.context_revision,
            "context_sha256": _context(_story(p))}


def _validate_changes(state, raw):
    if not isinstance(raw, list) or not raw:
        raise JournalError("amendment needs at least one explicit change")
    result, seen = [], set()
    for change in raw:
        if not isinstance(change, dict):
            raise JournalError("each change must be an object")
        _keys(change, {"path", "old_value", "new_value"})
        path = change["path"]
        if path not in ALLOWED_PATHS or path in seen:
            raise JournalError("unsupported or duplicate amendment path")
        seen.add(path)
        obj, key = v1._path(state, path)
        if _json(obj[key]) != _json(change["old_value"]):
            raise JournalError("amendment old_value is stale: " + path)
        if _json(change["old_value"]) == _json(change["new_value"]):
            raise JournalError("amendment must materially change its field")
        obj[key] = copy.deepcopy(change["new_value"])
        result.append(copy.deepcopy(change))
    # Preserve old accepted evidence, but validate new field types independently
    # from the intentionally invalidated active progress/context fingerprint.
    v1.CanonData.model_validate(state["canon"])
    if not isinstance(state["style_profile"], dict):
        raise JournalError("style_profile must remain an object")
    return result


def _impact_queue(state, target):
    queue = {}
    for chapter in state.accepted_chapters:
        key = "chapter:" + chapter["chapter_id"]
        queue[key] = {"target_id": key, "status": "pending", "review": None,
                      "source_fingerprint": v1.source_fingerprint(chapter["draft"]),
                      "target_context_sha256": target}
    queue["derived_context"] = {"target_id": "derived_context", "status": "pending", "review": None,
        "source_fingerprint": _hash({"active": state.active, "recall": state.recall}),
        "target_context_sha256": target}
    return queue


def _blocked(p: Projection) -> bool:
    return p.proposal is not None or (p.amendment is not None and p.amendment["status"] != "reconciled")


def _reduce(event: JournalEvent, p: Projection | None) -> Projection:
    if p is None:
        raise JournalError("journal needs its explicit migration origin")
    if event.previous_event_sha256 != p.head_sha256 or event.expected_journal_sha256 != _token(p):
        raise JournalError("journal hash chain or expected version differs")
    if event.operation_id in p.operations:
        raise JournalError("duplicate operation event; retries must not append")
    result = p.model_dump(mode="python")
    story = _story(p)
    data = copy.deepcopy(event.payload)
    action = event.action
    if action == "propose_amendment":
        _keys(data, {"reason", "changes"})
        if p.proposal:
            raise JournalError("cancel the pending proposal before replacing it")
        if not isinstance(data["reason"], str) or not data["reason"].strip():
            raise JournalError("amendment needs the author's intended change/reason")
        root = story.model_dump(mode="json")
        changes = _validate_changes(root, data["changes"])
        target = _hash({key: root[key] for key in ("canon", "style_profile", "active", "recall")})
        if p.amendment and any(item["status"] == "requires_revision" for item in p.impacts.values()) and target != p.amendment["base_context_sha256"]:
            raise JournalError("unresolved historical repair permits only an exact context reversal in this bounded workflow")
        binding = {"base_context_revision": p.context_revision, "base_context_sha256": _context(story),
                   "target_context_sha256": target, "reason": data["reason"], "changes": changes,
                   "affected_sources": _impact_queue(story, target)}
        result["proposal"] = {"proposal_id": "amendment-" + _hash(binding), **binding}
    elif action == "cancel_amendment":
        _keys(data, {"proposal_id"})
        if not p.proposal or data["proposal_id"] != p.proposal["proposal_id"]:
            raise JournalError("only the specific unaccepted proposal can be cancelled")
        result["proposal"] = None
    elif action == "accept_amendment":
        _keys(data, {"confirmation"})
        if not p.proposal:
            raise JournalError("no pending amendment")
        _confirmation(data["confirmation"], _amendment_binding(p, p.proposal))
        if p.proposal["base_context_sha256"] != _context(story):
            raise JournalError("proposal no longer matches current story materials")
        root = story.model_dump(mode="json")
        _validate_changes(root, p.proposal["changes"])
        old_progress = story.progress.model_dump(mode="json")
        result["archived_progress"].append({"context_revision": p.context_revision,
            "proposal_id": p.proposal["proposal_id"], "progress": old_progress,
            "pending_memory_updates": [c.model_dump(mode="json") for c in story.pending_memory_updates if c.status != "applied"]})
        committed = story.progress.phase in {"awaiting_save", "awaiting_readback", "ready_next"}
        story.canon, story.style_profile = root["canon"], root["style_profile"]
        for candidate in story.pending_memory_updates:
            if candidate.status == "pending":
                candidate.status = "invalidated"
        story.progress = v1.Progress(phase="planning", base_story_revision=story.revision,
            chapter_id=None if committed else old_progress["chapter_id"],
            plan_revision=None if committed else old_progress["plan_revision"],
            draft_revision=None if committed else old_progress["draft_revision"],
            base_context_sha256=_context(story))
        story.write_receipt = {"status": "pending"}
        story.readback_receipt = {"status": "pending"}
        result["context_revision"] += 1
        result["requires_checkpoint"] = True
        result["amendment"] = {**copy.deepcopy(p.proposal), "status": "awaiting_reviews",
                                "confirmation": data["confirmation"]}
        result["impacts"] = _impact_queue(story, _context(story))
        result["proposal"] = None
    elif action == "review_impact":
        _keys(data, {"target_id", "source_fingerprint", "target_context_sha256", "review_artifact", "verdict", "issues"})
        if p.proposal or not p.amendment or p.amendment["status"] == "reconciled":
            raise JournalError("no active amendment is ready for impact review")
        item = p.impacts.get(data["target_id"])
        if item is None or item["status"] != "pending":
            raise JournalError("unknown or already-reviewed target; incompatible review needs a new amendment")
        for key in ("source_fingerprint", "target_context_sha256"):
            if data[key] != item[key]:
                raise JournalError("review binds a different source or context")
        review = v1.Artifact.model_validate(data["review_artifact"])
        if data["verdict"] not in {"compatible", "requires_revision"}:
            raise JournalError("review verdict must be compatible or requires_revision")
        if not isinstance(data["issues"], list) or any(not isinstance(i, str) or not i.strip() for i in data["issues"]):
            raise JournalError("issues must be explicit nonblank descriptions")
        if (data["verdict"] == "compatible") != (len(data["issues"]) == 0):
            raise JournalError("compatible review cannot waive unresolved issues")
        result["impacts"][data["target_id"]] = {**item, "status": data["verdict"],
            "review": {"artifact": review.model_dump(mode="json"), "issues": data["issues"]}}
    elif action == "resume_reconciled":
        _keys(data, {"confirmation"})
        if p.proposal or not p.amendment or p.amendment["status"] == "reconciled":
            raise JournalError("no accepted amendment awaits resume")
        if not p.impacts or any(item["status"] != "compatible" for item in p.impacts.values()):
            raise JournalError("all accepted chapters and derived context need compatible reviews; historical repair is not implemented")
        _confirmation(data["confirmation"], _resume_binding(p))
        result["amendment"]["status"] = "reconciled"
        result["amendment"]["resume_confirmation"] = data["confirmation"]
    elif action == "story":
        _keys(data, {"action", "payload", "context_confirmation", "checkpoint"})
        if _blocked(p):
            raise JournalError("finish or cancel the amendment and reconcile its impacts before writing")
        if data["action"] in {"accept_plan", "accept_chapter", "accept_memory"}:
            _confirmation(data["context_confirmation"], {"scope": "story", "story_id": p.id,
                "context_revision": p.context_revision, "context_sha256": _context(story)})
        elif data["context_confirmation"] is not None:
            raise JournalError("nonacceptance actions must not fabricate author confirmations")
        committed = story.progress.phase in {"awaiting_save", "awaiting_readback", "ready_next"}
        needs_checkpoint = p.requires_checkpoint or (data["action"] == "start_chapter" and committed)
        if needs_checkpoint:
            checkpoint = data["checkpoint"]
            if not isinstance(checkpoint, dict) or checkpoint.get("journal_sha256") != _token(p):
                raise JournalError("next chapter requires actual readback of this envelope version")
            _keys(checkpoint, {"journal_sha256", "file_sha256", "location"})
            if len(checkpoint["file_sha256"]) != 64 or not checkpoint["location"]:
                raise JournalError("checkpoint must retain actual envelope file evidence")
            # Recorded historical evidence permits deterministic replay, not a new
            # read claim. Returned projections always clear these v1 receipts.
            result["requires_checkpoint"] = False
            if committed:
                story.progress.phase = "ready_next"
                story.readback_receipt = {"status": "verified", "story_revision": story.revision,
                                          "scope": "historical_envelope_checkpoint"}
        elif data["checkpoint"] is not None:
            raise JournalError("checkpoint is only valid for starting after a committed chapter")
        cmd = dict(action=data["action"], story_id=p.id, base_story_revision=story.revision,
                   operation_id="journal:" + event.operation_id,
                   expected_state_sha256=v1.state_fingerprint(story), payload=data["payload"])
        story = v1.transition(story, cmd)
        story.write_receipt = {"status": "pending"}
        story.readback_receipt = {"status": "pending"}
    result["story"] = v1.validate_state(story).model_dump(mode="json")
    result["operations"][event.operation_id] = _command_digest(action, event.operation_id,
        event.expected_journal_sha256, event.payload)
    result.update(version=event.originator_version, modified_on=event.timestamp,
                  head_sha256=_hash(event.model_dump(mode="json")))
    return Projection.model_validate(result)


PROJECTOR = aggregate_projector(_reduce)


def validate_journal(value: Journal | dict | str | bytes) -> Journal:
    # JSON round-trip also detaches nested fields and parses strict datetimes.
    if isinstance(value, Journal):
        value = value.model_dump_json()
    elif isinstance(value, dict):
        value = _json(value)
    journal = Journal.model_validate_json(value)
    _project_journal(journal)
    journal.readback_receipt = {"status": "pending"}
    return journal


def _project_journal(value: Journal | dict) -> Projection:
    if not isinstance(value, Journal):
        value = Journal.model_validate_json(_json(value))
    else:
        value = Journal.model_validate_json(value.model_dump_json())
    return PROJECTOR(_origin(value), value.events)


def journal_fingerprint(value: Journal | dict) -> str:
    return _token(_project_journal(value))


def migrate_state(origin: v1.Artifact | dict, confirmation: dict) -> Journal:
    origin = v1.Artifact.model_validate(origin.model_dump() if isinstance(origin, v1.Artifact) else copy.deepcopy(origin))
    story = v1.validate_state(origin.text)
    value = Journal(story_id=story.story_id, origin=origin, migration_confirmation=copy.deepcopy(confirmation), created_at=_now())
    return validate_journal(value)


def transition_journal(value: Journal | dict, command: JournalCommand | dict) -> Journal:
    observed = copy.deepcopy(value._observed_readback) if isinstance(value, Journal) else None
    journal = validate_journal(value)
    if observed and observed.get("journal_sha256") == journal_fingerprint(journal):
        journal._observed_readback = observed
        journal.readback_receipt = copy.deepcopy(observed)
    cmd = JournalCommand.model_validate(command.model_dump() if isinstance(command, JournalCommand) else copy.deepcopy(command))
    p = _project_journal(journal)
    if cmd.story_id != p.id:
        raise JournalError("cross-story command refused")
    digest = _command_digest(cmd.action, cmd.operation_id, cmd.expected_journal_sha256, cmd.payload)
    if cmd.operation_id in p.operations:
        if p.operations[cmd.operation_id] != digest:
            raise JournalError("operation ID already used with different input")
        return journal
    if cmd.expected_journal_sha256 != _token(p):
        raise JournalError("stale journal/context; reread before editing")
    if cmd.action == "story" and cmd.payload.get("checkpoint") is not None:
        expected = journal._observed_readback or {}
        checkpoint = cmd.payload["checkpoint"]
        if (expected.get("status") != "verified" or expected.get("journal_sha256") != _token(p)
            or checkpoint != {key: expected.get(key) for key in ("journal_sha256", "file_sha256", "location")}):
            raise JournalError("checkpoint is not the current actual load_journal readback")
    journal.events.append(JournalEvent(originator_id=p.id, originator_version=p.version + 1,
        timestamp=_now(), action=cmd.action, operation_id=cmd.operation_id,
        expected_journal_sha256=cmd.expected_journal_sha256, payload=copy.deepcopy(cmd.payload),
        previous_event_sha256=p.head_sha256))
    journal.write_receipt = {"status": "pending"}
    journal.readback_receipt = {"status": "pending"}
    journal._observed_readback = None
    return validate_journal(journal)


def project_journal(value: Journal | dict) -> Projection:
    """Public diagnostic projection: v1 writing APIs cannot bypass the envelope."""
    p = _project_journal(value)
    data = p.model_dump(mode="python")
    data["story"]["journal_owner"] = {"engine_version": OWNER, "journal_sha256": _token(p),
                                      "context_revision": p.context_revision}
    return Projection.model_validate(data)


def owned_story(value: Journal | dict) -> v1.StoryState:
    p = _project_journal(value)
    data = copy.deepcopy(p.story)
    data["journal_owner"] = {"engine_version": OWNER, "journal_sha256": _token(p),
                             "context_revision": p.context_revision}
    return v1.validate_state(data)


def preflight_journal(value: Journal | dict, sources: list[dict], budget_bytes: int, **kwargs) -> dict:
    p = _project_journal(value)
    result = v1.preflight_context(_story(p), sources, budget_bytes, **kwargs)
    if _blocked(p):
        result["blocked"] = True
        result["reasons"].append("author amendment/reconciliation is pending; do not draft")
    observed = value._observed_readback if isinstance(value, Journal) else None
    if p.requires_checkpoint and (not observed or observed.get("journal_sha256") != _token(p)):
        result["blocked"] = True
        result["reasons"].append("reconciled context requires actual save/readback before drafting")
    result["journal_sha256"] = _token(p)
    result["context_revision"] = p.context_revision
    return result


def _envelope_digest(journal):
    data = journal.model_dump(mode="json", exclude={"write_receipt", "readback_receipt"})
    return _hash(data)


def save_journal(path: str | Path, value: Journal | dict, *, expected_disk_sha256: str | None = None) -> dict:
    """Atomic single-local-file publication; callers serialize concurrent writers."""
    journal = validate_journal(value)
    path = v1._local_path(path)
    existed = path.exists()
    p = _project_journal(journal)
    if existed:
        raw = path.read_bytes()
        previous = validate_journal(raw)
        if expected_disk_sha256 is None or hashlib.sha256(raw).hexdigest() != expected_disk_sha256:
            raise JournalError("existing envelope changed; actual old file hash required")
        if (previous.story_id != journal.story_id or previous.origin != journal.origin
            or previous.migration_confirmation != journal.migration_confirmation or previous.created_at != journal.created_at):
            raise JournalError("cannot replace story migration origin or identity")
        if journal.events[:len(previous.events)] != previous.events:
            raise JournalError("journal is append-only; saved events cannot change or disappear")
        if len(journal.events) == len(previous.events):
            return {"journal": previous, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "changed": False}
    elif expected_disk_sha256 is not None:
        raise JournalError("expected existing journal is missing")
    journal.write_receipt = {"status": "success", "scope": "single_local_envelope", "location": str(path),
        "journal_sha256": _token(p), "content_sha256": _envelope_digest(journal), "written_at": _now().isoformat()}
    journal.readback_receipt = {"status": "pending"}
    raw = _json(journal.model_dump(mode="json")) + b"\n"
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if existed:
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_disk_sha256:
                raise JournalError("destination changed during save")
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"journal": journal, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "changed": True}


def load_journal(path: str | Path, *, expected_story_id: str, expected_sha256: str | None = None) -> Journal:
    path = v1._local_path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    journal = validate_journal(raw)
    if journal.story_id != expected_story_id or (expected_sha256 is not None and digest != expected_sha256):
        raise JournalError("restored envelope story identity or file hash differs")
    token = journal_fingerprint(journal)
    receipt = journal.write_receipt
    if (receipt.get("status") != "success" or receipt.get("journal_sha256") != token
        or receipt.get("content_sha256") != _envelope_digest(journal)):
        raise JournalError("saved envelope differs from its successful write receipt")
    journal.readback_receipt = {"status": "verified", "location": str(path), "file_sha256": digest,
        "journal_sha256": token, "read_at": _now().isoformat(), "receipt_persisted": False}
    journal._observed_readback = copy.deepcopy(journal.readback_receipt)
    return journal
