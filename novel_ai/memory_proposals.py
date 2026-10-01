"""Version-bound memory candidates; calculation never accepts or writes Canon.

Only explicit caller author decisions may enter the fixed confirmed commit.
These checks bind local content and phases, not a human's identity. The GPT
dialogue protocol still owns actual author intent and private-source access.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from ._vendor.transitions import Machine
from .longform_analytics import chapter_analytics
from .longform_consistency import build_longform_health
from .longform_tools import build_story_graph
from .memory import apply_extraction
from .models import Character, ChapterPlan, MemoryExtraction, StoryBible
from .output_policy import strict_json_object
from .storage import ProjectStore, StorageIntegrityError
from .storage_guard import project_lock, reject_links
from .story_dna import story_dna_from_plan

MAX_BYTES = 64 * 1024 * 1024
PENDING_INTENTS = (".extraction-transaction.json", ".memory-commit-transaction.json", ".style-commit-transaction.json")
CONFIG_PATHS = (
    "memory/story_bible.json", "memory/outline.json", "memory/hierarchical_outline.json",
    "styles/style_dna.json", "styles/style_profiles.json", "styles/reference_signature.json",
)


def _json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("memory proposal exceeds its supported byte allowance")
    return text


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _id(value: str, name: str, store: ProjectStore) -> str:
    if not isinstance(value, str) or not value or store.slugify(value) != value:
        raise ValueError(f"{name} requires a canonical stable identifier")
    return value


def _read(path: Path) -> str | None:
    reject_links(path)
    if not path.exists():
        return None
    with path.open("rb") as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("memory source exceeds its supported byte allowance")
    return raw.decode("utf-8")


def _decode(text: str, *, object_only: bool = False) -> Any:
    # Reuse the strict object parser for every nested value while preserving
    # array roots for characters and rejecting duplicate keys/nonfinite values.
    if object_only:
        return strict_json_object(text, max_bytes=MAX_BYTES)
    return strict_json_object('{"value":' + text + '}', max_bytes=MAX_BYTES)["value"]


def _no_pending(store: ProjectStore, project: str) -> None:
    for name in PENDING_INTENTS:
        if store._path(project, name, internal=True).exists():
            raise StorageIntegrityError("a pending memory transaction must be recovered or reconciled first")


def _targets(chapter_id: str) -> tuple[str, ...]:
    return (
        "memory/characters.json", "memory/story_state.json",
        f"memory/extractions/{chapter_id}.json", "memory/chapter_summaries.jsonl",
        "memory/story_graph.json", f"memory/voice_dna/{chapter_id}.json",
        "memory/longform_health.json", f"memory/story_dna/{chapter_id}.json",
        f"memory/chapter_analytics/{chapter_id}.json",
    )


def _input_paths(chapter_id: str) -> tuple[str, ...]:
    return (f"chapters/{chapter_id}.md", f"memory/chapter_plans/{_sha(chapter_id)}.json", *CONFIG_PATHS)


def _raw_files(store: ProjectStore, project: str, paths: tuple[str, ...]) -> dict[str, str | None]:
    result = {p: _read(store._path(project, p)) for p in paths}
    _json(result)  # Also bound the combined snapshot before model dispatch.
    return result


def _hashes(files: dict[str, str | None]) -> dict[str, str | None]:
    return {p: _sha(v) if v is not None else None for p, v in files.items()}


def author_context(*, bible: dict[str, Any], characters: list[dict[str, Any]],
                   extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Detach the complete caller context, including unsaved author additions."""
    value = _decode(_json({"bible": bible, "characters": characters, "extra": extra or {}}), object_only=True)
    if not isinstance(value["bible"], dict) or not isinstance(value["characters"], list):
        raise ValueError("author context requires a Bible object and character list")
    StoryBible.model_validate(value["bible"], strict=True)
    names = []
    for row in value["characters"]:
        if not isinstance(row, dict):
            raise ValueError("character card must be an object")
        c = Character.model_validate(row, strict=True)
        if not c.name or c.name != c.name.strip() or c.name in names:
            raise ValueError("character names must be unique nonblank canonical names")
        names.append(c.name)
    return value


@dataclass(frozen=True)
class MemorySource:
    _serialized: str

    def to_dict(self) -> dict[str, Any]:
        return _decode(self._serialized, object_only=True)


