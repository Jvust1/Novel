from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import re
from statistics import mean
from typing import Any, Sequence

from .reference_similarity import fuzzy_similarity


_SPEECH_VERBS = r"(?:说|问|答|道|喊|叫|嘀咕|低声说|轻声说|冷笑道|笑道|反问)"
_PARTICLES = tuple("吧呢啊呀嘛呗哦嗯吗啦")
_CURVE_HIGH = ("高潮", "爆发", "峰", "climax", "peak", "surge", "high")
_CURVE_RISE = ("上升", "升温", "推进", "rise", "rising")
_CURVE_LOW = ("低谷", "缓和", "平静", "回落", "low", "fall", "quiet", "rest")


@dataclass(frozen=True)
class BehaviorAlert:
    character: str
    chapter_id: str
    score: float
    current_pattern: str
    historical_pattern: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _dialogue_for_character(text: str, name: str) -> list[str]:
    if not name.strip():
        return []
    n = re.escape(name.strip())
    patterns = [
        rf"{n}[^。！？\n]{{0,8}}{_SPEECH_VERBS}[：:]?[“\"]([^”\"]+)[”\"]",
        rf'[“"]([^”"]+)[”"][，,]?[^。！？\\n]{{0,8}}{n}[^。！？\\n]{{0,6}}{_SPEECH_VERBS}',
    ]
    rows: list[str] = []
    for pattern in patterns:
        rows.extend(m.strip() for m in re.findall(pattern, text or "") if m.strip())
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        if row not in seen:
            seen.add(row)
            result.append(row)
    return result


def character_voice_dna(text: str, character_names: Sequence[str]) -> dict[str, Any]:
    """Extract durable per-character dialogue metrics without storing raw dialogue."""
    result: dict[str, Any] = {}
    for name in character_names:
        lines = _dialogue_for_character(text, str(name))
        if not lines:
            continue
        lengths = [len(_compact(line)) for line in lines]
        total = max(1, len(lines))
        ending = Counter(line[-1] for line in lines if line and line[-1] in _PARTICLES)
        result[str(name)] = {
            "line_count": len(lines),
            "avg_line_chars": round(mean(lengths), 2),
            "short_line_ratio": round(sum(x <= 8 for x in lengths) / total, 4),
            "long_line_ratio": round(sum(x >= 24 for x in lengths) / total, 4),
            "question_ratio": round(sum("？" in x or "?" in x for x in lines) / total, 4),
            "exclamation_ratio": round(sum("！" in x or "!" in x for x in lines) / total, 4),
            "ellipsis_ratio": round(sum("……" in x or "..." in x for x in lines) / total, 4),
            "first_person_density": round(sum(x.count("我") for x in lines) / max(1, sum(lengths)), 4),
            "second_person_density": round(sum(x.count("你") for x in lines) / max(1, sum(lengths)), 4),
            "ending_particles": dict(ending.most_common(5)),
        }
    return result


