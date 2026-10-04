from __future__ import annotations

"""Spindle-derived temporal coherence scanner.

Ported and adapted from:
https://github.com/VerifiedOrganic/spindle
Source file: crates/spindle-core/src/temporal/mod.rs
Upstream commit: d88500849b3561b78cd4a80e85443aa66122155d
License: MIT; see third_party/spindle/LICENSE.

The scanner is advisory and deterministic. It does not decide whether a
chapter is publishable; Novel's existing review and author-acceptance gates
remain authoritative.
"""

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class TemporalSceneInput:
    prose: str
    duration_days: float | None = None
    temporal_mode: str | None = "linear"
    precision: str | None = "hour"


@dataclass(frozen=True)
class TemporalCoherenceHit:
    kind: str
    severity: str
    message: str
    start: int | None = None
    end: int | None = None
    marker: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# The ordinal bands intentionally stay coarse. A two-band move (morning to
# afternoon) is allowed; larger unbridged jumps are tripwires.
_TIME_OF_DAY_BANDS: tuple[tuple[str, int], ...] = (
    ("黎明", 0), ("破晓", 0), ("清晨", 0), (" dawn", 0), ("daybreak", 0),
    ("sunrise", 0), ("first light", 0),
    ("早晨", 1), ("上午", 1), ("morning", 1), ("forenoon", 1), ("早餐时", 1),
    ("正午", 2), ("中午", 2), ("noon", 2), ("midday", 2), ("午餐时", 2),
    ("下午", 3), ("afternoon", 3),
    ("傍晚", 4), ("黄昏", 4), ("日落", 4), ("evening", 4), ("dusk", 4),
    ("sunset", 4), ("twilight", 4), ("nightfall", 4),
    ("深夜", 5), ("午夜", 5), ("夜里", 5), ("夜晚", 5), ("night", 5),
    ("midnight", 5),
)

_TRANSITION_MARKERS = (
    "后来", "随后", "不久后", "过了一会儿", "几个小时后", "数小时后",
    "第二天", "次日", "翌日", "到了晚上", "到了夜里", "天黑后", "天亮后",
    "日落后", "太阳落山", "太阳升起", "夜幕降临", "黎明到来",
    "later", "afterward", "afterwards", "thereafter", "eventually",
    "meanwhile", "soon after", "by the time", "next morning", "next day",
    "hours later", "days later", "time passed", "the sun rose", "the sun set",
    "darkness fell", "night fell", "dawn broke",
)

_RECALL_MARKERS = (
    "回忆", "想起", "记得", "忆及", "往事", "多年以前", "很久以前", "当年",
    "remember", "remembered", "recall", "recalled", "memory of", "years ago",
    "years earlier", "long ago", "back when", "flashed back",
)

_SCENE_BREAK_RE = re.compile(
    r"(?:\n\s*(?:---+|\*\*\*+|###)\s*\n|\n\s*场景(?:切换|转换)|\n\s*镜头(?:切换|转向))",
    re.IGNORECASE,
)