@dataclass(frozen=True)
class MemoryProposal:
    _serialized: str

    def to_dict(self) -> dict[str, Any]:
        return _decode(self._serialized, object_only=True)

    @property
    def proposal_id(self) -> str:
        return self.to_dict()["proposal_id"]

    def preview(self) -> dict[str, Any]:
        data = _validate_proposal(self)
        return {"proposal_id": data["proposal_id"], "project": data["source"]["project"],
                "chapter_id": data["source"]["chapter_id"], "phase": "awaiting_author_confirmation",
                "source_text_sha256": data["source"]["source_text_sha256"],
                "extraction": deepcopy(data["extraction"]),
                "proposed_characters": _decode(data["files"]["memory/characters.json"]),
                "proposed_story_state": _decode(data["files"]["memory/story_state.json"]),
                "affected_files": list(data["files"]),
                "history_coverage": "unbound legacy Voice/Story DNA histories omitted"}


def _validate_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("story state must be an object")
    if "journal_owner" in value or value.get("engine_version") in {"gpt-state-checks-v1", "gpt-author-journal-v1"}:
        raise ValueError("use the GPT story/journal protocol for its owned state")
    state = deepcopy(value)
    for key in ("facts", "timeline", "foreshadowing", "open_threads", "unapplied_updates"):
        rows = state.get(key, [])
        if not isinstance(rows, list):
            raise ValueError("story state collections must be lists")
        wanted = str if key in {"facts", "open_threads"} else dict
        if any(not isinstance(row, wanted) for row in rows):
            raise ValueError("story state collection contains unsupported records")
    for row in state.get("foreshadowing", []):
        for key in ("history", "lifecycle_warnings"):
            if key in row and (not isinstance(row[key], list) or any(not isinstance(r, dict) for r in row[key])):
                raise ValueError("foreshadowing audit collections must be object lists")
    return state


def _summaries(text: str | None, chapter_id: str) -> list[dict[str, Any]]:
    result = []
    ids = set()
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        row = _decode(line, object_only=True)
        cid = row.get("chapter_id")
        if not isinstance(cid, str) or not cid or cid in ids:
            raise ValueError("existing chapter summary identities must be unique")
        if cid == chapter_id:
            raise ValueError("an already applied chapter requires explicit historical reconciliation")
        ids.add(cid)
        result.append(row)
    return result


def _validate_source(data: dict[str, Any]) -> None:
    expected = {"schema", "project_root", "project", "chapter_id", "source_text_sha256", "plan",
                "inputs", "before", "author_context"}
    if set(data) != expected or data["schema"] != "novel-memory-source-v1":
        raise ValueError("unsupported memory source")
    cid = data["chapter_id"]
    if set(data["inputs"]) != set(_input_paths(cid)) or set(data["before"]) != set(_targets(cid)):
        raise ValueError("memory source paths differ")
    text = data["inputs"][f"chapters/{cid}.md"]
    if not isinstance(text, str) or not text.strip() or _sha(text) != data["source_text_sha256"]:
        raise ValueError("chapter source is missing or changed")
    record = _decode(data["inputs"][f"memory/chapter_plans/{_sha(cid)}.json"], object_only=True)
    if (set(record) != {"version", "project", "chapter_id", "text_sha256", "plan"}
            or record["version"] != "1" or record["project"] != data["project"]
            or record["chapter_id"] != cid or record["text_sha256"] != _sha(text)
            or record["plan"] != data["plan"]):
        raise ValueError("saved plan does not bind this exact chapter")
    if ChapterPlan.model_validate(data["plan"]).model_dump() != data["plan"]:
        raise ValueError("saved plan contains unsupported or noncanonical fields")
    context = data["author_context"]
    if author_context(bible=context["bible"], characters=context["characters"], extra=context["extra"]) != context:
        raise ValueError("author context differs")
    before = data["before"]
    saved_cards = _decode(before["memory/characters.json"] or "[]")
    if saved_cards != context["characters"]:
        raise ValueError("author cards differ from saved Canon; save or reload the intended author version first")
    saved_bible = data["inputs"]["memory/story_bible.json"]
    if saved_bible is not None:
        saved_native = StoryBible.model_validate(_decode(saved_bible, object_only=True), strict=True).model_dump()
        if saved_native != StoryBible.model_validate(context["bible"], strict=True).model_dump():
            raise ValueError("author Bible differs from saved Canon; save or reload the intended author version first")
    _validate_state(_decode(before["memory/story_state.json"] or "{}", object_only=True))
    _summaries(before["memory/chapter_summaries.jsonl"], cid)
    if before[f"memory/extractions/{cid}.json"] is not None:
        raise ValueError("existing extraction requires historical reconciliation")
    # Even currently unused before-images must be valid UTF-8 strings or absent.
    if any(v is not None and not isinstance(v, str) for v in (*data["inputs"].values(), *before.values())):
        raise ValueError("memory snapshot contains unsupported bytes")
    for path, text in before.items():
        if text is None or path.endswith(".jsonl"):
            continue
        value = _decode(text)
        expected_type = list if path == "memory/characters.json" else dict
        if not isinstance(value, expected_type):
            raise ValueError("existing memory target has unsupported JSON shape")
    _json(data)


