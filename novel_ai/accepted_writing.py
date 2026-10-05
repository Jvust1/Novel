"""Optional source-bound continuation through the existing history and budget APIs.

An actually read v1 archive or explicitly opted-in author journal is admitted
through its owning protocol. Embedded accepted snapshots are authoritative;
their locations are never fetched. No new confirmation/event, cache or
canonical write occurs. Journal replay retains its existing pure reducer.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import gpt_story_journal as journal_api
from . import gpt_story_state as state_api
from .engine import ChapterResult, NovelEngine
from .models import ChapterPlan, Character, SceneBeat, StoryBible, StyleFingerprint
from .output_policy import OutputPolicy, positive_int, strict_json_object
from .provider import OpenAICompatibleProvider
from .storage_guard import reject_links

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class ArchiveError(state_api.StateError):
    """The actual source, accepted plan, context or execution evidence changed."""


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    return _hash(_json(value))


def _read(path: str | Path) -> tuple[Path, bytes]:
    if "://" in str(path) or "\0" in str(path):
        raise ArchiveError("archive must be an explicit local file")
    target = Path(path).expanduser().absolute()
    reject_links(target)
    if not target.is_file():
        raise ArchiveError("archive is not an available regular file")
    if target.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive exceeds the supported byte allowance")
    with target.open("rb") as stream:
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive exceeds the supported byte allowance")
    return target.resolve(), raw


@dataclass(frozen=True)
class RestoredSource:
    """Immutable expected identity. Every use rereads the actual archive."""

    path: str
    story_id: str
    revision: int
    file_sha256: str
    state_sha256: str

    def binding(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in (
            "path", "story_id", "revision", "file_sha256", "state_sha256")}

    @property
    def state(self) -> state_api.StoryState:
        return _fresh(self)[1]

    def assert_current(self) -> None:
        _fresh(self)


@dataclass(frozen=True)
class RestoredJournalSource:
    """A separate owned-envelope identity; v1 source bindings stay unchanged."""

    path: str
    story_id: str
    revision: int
    file_sha256: str
    state_sha256: str
    context_revision: int
    journal_sha256: str

    def binding(self) -> dict[str, Any]:
        return {"source_kind": "author_journal", **{key: getattr(self, key) for key in (
            "path", "story_id", "revision", "file_sha256", "state_sha256",
            "context_revision", "journal_sha256")}}

    def expected_identity(self) -> dict[str, Any]:
        return {"expected_story_id": self.story_id, "expected_revision": self.revision,
                "expected_context_revision": self.context_revision,
                "expected_journal_sha256": self.journal_sha256,
                "expected_file_sha256": self.file_sha256}

    @property
    def state(self) -> state_api.StoryState:
        return _fresh(self)[1]

    @property
    def journal(self) -> journal_api.Journal:
        current, _, value = _load_journal(self.path, **self.expected_identity())
        if current.binding() != self.binding():
            raise ArchiveError("journal binding differs from its actual saved content")
        return value

    def assert_current(self) -> None:
        _fresh(self)


ArchiveSource = RestoredSource | RestoredJournalSource


def _load_journal(path: str | Path, *, expected_story_id: str, expected_revision: int,
                  expected_context_revision: int, expected_journal_sha256: str,
                  expected_file_sha256: str) -> tuple[RestoredJournalSource, state_api.StoryState, journal_api.Journal]:
    target, raw = _read(path)
    if not isinstance(expected_file_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_file_sha256):
        raise ArchiveError("an actual expected journal file SHA-256 is required")
    if _hash(raw) != expected_file_sha256:
        raise ArchiveError("journal archive bytes changed; restore and reconcile")
    payload = strict_json_object(raw.decode("utf-8"), max_bytes=MAX_ARCHIVE_BYTES)
    if payload.get("engine_version") != journal_api.OWNER:
        raise ArchiveError("the explicit journal entry requires an author journal envelope")
    value = journal_api.load_journal(target, expected_story_id=expected_story_id,
                                     expected_sha256=expected_file_sha256)
    # Only the owning journal API can admit its current actual observed readback.
    # This never creates v1 write/read receipts or removes journal_owner.
    journal_api.rebuild_journal_accepted_history(value, expected_story_id=expected_story_id,
        expected_revision=expected_revision, expected_context_revision=expected_context_revision,
        expected_journal_sha256=expected_journal_sha256, expected_file_sha256=expected_file_sha256)
    state = journal_api.owned_story(value)
    result = RestoredJournalSource(str(target), state.story_id, state.revision,
        expected_file_sha256, state_api.state_fingerprint(state), expected_context_revision,
        expected_journal_sha256)
    after, content = _read(target)
    if str(after) != result.path or _hash(content) != expected_file_sha256:
        raise ArchiveError("journal archive changed during restore")
    return result, state, value


def restore_journal_source(path: str | Path, *, expected_story_id: str, expected_revision: int,
                            expected_context_revision: int, expected_journal_sha256: str,
                            expected_file_sha256: str) -> RestoredJournalSource:
    """Explicitly opt into the owning journal's observed continuation protocol."""
    return _load_journal(path, expected_story_id=expected_story_id, expected_revision=expected_revision,
        expected_context_revision=expected_context_revision, expected_journal_sha256=expected_journal_sha256,
        expected_file_sha256=expected_file_sha256)[0]