def aggregate_voice_baseline(history: Sequence[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history:
        voices = row.get("voice_dna") or row.get("characters") or {}
        for name, metrics in voices.items():
            if isinstance(metrics, dict) and int(metrics.get("line_count", 0) or 0) > 0:
                buckets[str(name)].append(metrics)
    result: dict[str, Any] = {}
    numeric = (
        "avg_line_chars", "short_line_ratio", "long_line_ratio", "question_ratio",
        "exclamation_ratio", "ellipsis_ratio", "first_person_density", "second_person_density",
    )
    for name, rows in buckets.items():
        total_lines = sum(int(x.get("line_count", 0) or 0) for x in rows)
        if not total_lines:
            continue
        result[name] = {"line_count": total_lines, "chapter_count": len(rows)}
        for key in numeric:
            result[name][key] = round(
                sum(float(x.get(key, 0) or 0) * int(x.get("line_count", 0) or 0) for x in rows) / total_lines,
                4,
            )
        particles = Counter()
        for row in rows:
            particles.update({str(k): int(v) for k, v in (row.get("ending_particles") or {}).items()})
        result[name]["ending_particles"] = dict(particles.most_common(5))
    return result


def voice_drift(current: dict[str, Any], baseline: dict[str, Any], threshold: float = 0.42) -> list[dict[str, Any]]:
    alerts = []
    keys = ("avg_line_chars", "question_ratio", "exclamation_ratio", "ellipsis_ratio", "short_line_ratio")
    for name, now in current.items():
        old = baseline.get(name)
        if not old or int(old.get("line_count", 0) or 0) < 4 or int(now.get("line_count", 0) or 0) < 2:
            continue
        diffs = []
        for key in keys:
            a, b = float(now.get(key, 0) or 0), float(old.get(key, 0) or 0)
            scale = max(1.0 if key == "avg_line_chars" else 0.25, abs(b))
            diffs.append(min(1.0, abs(a - b) / scale))
        score = round(sum(diffs) / len(diffs), 4)
        if score >= threshold:
            alerts.append({
                "character": name,
                "score": score,
                "reason": f"{name} 本章对白节奏/标点习惯偏离长期口吻 DNA {score:.1%}",
                "suggestion": "核对是否为剧情驱动的刻意变化；若不是，恢复人物惯常句长、问答方式和语气。",
            })
    return sorted(alerts, key=lambda x: x["score"], reverse=True)


def behavior_patterns(story_dna: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for beat in story_dna.get("beats") or []:
        parts = [
            str(beat.get("objective", "") or ""),
            str(beat.get("opposition", "") or ""),
            str(beat.get("choice", "") or ""),
            str(beat.get("cost", "") or ""),
            str(beat.get("state_change", "") or ""),
        ]
        rows.append({
            "character": str(beat.get("pov", "") or "(未指定POV)"),
            "pattern": " | ".join(x for x in parts if x.strip()),
        })
    return [x for x in rows if x["pattern"].strip()]


def behavior_repetition(
    current_story_dna: dict[str, Any],
    history: Sequence[dict[str, Any]],
    *,
    threshold: float = 0.76,
) -> dict[str, Any]:
    current = behavior_patterns(current_story_dna)
    alerts: list[BehaviorAlert] = []
    for oldrow in history:
        chapter_id = str(oldrow.get("chapter_id", "") or "")
        olddna = oldrow.get("story_dna") or oldrow
        old = behavior_patterns(olddna)
        for now in current:
            for prev in old:
                if now["character"] != prev["character"]:
                    continue
                score = fuzzy_similarity(now["pattern"], prev["pattern"])
                if score >= threshold:
                    alerts.append(BehaviorAlert(
                        now["character"], chapter_id, round(score, 6), now["pattern"], prev["pattern"]
                    ))
    alerts.sort(key=lambda x: x.score, reverse=True)
    context = ""
    if alerts:
        lines = [
            "【人物行为模式去重】",
            "以下人物的选择→代价→状态变化与历史章过近。保留人物性格，但改变具体决策机制、阻力或代价，不要只换措辞。",
        ]
        for item in alerts[:5]:
            lines.append(f"- {item.character} vs {item.chapter_id}: {item.score:.1%}")
        context = "\n".join(lines)
    return {
        "max_score": alerts[0].score if alerts else 0.0,
        "alerts": [x.to_dict() for x in alerts[:20]],
        "should_avoid": bool(alerts),
        "avoid_context": context,
    }


def _parse_time_hint(value: str) -> tuple[str, float] | None:
    text = _compact(value)
    if not text:
        return None
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if m:
        try:
            return ("date", float(date(int(m.group(1)), int(m.group(2)), int(m.group(3))).toordinal()))
        except ValueError:
            return None
    for label, pattern, scale in (
        ("day", r"第(\d+)(?:天|日)", 1.0),
        ("week", r"第(\d+)周", 1.0),
        ("month", r"第(\d+)月", 1.0),
        ("year", r"第(\d+)年", 1.0),
    ):
        m = re.search(pattern, text)
        if m:
            return (label, float(m.group(1)) * scale)
    return None


def timeline_contradictions(story_state: dict[str, Any]) -> list[dict[str, Any]]:
    events = list(story_state.get("timeline") or [])
    alerts: list[dict[str, Any]] = []
    previous: dict[str, tuple[float, str]] = {}
    seen_event_time: dict[str, tuple[str, float]] = {}
    for idx, event in enumerate(events):
        hint = str(event.get("time_hint", "") or "")
        parsed = _parse_time_hint(hint)
        desc = _compact(str(event.get("description", "") or ""))
        if parsed:
            unit, value = parsed
            if unit in previous and value < previous[unit][0]:
                alerts.append({
                    "type": "time_reversal",
                    "chapter_id": str(event.get("chapter_id", "")),
                    "reason": f"时间线从 {previous[unit][1]} 回退到 {hint}",
                    "index": idx,
                })
            previous[unit] = (value, hint)
            if desc:
                old = seen_event_time.get(desc)
                if old and old != parsed:
                    alerts.append({
                        "type": "same_event_conflicting_time",
                        "chapter_id": str(event.get("chapter_id", "")),
                        "reason": f"同一事件出现冲突时间：{old} vs {parsed}",
                        "index": idx,
                    })
                else:
                    seen_event_time[desc] = parsed
    return alerts


def foreshadow_lifecycle(story_state: dict[str, Any], chapter_order: Sequence[str]) -> dict[str, Any]:
    order = {str(ch): i for i, ch in enumerate(chapter_order)}
    current = max(order.values(), default=-1)
    items = list(story_state.get("foreshadowing") or [])
    status = Counter(str(x.get("status", "planted") or "planted") for x in items)
    overdue, stagnant, lifetimes = [], [], []
    for item in items:
        planted = str(item.get("planted_chapter", "") or item.get("chapter_id", "") or "")
        last = str(item.get("last_chapter", "") or planted)
        pidx = order.get(planted)
        lidx = order.get(last, pidx)
        age = (current - pidx) if pidx is not None and current >= pidx else None
        since_touch = (current - lidx) if lidx is not None and current >= lidx else None
        row = {
            "id": str(item.get("id", "")),
            "description": str(item.get("description", "")),
            "status": str(item.get("status", "planted")),
            "age_chapters": age,
            "chapters_since_touch": since_touch,
        }
        if row["status"] != "resolved" and age is not None and age >= 12:
            overdue.append(row)
        if row["status"] != "resolved" and since_touch is not None and since_touch >= 8:
            stagnant.append(row)
        if row["status"] == "resolved" and pidx is not None and lidx is not None and lidx >= pidx:
            lifetimes.append(lidx - pidx)
    resolved = status.get("resolved", 0)
    return {
        "total": len(items),
        "status_counts": dict(status),
        "resolved_ratio": round(resolved / len(items), 4) if items else 0.0,
        "avg_resolve_lifetime": round(sum(lifetimes) / len(lifetimes), 2) if lifetimes else None,
        "overdue": overdue,
        "stagnant": stagnant,
    }


def _intensity(dna: dict[str, Any]) -> float:
    beats = list(dna.get("beats") or [])
    scenes = max(1, len(beats))
    structural = (
        int(dna.get("hook_count", 0) or 0)
        + int(dna.get("choice_count", 0) or 0)
        + int(dna.get("cost_count", 0) or 0)
        + int(dna.get("state_change_count", 0) or 0)
    ) / (4 * scenes)
    curve = str(dna.get("tension_curve", "") or "").lower()
    bias = 0.0
    if any(k in curve for k in _CURVE_HIGH):
        bias += 0.22
    elif any(k in curve for k in _CURVE_RISE):
        bias += 0.10
    if any(k in curve for k in _CURVE_LOW):
        bias -= 0.18
    return round(max(0.0, min(1.0, 0.22 + 0.58 * structural + bias)), 4)


def tension_density(history: Sequence[dict[str, Any]], window: int = 8) -> dict[str, Any]:
    rows = []
    for row in history:
        dna = row.get("story_dna") or row
        score = _intensity(dna)
        rows.append({
            "chapter_id": str(row.get("chapter_id", "")),
            "score": score,
            "band": "high" if score >= 0.68 else ("low" if score <= 0.34 else "mid"),
        })
    high = sum(x["band"] == "high" for x in rows)
    low = sum(x["band"] == "low" for x in rows)
    recent = rows[-window:]
    warnings = []
    if recent:
        high_recent = sum(x["band"] == "high" for x in recent) / len(recent)
        low_recent = sum(x["band"] == "low" for x in recent) / len(recent)
        if len(recent) >= 5 and high_recent >= 0.60:
            warnings.append("最近章节高潮/高压段过密，可能缺少呼吸和蓄力空间。")
        if len(recent) >= 5 and low_recent >= 0.70:
            warnings.append("最近章节低压/低谷段过密，可能缺少推进和兑现。")
    high_streak = low_streak = max_high = max_low = 0
    for row in rows:
        if row["band"] == "high":
            high_streak += 1; low_streak = 0
        elif row["band"] == "low":
            low_streak += 1; high_streak = 0
        else:
            high_streak = low_streak = 0
        max_high = max(max_high, high_streak); max_low = max(max_low, low_streak)
    if max_high >= 4:
        warnings.append(f"出现连续 {max_high} 章高强度段，检查高潮是否透支。")
    if max_low >= 5:
        warnings.append(f"出现连续 {max_low} 章低强度段，检查中段是否失速。")
    return {
        "chapters": rows,
        "high_density": round(high / len(rows), 4) if rows else 0.0,
        "low_density": round(low / len(rows), 4) if rows else 0.0,
        "max_high_streak": max_high,
        "max_low_streak": max_low,
        "warnings": warnings,
    }


def build_longform_health(
    *,
    current_text: str,
    character_names: Sequence[str],
    voice_history: Sequence[dict[str, Any]],
    current_story_dna: dict[str, Any],
    story_dna_history: Sequence[dict[str, Any]],
    story_state: dict[str, Any],
    chapter_order: Sequence[str],
    observed_entities: Sequence[str] = (),
    canonical_aliases: dict[str, Sequence[str]] | None = None,
    entity_matcher: Any | None = None,
) -> dict[str, Any]:
    current_voice = character_voice_dna(current_text, character_names)
    voice_base = aggregate_voice_baseline(voice_history)
    voice_alerts = voice_drift(current_voice, voice_base)
    behavior = behavior_repetition(current_story_dna, story_dna_history)
    timeline = timeline_contradictions(story_state)
    foreshadow = foreshadow_lifecycle(story_state, chapter_order)
    tension = tension_density([*story_dna_history, {"chapter_id": chapter_order[-1] if chapter_order else "", "story_dna": current_story_dna}])
    entity_alias_drift: list[dict[str, Any]] = []
    if entity_matcher is not None and canonical_aliases and observed_entities:
        finder = getattr(entity_matcher, "find_drift", None)
        if not callable(finder):
            raise TypeError("entity_matcher must provide find_drift()")
        entity_alias_drift = [
            item.to_dict() if callable(getattr(item, "to_dict", None)) else dict(item)
            for item in finder(observed_entities, canonical_aliases)
        ]

    guard_lines = ["【长篇一致性约束】"]
    for row in voice_alerts[:4]:
        guard_lines.append(f"- 人物口吻：{row['reason']}")
    for row in timeline[:4]:
        guard_lines.append(f"- 时间线矛盾：{row['reason']}")
    for row in foreshadow["overdue"][:4]:
        guard_lines.append(f"- 伏笔过期候选：{row['id']} 已悬置 {row['age_chapters']} 章")
    for warning in tension["warnings"][:3]:
        guard_lines.append(f"- 节奏：{warning}")
    for row in entity_alias_drift[:4]:
        guard_lines.append(
            f"- 实体别名：{row.get('observed','')} 可能应为 {row.get('canonical','')} "
            f"(相似度 {float(row.get('score',0.0)):.1f})"
        )
    if len(guard_lines) == 1:
        guard_lines.append("- 当前未发现需要写入生成上下文的长篇一致性告警。")

    return {
        "voice_dna": current_voice,
        "voice_baseline": voice_base,
        "voice_drift": voice_alerts,
        "behavior_repetition": behavior,
        "timeline_contradictions": timeline,
        "foreshadow_lifecycle": foreshadow,
        "tension_density": tension,
        "entity_alias_drift": entity_alias_drift,
        "guard_context": "\n".join(guard_lines),
    }


def behavior_review_payload(report: dict[str, Any]) -> dict[str, Any]:
    issues = []
    for row in list(report.get("alerts") or [])[:5]:
        issues.append({
            "category": "人物行为模式重复",
            "severity": "high" if float(row.get("score", 0.0)) >= 0.88 else "medium",
            "excerpt": "",
            "reason": (
                f"{row.get('character','(未知人物)')} 与历史章节 {row.get('chapter_id','')} 的"
                f"选择/代价/状态变化模式相似度 {float(row.get('score',0.0)):.1%}。"
            ),
            "suggestion": "改变具体决策、阻力来源、代价或后续状态，不要只改表面措辞。",
        })
    return {"issues": issues}


def voice_review_payload(alerts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    for row in list(alerts)[:5]:
        issues.append({
            "category": "人物口吻漂移",
            "severity": "medium" if float(row.get("score", 0.0)) < 0.70 else "high",
            "excerpt": "",
            "reason": str(row.get("reason", "")),
            "suggestion": str(row.get("suggestion", "")),
        })
    return {"issues": issues}
