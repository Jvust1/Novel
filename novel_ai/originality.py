from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib
import re
from typing import Any, Sequence

from .semantic import Encoder, semantic_similarity


_DEFAULT_THRESHOLDS = {
    "shingle": 0.42,
    "fuzzy": 0.86,
    "embedding": 0.90,
    "event_sequence": 0.78,
}

_EVENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("threat", re.compile(r"追杀|围攻|战争|灾难|警报|爆炸|危险|封锁")),
    ("conflict", re.compile(r"争吵|质问|误会|背叛|拒绝|威胁|谈判|对峙")),
    ("reveal", re.compile(r"发现|真相|线索|证据|身份|秘密|原来|答案")),
    ("decision", re.compile(r"决定|选择|答应|拒绝|离开|回归|加入")),
    ("gain", re.compile(r"获得|拿到|得到|赢得|突破|晋升|救出")),
    ("loss", re.compile(r"失去|牺牲|死亡|受伤|失败|崩溃|破裂")),
    ("reversal", re.compile(r"却|然而|但是|突然|没想到|反而")),
)


@dataclass(frozen=True)
class OriginalityLayerResult:
    """One explainable layer of the originality gate."""

    name: str
    score: float
    threshold: float
    flagged: bool
    available: bool = True
    method: str = ""
    best_reference_index: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "threshold": self.threshold,
            "flagged": self.flagged,
            "available": self.available,
            "method": self.method,
            "best_reference_index": self.best_reference_index,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class OriginalityGateResult:
    """Auditable result for a target against one or more references.

    The result contains source hashes and derived measurements only; it never
    stores target or reference prose.
    """

    passed: bool
    strict: bool
    target_id: str
    reference_ids: list[str]
    layers: list[OriginalityLayerResult]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "strict": self.strict,
            "target_id": self.target_id,
            "reference_ids": self.reference_ids,
            "layers": [layer.to_dict() for layer in self.layers],
            "notes": self.notes,
        }


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _lexical(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_\u3400-\u9fff]", "", text or "").lower()


def _source_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _shingles(text: str, size: int) -> set[str]:
    compact = _lexical(text)
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return round(len(left & right) / len(union), 6) if union else 0.0


def shingle_similarity(text_a: str, text_b: str, *, size: int = 5) -> float:
    """Return character-shingle Jaccard similarity for Chinese prose."""
    if size < 2:
        raise ValueError("shingle size 必须至少为 2")
    return _jaccard(_shingles(text_a, size), _shingles(text_b, size))


def _bounded(text: str, limit: int = 4000) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    half = limit // 2
    return compact[:half] + compact[-half:]


def fuzzy_similarity(text_a: str, text_b: str) -> float:
    """Bounded sequence similarity for near-copy and reordering signals."""
    return round(SequenceMatcher(None, _bounded(text_a), _bounded(text_b), autojunk=False).ratio(), 6)


def _event_sequence(text: str, *, limit: int = 64) -> list[str]:
    events: list[tuple[int, str]] = []
    for label, pattern in _EVENT_PATTERNS:
        events.extend((match.start(), label) for match in pattern.finditer(text))
    events.sort()
    sequence: list[str] = []
    for _, label in events:
        if not sequence or sequence[-1] != label:
            sequence.append(label)
        if len(sequence) >= limit:
            break
    return sequence


def _lcs_length(left: Sequence[str], right: Sequence[str]) -> int:
    row = [0] * (len(right) + 1)
    for left_item in left:
        previous = 0
        for index, right_item in enumerate(right, start=1):
            saved = row[index]
            if left_item == right_item:
                row[index] = previous + 1
            else:
                row[index] = max(row[index], row[index - 1])
            previous = saved
    return row[-1]


def event_sequence_similarity(text_a: str, text_b: str) -> tuple[float, list[str], list[str]]:
    """Compare the order of explainable event categories, without prose."""
    left = _event_sequence(text_a)
    right = _event_sequence(text_b)
    if not left or not right:
        return 0.0, left, right
    score = _lcs_length(left, right) / max(len(left), len(right))
    return round(score, 6), left, right


def _best_pair(
    target: str,
    references: Sequence[str],
    scorer,
) -> tuple[float, int | None, list[float]]:
    scores = [round(float(scorer(target, reference)), 6) for reference in references]
    if not scores:
        return 0.0, None, []
    best = max(range(len(scores)), key=scores.__getitem__)
    return scores[best], best, scores


