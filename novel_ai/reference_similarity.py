from __future__ import annotations

from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
import importlib.util
import re
from typing import Any, Sequence

from .semantic import Encoder, max_reference_similarity
from .style_engine import reference_overlap


@dataclass
class SimilarityIssue:
    category: str
    severity: str
    reason: str
    suggestion: str
    reference_index: int | None = None


@dataclass
class SimilarityReport:
    shingle_overlap: float = 0.0
    fuzzy_max: float = 0.0
    semantic_max: float = 0.0
    event_sequence_max: float = 0.0
    backends: dict[str, bool] = field(default_factory=dict)
    issues: list[SimilarityIssue] = field(default_factory=list)
    score: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _bigram_set(text: str) -> set[str]:
    text = _compact(text)
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i+2] for i in range(len(text)-1)}


def fuzzy_similarity(a: str, b: str) -> float:
    if importlib.util.find_spec("rapidfuzz") is not None:
        try:
            from rapidfuzz.fuzz import ratio
            return round(float(ratio(a, b)) / 100.0, 6)
        except Exception:
            pass
    ga, gb = _bigram_set(a), _bigram_set(b)
    if not ga or not gb:
        return 0.0
    return round(2 * len(ga & gb) / (len(ga) + len(gb)), 6)


def _max_score(text: str, refs: Sequence[str]) -> tuple[float, int | None]:
    if not refs:
        return 0.0, None
    scores = [fuzzy_similarity(text, ref) for ref in refs]
    idx = max(range(len(scores)), key=scores.__getitem__)
    return scores[idx], idx


_EVENT_CANONICAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("接到", "收到"),
    ("来电", "电话"),
    ("遭人跟踪", "被跟踪"),
    ("遭跟踪", "被跟踪"),
    ("决定", "选择"),
    ("丢失", "失去"),
    ("丢掉", "失去"),
    ("获得", "得到"),
)


def _normalize_event_label(text: str) -> str:
    value = str(text or "").strip()
    for source, target in _EVENT_CANONICAL_REPLACEMENTS:
        value = value.replace(source, target)
    return value


def _event_tokens(text: str) -> set[str]:
    clean = re.sub(
        r"[^\w\u4e00-\u9fff]+",
        "",
        _normalize_event_label(text),
        flags=re.UNICODE,
    )
    return _bigram_set(clean)


def _flatten_events(items: Sequence[str]) -> list[str]:
    rows: list[str] = []
    for item in items:
        rows.extend(
            part.strip()
            for part in re.split(r"[|｜]", str(item))
            if part.strip()
        )
    return rows


def event_sequence_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    left = _flatten_events(a)
    right = _flatten_events(b)
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    parts: list[float] = []
    for i in range(n):
        x_tokens, y_tokens = _event_tokens(left[i]), _event_tokens(right[i])
        jaccard = (
            len(x_tokens & y_tokens) / len(x_tokens | y_tokens)
            if x_tokens and y_tokens
            else 0.0
        )
        # Fuzzy aligned-event comparison catches near-synonymous Chinese event
        # labels while Jaccard keeps a deterministic dependency-free floor.
        parts.append(
            max(
                jaccard,
                fuzzy_similarity(
                    _normalize_event_label(left[i]),
                    _normalize_event_label(right[i]),
                ),
            )
        )
    return round((sum(parts) / n) * (n / max(len(left), len(right))), 6)


def analyze_reference_similarity(
    text: str,
    *,
    reference_hashes: set[str] | None = None,
    temporary_reference_passages: Sequence[str] | None = None,
    current_events: Sequence[str] | None = None,
    reference_event_sequences: Sequence[Sequence[str]] | None = None,
    encoder: Encoder | None = None,
) -> SimilarityReport:
    """Detect risky closeness to references.

    Safe default uses non-reversible shingle hashes. Optional raw reference
    passages are runtime-only inputs; this module does not persist them.
    """
    hashes = reference_hashes or set()
    refs = list(temporary_reference_passages or [])
    event_refs = list(reference_event_sequences or [])

    shingle = reference_overlap(text, hashes) if hashes else 0.0
    fuzzy_max, fuzzy_idx = _max_score(text, refs)

    semantic_max = 0.0
    semantic_idx = None
    if refs:
        semantic = max_reference_similarity(text, refs, encoder)
        semantic_max = float(semantic["max_similarity"])
        semantic_idx = semantic["reference_index"]

    event_max = 0.0
    event_idx = None
    if current_events and event_refs:
        scores = [event_sequence_similarity(current_events, ref) for ref in event_refs]
        event_idx = max(range(len(scores)), key=scores.__getitem__)
        event_max = scores[event_idx]

    issues: list[SimilarityIssue] = []
    if shingle >= 0.03:
        issues.append(SimilarityIssue(
            category="参考片段重合",
            severity="high" if shingle >= 0.08 else "medium",
            reason=f"与不可逆参考签名的连续片段重合率约 {shingle:.2%}。",
            suggestion="重构该段的表达、动作链和细节来源，避免沿用参考文本的连续表述。",
        ))
    if fuzzy_max >= 0.72:
        issues.append(SimilarityIssue(
            category="措辞近似",
            severity="medium",
            reason=f"与运行时参考片段的最高模糊相似度约 {fuzzy_max:.2%}。",
            suggestion="优先重构句法与信息组织，不做机械同义词替换。",
            reference_index=fuzzy_idx,
        ))
    if semantic_max >= 0.88:
        issues.append(SimilarityIssue(
            category="语义段落近似",
            severity="medium",
            reason=f"与运行时参考片段的最高语义相似度约 {semantic_max:.2%}。",
            suggestion="检查场景组织、视角、动作与信息释放是否过度接近参考来源。",
            reference_index=semantic_idx,
        ))
    if event_max >= 0.72:
        issues.append(SimilarityIssue(
            category="事件序列近似",
            severity="high" if event_max >= 0.86 else "medium",
            reason=f"与参考事件序列的最高相似度约 {event_max:.2%}。",
            suggestion="改变人物选择、阻力、因果链或代价，而不是只改表面措辞。",
            reference_index=event_idx,
        ))

    penalty = {"medium": 15, "high": 28}
    score = max(0, 100 - sum(penalty.get(i.severity, 0) for i in issues))
    return SimilarityReport(
        shingle_overlap=round(shingle, 6),
        fuzzy_max=round(fuzzy_max, 6),
        semantic_max=round(semantic_max, 6),
        event_sequence_max=round(event_max, 6),
        backends={
            "rapidfuzz": importlib.util.find_spec("rapidfuzz") is not None,
            "embedding": encoder is not None,
            "reference_hashes": bool(hashes),
            "temporary_reference_passages": bool(refs),
            "event_sequences": bool(event_refs),
        },
        issues=issues,
        score=score,
    )


def similarity_review_payload(report: SimilarityReport) -> dict[str, Any]:
    return {
        "score": report.score,
        "metrics": {
            "shingle_overlap": report.shingle_overlap,
            "fuzzy_max": report.fuzzy_max,
            "semantic_max": report.semantic_max,
            "event_sequence_max": report.event_sequence_max,
        },
        "issues": [asdict(i) for i in report.issues],
    }
