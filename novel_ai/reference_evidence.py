"""Bounded, local-only reference evidence retrieval.

This module keeps reference bodies out of persistent artifacts.  It extracts
each explicitly supplied local file through :func:`reading.extract_reference`,
builds deterministic paragraph/chapter chunks, scores them lexically, and
uses the small licensed MMR source port already vendored in this repository.
Returned offsets are zero-based half-open indices into the sanitized extracted
Unicode text.  The text itself is intentionally never placed in the result;
callers can verify an excerpt by re-reading the source and checking its two
hashes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ._vendor.langchain_mmr import maximal_marginal_relevance
from .reading import extract_reference

EVIDENCE_SCHEMA = "novel-reference-evidence-v1"
OFFSET_BASIS = "sanitized-extracted-unicode-codepoints"

# These are deliberately conservative.  They are part of the local artifact
# contract and can be raised only by a future schema change.
DEFAULT_TOP_N = 5
DEFAULT_CHUNK_CHARS = 720
DEFAULT_MAX_EXCERPT_CHARS = 360
DEFAULT_LAMBDA_MULT = 0.5
MAX_TOP_N = 20
MAX_CHUNK_CHARS = 4096
MAX_EXCERPT_CHARS = 2048
MAX_CHUNKS = 10_000
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024

_CHAPTER_LINE = re.compile(
    r"^\s*(?:(?:第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*章.*)"
    r"|(?:#{1,6}\s+\S.*)|(?:chapter\s+[0-9]+\b.*))\s*$",
    re.IGNORECASE,
)
_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)?", re.IGNORECASE)


@dataclass(frozen=True)
class EvidenceSource:
    """One local source before extraction.

    ``filename`` is a display name, not a path.  The CLI reads and validates
    paths before constructing these records.
    """

    filename: str
    data: bytes
    encoding: str | None = None


@dataclass(frozen=True)
class _ExtractedSource:
    filename: str
    raw_sha256: str
    extracted_sha256: str
    text: str
    backend: str
    encoding: str | None
    decoding: dict[str, Any] | None


@dataclass(frozen=True)
class _Candidate:
    source: _ExtractedSource
    chapter: str | None
    start: int
    end: int
    excerpt: str
    score: float
    tokens: frozenset[str]
    excerpt_sha256: str
    stable_id: str


def _validate_int(name: str, value: int, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def _validate_limits(
    *, top_n: int, chunk_chars: int, max_excerpt_chars: int,
    lambda_mult: float, max_chunks: int,
) -> None:
    _validate_int("top_n", top_n, 1, MAX_TOP_N)
    _validate_int("chunk_chars", chunk_chars, 1, MAX_CHUNK_CHARS)
    _validate_int("max_excerpt_chars", max_excerpt_chars, 1, MAX_EXCERPT_CHARS)
    _validate_int("max_chunks", max_chunks, 1, MAX_CHUNKS)
    if type(lambda_mult) not in {int, float} or not math.isfinite(float(lambda_mult)):
        raise ValueError("lambda_mult must be finite and between 0 and 1")
    if not 0 <= float(lambda_mult) <= 1:
        raise ValueError("lambda_mult must be finite and between 0 and 1")


def _coerce_source(item: EvidenceSource | Sequence[Any]) -> EvidenceSource:
    if isinstance(item, EvidenceSource):
        return item
    if isinstance(item, (str, Path)):
        path = Path(item)
        if path.is_symlink() or not path.exists() or not path.is_file():
            raise ValueError(f"输入必须是普通文件: {path}")
        return EvidenceSource(path.name, path.read_bytes())
    if not isinstance(item, (tuple, list)) or len(item) not in {2, 3}:
        raise ValueError("每个参考源需要 filename、bytes 及可选 encoding")
    filename, data = item[0], item[1]
    encoding = item[2] if len(item) == 3 else None
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("参考源 filename 不能为空")
    if type(data) is not bytes:
        raise ValueError("参考源必须是原始 bytes")
    if encoding is not None and not isinstance(encoding, str):
        raise ValueError("encoding 必须是字符串或 None")
    display_name = Path(filename).name
    if not display_name:
        raise ValueError("参考源 filename 不能为空")
    return EvidenceSource(display_name, data, encoding)


def _normalise_query(query: str) -> str:
    if not isinstance(query, str):
        raise ValueError("query must be a non-empty string")
    value = re.sub(r"\s+", "", query.casefold())
    if not value:
        raise ValueError("query must not be empty")
    return value


def _tokens(value: str) -> tuple[str, ...]:
    """Return deterministic word plus CJK n-gram tokens without dependencies."""
    text = value.casefold()
    found: list[str] = []
    for match in _LATIN.finditer(text):
        found.append(match.group(0))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        chars = list(run)
        found.extend(chars)
        for size in (2, 3):
            found.extend("".join(chars[i:i + size]) for i in range(len(chars) - size + 1))
    return tuple(found)


def _lexical_score(query: str, text: str) -> tuple[float, frozenset[str]]:
    query_tokens = _tokens(query)
    text_tokens = Counter(_tokens(text))
    if not query_tokens:
        return 0.0, frozenset()
    query_counts = Counter(query_tokens)
    matched = sum(min(count, text_tokens.get(token, 0)) for token, count in query_counts.items())
    coverage = matched / max(sum(query_counts.values()), 1)
    phrase = query in re.sub(r"\s+", "", text.casefold())
    cjk_only = bool(_CJK.search(query)) and not bool(_LATIN.search(query))
    # A single common CJK character is not enough to make an unrelated chunk
    # an evidence hit.  A contiguous phrase always qualifies.
    if matched == 0 or (cjk_only and coverage < 0.5 and not phrase):
        return 0.0, frozenset(text_tokens)
    score = min(1.0, coverage * 0.7 + (0.3 if phrase else 0.0))
    return round(score, 12), frozenset(text_tokens)


def _chapter_spans(text: str) -> list[tuple[int, int, str]]:
    rows: list[tuple[int, int, str]] = []
    for match in re.finditer(r".*(?:\n|$)", text):
        line = match.group(0).rstrip("\r\n")
        if line and _CHAPTER_LINE.match(line):
            label = line.strip()
            if label.startswith("#"):
                label = label.lstrip("#").strip()
            rows.append((match.start(), match.end(), label))
    if not rows:
        return [(0, len(text), "")] if text else []
    spans: list[tuple[int, int, str]] = []
    for index, (start, heading_end, label) in enumerate(rows):
        end = rows[index + 1][0] if index + 1 < len(rows) else len(text)
        spans.append((start, end, label))
    if rows[0][0] > 0:
        spans.insert(0, (0, rows[0][0], ""))
    return spans


def _chapter_for(spans: Sequence[tuple[int, int, str]], start: int) -> str | None:
    for span_start, span_end, label in spans:
        if span_start <= start < span_end:
            return label or None
    return None


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    # Blank lines are paragraph boundaries.  A source without blank lines is
    # still bounded later by the fixed-size splitter.
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.DOTALL):
        start, end = match.span()
        if start < end:
            ranges.append((start, end))
    if not ranges and text.strip():
        stripped = text.strip()
        start = text.index(stripped)
        ranges.append((start, start + len(stripped)))
    return ranges


def _bounded_ranges(text: str, chunk_chars: int, *, max_ranges: int | None = None) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for start, end in _paragraph_ranges(text):
        cursor = start
        while cursor < end:
            stop = min(cursor + chunk_chars, end)
            # Prefer a nearby whitespace boundary, but never create an empty
            # range and never exceed the hard bound.
            if stop < end:
                boundary = text.rfind(" ", cursor + 1, stop + 1)
                if boundary > cursor + max(1, chunk_chars // 3):
                    stop = boundary
            ranges.append((cursor, stop))
            if max_ranges is not None and len(ranges) > max_ranges:
                raise ValueError("分段数量超过资源上限")
            cursor = stop
            while cursor < end and text[cursor].isspace():
                cursor += 1
    return ranges


def _extract_sources(items: Iterable[EvidenceSource | Sequence[Any]]) -> list[_ExtractedSource]:
    sources = [_coerce_source(item) for item in items]
    if not sources:
        raise ValueError("至少需要一个参考源")
    total = 0
    seen_names: set[str] = set()
    result: list[_ExtractedSource] = []
    for source in sources:
        if source.filename in seen_names:
            raise ValueError(f"参考源 filename 重复: {source.filename}")
        seen_names.add(source.filename)
        if len(source.data) > MAX_SOURCE_BYTES:
            raise ValueError(f"参考源超过单文件资源上限: {source.filename}")
        total += len(source.data)
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("参考源超过累计资源上限")
        extracted = extract_reference(source.filename, source.data, encoding=source.encoding)
        text = extracted.text
        decoding = dict(extracted.decoding) if extracted.decoding else None
        result.append(_ExtractedSource(
            filename=source.filename,
            raw_sha256=hashlib.sha256(source.data).hexdigest(),
            extracted_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            text=text,
            backend=extracted.backend,
            encoding=(decoding or {}).get("encoding"),
            decoding=decoding,
        ))
    return sorted(result, key=lambda row: (row.filename.casefold(), row.filename, row.raw_sha256))


def _source_manifest(source: _ExtractedSource, chunk_count: int) -> dict[str, Any]:
    return {
        "source_filename": source.filename,
        "filename": source.filename,
        "raw_source_sha256": source.raw_sha256,
        "extracted_text_sha256": source.extracted_sha256,
        "normalized_text_sha256": source.extracted_sha256,
        "extracted_char_count": len(source.text),
        "backend": source.backend,
        "encoding": source.encoding,
        "decoding": source.decoding,
        "chunk_count": chunk_count,
    }


def build_reference_evidence(
    sources: Iterable[EvidenceSource | Sequence[Any]],
    query: str,
    *,
    top_n: int = DEFAULT_TOP_N,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_excerpt_chars: int = DEFAULT_MAX_EXCERPT_CHARS,
    lambda_mult: float = DEFAULT_LAMBDA_MULT,
    max_chunks: int = MAX_CHUNKS,
) -> dict[str, Any]:
    """Build a deterministic, bounded evidence artifact in memory.

    No source body is returned.  ``start``/``end`` identify a half-open slice
    of the sanitized extracted Unicode text, and each match carries both the
    raw-byte and extracted-text hashes needed to verify that slice locally.
    """
    query_norm = _normalise_query(query)
    _validate_limits(
        top_n=top_n, chunk_chars=chunk_chars, max_excerpt_chars=max_excerpt_chars,
        lambda_mult=lambda_mult, max_chunks=max_chunks,
    )
    extracted = _extract_sources(sources)
    candidates: list[_Candidate] = []
    chunk_counts: dict[str, int] = {}
    for source in extracted:
        spans = _chapter_spans(source.text)
        ranges = _bounded_ranges(source.text, chunk_chars, max_ranges=max_chunks)
        chunk_counts[source.filename] = len(ranges)
        if sum(chunk_counts.values()) > max_chunks:
            raise ValueError("分段数量超过资源上限")
        for start, end in ranges:
            chunk_text = source.text[start:end]
            score, tokens = _lexical_score(query_norm, chunk_text)
            if score <= 0:
                continue
            excerpt_start = start
            excerpt_end = min(end, start + max_excerpt_chars)
            if end - start > max_excerpt_chars:
                # Keep the bounded evidence window near the first matching
                # lexical token when the paragraph itself is longer than the
                # artifact excerpt cap.
                anchors = sorted(set(_tokens(query_norm)), key=len, reverse=True)
                lowered = chunk_text.casefold()
                positions = [lowered.find(anchor) for anchor in anchors if anchor and lowered.find(anchor) >= 0]
                if positions:
                    anchor = start + min(positions)
                    excerpt_start = max(start, min(anchor - max_excerpt_chars // 3, end - max_excerpt_chars))
                    excerpt_end = excerpt_start + max_excerpt_chars
            excerpt = source.text[excerpt_start:excerpt_end]
            excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
            stable_material = "|".join((source.filename, source.raw_sha256, str(excerpt_start), str(excerpt_end), excerpt_hash))
            stable_id = hashlib.sha256(stable_material.encode("utf-8")).hexdigest()
            candidates.append(_Candidate(
                source=source,
                chapter=_chapter_for(spans, excerpt_start),
                start=excerpt_start,
                end=excerpt_end,
                excerpt=excerpt,
                score=score,
                tokens=tokens,
                excerpt_sha256=excerpt_hash,
                stable_id=stable_id,
            ))
    candidates.sort(key=lambda row: (-row.score, row.source.filename.casefold(), row.start, row.end, row.stable_id))
    if not candidates:
        selected: list[_Candidate] = []
    else:
        scores = [row.score for row in candidates]

        def pair_similarity(left: int, right: int) -> float:
            a, b = candidates[left], candidates[right]
            union = a.tokens | b.tokens
            overlap = len(a.tokens & b.tokens) / len(union) if union else 0.0
            # Same-source excerpts are slightly more redundant, so MMR prefers
            # a second source when lexical relevance is comparable.
            return min(1.0, overlap + (0.15 if a.source.filename == b.source.filename else 0.0))

        selected = [candidates[index] for index in maximal_marginal_relevance(
            scores, pair_similarity, lambda_mult=float(lambda_mult), k=min(top_n, len(candidates))
        )]

    matches = []
    for row in selected:
        matches.append({
            "id": row.stable_id,
            "source_filename": row.source.filename,
            "filename": row.source.filename,
            "chapter": row.chapter,
            "start": row.start,
            "end": row.end,
            "score": row.score,
            "excerpt": row.excerpt,
            "excerpt_sha256": row.excerpt_sha256,
            "raw_source_sha256": row.source.raw_sha256,
            "extracted_text_sha256": row.source.extracted_sha256,
            "normalized_text_sha256": row.source.extracted_sha256,
            "backend": row.source.backend,
            "encoding": row.source.encoding,
            "offset_basis": OFFSET_BASIS,
        })
    return {
        "schema": EVIDENCE_SCHEMA,
        "query": query.strip(),
        "offset_basis": OFFSET_BASIS,
        "sources": [_source_manifest(source, chunk_counts[source.filename]) for source in extracted],
        "parameters": {
            "top_n": top_n,
            "chunk_chars": chunk_chars,
            "max_excerpt_chars": max_excerpt_chars,
            "lambda_mult": float(lambda_mult),
            "max_chunks": max_chunks,
        },
        "matches": matches,
        "notes": [
            "摘录仅来自显式本地输入；默认不生成本 artifact。",
            "offset 是清洗后的 extracted Unicode 字符索引，不是 HTML DOM 或原始字节位置。",
            "artifact 不保存源正文，不自动注入 ContextAssembler、模型或写作流程。",
        ],
    }


def query_reference_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility alias for callers that name the operation as a query."""
    return build_reference_evidence(*args, **kwargs)