# The leading space on " dawn" above avoids matching the suffix of "redawn";
# normalize it for the actual matcher while retaining a simple ordered table.
_TIME_OF_DAY_BANDS = tuple((phrase.strip(), band) for phrase, band in _TIME_OF_DAY_BANDS)


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    if re.fullmatch(r"[A-Za-z][A-Za-z -]*", phrase):
        return re.compile(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", re.IGNORECASE)
    return re.compile(re.escape(phrase), re.IGNORECASE)


_ANCHOR_PATTERNS = tuple(
    (_phrase_pattern(phrase), band, phrase) for phrase, band in _TIME_OF_DAY_BANDS
)


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _has_scene_break(text: str) -> bool:
    return bool(_SCENE_BREAK_RE.search(text))


def _anchors(prose: str) -> list[tuple[int, int, int, str]]:
    found: list[tuple[int, int, int, str]] = []
    for pattern, band, phrase in _ANCHOR_PATTERNS:
        for match in pattern.finditer(prose):
            found.append((match.start(), match.end(), band, match.group(0) or phrase))
    found.sort(key=lambda row: (row[0], row[1], row[2]))
    # Same-span aliases such as "night" and "nightfall" are collapsed to the
    # strongest/latest band, preventing duplicate findings.
    compacted: list[tuple[int, int, int, str]] = []
    for row in found:
        if compacted and row[0] < compacted[-1][1]:
            if row[2] >= compacted[-1][2]:
                compacted[-1] = row
            continue
        compacted.append(row)
    return compacted


def scan_temporal_coherence(scene: TemporalSceneInput) -> list[TemporalCoherenceHit]:
    """Scan one scene for unmarked intra-scene time jumps.

    This is a high-precision advisory tripwire. Non-linear scenes and scenes
    declared at week-or-coarser precision are intentionally skipped.
    """
    if not isinstance(scene, TemporalSceneInput):
        raise TypeError("scene 必须是 TemporalSceneInput")
    if scene.temporal_mode in {"flashback", "flashforward", "concurrent"}:
        return []
    if scene.precision in {"week", "month", "year"}:
        return []
    prose = scene.prose or ""
    anchors = _anchors(prose)
    hits: list[TemporalCoherenceHit] = []

    for previous, current in zip(anchors, anchors[1:]):
        start, _, previous_band, previous_marker = previous
        current_start, current_end, current_band, current_marker = current
        if current_start <= start:
            continue
        between = prose[previous[1]:current_start]
        if _contains_marker(between, _TRANSITION_MARKERS) or _contains_marker(between, _RECALL_MARKERS):
            continue
        if _has_scene_break(between):
            continue
        delta = current_band - previous_band
        if delta >= 3:
            hits.append(TemporalCoherenceHit(
                kind="temporal_teleport",
                severity="warning",
                message=f"时间从“{previous_marker}”跳到“{current_marker}”，中间没有明确过渡。",
                start=previous[0],
                end=current_end,
                marker=current_marker,
            ))
        elif delta <= -2:
            hits.append(TemporalCoherenceHit(
                kind="temporal_drift",
                severity="warning",
                message=f"时间从“{previous_marker}”回到“{current_marker}”，可能造成场景内时间矛盾。",
                start=previous[0],
                end=current_end,
                marker=current_marker,
            ))

    if (
        scene.duration_days is not None
        and scene.duration_days >= 1
        and len(anchors) >= 2
        and not _contains_marker(prose, _TRANSITION_MARKERS)
        and not _has_scene_break(prose)
    ):
        hits.append(TemporalCoherenceHit(
            kind="unrendered_declared_span",
            severity="info",
            message="场景声明跨越至少一天，但正文没有明确的时间推进标记或场景切换。",
            start=None,
            end=None,
        ))
    return hits


def temporal_coherence_report(
    prose: str,
    *,
    duration_days: float | None = None,
    temporal_mode: str | None = "linear",
    precision: str | None = "hour",
) -> dict[str, Any]:
    """Return a prompt-safe report suitable for Novel's review pipeline."""
    hits = scan_temporal_coherence(TemporalSceneInput(
        prose=prose,
        duration_days=duration_days,
        temporal_mode=temporal_mode,
        precision=precision,
    ))
    severity_map = {"warning": "medium", "info": "low"}
    issues = [
        {
            "category": "时间连续性",
            "severity": severity_map.get(hit.severity, "medium"),
            "excerpt": hit.marker,
            "reason": hit.message,
            "suggestion": (
                "补充必要的时间推进、场景切换或过渡动作；如果是回忆/闪回，应明确标记。"
            ),
        }
        for hit in hits
    ]
    return {
        "schema": "spindle-temporal-coherence-v1",
        "backend": "spindle-port",
        "source": {
            "repository": "VerifiedOrganic/spindle",
            "path": "crates/spindle-core/src/temporal/mod.rs",
            "commit": "d88500849b3561b78cd4a80e85443aa66122155d",
            "license": "MIT",
        },
        "hit_count": len(hits),
        "hits": [hit.to_dict() for hit in hits],
        "issues": issues,
        "advisory_only": True,
    }