def _load(path: str | Path, *, expected_story_id: str, expected_revision: int,
          expected_sha256: str) -> tuple[RestoredSource, state_api.StoryState]:
    if not isinstance(expected_story_id, str) or not expected_story_id.strip():
        raise ArchiveError("an explicit expected story ID is required")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ArchiveError("an explicit nonnegative expected revision is required")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ArchiveError("an actual expected file SHA-256 is required")
    target, raw = _read(path)
    if _hash(raw) != expected_sha256:
        raise ArchiveError("archive bytes changed; restore and reconcile")
    payload = strict_json_object(raw.decode("utf-8"), max_bytes=MAX_ARCHIVE_BYTES)
    if "journal_owner" in payload or payload.get("engine_version") == "gpt-author-journal-v1":
        raise ArchiveError("journal-owned stories require the existing journal protocol; this entry does not strip ownership")
    state = state_api.load_state(target, expected_story_id=expected_story_id,
                                 expected_revision=expected_revision, expected_sha256=expected_sha256)
    if (state.template_version != "gpt-writing-entry-v1"
        or state.write_receipt.get("status") != "success"
        or state.readback_receipt.get("status") != "verified"
        or state.readback_receipt.get("file_sha256") != expected_sha256):
        raise ArchiveError("archive needs a saved v1 story and actual verified readback")
    result = RestoredSource(str(target), state.story_id, state.revision, expected_sha256,
                            state_api.state_fingerprint(state))
    after, content = _read(target)
    if str(after) != result.path or _hash(content) != expected_sha256:
        raise ArchiveError("archive changed during restore")
    return result, state


def restore_source(path: str | Path, *, expected_story_id: str, expected_revision: int,
                   expected_sha256: str) -> RestoredSource:
    """Read and verify the exact saved local story; never follow artifact URLs.

    Trusted local/cooperating writers only. The existing loader rereads after the
    bounded precheck; this is not hostile-process memory isolation or a file lock.
    """
    return _load(path, expected_story_id=expected_story_id, expected_revision=expected_revision,
                 expected_sha256=expected_sha256)[0]


def _fresh(source: ArchiveSource) -> tuple[ArchiveSource, state_api.StoryState]:
    if type(source) is RestoredJournalSource:
        current, state, _ = _load_journal(source.path, **source.expected_identity())
    elif type(source) is RestoredSource:
        current, state = _load(source.path, expected_story_id=source.story_id,
                              expected_revision=source.revision, expected_sha256=source.file_sha256)
    else:
        raise ArchiveError("restore an explicit local archive before continuation")
    if current.binding() != source.binding():
        raise ArchiveError("archive binding differs from its actual saved content")
    return current, state


def _plan(artifact: state_api.Artifact) -> ChapterPlan:
    """Reuse the checkpoint's explicit plan adapter, without coercion or synthesis."""
    raw = strict_json_object(artifact.text, max_bytes=MAX_ARCHIVE_BYTES)
    if set(raw) == {"chapter_plan"} and isinstance(raw["chapter_plan"], dict):
        raw = raw["chapter_plan"]
    if set(raw) - set(ChapterPlan.model_fields) or not isinstance(raw.get("scenes"), list) or not raw["scenes"]:
        raise ArchiveError("accepted current plan requires supported fields and explicit nonempty scenes")
    required = {"scene_no", "objective", "opposition", "choice", "cost", "state_change"}
    for scene in raw["scenes"]:
        if not isinstance(scene, dict) or not required <= set(scene) or set(scene) - set(SceneBeat.model_fields):
            raise ArchiveError("accepted current plan has unsupported or incomplete scene evidence")
        if any(not isinstance(scene[key], str) or not scene[key].strip() for key in required - {"scene_no"}):
            raise ArchiveError("accepted current plan has blank causal scene fields")
    plan = ChapterPlan.model_validate(raw, strict=True)
    numbers = [scene.scene_no for scene in plan.scenes]
    if any(number <= 0 for number in numbers) or len(numbers) != len(set(numbers)):
        raise ArchiveError("accepted current plan requires positive unique scene IDs")
    return plan