def save_evidence_artifact(artifact: dict[str, Any], path: str | Path) -> Path:
    """Atomically create a new evidence artifact without overwriting one."""
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError(f"evidence-out 已存在，拒绝覆盖: {target}")
    if target.name in {"", ".", ".."} or target.exists() and not target.is_file():
        raise ValueError("evidence-out 必须是新的普通文件路径")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(artifact, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return target


def validate_evidence_output_path(path: str | Path, source_paths: Iterable[str | Path], *, pack_out: str | Path | None = None) -> Path:
    """Reject source/pack aliases and non-new output paths before extraction."""
    target = Path(path)
    target_resolved = target.resolve(strict=False)
    if target.exists() or target.is_symlink():
        raise ValueError(f"evidence-out 已存在，拒绝覆盖: {target}")
    if pack_out is not None and target_resolved == Path(pack_out).resolve(strict=False):
        raise ValueError("evidence-out 不得与 Reference Pack 输出路径相同")
    for raw in source_paths:
        source = Path(raw)
        if source.is_symlink() or not source.exists() or not source.is_file():
            raise ValueError(f"输入必须是普通文件: {source}")
        if target_resolved == source.resolve(strict=True):
            raise ValueError("evidence-out 不得覆盖参考源文件")
    return target


__all__ = [
    "DEFAULT_CHUNK_CHARS", "DEFAULT_LAMBDA_MULT", "DEFAULT_MAX_EXCERPT_CHARS",
    "DEFAULT_TOP_N", "EVIDENCE_SCHEMA", "EvidenceSource", "OFFSET_BASIS",
    "build_reference_evidence", "query_reference_evidence", "save_evidence_artifact",
    "validate_evidence_output_path",
]
