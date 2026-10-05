"""Explicit local semantic recall of current-project historical summaries.

This adapter replaces the full derived corpus, validates returned source identity,
and does not promote recalled summaries into Canon or enable a backend by default.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import math
from typing import Any

from .recall import RecallDocument, RecallHit
from .recall_backends import LocalSemanticRecall


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def select_semantic_history(backend: LocalSemanticRecall, query: str, rows: list[dict[str, Any]],
                            *, project_scope: str, limit: int = 8, summary_chars: int = 80):
    if not isinstance(backend, LocalSemanticRecall):
        raise TypeError("the writing-context option accepts an explicit LocalSemanticRecall instance only")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("semantic history selection requires an explicit query")
    if type(limit) is not int or limit < 1 or type(summary_chars) is not int or summary_chars < 0:
        raise ValueError("semantic history limit must be positive and summary_chars nonnegative integers")
    if not isinstance(project_scope, str) or not project_scope:
        raise ValueError("an explicit current-project scope is required")
    records, docs, excluded = {}, [], []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("historical summaries must be objects")
        raw = deepcopy(raw)  # Freeze source identity before any backend/encoder callback.
        chapter_id, summary = raw.get("chapter_id"), raw.get("summary", "")
        if not isinstance(chapter_id, str) or not chapter_id.strip() or not isinstance(summary, str):
            raise ValueError("historical summary needs a stable chapter ID and string text")
        if not summary.strip():
            excluded.append(chapter_id)
            continue
        identity = _fingerprint(raw)
        document_id = "history-" + _fingerprint([project_scope, chapter_id])
        meta = {"schema": "novel-local-history-v1", "project_scope": project_scope,
                "chapter_id": chapter_id, "source_fingerprint": identity}
        document = RecallDocument(document_id, summary, meta)
        if document_id in records:
            if records[document_id][0] != document:
                raise ValueError("conflicting duplicate chapter summaries must be reconciled before semantic recall")
            continue
        records[document_id] = (document, raw)
        docs.append(RecallDocument(document_id, summary, deepcopy(meta)))
    corpus_fingerprint = _fingerprint([expected[0].metadata for expected in records.values()])
    # Replacement is required: upsert alone could retain removed/other-project rows.
    # If encoding/indexing fails, no new context is returned; no stale fallback.
    backend.replace_documents(docs if summary_chars else [])
    hits = backend.query(query, limit=limit) if docs and summary_chars else []
    if len(hits) > limit:
        raise ValueError("semantic recall returned more hits than the requested limit")
    selected, seen, sources, omitted = [], set(), [], []
    for hit in hits:
        if not isinstance(hit, RecallHit) or hit.document_id in seen or hit.document_id not in records:
            raise ValueError("semantic recall returned a duplicate or unknown source")
        expected, raw = records[hit.document_id]
        if hit.text != expected.text or hit.metadata != expected.metadata:
            raise ValueError("semantic recall returned stale text or a different source identity")
        if not isinstance(hit.score, (int, float)) or isinstance(hit.score, bool) or not math.isfinite(hit.score) or not -1 <= hit.score <= 1:
            raise ValueError("semantic recall score must be a finite cosine in [-1, 1]")
        seen.add(hit.document_id)
        sources.append({"chapter_id": raw["chapter_id"], "document_id": hit.document_id,
                        "source_fingerprint": expected.metadata["source_fingerprint"], "score": hit.score,
                        "source_file": "memory/chapter_summaries.jsonl"})
        if len(hit.text) > summary_chars:
            omitted.append({"chapter_id": raw["chapter_id"],
                            "source_fingerprint": expected.metadata["source_fingerprint"],
                            "reason": "complete source summary exceeds per-source character budget; no partial claim emitted"})
            continue
        selected.append({**deepcopy(raw), "recall_excerpt": hit.text})
    return selected, {"mode": "local-semantic", "backend": backend.name,
                      "project_scope": project_scope, "corpus_fingerprint": corpus_fingerprint,
                      "candidate_count": len(docs), "indexed_candidate_count": len(docs) if summary_chars else 0,
                      "selected_sources": sources, "included_chapter_ids": [], "prompt_chars": 0,
                      "omitted_sources": omitted,
                      "excluded_empty_chapter_ids": excluded,
                      "summary_chars": summary_chars, "limit": limit,
                      "semantic_quality_validated": False,
                      "note": "Derived summary clues only; Canon and actual source text remain authoritative"}