class ArchiveStyleProfile(StyleFingerprint):
    """Declared high-level style, never invented reference measurements."""

    source_count: int = 0
    raw_profile: dict[str, Any]

    def prompt_view(self) -> dict[str, Any]:
        return {"scope": "declared_style_card_in_current_accepted_plan_context",
                "measured_statistics": "not supplied by this adapter",
                "profile": deepcopy(self.raw_profile)}


def _models(state) -> tuple[StoryBible, list[Character], ArchiveStyleProfile]:
    raw = state.canon.get("story_bible")
    if raw is None or isinstance(raw, str):
        fields = {}  # Full free text stays in the authoritative preflight context.
    elif isinstance(raw, dict):
        fields = {key: deepcopy(value) for key, value in raw.items() if key in StoryBible.model_fields}
    else:
        raise ArchiveError("unsupported story Bible representation")
    fields.setdefault("title", state.title or "未命名小说")
    bible = StoryBible.model_validate(fields, strict=True)
    for key in ("world_rules", "locked_facts"):
        rows = list(getattr(bible, key))
        for value in state.canon.get(key, []):
            text = value if isinstance(value, str) else _json(value).decode("utf-8")
            if text not in rows:
                rows.append(text)
        setattr(bible, key, rows)
    characters = [Character.model_validate(
        {key: deepcopy(value) for key, value in row.items() if key in Character.model_fields}, strict=True
    ) for row in state.canon.get("characters", [])]
    return bible, characters, ArchiveStyleProfile(name="archive-declared-style", raw_profile=deepcopy(state.style_profile))


def _check_names(state: state_api.StoryState) -> None:
    names = []
    for card in state.canon.get("characters", []):
        name = card.get("name")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
            raise ArchiveError("characters require unique exact nonblank unpadded names; reconcile aliases first")
        names.append(name)


def _ids(values, name: str) -> list[str]:
    if not isinstance(values, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip() or value != value.strip() for value in values
    ) or len(set(values)) != len(values):
        raise ArchiveError(name + " must contain unique explicit nonblank chapter IDs")
    return list(values)


@dataclass(frozen=True)
class _Prepared:
    source: ArchiveSource
    history: dict[str, Any]
    plan: ChapterPlan
    bible: StoryBible
    characters: list[Character]
    style: ArchiveStyleProfile
    context: dict[str, Any]
    plan_source_fingerprint: str
    voice_history: list[dict[str, Any]]
    story_history: list[dict[str, Any]]


