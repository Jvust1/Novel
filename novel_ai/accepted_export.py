"""Accepted-source adapter over the existing deterministic local review packager.

Manuscript bytes come only from admitted embedded accepted records. Metadata
and scores remain separately supplied review context, never a
publishing decision. No model, author transition or canonical write occurs.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import author_workflow, gpt_story_journal, gpt_story_state
from .accepted_writing import (
    ArchiveSource,
    RestoredJournalSource,
    RestoredSource,
    _fresh,
)
from .market_eval import STAGE_SIZES, MarketChapter, MarketCorpus, MarketScore, Stage
from .release_pack import MarketProfile, build_release_pack
from .storage import ProjectStore


class AcceptedExportError(ValueError):
    """The bound accepted source, selection or package no longer matches."""


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _data_digest(value: Any) -> str:
    return _digest(_json(value))


def _admit(source: ArchiveSource, chapter_ids: list[str], stage: Stage, profile: MarketProfile):
    if type(source) not in {RestoredSource, RestoredJournalSource}:
        raise AcceptedExportError("restore an explicit accepted archive or owned journal first")
    current, state = _fresh(source)
    ids = author_workflow._chapter_ids(chapter_ids)
    if type(stage) is not str or stage not in STAGE_SIZES or len(ids) != STAGE_SIZES[stage]:
        raise AcceptedExportError("select exactly 3 or 20 accepted chapter IDs for the existing review stage")
    if type(profile) is not MarketProfile:
        raise TypeError("an explicit MarketProfile is required")
    checked_profile = MarketProfile.model_validate(profile.model_dump(), strict=True)
    records = {row['chapter_id']: (index, gpt_story_state.AcceptedChapter.model_validate(row))
               for index, row in enumerate(state.accepted_chapters, start=1)}
    if any(chapter_id not in records for chapter_id in ids):
        raise AcceptedExportError("selection contains a missing, pending, future or other-story chapter")
    if type(current) is RestoredJournalSource:
        history = gpt_story_journal.rebuild_journal_accepted_history(
            current.journal, **current.expected_identity())
    else:
        history = gpt_story_state.rebuild_accepted_history(state, expected_story_id=current.story_id)
    chapters = [MarketChapter(number=number, title=chapter_id, text=records[chapter_id][1].draft.text)
                for number, chapter_id in enumerate(ids, start=1)]
    corpus = MarketCorpus(project=current.story_id, stage=stage, chapters=chapters,
                           audience=checked_profile.audience, genre=checked_profile.genre).validate_stage()
    entries = []
    for number, chapter_id in enumerate(ids, start=1):
        ordinal, record = records[chapter_id]
        raw = corpus.chapters[number - 1].text.encode("utf-8")
        if raw != record.draft.text.encode("utf-8") or _digest(raw) != record.draft.source.sha256:
            raise AcceptedExportError("accepted manuscript bytes changed during corpus adaptation")
        entries.append({
            "number": number, "chapter_id": chapter_id, "accepted_history_ordinal": ordinal,
            "base_story_revision": record.base_story_revision,
            "resulting_story_revision": record.resulting_story_revision,
            "plan_revision": record.plan_revision, "draft_revision": record.draft_revision,
            "text_sha256": record.draft.source.sha256,
            "text_bytes": len(raw),
            "plan_source_fingerprint": gpt_story_state.source_fingerprint(record.plan),
            "draft_source_fingerprint": gpt_story_state.source_fingerprint(record.draft),
            "acceptance_records_sha256": _data_digest({key: getattr(record, key).model_dump(mode="json")
                for key in ("plan_acceptance", "chapter_acceptance", "memory_acceptance")}),
            "memory_update_id": record.memory_update_id,
        })
    authority = {
        "schema": "accepted-review-source-v1", "story_id": current.story_id,
        "stage": stage,
        "story_revision": current.revision,
        "source_kind": "author_journal" if type(current) is RestoredJournalSource else "v1_story",
        "source_file_sha256": current.file_sha256,
        "source_state_sha256": current.state_sha256,
        "accepted_history_sha256": history["accepted_history_sha256"],
        "accepted_chapter_count": len(state.accepted_chapters),
        "selection_order": "explicit_author_declared_not_inferred_narrative_order",
        "chapters": entries,
        "scope": "embedded accepted manuscripts only; no external-original freshness or human authentication",
        "non_manuscript_metadata": "supplied separately; author acceptance is not market review or publication approval",
    }
    if type(current) is RestoredJournalSource:
        authority["journal_sha256"] = current.journal_sha256
        authority["context_revision"] = current.context_revision
    current.assert_current()
    return current, corpus, checked_profile, authority


def preview_accepted_corpus(source: ArchiveSource, *, chapter_ids: list[str], stage: Stage,
                            profile: MarketProfile) -> MarketCorpus:
    """Detached review preview; a mutable corpus is not an export capability."""
    return _admit(source, chapter_ids, stage, profile)[1]


def _profile(value: dict[str, Any]) -> MarketProfile:
    if type(value) is not dict or set(value) - set(MarketProfile.model_fields):
        raise AcceptedExportError("release profile contains unsupported fields")
    return MarketProfile.model_validate(value, strict=True)


def _add_authority(bundle: bytes, authority: dict[str, Any], texts: list[bytes], *,
                   has_scores: bool) -> bytes:
    """Keep the existing ZIP contents/metadata and add bound acceptance evidence."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as original, zipfile.ZipFile(output, "w") as target:
        manifest = json.loads(original.read("manifest.json"))
        paths = [f"chapters/{row['number']:03d}.md" for row in authority["chapters"]]
        expected_members = {"manifest.json", "release_pack.json", "market_scoring.csv", "README.txt", *paths}
        if has_scores:
            expected_members.update({"human_scores.json", "human_review_summary.json"})
        if len(original.namelist()) != len(expected_members) or set(original.namelist()) != expected_members:
            raise AcceptedExportError("review package has duplicate, missing or unexpected members")
        expected = [(row["number"], row["chapter_id"], row["text_sha256"]) for row in authority["chapters"]]
        actual = [(row["number"], row["chapter_id"], row["text_sha256"]) for row in manifest["chapters"]]
        if (manifest["project"] != authority["story_id"] or actual != expected
            or manifest["stage"] != authority["stage"] or manifest["kind"] != "local_review_candidate"
            or manifest["publishability_verdict"] is not None
            or manifest["human_review_status"] != ("human_review_recorded" if has_scores else "awaiting_human_review")):
            raise AcceptedExportError("review packager changed accepted chapter membership, order or text")
        for index, row in enumerate(manifest["chapters"]):
            if row["path"] != paths[index] or original.read(paths[index]) != texts[index]:
                raise AcceptedExportError("review package manuscript bytes differ from the accepted source")
        authority_bytes = author_workflow._json_bytes(authority)
        manifest["accepted_source_manifest"] = "accepted_source.json"
        manifest["accepted_source_sha256"] = _digest(authority_bytes)
        manifest["manuscript_source"] = "bound_embedded_author_accepted_versions"
        for info in original.infolist():
            data = author_workflow._json_bytes(manifest) if info.filename == "manifest.json" else original.read(info.filename)
            target.writestr(info, data)
        info = zipfile.ZipInfo("accepted_source.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o100600 << 16
        target.writestr(info, authority_bytes)
    return output.getvalue()


def _build(source: ArchiveSource, spec: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    current, corpus, profile, authority = _admit(source, spec["chapter_ids"], spec["stage"], _profile(spec["profile"]))
    pack = build_release_pack(corpus, profile, **spec["copy"])
    scores = None if spec["scores"] is None else [MarketScore.model_validate(row, strict=True) for row in spec["scores"]]
    bundle = author_workflow.release_bundle_bytes(corpus, pack, chapter_ids=spec["chapter_ids"],
                                                  scores=scores)
    bundle = _add_authority(bundle, authority, [row.text.encode("utf-8") for row in corpus.chapters],
                            has_scores=scores is not None)
    current.assert_current()
    return bundle, authority


@dataclass(frozen=True)
class AcceptedReviewBundle:
    """An observed, source-bound review package, never publication approval.

    Serialized metadata cannot recreate this live observation. Historical saved
    bytes remain historical evidence, not authority to bypass current checks.
    """

    _source: ArchiveSource = field(repr=False)
    _spec_json: bytes = field(repr=False)
    _bundle_bytes: bytes = field(repr=False)
    _observed_digest: str | None = field(default=None, init=False, repr=False)

    def _identity(self) -> str:
        return _data_digest({"source": self._source.binding(), "spec_sha256": _digest(self._spec_json),
                             "bundle_sha256": _digest(self._bundle_bytes)})

    def assert_current(self) -> None:
        if self._observed_digest is None or self._identity() != self._observed_digest:
            raise AcceptedExportError("no unchanged observed accepted export; a report is not an approval")
        expected, _ = _build(self._source, json.loads(self._spec_json))
        if expected != self._bundle_bytes:
            raise AcceptedExportError("package differs from the actual accepted source and selection")

    @property
    def bundle_bytes(self) -> bytes:
        self.assert_current()
        return self._bundle_bytes

    def report(self) -> dict[str, Any]:
        self.assert_current()
        with zipfile.ZipFile(io.BytesIO(self._bundle_bytes)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            authority = json.loads(archive.read("accepted_source.json"))
        return {"bundle_sha256": _digest(self._bundle_bytes), "bundle_bytes": len(self._bundle_bytes),
                "source": authority, "stage": manifest["stage"],
                "human_review_status": manifest["human_review_status"],
                "publishability_verdict": manifest["publishability_verdict"]}


def build_accepted_review_bundle(source: ArchiveSource, *, chapter_ids: list[str], stage: Stage,
                                 profile: MarketProfile, title: str, one_line_hook: str,
                                 short_blurb: str, long_blurb: str = "", tags=(),
                                 content_warnings=(), manual_checks=(),
                                 scores: list[MarketScore] | None = None) -> AcceptedReviewBundle:
    """Build a pending review ZIP from accepted manuscripts, preserving raw UTF-8."""
    if type(profile) is not MarketProfile:
        raise TypeError("an explicit MarketProfile is required")
    for values in (tags, content_warnings, manual_checks):
        if type(values) not in {list, tuple} or any(type(value) is not str for value in values):
            raise AcceptedExportError("metadata lists must preserve explicit text order")
    if scores is not None and (type(scores) is not list or any(type(row) is not MarketScore for row in scores)):
        raise TypeError("scores must be explicitly supplied MarketScore records")
    spec = {"chapter_ids": author_workflow._chapter_ids(chapter_ids), "stage": stage,
            "profile": profile.model_dump(),
            "copy": {"title": title, "one_line_hook": one_line_hook, "short_blurb": short_blurb,
                     "long_blurb": long_blurb, "tags": list(tags), "content_warnings": list(content_warnings),
                     "manual_checks": list(manual_checks)},
            "scores": None if scores is None else [row.model_dump() for row in scores]}
    encoded = _json(spec)  # Detach and reject non-JSON/nonfinite values before packaging.
    bundle, _ = _build(source, json.loads(encoded))
    result = AcceptedReviewBundle(source, encoded, bundle)
    object.__setattr__(result, "_observed_digest", result._identity())
    result.assert_current()
    return result


def save_accepted_review_bundle(store: ProjectStore, project: str, bundle: AcceptedReviewBundle) -> Path:
    """Save via the existing no-clobber publisher, checking every reuse boundary.

    A source change or late I/O error can leave a complete historical artifact;
    no partial file or rollback/directory-fsync guarantee is claimed here.
    """
    if type(bundle) is not AcceptedReviewBundle:
        raise TypeError("build an observed accepted review bundle first")
    if type(project) is not str or project != bundle._source.story_id:
        raise AcceptedExportError("export target belongs to a different story")
    if store.slugify(project) != project:
        raise AcceptedExportError("export storage name must match the story ID without normalization")
    bundle.assert_current()
    return author_workflow.save_release_bundle(store, project, bundle._bundle_bytes,
                                               source_guard=bundle.assert_current)