def evaluate_originality(
    target: str,
    references: Sequence[str],
    *,
    encoder: Encoder | None = None,
    thresholds: dict[str, float] | None = None,
    strict: bool = False,
    shingle_size: int = 5,
) -> OriginalityGateResult:
    """Run shingle, fuzzy, embedding, and event-sequence checks.

    The embedding layer uses the configured encoder when supplied. Without an
    encoder it reports the dependency-free semantic fallback as unavailable;
    strict mode then fails closed until an embedding backend is configured.
    """

    refs = [reference for reference in references if reference and reference.strip()]
    limit = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
    target_id = _source_id(target)
    reference_ids = [_source_id(reference) for reference in refs]
    if not target.strip() or not refs:
        return OriginalityGateResult(
            passed=False,
            strict=strict,
            target_id=target_id,
            reference_ids=reference_ids,
            layers=[],
            notes=["目标文本和参考文本均不能为空；原创性 Gate 已 fail-closed。"],
        )

    shingle_score, shingle_index, shingle_scores = _best_pair(
        target, refs, lambda left, right: shingle_similarity(left, right, size=shingle_size)
    )
    fuzzy_score, fuzzy_index, fuzzy_scores = _best_pair(target, refs, fuzzy_similarity)

    if encoder is None:
        embedding_score, embedding_index, embedding_scores = _best_pair(
            target, refs, semantic_similarity
        )
        embedding_available = False
        embedding_method = "char_ngram_fallback"
    else:
        embedding_score, embedding_index, embedding_scores = _best_pair(
            target, refs, lambda left, right: semantic_similarity(left, right, encoder)
        )
        embedding_available = True
        embedding_method = "configured_encoder"

    event_scores: list[float] = []
    event_pairs: list[tuple[list[str], list[str]]] = []
    for reference in refs:
        score, left_events, right_events = event_sequence_similarity(target, reference)
        event_scores.append(score)
        event_pairs.append((left_events, right_events))
    event_score = max(event_scores, default=0.0)
    event_index = max(range(len(event_scores)), key=event_scores.__getitem__) if event_scores else None
    event_left, event_right = event_pairs[event_index] if event_index is not None else ([], [])

    layers = [
        OriginalityLayerResult(
            name="shingle",
            score=shingle_score,
            threshold=float(limit["shingle"]),
            flagged=shingle_score >= float(limit["shingle"]),
            method=f"character_jaccard_{shingle_size}gram",
            best_reference_index=shingle_index,
            evidence={"scores": shingle_scores},
        ),
        OriginalityLayerResult(
            name="fuzzy",
            score=fuzzy_score,
            threshold=float(limit["fuzzy"]),
            flagged=fuzzy_score >= float(limit["fuzzy"]),
            method="bounded_sequence_matcher",
            best_reference_index=fuzzy_index,
            evidence={"scores": fuzzy_scores, "max_chars": 4000},
        ),
        OriginalityLayerResult(
            name="embedding",
            score=embedding_score,
            threshold=float(limit["embedding"]),
            flagged=embedding_available and embedding_score >= float(limit["embedding"]),
            available=embedding_available,
            method=embedding_method,
            best_reference_index=embedding_index,
            evidence={"scores": embedding_scores},
        ),
        OriginalityLayerResult(
            name="event_sequence",
            score=event_score,
            threshold=float(limit["event_sequence"]),
            flagged=event_score >= float(limit["event_sequence"]),
            method="keyword_event_lcs",
            best_reference_index=event_index,
            evidence={
                "scores": event_scores,
                "target_events": event_left,
                "best_reference_events": event_right,
            },
        ),
    ]

    notes: list[str] = []
    if not embedding_available:
        notes.append("未配置 embedding encoder；当前仅报告 char n-gram fallback，strict 模式会阻断。")
    flagged = [layer.name for layer in layers if layer.flagged]
    if flagged:
        notes.append("触发层：" + "、".join(flagged) + "；需要人工复核或改写。")
    if not any(_event_sequence(target)) or not any(_event_sequence(reference) for reference in refs):
        notes.append("至少一侧缺少可解释事件信号，event-sequence 结果只能作为弱证据。")

    passed = not flagged and (not strict or embedding_available)
    return OriginalityGateResult(
        passed=passed,
        strict=strict,
        target_id=target_id,
        reference_ids=reference_ids,
        layers=layers,
        notes=notes,
    )
