"""One fixed, recoverable local commit for explicitly confirmed memory after-images.

Uses ProjectStore confinement, its stable native lock and licensed atomic writer.
No model, extraction, author authentication, legacy recovery or chapter write is
performed here. Cooperating readers recover or block; this is not a generic
filesystem transaction or hostile-process/remote-storage security boundary.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from ._vendor.boltons_atomic import sync_directory
from .models import Character, MemoryExtraction
from .storage_guard import project_lock, reject_links

INTENT_PATH = ".memory-commit-transaction.json"
LEGACY_INTENT_PATH = ".extraction-transaction.json"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_INTENT_BYTES = 64 * 1024 * 1024
SCHEMA = "memory-commit-transaction-v1"
RECEIPT_SCHEMA = "memory-commit-receipt-v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PROPOSAL = re.compile(r"memory-[0-9a-f]{64}\Z")


class MemoryCommitError(ValueError):
    """Refused or incomplete memory commit; existing evidence must be retained."""


def _json(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")
        return text
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise MemoryCommitError("memory commit contains unsupported JSON values") from None


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise MemoryCommitError("duplicate JSON keys are not supported")
        result[key] = value
    return result


def _constant(_value):
    raise MemoryCommitError("nonfinite JSON values are not supported")


def _loads(text: str):
    if not isinstance(text, str):
        raise MemoryCommitError("memory after-images must be explicit UTF-8 strings")
    try:
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            raise MemoryCommitError("memory file exceeds the supported byte allowance")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        _json(value)
        return value
    except MemoryCommitError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise MemoryCommitError("memory JSON is malformed or unsupported") from None


def _read(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes | None:
    reject_links(path)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > limit:
        raise MemoryCommitError("memory source is not a bounded regular file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise MemoryCommitError("memory source exceeds the supported byte allowance")
    return raw


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        raise MemoryCommitError("memory files must contain valid UTF-8") from None


def _digest(raw: bytes | None) -> str | None:
    return _hash(raw) if raw is not None else None


def _identity(store, project: str, chapter_id: str | None = None) -> Path:
    if not isinstance(project, str) or not project or project != store.slugify(project):
        raise MemoryCommitError("memory commit requires a canonical explicit project ID")
    if chapter_id is not None and (not isinstance(chapter_id, str) or not chapter_id
            or chapter_id != store.slugify(chapter_id)):
        raise MemoryCommitError("memory commit requires a canonical explicit chapter ID")
    return store.project_dir(project)


def _paths(chapter: str) -> set[str]:
    return {"memory/characters.json", "memory/story_state.json", "memory/extractions/" + chapter + ".json",
        "memory/chapter_summaries.jsonl", "memory/story_graph.json", "memory/voice_dna/" + chapter + ".json",
        "memory/longform_health.json", "memory/story_dna/" + chapter + ".json",
        "memory/chapter_analytics/" + chapter + ".json"}


def _input_paths(chapter: str) -> set[str]:
    return {"chapters/" + chapter + ".md", "memory/chapter_plans/" + _hash(chapter.encode("utf-8")) + ".json",
        "memory/story_bible.json", "memory/outline.json", "memory/hierarchical_outline.json",
        "styles/style_dna.json", "styles/style_profiles.json", "styles/reference_signature.json"}


def _hashes(values, *, keys: set[str] | None = None):
    if not isinstance(values, dict) or (keys is not None and set(values) != keys):
        raise MemoryCommitError("memory commit digest map has unexpected paths")
    if any(not isinstance(key, str) or (value is not None and
            (not isinstance(value, str) or not _DIGEST.fullmatch(value))) for key, value in values.items()):
        raise MemoryCommitError("memory commit requires actual SHA-256 values or explicit absence")


def _summaries(text: str) -> list[dict]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise MemoryCommitError("summary after-image exceeds the supported byte allowance")
    rows = [_loads(line) for line in text.splitlines() if line.strip()]
    ids = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("chapter_id"), str) or not row["chapter_id"].strip()
                or not isinstance(row.get("summary"), str) or not isinstance(row.get("chapter_title", ""), str)):
            raise MemoryCommitError("summary records must retain explicit chapter identity and text")
        ids.append(row["chapter_id"])
    if len(ids) != len(set(ids)):
        raise MemoryCommitError("summary chapter identities must be unique")
    return rows


def _validate_files(files: dict[str, str], chapter: str) -> None:
    if not isinstance(files, dict) or set(files) != _paths(chapter):
        raise MemoryCommitError("memory commit requires exactly its nine supported after-images")
    parsed = {path: _summaries(text) if path.endswith(".jsonl") else _loads(text) for path, text in files.items()}
    characters = parsed["memory/characters.json"]
    if not isinstance(characters, list) or any(not isinstance(row, dict) for row in characters):
        raise MemoryCommitError("character after-image must be an explicit card list")
    names = []
    for row in characters:
        Character.model_validate(row, strict=True)
        name = row.get("name")
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise MemoryCommitError("character names must be explicit and unpadded")
        names.append(name)
    if len(names) != len(set(names)):
        raise MemoryCommitError("ambiguous duplicate character names cannot be committed")
    state = parsed["memory/story_state.json"]
    if not isinstance(state, dict) or "journal_owner" in state or state.get("engine_version") in ("gpt-state-checks-v1", "gpt-author-journal-v1"):
        raise MemoryCommitError("legacy memory commit cannot overwrite a GPT state or owned journal")
    for key in ("facts", "timeline", "foreshadowing", "open_threads", "unapplied_updates"):
        if not isinstance(state.get(key), list):
            raise MemoryCommitError("story-state after-image has unsupported field shapes")
        kind = str if key in {"facts", "open_threads"} else dict
        if any(not isinstance(row, kind) for row in state[key]):
            raise MemoryCommitError("story-state after-image has unsupported entry shapes")
    extraction_raw = parsed["memory/extractions/" + chapter + ".json"]
    if not isinstance(extraction_raw, dict):
        raise MemoryCommitError("extraction after-image must be an object")
    extraction = MemoryExtraction.model_validate(extraction_raw, strict=True)
    if extraction.chapter_id != chapter or any(item.chapter_id not in {"", chapter} for item in [*extraction.timeline_events, *extraction.foreshadowing]):
        raise MemoryCommitError("extraction source chapter does not match the confirmed chapter")
    expected_summary = {"chapter_id": chapter, "chapter_title": extraction.chapter_title, "summary": extraction.summary}
    matching = [row for row in parsed["memory/chapter_summaries.jsonl"] if row["chapter_id"] == chapter]
    if matching != [expected_summary]:
        raise MemoryCommitError("extraction and current chapter summary do not agree")
    graph = parsed["memory/story_graph.json"]
    if not isinstance(graph, dict) or any(not isinstance(graph.get(key), list) or any(not isinstance(row, dict) for row in graph[key]) for key in ("nodes", "edges")):
        raise MemoryCommitError("story graph must retain nodes and edges lists")
    for directory, field in (("voice_dna", "voice_dna"), ("story_dna", "story_dna"), ("chapter_analytics", "analytics")):
        row = parsed["memory/" + directory + "/" + chapter + ".json"]
        if not isinstance(row, dict) or set(row) != {"chapter_id", field} or row["chapter_id"] != chapter or not isinstance(row[field], dict):
            raise MemoryCommitError("derived memory record does not bind the confirmed chapter")
    analytics = parsed["memory/chapter_analytics/" + chapter + ".json"]["analytics"]
    if analytics.get("chapter_id") != chapter:
        raise MemoryCommitError("analytics source chapter does not match the confirmed chapter")
    health = parsed["memory/longform_health.json"]
    if not isinstance(health, dict) or not isinstance(health.get("voice_dna"), dict) or health["voice_dna"] != parsed["memory/voice_dna/" + chapter + ".json"]["voice_dna"]:
        raise MemoryCommitError("health and current Voice DNA after-images do not agree")


def _validate_inputs(inputs, chapter_id):
    _hashes(inputs)
    required = {"chapters/" + chapter_id + ".md", "memory/chapter_plans/" + _hash(chapter_id.encode("utf-8")) + ".json"}
    if not set(inputs) <= _input_paths(chapter_id) or not required <= set(inputs) or any(inputs[key] is None for key in required):
        raise MemoryCommitError("memory commit needs its actual chapter and saved plan plus allowlisted inputs")


def _validate_confirmation(project, chapter_id, proposal_id, inputs, confirmation):
    keys = {"project", "chapter_id", "proposal_id", "source_text_sha256", "chapter_accepted", "memory_accepted", "confirmation_source"}
    if not isinstance(confirmation, dict) or set(confirmation) != keys:
        raise MemoryCommitError("memory commit needs the exact explicit author confirmation binding")
    if (confirmation["project"] != project or confirmation["chapter_id"] != chapter_id or confirmation["proposal_id"] != proposal_id
            or confirmation["source_text_sha256"] != inputs["chapters/" + chapter_id + ".md"]
            or confirmation["chapter_accepted"] is not True or confirmation["memory_accepted"] is not True
            or not isinstance(confirmation["confirmation_source"], str) or not confirmation["confirmation_source"].strip()):
        raise MemoryCommitError("author confirmation does not bind this exact proposal and source")


def _request(store, project, proposal_id, chapter_id, files, expected_before, inputs, confirmation):
    root = _identity(store, project, chapter_id)
    if not isinstance(proposal_id, str) or not _PROPOSAL.fullmatch(proposal_id):
        raise MemoryCommitError("proposal identity must be memory- followed by its SHA-256")
    _validate_files(files, chapter_id)
    _hashes(expected_before, keys=_paths(chapter_id))
    _validate_inputs(inputs, chapter_id)
    _validate_confirmation(project, chapter_id, proposal_id, inputs, confirmation)
    receipt = {"schema": RECEIPT_SCHEMA, "project": project, "project_root": str(root.resolve()),
        "chapter_id": chapter_id, "proposal_id": proposal_id, "before_sha256": deepcopy(expected_before),
        "after_sha256": {path: _hash(text.encode("utf-8")) for path, text in files.items()},
        "input_sha256": deepcopy(inputs), "confirmation": deepcopy(confirmation), "status": "committed"}
    receipt["commit_sha256"] = _hash(_json(receipt).encode("utf-8"))
    # Confinement and aliases are checked before any canonical publication.
    paths = [store._path(project, path) for path in [*files, *inputs, "memory/memory_commits/" + proposal_id + ".json"]]
    seen = set()
    for path in paths:
        raw = _read(path)
        if raw is not None:
            key = (path.stat().st_dev, path.stat().st_ino)
            if key in seen:
                raise MemoryCommitError("memory target/input hard-link aliases are not supported")
            seen.add(key)
    return receipt


def _internal(store, project, relative):
    return store._path(project, relative, internal=True)


def _no_legacy(store, project):
    if _read(_internal(store, project, LEGACY_INTENT_PATH)) is not None:
        raise MemoryCommitError("pending legacy extraction recovery must be resolved separately")
    if _read(_internal(store, project, ".style-commit-transaction.json")) is not None:
        raise MemoryCommitError("pending style recovery must be resolved before memory publication")
    if _read(_internal(store, project, ".settings-commit-transaction.json")) is not None:
        raise MemoryCommitError("pending settings recovery must be resolved before memory publication")


def _receipt_path(store, project, proposal_id):
    return store._path(project, "memory/memory_commits/" + proposal_id + ".json")


def _existing_receipt(store, project, expected):
    raw = _read(_receipt_path(store, project, expected["proposal_id"]))
    if raw is None:
        return False
    if _loads(_text(raw)) != expected:
        raise MemoryCommitError("existing append-only receipt differs from the proposed operation")
    return True


def _validate_old_images(rows):
    for row in rows:
        if row["before_content"] is None:
            continue
        relative, text = row["path"], row["before_content"]
        if relative.endswith(".jsonl"):
            _summaries(text)
            continue
        value = _loads(text)
        kind = list if relative == "memory/characters.json" else dict
        if not isinstance(value, kind):
            raise MemoryCommitError("existing memory target has an unsupported JSON shape")
        if relative == "memory/story_state.json" and ("journal_owner" in value or
                value.get("engine_version") in ("gpt-state-checks-v1", "gpt-author-journal-v1")):
            raise MemoryCommitError("legacy memory commit must not replace a GPT state or owned journal")


def _parse_intent(store, project, raw):
    if len(raw) > MAX_INTENT_BYTES:
        raise MemoryCommitError("memory commit intent exceeds the supported byte allowance")
    value = _loads(_text(raw))
    keys = {"schema", "project", "project_root", "chapter_id", "proposal_id", "inputs", "confirmation", "files", "receipt"}
    if not isinstance(value, dict) or set(value) != keys or value["schema"] != SCHEMA or value["project"] != project:
        raise MemoryCommitError("memory commit intent has invalid project identity or shape")
    rows = value["files"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != {"path", "before_sha256", "after_sha256", "before_content", "after_content"} for row in rows):
        raise MemoryCommitError("memory commit intent has invalid file records")
    if any(not isinstance(row["path"], str) for row in rows) or len({row["path"] for row in rows}) != len(rows):
        raise MemoryCommitError("memory commit intent repeats a target")
    files, before = {}, {}
    for row in rows:
        old, new = row["before_content"], row["after_content"]
        if old is not None and not isinstance(old, str) or not isinstance(new, str):
            raise MemoryCommitError("memory commit intent must retain complete old/new images")
        if row["before_sha256"] != (_hash(old.encode("utf-8")) if old is not None else None) or row["after_sha256"] != _hash(new.encode("utf-8")):
            raise MemoryCommitError("memory commit image differs from its bound digest")
        files[row["path"]], before[row["path"]] = new, row["before_sha256"]
    _validate_old_images(rows)
    expected = _request(store, project, value["proposal_id"], value["chapter_id"], files, before, value["inputs"], value["confirmation"])
    if value["receipt"] != expected or value["project_root"] != expected["project_root"]:
        raise MemoryCommitError("memory commit intent differs from its complete receipt binding")
    return value


def _check_inputs(store, project, inputs):
    for relative, expected in inputs.items():
        if _digest(_read(store._path(project, relative))) != expected:
            raise MemoryCommitError("memory input changed; preserve proposal and reconcile")


def _check_targets(store, project, rows, *, after_only=False):
    for row in rows:
        current = _digest(_read(store._path(project, row["path"])))
        accepted = {row["after_sha256"]} if after_only else {row["before_sha256"], row["after_sha256"]}
        if current not in accepted:
            raise MemoryCommitError("memory target changed independently; pending commit requires reconciliation")


def _sync(store, project, relatives):
    root = _identity(store, project)
    parents = {root}
    for relative in relatives:
        path = store._path(project, relative).parent
        while path.is_relative_to(root):
            parents.add(path)
            if path == root:
                break
            path = path.parent
    for path in sorted(parents, key=lambda p: (-len(p.parts), str(p))):
        if path.exists():
            reject_links(path)
            sync_directory(path)


def _cleanup(store, project, intent, receipt):
    _sync(store, project, [*receipt["after_sha256"], "memory/memory_commits/" + receipt["proposal_id"] + ".json"])
    intent.unlink()
    sync_directory(intent.parent)


def _recover_locked(store, project):
    intent_path = _internal(store, project, INTENT_PATH)
    raw = _read(intent_path, limit=MAX_INTENT_BYTES)
    if raw is None:
        return None
    _no_legacy(store, project)
    intent = _parse_intent(store, project, raw)
    expected = intent["receipt"]
    if _existing_receipt(store, project, expected):
        # Receipt is published last, after the entire batch was verified. A
        # cleanup retry must not overwrite newer author state with old images.
        _cleanup(store, project, intent_path, expected)
        return deepcopy(expected)
    _check_inputs(store, project, intent["inputs"])
    _check_targets(store, project, intent["files"])
    for row in intent["files"]:
        _check_inputs(store, project, intent["inputs"])
        _check_targets(store, project, intent["files"])
        path = store._path(project, row["path"])
        if _digest(_read(path)) != row["after_sha256"]:
            store._write(path, row["after_content"])
        if _digest(_read(path)) != row["after_sha256"]:
            raise MemoryCommitError("memory after-image did not read back; commit remains pending")
    _check_inputs(store, project, intent["inputs"])
    _check_targets(store, project, intent["files"], after_only=True)
    _sync(store, project, [row["path"] for row in intent["files"]])
    receipt_path = _receipt_path(store, project, expected["proposal_id"])
    store._write(receipt_path, _json(expected) + "\n", overwrite=False)
    if not _existing_receipt(store, project, expected):
        raise MemoryCommitError("memory commit receipt did not read back")
    _cleanup(store, project, intent_path, expected)
    return deepcopy(expected)


def recover_memory_commit(store, project: str):
    """Finish only one already-confirmed fixed batch, or refuse its conflict.

    May be called from ProjectStore's reentrant guard. Never performs legacy
    extraction recovery and never invokes a model or computes another delta.
    """
    _identity(store, project)
    with project_lock(_internal(store, project, ".store.lock")):
        return _recover_locked(store, project)


def read_memory_commit_receipt(store, project: str, proposal_id: str):
    """Read validated historical commit metadata without recovering or writing.

    A committed receipt is evidence of that historical publication, not a claim
    that current project files still equal its old after-images. It does not
    authenticate the author; ordinary local protocol integrity is assumed.
    """
    root = _identity(store, project)
    if not isinstance(proposal_id, str) or not _PROPOSAL.fullmatch(proposal_id):
        raise MemoryCommitError("invalid memory proposal identity")
    with project_lock(_internal(store, project, ".store.lock")):
        raw = _read(_receipt_path(store, project, proposal_id))
        if raw is None:
            return None
        value = _loads(_text(raw))
        keys = {"schema", "project", "project_root", "chapter_id", "proposal_id", "before_sha256",
                "after_sha256", "input_sha256", "confirmation", "status", "commit_sha256"}
        if (not isinstance(value, dict) or set(value) != keys or value["schema"] != RECEIPT_SCHEMA
                or value["project"] != project or value["project_root"] != str(root.resolve())
                or value["proposal_id"] != proposal_id or value["status"] != "committed"):
            raise MemoryCommitError("memory commit receipt identity or shape is invalid")
        chapter = value["chapter_id"]
        _identity(store, project, chapter)
        _hashes(value["before_sha256"], keys=_paths(chapter))
        _hashes(value["after_sha256"], keys=_paths(chapter))
        if any(item is None for item in value["after_sha256"].values()):
            raise MemoryCommitError("committed memory after-images must have exact digests")
        _validate_inputs(value["input_sha256"], chapter)
        _validate_confirmation(project, chapter, proposal_id, value["input_sha256"], value["confirmation"])
        expected = _hash(_json({key: item for key, item in value.items() if key != "commit_sha256"}).encode("utf-8"))
        if value["commit_sha256"] != expected:
            raise MemoryCommitError("memory commit receipt content differs from its identity")
        return deepcopy(value)


def inspect_memory_commit(store, project: str):
    """Read-only pending-commit metadata. Does not recover or consume an intent."""
    _identity(store, project)
    with project_lock(_internal(store, project, ".store.lock")):
        raw = _read(_internal(store, project, INTENT_PATH), limit=MAX_INTENT_BYTES)
        if raw is None:
            return None
        _no_legacy(store, project)
        value = _parse_intent(store, project, raw)
        return {"schema": SCHEMA, "status": "receipt_published_cleanup_pending" if _existing_receipt(store, project, value["receipt"]) else "pending",
                "project": project, "chapter_id": value["chapter_id"], "proposal_id": value["proposal_id"],
                "commit_sha256": value["receipt"]["commit_sha256"], "targets": [row["path"] for row in value["files"]]}


def commit_confirmed_memory(store, project: str, *, proposal_id: str, chapter_id: str,
                            files: dict[str, str], expected_before: dict[str, str | None],
                            inputs: dict[str, str | None], confirmation: dict) -> dict:
    """Publish the exact confirmed nine-file batch and immutable receipt.

    Refusal before intent publication changes no canonical file. Failure after
    publication may leave a partial/pending or fully committed operation; inspect
    and retry the same operation. An error is never a guarantee of rollback.
    """
    # Detach caller-owned mutable containers before any callbacks/writes.
    files, expected_before, inputs, confirmation = deepcopy((files, expected_before, inputs, confirmation))
    _identity(store, project, chapter_id)
    with project_lock(_internal(store, project, ".store.lock")):
        _no_legacy(store, project)
        expected = _request(store, project, proposal_id, chapter_id, files, expected_before, inputs, confirmation)
        intent_path = _internal(store, project, INTENT_PATH)
        existing_intent = _read(intent_path, limit=MAX_INTENT_BYTES)
        if existing_intent is not None:
            pending = _parse_intent(store, project, existing_intent)
            if pending["receipt"] != expected:
                raise MemoryCommitError("another memory commit is pending; do not replace its evidence")
            return _recover_locked(store, project)
        if _existing_receipt(store, project, expected):
            _sync(store, project, [*files, "memory/memory_commits/" + proposal_id + ".json"])
            return deepcopy(expected)
        _check_inputs(store, project, inputs)
        rows = []
        for relative in sorted(files):
            raw = _read(store._path(project, relative))
            if _digest(raw) != expected_before[relative]:
                raise MemoryCommitError("memory baseline changed before commit; no canonical writes performed")
            rows.append({"path": relative, "before_sha256": expected_before[relative], "after_sha256": expected["after_sha256"][relative],
                         "before_content": _text(raw) if raw is not None else None, "after_content": files[relative]})
        intent = {"schema": SCHEMA, "project": project, "project_root": expected["project_root"], "chapter_id": chapter_id,
                  "proposal_id": proposal_id, "inputs": inputs, "confirmation": confirmation, "files": rows, "receipt": expected}
        encoded = _json(intent) + "\n"
        if len(encoded.encode("utf-8")) > MAX_INTENT_BYTES:
            raise MemoryCommitError("memory commit intent exceeds its recoverable allowance; no canonical writes performed")
        _parse_intent(store, project, encoded.encode("utf-8"))
        _check_inputs(store, project, inputs)
        # Exact old images must still be current immediately before publication.
        for row in rows:
            if _digest(_read(store._path(project, row["path"]))) != row["before_sha256"]:
                raise MemoryCommitError("memory baseline changed before intent publication")
        store._write(intent_path, encoded, overwrite=False)
        if _read(intent_path, limit=MAX_INTENT_BYTES) != encoded.encode("utf-8"):
            raise MemoryCommitError("memory intent did not read back exactly; publication needs reconciliation")
        return _recover_locked(store, project)