def capture_memory_source(store: ProjectStore, project: str, chapter_id: str, *,
                          final_text: str, plan: ChapterPlan, context: dict[str, Any]) -> MemorySource:
    """Read exact disk sources before a model call, without invoking recovery."""
    _id(project, "project", store); _id(chapter_id, "chapter", store)
    if not isinstance(final_text, str) or not final_text.strip():
        raise ValueError("memory needs a complete saved chapter")
    context = author_context(bible=context["bible"], characters=context["characters"], extra=context["extra"])
    with project_lock(store._path(project, ".store.lock", internal=True)):
        _no_pending(store, project)
        inputs = _raw_files(store, project, _input_paths(chapter_id))
        if inputs[f"chapters/{chapter_id}.md"] != final_text.strip() + "\n":
            raise ValueError("saved chapter differs from the displayed candidate")
        data = {"schema": "novel-memory-source-v1", "project_root": str(store.project_dir(project).resolve()),
                "project": project, "chapter_id": chapter_id,
                "source_text_sha256": _sha(inputs[f"chapters/{chapter_id}.md"]),
                "plan": plan.model_dump(), "inputs": inputs,
                "before": _raw_files(store, project, _targets(chapter_id)), "author_context": context}
        _validate_source(data)
        return MemorySource(_json(data))


def assert_memory_source_current(store: ProjectStore, source: MemorySource, *, context: dict[str, Any]) -> None:
    data = source.to_dict(); _validate_source(data)
    project = _id(data["project"], "project", store); _id(data["chapter_id"], "chapter", store)
    with project_lock(store._path(project, ".store.lock", internal=True)):
        _no_pending(store, project)
        if str(store.project_dir(project).resolve()) != data["project_root"]:
            raise ValueError("memory source belongs to another project location")
        if _json(context) != _json(data["author_context"]):
            raise ValueError("author context changed; regenerate or reconcile the memory candidate")
        for key in ("inputs", "before"):
            actual = _raw_files(store, project, tuple(data[key]))
            if actual != data[key]:
                raise ValueError("memory source or destination changed; old approval cannot be reused")


def _project(source: dict[str, Any], extraction: MemoryExtraction) -> dict[str, str]:
    _validate_source(source)
    extraction = MemoryExtraction.model_validate(extraction.model_dump())
    if not extraction.summary.strip():
        raise ValueError("memory summary must not be blank")
    cid = source["chapter_id"]
    if extraction.chapter_id != cid:
        raise ValueError("memory extraction belongs to another chapter")
    if any(row.chapter_id not in {"", cid} for row in (*extraction.timeline_events, *extraction.foreshadowing)):
        raise ValueError("memory event belongs to another chapter")
    raw_chars = source["author_context"]["characters"]
    native = [Character.model_validate(c) for c in raw_chars]
    old_state = _validate_state(_decode(source["before"]["memory/story_state.json"] or "{}", object_only=True))
    chars, state = apply_extraction(native, old_state, extraction)
    # Overlay only changed native fields onto raw author cards. Preserve every
    # extension/alias/custom voice field and unchanged compact representation.
    merged = deepcopy(raw_chars)
    for index, (old, new) in enumerate(zip(native, chars, strict=True)):
        old_data, new_data = old.model_dump(), new.model_dump()
        for key, value in new_data.items():
            if old_data[key] != value:
                merged[index][key] = deepcopy(value)
    summaries = _summaries(source["before"]["memory/chapter_summaries.jsonl"], cid)
    summaries.append({"chapter_id": cid, "chapter_title": extraction.chapter_title, "summary": extraction.summary})
    dna = story_dna_from_plan(ChapterPlan.model_validate(source["plan"])).to_dict()
    text = source["inputs"][f"chapters/{cid}.md"]
    health = build_longform_health(current_text=text, character_names=[c.name for c in chars],
        voice_history=[], current_story_dna=dna, story_dna_history=[], story_state=state,
        chapter_order=[row["chapter_id"] for row in summaries])
    health["history_coverage"] = "unbound legacy Voice/Story DNA histories omitted; not whole-book clearance"
    health["source_text_sha256"] = source["source_text_sha256"]
    health["guard_context"] = "【局部检查；未验证历史口吻与结构缓存，不能视为整书通过】\n" + health["guard_context"]
    values = {
        "memory/characters.json": merged, "memory/story_state.json": state,
        f"memory/extractions/{cid}.json": extraction.model_dump(),
        "memory/story_graph.json": build_story_graph(merged, state),
        f"memory/voice_dna/{cid}.json": {"chapter_id": cid, "voice_dna": health["voice_dna"]},
        "memory/longform_health.json": health,
        f"memory/story_dna/{cid}.json": {"chapter_id": cid, "story_dna": dna},
        f"memory/chapter_analytics/{cid}.json": {"chapter_id": cid, "analytics": chapter_analytics(cid, text, dna).to_dict()},
    }
    files = {path: _json(value) for path, value in values.items()}
    files["memory/chapter_summaries.jsonl"] = "".join(_json(row) + "\n" for row in summaries)
    return files


