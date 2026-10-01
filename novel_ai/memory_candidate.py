from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import MemoryExtraction

_SCHEMA = "novel-memory-candidate-v1"
_RECEIPT_SCHEMA = "novel-memory-acceptance-v1"


class MemoryCandidateError(ValueError):
    """A pending memory candidate is malformed, stale, or bound elsewhere."""


def _json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise MemoryCandidateError("memory candidate contains unsupported values") from None


def _integrity_checked_extraction(candidate: dict[str, Any]) -> MemoryExtraction:
    required = {"schema", "project", "chapter_id", "chapter_text_sha256", "extraction", "candidate_id"}
    if not isinstance(candidate, dict) or set(candidate) != required or candidate.get("schema") != _SCHEMA:
        raise MemoryCandidateError("memory candidate envelope is malformed")
    project = candidate.get("project")
    chapter_id = candidate.get("chapter_id")
    text_sha = candidate.get("chapter_text_sha256")
    if not isinstance(project, str) or not project.strip() or not isinstance(chapter_id, str) or not chapter_id.strip():
        raise MemoryCandidateError("memory candidate binding is invalid")
    if not isinstance(text_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", text_sha):
        raise MemoryCandidateError("memory candidate chapter hash is invalid")
    try:
        extraction = MemoryExtraction.model_validate(candidate["extraction"])
    except Exception:
        raise MemoryCandidateError("memory extraction does not match the required schema") from None
    if extraction.chapter_id != chapter_id:
        raise MemoryCandidateError("memory extraction chapter_id does not match the bound chapter")
    binding = {key: candidate[key] for key in required if key != "candidate_id"}
    candidate_id = "memory-candidate-" + hashlib.sha256(_json(binding)).hexdigest()
    if candidate.get("candidate_id") != candidate_id:
        raise MemoryCandidateError("memory candidate integrity check failed")
    return extraction


def chapter_text_sha256(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise MemoryCandidateError("chapter text must be nonblank")
    return hashlib.sha256((text.strip() + "\n").encode("utf-8")).hexdigest()


def build_memory_candidate(project: str, chapter_id: str, chapter_text: str,
                           extraction: MemoryExtraction | dict[str, Any]) -> dict[str, Any]:
    project = str(project or "").strip()
    chapter_id = str(chapter_id or "").strip()
    if not project or not chapter_id:
        raise MemoryCandidateError("project and chapter_id are required")
    try:
        extraction = MemoryExtraction.model_validate(
            extraction.model_dump(mode="python") if isinstance(extraction, MemoryExtraction) else extraction
        )
    except Exception:
        raise MemoryCandidateError("memory extraction does not match the required schema") from None
    if extraction.chapter_id != chapter_id:
        raise MemoryCandidateError("memory extraction chapter_id does not match the bound chapter")
    binding = {
        "schema": _SCHEMA,
        "project": project,
        "chapter_id": chapter_id,
        "chapter_text_sha256": chapter_text_sha256(chapter_text),
        "extraction": extraction.model_dump(mode="json"),
    }
    return {
        **binding,
        "candidate_id": "memory-candidate-" + hashlib.sha256(_json(binding)).hexdigest(),
    }


def validate_memory_candidate(candidate: dict[str, Any], *, project: str, chapter_id: str,
                              chapter_text: str) -> MemoryExtraction:
    extraction = _integrity_checked_extraction(candidate)
    if candidate.get("project") != str(project or "").strip():
        raise MemoryCandidateError("memory candidate belongs to another project")
    if candidate.get("chapter_id") != str(chapter_id or "").strip():
        raise MemoryCandidateError("memory candidate belongs to another chapter")
    if candidate.get("chapter_text_sha256") != chapter_text_sha256(chapter_text):
        raise MemoryCandidateError("memory candidate belongs to a different chapter revision")
    return extraction


def acceptance_receipt(candidate: dict[str, Any]) -> dict[str, Any]:
    """Build the exact local-workbench receipt for the candidate.

    This is workflow evidence only. It is intentionally not a cryptographic
    identity proof; the UI must call it only from the explicit author-confirm
    button path.
    """
    _integrity_checked_extraction(candidate)
    candidate_id = candidate["candidate_id"]
    extraction_sha256 = hashlib.sha256(_json(candidate["extraction"])).hexdigest()
    return {
        "schema": _RECEIPT_SCHEMA,
        "status": "applied",
        "candidate_id": candidate_id,
        "project": candidate.get("project"),
        "chapter_id": candidate.get("chapter_id"),
        "chapter_text_sha256": candidate.get("chapter_text_sha256"),
        "extraction_sha256": extraction_sha256,
        "confirmed_by": "author",
        "confirmation_source": "local-workbench-confirm-button",
    }


def receipt_matches(receipt: Any, candidate: dict[str, Any]) -> bool:
    if not isinstance(receipt, dict):
        return False
    try:
        return receipt == acceptance_receipt(candidate)
    except MemoryCandidateError:
        return False