def _prepare(source: ArchiveSource, *, current_chapter_id: str,
             recall_chapter_ids=(), required_chapter_ids=(), expected_history_sha256: str | None = None,
             budget_bytes: int = 120000, reserve_bytes: int = 0, history_source_limit: int = 4) -> _Prepared:
    source, state = _fresh(source)
    if not state.accepted_chapters:
        raise ArchiveError("this continuation entry requires accepted history; use the existing first-chapter workflow")
    if type(current_chapter_id) is not str or current_chapter_id != state.progress.chapter_id:
        raise ArchiveError("target must match the actual current chapter")
    if state.progress.phase != "ready_to_draft" or state.progress.plan is None or state.progress.plan_acceptance is None:
        raise ArchiveError("writing requires the current explicitly accepted plan in ready_to_draft")
    if state.progress.chapter_acceptance is not None or state.progress.memory_acceptance is not None:
        raise ArchiveError("this new-draft entry cannot replace accepted chapter or memory")
    accepted = {row["chapter_id"]: state_api.AcceptedChapter.model_validate(row) for row in state.accepted_chapters}
    if current_chapter_id in accepted:
        raise ArchiveError("historical chapter rewriting requires a separate reconciliation")
    plan = _plan(state.progress.plan)
    _check_names(state)
    if type(source) is RestoredJournalSource:
        journal = source.journal
        history = journal_api.rebuild_journal_accepted_history(journal, **source.expected_identity(),
            expected_history_sha256=expected_history_sha256)
    else:
        history = state_api.rebuild_accepted_history(state, expected_story_id=source.story_id,
                                                    expected_history_sha256=expected_history_sha256)
    recall, required = _ids(recall_chapter_ids, "recall_chapter_ids"), _ids(required_chapter_ids, "required_chapter_ids")
    chosen = recall + [key for key in required if key not in recall]
    if any(key not in accepted for key in chosen):
        raise ArchiveError("Recall can select only actually accepted historical chapters")
    sources = [{"artifact": item.model_dump(mode="json"), "required": key in required,
                "priority": len(chosen) - index}
               for index, key in enumerate(chosen) for item in (accepted[key].plan, accepted[key].draft)]
    authority = {"archive_binding_sha256": _digest(source.binding()),
                 "accepted_history_sha256": history["accepted_history_sha256"],
                 "accepted_plan_source_fingerprint": state_api.source_fingerprint(state.progress.plan)}
    footer = "\nACCEPTED ARCHIVE IDENTITY DATA ONLY\n" + _json(authority).decode("utf-8")
    footer_bytes = len(footer.encode("utf-8"))
    positive_int(budget_bytes, name="budget_bytes")
    if type(reserve_bytes) is not int or reserve_bytes < 0:
        raise ArchiveError("reserve_bytes must be a nonnegative integer")
    preflight_options = {"reserve_bytes": reserve_bytes + footer_bytes,
        "expected_history_sha256": history["accepted_history_sha256"],
        "history_source_limit": history_source_limit, "include_current_draft": False}
    if type(source) is RestoredJournalSource:
        context = journal_api.preflight_journal_next_chapter_context(
            journal, sources, budget_bytes, **source.expected_identity(), **preflight_options)
    else:
        context = state_api.preflight_next_chapter_context(
            state, sources, budget_bytes, expected_story_id=source.story_id, **preflight_options)
    if context["blocked"]:
        raise ArchiveError("accepted context is blocked; required source/context must be reconciled before writing")
    context["context_text"] += footer
    context["used_bytes"] = len(context["context_text"].encode("utf-8"))
    context["reserve_bytes"] = reserve_bytes
    context["authority_binding_bytes"] = footer_bytes
    context["authority_binding"] = authority
    if context["used_bytes"] + reserve_bytes > budget_bytes:
        raise ArchiveError("required archive authority and context do not fit; no truncation")
    voices = [{"chapter_id": row["chapter_id"], "voice_dna": deepcopy(row["voice_dna"])}
              for row in history["accepted_chapters"]]
    plans = [{"chapter_id": row["chapter_id"], "story_dna": deepcopy(row["structure"]["story_dna"])}
             for row in history["accepted_chapters"] if row["structure"]["status"] == "parsed"]
    bible, characters, style = _models(state)
    source.assert_current()
    return _Prepared(source, history, plan, bible, characters, style, context,
                     state_api.source_fingerprint(state.progress.plan), voices, plans)


def prepare_accepted_context(source: ArchiveSource, **options: Any) -> dict[str, Any]:
    """Read-only preview. Full private context is returned only to the caller."""
    prepared = _prepare(source, **options)
    return {"source": prepared.source.binding(), "history": deepcopy(prepared.history),
            "plan_source_fingerprint": prepared.plan_source_fingerprint,
            "preflight": deepcopy(prepared.context), "author_acceptance": "unchanged"}


def _expected_inputs(prepared: _Prepared, target_chars: int) -> dict[str, Any]:
    return {"bible": _digest(prepared.bible.model_dump()),
            "characters": _digest([c.model_dump() for c in prepared.characters]),
            "style": _digest(prepared.style.model_dump()), "recent_summaries": _digest([]),
            "extra_context": _hash(prepared.context["context_text"].encode("utf-8")),
            "historical_voice_dna": _digest(prepared.voice_history),
            "historical_story_dna": _digest(prepared.story_history), "target_chars": target_chars}


