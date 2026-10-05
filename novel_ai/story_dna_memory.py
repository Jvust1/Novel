from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .reference_similarity import event_sequence_similarity


@dataclass(frozen=True)
class StoryDNAMatch:
    chapter_id: str
    score: float
    event_similarity: float
    structure_similarity: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoryDNASimilarityReport:
    max_score: float
    matches: list[StoryDNAMatch]
    should_avoid: bool
    avoid_context: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _structure_similarity(current: dict[str, Any], old: dict[str, Any]) -> float:
    keys = ["hook_count", "choice_count", "cost_count", "state_change_count"]
    if not keys:
        return 0.0
    parts: list[float] = []
    for key in keys:
        a = float(current.get(key, 0) or 0)
        b = float(old.get(key, 0) or 0)
        if a == b == 0:
            parts.append(1.0)
        else:
            parts.append(max(0.0, 1.0 - abs(a - b) / max(1.0, a, b)))

    # Same tension-curve label is a weak structural signal, not a verdict.
    if str(current.get("tension_curve", "")).strip() and (
        str(current.get("tension_curve", "")).strip()
        == str(old.get("tension_curve", "")).strip()
    ):
        parts.append(1.0)
    return round(sum(parts) / len(parts), 6) if parts else 0.0


def compare_story_dna(
    current: dict[str, Any],
    history: Sequence[dict[str, Any]],
    *,
    threshold: float = 0.72,
    high_threshold: float = 0.86,
) -> StoryDNASimilarityReport:
    """Compare one approved plan's Story DNA with prior chapters.

    Event sequence carries most weight; structural counts/tension are a weaker
    signal. The result is used to diversify causality and choices, not to force
    random surface variation.
    """
    rows: list[StoryDNAMatch] = []
    current_events = list(current.get("event_sequence") or [])
    for item in history:
        old = item.get("story_dna") or item
        event = event_sequence_similarity(current_events, list(old.get("event_sequence") or []))
        structure = _structure_similarity(current, old)
        score = round(event * 0.78 + structure * 0.22, 6)
        reasons: list[str] = []
        if event >= threshold:
            reasons.append(f"事件序列相似 {event:.1%}")
        if structure >= 0.85:
            reasons.append(f"场景结构相似 {structure:.1%}")
        if score >= threshold:
            rows.append(
                StoryDNAMatch(
                    chapter_id=str(item.get("chapter_id") or old.get("chapter_id") or ""),
                    score=score,
                    event_similarity=event,
                    structure_similarity=structure,
                    reasons=reasons,
                )
            )
    rows.sort(key=lambda x: x.score, reverse=True)
    max_score = rows[0].score if rows else 0.0
    should_avoid = max_score >= threshold

    avoid_context = ""
    if should_avoid:
        top = rows[:3]
        lines = [
            "【历史 Story DNA 去重约束】",
            "当前章计划与历史章节存在套路/事件链近似。保持本章既定事实和人物动机，但必须改变实现路径，优先改变：人物选择、阻力来源、因果链、代价、状态变化或信息释放顺序。不要只做同义改写。",
        ]
        for row in top:
            level = "高风险" if row.score >= high_threshold else "中风险"
            lines.append(
                f"- {level} 历史章 {row.chapter_id or '(未知)'}：综合 {row.score:.1%}，"
                f"事件 {row.event_similarity:.1%}，结构 {row.structure_similarity:.1%}"
            )
        avoid_context = "\n".join(lines)

    return StoryDNASimilarityReport(
        max_score=max_score,
        matches=rows,
        should_avoid=should_avoid,
        avoid_context=avoid_context,
    )


def story_dna_review_payload(report: StoryDNASimilarityReport) -> dict[str, Any]:
    issues = []
    for row in report.matches[:3]:
        issues.append(
            {
                "category": "历史剧情套路重复",
                "severity": "high" if row.score >= 0.86 else "medium",
                "excerpt": "",
                "reason": (
                    f"与历史章节 {row.chapter_id or '(未知)'} 的 Story DNA 综合相似度"
                    f" {row.score:.1%}（事件 {row.event_similarity:.1%}，结构 {row.structure_similarity:.1%}）。"
                ),
                "suggestion": "改变人物选择、阻力、因果链、代价或状态变化；不要只改措辞。",
            }
        )
    return {
        "max_score": report.max_score,
        "should_avoid": report.should_avoid,
        "issues": issues,
    }