def make_memory_proposal(source: MemorySource, extraction: MemoryExtraction) -> MemoryProposal:
    """Build a pending candidate; caller-supplied output is not author consent."""
    data = source.to_dict()
    body = {"schema": "novel-memory-proposal-v1", "source": data,
            "extraction": extraction.model_dump(), "files": _project(data, extraction)}
    body["proposal_id"] = "memory-" + _sha(_json(body))
    return MemoryProposal(_json(body))


def _validate_proposal(proposal: MemoryProposal) -> dict[str, Any]:
    if type(proposal) is not MemoryProposal:
        raise TypeError("MemoryProposal required")
    data = proposal.to_dict()
    if set(data) != {"schema", "source", "extraction", "files", "proposal_id"} or data["schema"] != "novel-memory-proposal-v1":
        raise ValueError("unsupported memory proposal")
    body = {k: v for k, v in data.items() if k != "proposal_id"}
    if data["proposal_id"] != "memory-" + _sha(_json(body)):
        raise ValueError("memory proposal identity changed")
    if _project(data["source"], MemoryExtraction.model_validate(data["extraction"])) != data["files"]:
        raise ValueError("memory after-images do not match the proposed extraction")
    return data


def extract_memory_proposal(store: ProjectStore, source: MemorySource, engine: Any,
                            *, context: dict[str, Any], current_context: Any | None = None) -> MemoryProposal:
    """Actual extraction, then source recheck; no canonical or proposal writes."""
    if current_context is not None and not callable(current_context):
        raise TypeError("current_context must be a live reader callback")
    latest = lambda: current_context() if current_context is not None else context
    assert_memory_source_current(store, source, context=latest())
    data = source.to_dict()
    ctx = data["author_context"]
    result = engine.extract_memory(StoryBible.model_validate(ctx["bible"]),
        [Character.model_validate(c) for c in ctx["characters"]], data["chapter_id"],
        data["inputs"][f"chapters/{data['chapter_id']}.md"])
    assert_memory_source_current(store, source, context=latest())
    return make_memory_proposal(source, result)


def save_memory_proposal(store: ProjectStore, proposal: MemoryProposal, *, context: dict[str, Any]) -> Path:
    data = _validate_proposal(proposal); project = data["source"]["project"]
    with project_lock(store._path(project, ".store.lock", internal=True)):
        assert_memory_source_current(store, MemorySource(_json(data["source"])), context=context)
        path = store._path(project, f"memory/proposals/{data['source']['chapter_id']}/{data['proposal_id']}.json")
        if path.exists():
            if _read(path) != proposal._serialized:
                raise ValueError("different proposal already occupies this identity")
            return path
        store._write(path, proposal._serialized, overwrite=False)
        if _read(path) != proposal._serialized:
            raise StorageIntegrityError("proposal publication requires readback reconciliation")
        return path


def load_memory_proposal(store: ProjectStore, project: str, proposal_id: str, *, chapter_id: str | None = None) -> MemoryProposal:
    if not re.fullmatch(r"memory-[0-9a-f]{64}", proposal_id):
        raise ValueError("invalid memory proposal identity")
    _id(project, "project", store)
    with project_lock(store._path(project, ".store.lock", internal=True)):
        if chapter_id is None:
            matches = list(store._path(project, "memory/proposals").glob(f"*/{proposal_id}.json"))
            if len(matches) != 1:
                raise ValueError("memory proposal is missing or has multiple locations")
            chapter_id = matches[0].parent.name
        _id(chapter_id, "chapter", store)
        text = _read(store._path(project, f"memory/proposals/{chapter_id}/{proposal_id}.json"))
        if text is None:
            raise ValueError("memory proposal is unavailable")
        proposal = MemoryProposal(text); data = _validate_proposal(proposal)
        if (data["proposal_id"] != proposal_id or data["source"]["project"] != project or data["source"]["chapter_id"] != chapter_id
                or data["source"]["project_root"] != str(store.project_dir(project).resolve())):
            raise ValueError("memory proposal belongs to another source")
        return proposal