@dataclass(frozen=True)
class AcceptedWritingResult:
    """A pending draft with observed execution evidence; never author acceptance."""

    result: ChapterResult
    _source: ArchiveSource = field(repr=False)
    _evidence_json: bytes = field(repr=False)
    _observed_evidence_sha256: str | None = field(default=None, init=False, repr=False)

    def assert_current(self) -> None:
        if self._observed_evidence_sha256 is None or _hash(self._evidence_json) != self._observed_evidence_sha256:
            raise ArchiveError("no unchanged observed writing evidence; a report is not execution")
        evidence = json.loads(self._evidence_json)
        parameters = dict(evidence["parameters"])
        target_chars = parameters.pop("target_chars")
        prepared = _prepare(self._source, **parameters)
        if evidence["source"] != prepared.source.binding() or evidence["authority"] != prepared.context["authority_binding"]:
            raise ArchiveError("candidate authority differs from freshly read source")
        # These properties validate the engine's sealed result before readback.
        _ = self.result.final_text, self.result.final_review
        if (_digest(self.result.final_report) != evidence["final_report_sha256"]
            or self.result.final_report["plan_sha256"] != _digest(prepared.plan.model_dump())
            or any(self.result.final_report["input_fingerprints"].get(key) != value
                   for key, value in _expected_inputs(prepared, target_chars).items())):
            raise ArchiveError("candidate report, plan or inputs changed after execution")

    @property
    def final_text(self) -> str:
        self.assert_current()
        return self.result.final_text

    def report(self) -> dict[str, Any]:
        self.assert_current()
        return json.loads(self._evidence_json)


def _run(source: ArchiveSource, *, writer_provider: OpenAICompatibleProvider,
         reviewer_provider: OpenAICompatibleProvider | None, output_policy: OutputPolicy,
         current_chapter_id: str, recall_chapter_ids=(), required_chapter_ids=(),
         expected_history_sha256: str | None = None, budget_bytes: int = 120000,
         reserve_bytes: int = 0, history_source_limit: int = 4, target_chars: int = 3500,
         review: bool = True, auto_repair: bool = False,
         reference_hashes: set[str] | None = None) -> AcceptedWritingResult:
    positive_int(target_chars, name="target_chars")
    if type(review) is not bool or type(auto_repair) is not bool:
        raise ArchiveError("review and auto_repair must be booleans")
    parameters = {"current_chapter_id": current_chapter_id,
                  "recall_chapter_ids": _ids(recall_chapter_ids, "recall_chapter_ids"),
                  "required_chapter_ids": _ids(required_chapter_ids, "required_chapter_ids"),
                  "expected_history_sha256": expected_history_sha256, "budget_bytes": budget_bytes,
                  "reserve_bytes": reserve_bytes, "history_source_limit": history_source_limit}
    prepared = _prepare(source, **parameters)
    if type(writer_provider) is not OpenAICompatibleProvider or writer_provider.request_budget is None:
        raise TypeError("accepted writing requires the owned budgeted transport")
    if review and (type(reviewer_provider) is not OpenAICompatibleProvider
                   or reviewer_provider.request_budget is not writer_provider.request_budget):
        raise TypeError("writer and reviewer must share the same owned request budget")
    writer = NovelEngine(writer_provider.guarded(prepared.source.assert_current), output_policy=output_policy)
    reviewer = NovelEngine(reviewer_provider.guarded(prepared.source.assert_current), output_policy=output_policy) if review else None
    before = writer_provider.request_budget.snapshot()
    result = writer.run_from_plan(bible=prepared.bible, plan=prepared.plan, characters=prepared.characters,
        style=prepared.style, target_chars=target_chars, review=review, auto_repair=auto_repair,
        extra_context=prepared.context["context_text"], reference_hashes=reference_hashes,
        historical_voice_dna=prepared.voice_history, historical_story_dna=prepared.story_history, reviewer=reviewer)
    prepared.source.assert_current()
    evidence = {"schema": "accepted-writing-candidate-v2", "source": prepared.source.binding(),
        "authority": prepared.context["authority_binding"], "parameters": {**parameters, "target_chars": target_chars},
        "final_report_sha256": _digest(result.final_report),
        "budget_before": before, "budget_after": writer_provider.request_budget.snapshot(),
        "source_guard": "actual_read_before_each_HTTP_attempt_and_after_each_response_body",
        "history_chapter_ids": prepared.history["history_chapter_ids"],
        "unparsed_historical_plans": [row["chapter_id"] for row in prepared.history["accepted_chapters"]
                                      if row["structure"]["status"] != "parsed"],
        "author_acceptance": "pending; source state unchanged",
        "external_originals": "not fetched; embedded accepted snapshots only",
        "scope": ("author-journal owned continuation; no transition or acceptance"
                  if type(source) is RestoredJournalSource else "unowned v1 local archive")}
    bound = AcceptedWritingResult(result, prepared.source, _json(evidence))
    object.__setattr__(bound, "_observed_evidence_sha256", _hash(bound._evidence_json))
    bound.assert_current()
    return bound