def list_memory_proposals(store: ProjectStore, project: str, chapter_id: str) -> list[str]:
    _id(project, "project", store); _id(chapter_id, "chapter", store)
    directory = store._path(project, f"memory/proposals/{chapter_id}")
    with project_lock(store._path(project, ".store.lock", internal=True)):
        ids = []
        for path in sorted(directory.glob("memory-*.json")):
            proposal = load_memory_proposal(store, project, path.stem, chapter_id=chapter_id)
            if proposal.to_dict()["source"]["chapter_id"] == chapter_id:
                ids.append(path.stem)
        return ids


def memory_proposal_receipt(store: ProjectStore, proposal: MemoryProposal) -> dict[str, Any] | None:
    """Read historical success only when its operation matches this candidate."""
    from .memory_commit import read_memory_commit_receipt
    data = _validate_proposal(proposal); source = data["source"]
    receipt = read_memory_commit_receipt(store, source["project"], data["proposal_id"])
    if receipt is None:
        return None
    expected = {"project": source["project"], "project_root": source["project_root"],
                "chapter_id": source["chapter_id"], "proposal_id": data["proposal_id"],
                "before_sha256": _hashes(source["before"]), "after_sha256": _hashes(data["files"]),
                "input_sha256": _hashes(source["inputs"])}
    if any(receipt[key] != value for key, value in expected.items()):
        raise ValueError("historical receipt differs from this exact memory proposal operation")
    return receipt


def apply_memory_proposal(store: ProjectStore, proposal: MemoryProposal, *, context: dict[str, Any],
                          chapter_accepted: bool, memory_accepted: bool, confirmation_source: str) -> dict[str, Any]:
    """Explicit caller author decisions, revalidation, then fixed commit.

    Confirmation values must represent an actual author action. They are not
    inferred from model pass/saved bytes, and do not authenticate that person.
    """
    if type(chapter_accepted) is not bool or type(memory_accepted) is not bool or not (chapter_accepted and memory_accepted):
        raise ValueError("both exact chapter and memory changes require explicit author acceptance")
    if not isinstance(confirmation_source, str) or not confirmation_source.strip():
        raise ValueError("explicit author confirmation source required")
    data = _validate_proposal(proposal); source = data["source"]; project = source["project"]
    with project_lock(store._path(project, ".store.lock", internal=True)):
        # A persisted pending candidate is required, so a model output alone
        # cannot quietly become a canonical update.
        if load_memory_proposal(store, project, data["proposal_id"], chapter_id=source["chapter_id"])._serialized != proposal._serialized:
            raise ValueError("saved proposal differs from the one being accepted")
        from .memory_commit import commit_confirmed_memory, read_memory_commit_receipt
        # Resume only the exact already-confirmed operation. Replays never
        # recalculate a delta against partially changed or newer Canon.
        previously_confirmed = (
            store._path(project, ".memory-commit-transaction.json", internal=True).exists()
            or read_memory_commit_receipt(store, project, data["proposal_id"]) is not None
        )
        if not previously_confirmed:
            assert_memory_source_current(store, MemorySource(_json(source)), context=context)
        phase = SimpleNamespace(state="candidate")
        Machine(model=phase, states=["candidate", "chapter_accepted", "confirmed"], initial="candidate",
                transitions=[["accept_chapter", "candidate", "chapter_accepted"],
                             ["accept_memory", "chapter_accepted", "confirmed"]], auto_transitions=False)
        phase.accept_chapter(); phase.accept_memory()
        if phase.state != "confirmed":
            raise ValueError("memory confirmation sequence incomplete")
        return commit_confirmed_memory(store, project, proposal_id=data["proposal_id"],
            chapter_id=source["chapter_id"], files=data["files"], expected_before=_hashes(source["before"]),
            inputs=_hashes(source["inputs"]), confirmation={"project": project, "chapter_id": source["chapter_id"],
                "proposal_id": data["proposal_id"], "source_text_sha256": source["source_text_sha256"],
                "chapter_accepted": True, "memory_accepted": True, "confirmation_source": confirmation_source})
