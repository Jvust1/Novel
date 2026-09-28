from __future__ import annotations

import hashlib
import re
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable

from pydantic import BaseModel, Field

from .reading import extract_reference_text


_CHAPTER_RE = re.compile(
    r"(?m)^\s*(?:第[0-9一二三四五六七八九十百千万零〇两]+[章节卷回]|Chapter\s+\d+)\s*[^\n]*"
)

_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "external_threat": re.compile(r"追杀|围攻|战争|灾难|暴雨|地震|火灾|怪物|敌人|警报|封锁"),
    "interpersonal_conflict": re.compile(r"争吵|质问|误会|背叛|拒绝|威胁|谈判|承诺|秘密"),
    "internal_conflict": re.compile(r"犹豫|恐惧|后悔|羞愧|自责|怀疑|挣扎|想起|不愿"),
    "goal_pressure": re.compile(r"必须|不得不|来不及|最后期限|代价|任务|目标|决定|选择"),
    "mystery_reveal": re.compile(r"发现|真相|线索|证据|身份|秘密|原来|竟然|答案"),
}

_ARC_PATTERNS: dict[str, re.Pattern[str]] = {
    "gain": re.compile(r"获得|拿到|得到|赢得|突破|晋升|救出"),
    "loss": re.compile(r"失去|牺牲|死亡|受伤|失败|崩溃|破裂"),
    "decision": re.compile(r"决定|选择|答应|拒绝|离开|回归|加入"),
    "reversal": re.compile(r"却|然而|但是|突然|没想到|反而|转眼"),
}

_HOOK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("question", re.compile(r"谁|为什么|怎么|难道|究竟|是否")),
    ("immediate_danger", re.compile(r"追杀|警报|爆炸|血|死亡|危险|失踪")),
    ("discovery", re.compile(r"醒来|发现|看见|收到|打开|敲门|电话|消息")),
    ("contradiction", re.compile(r"却|然而|但是|原本|没想到|反而")),
]

_CLIFFHANGER_RE = re.compile(
    r"突然|却发现|门外|脚步|电话|声音|答案|真相|危险|来不及|不知道|无法|未完"
)


class StoryPatternProfile(BaseModel):
    """Deterministic, non-reversible story-pattern features for one reference."""

    source_id: str
    filename: str
    weight: float = 1.0
    chapter_count: int = 0
    total_char_count: int = 0
    opening_hook_types: list[str] = Field(default_factory=list)
    opening_hook_ratio: float = 0.0
    cliffhanger_ratio: float = 0.0
    conflict_signals: dict[str, int] = Field(default_factory=dict)
    arc_markers: dict[str, int] = Field(default_factory=dict)
    pacing: dict[str, float] = Field(default_factory=dict)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class StoryDNA(BaseModel):
    """Weighted aggregate of story-pattern profiles.

    It stores counts, ratios, and provenance hashes only. Reference prose is never
    retained in this object.
    """

    name: str = "story-dna"
    source_count: int
    profiles: list[StoryPatternProfile]
    aggregate: dict[str, object] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _chapter_chunks(text: str) -> tuple[list[str], int]:
    matches = list(_CHAPTER_RE.finditer(text))
    if not matches:
        return ([text] if text.strip() else []), 0
    chunks = [
        text[match.start() : (matches[index + 1].start() if index + 1 < len(matches) else len(text))]
        for index, match in enumerate(matches)
    ]
    return chunks, len(matches)


def _safe_std(values: list[int]) -> float:
    return float(pstdev(values)) if len(values) > 1 else 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _hook_types(opening: str) -> list[str]:
    found = [label for label, pattern in _HOOK_PATTERNS if pattern.search(opening)]
    return found or ["scene_entry"]


def extract_story_pattern(filename: str, data: bytes, *, weight: float = 1.0) -> StoryPatternProfile:
    """Extract explainable story signals without persisting source text."""

    text = extract_reference_text(filename, data)
    chunks, chapter_markers = _chapter_chunks(text)
    compact_text = _compact(text)
    chapter_lengths = [len(_compact(chunk)) for chunk in chunks] or [0]

    hook_types: list[str] = []
    hooked = 0
    cliffhangers = 0
    for chunk in chunks:
        compact = _compact(chunk)
        types = _hook_types(compact[:180])
        hook_types.extend(types)
        hooked += int(types != ["scene_entry"])
        cliffhangers += int(bool(_CLIFFHANGER_RE.search(compact[-180:])))

    conflict_signals = {
        name: len(pattern.findall(text))
        for name, pattern in _SIGNAL_PATTERNS.items()
    }
    arc_markers = {
        name: len(pattern.findall(text))
        for name, pattern in _ARC_PATTERNS.items()
    }

    total_chars = len(compact_text)
    dialogue_chars = sum(len(_compact(match.group(0))) for match in re.finditer(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"", text))
    paragraphs = [part for part in re.split(r"\n\s*\n|\n", text) if part.strip()]
    pacing = {
        "avg_chapter_chars": round(mean(chapter_lengths), 2),
        "chapter_chars_std": round(_safe_std(chapter_lengths), 2),
        "short_chapter_ratio": _ratio(sum(length <= 1800 for length in chapter_lengths), len(chapter_lengths)),
        "long_chapter_ratio": _ratio(sum(length >= 5000 for length in chapter_lengths), len(chapter_lengths)),
        "dialogue_ratio": _ratio(dialogue_chars, total_chars),
        "paragraphs_per_chapter": round(len(paragraphs) / max(len(chunks), 1), 2),
        "chapter_breaks_per_1000_chars": round(chapter_markers / max(total_chars, 1) * 1000, 4),
    }

    notes = [
        "Story DNA 由规则和文本统计提取，不能替代人工剧情分析。",
        "conflict_signals 与 arc_markers 是线索频次，不是质量分数。",
    ]
    if chapter_markers == 0:
        notes.append("未检测到标准章节标题，当前按整篇文本估计节奏。")

    return StoryPatternProfile(
        source_id=hashlib.sha256(data).hexdigest()[:24],
        filename=Path(filename).name,
        weight=max(float(weight), 0.0),
        chapter_count=len(chunks),
        total_char_count=total_chars,
        opening_hook_types=sorted(set(hook_types)),
        opening_hook_ratio=_ratio(hooked, len(chunks)),
        cliffhanger_ratio=_ratio(cliffhangers, len(chunks)),
        conflict_signals=conflict_signals,
        arc_markers=arc_markers,
        pacing=pacing,
        evidence_counts={
            "chapter_markers": chapter_markers,
            "hooked_chapters": hooked,
            "cliffhanger_chapters": cliffhangers,
            "paragraph_count": len(paragraphs),
        },
        notes=notes,
    )


def _weighted_mean(profiles: list[StoryPatternProfile], field: str) -> float:
    weighted = [(profile.pacing.get(field, 0.0), profile.weight) for profile in profiles if profile.weight > 0]
    if not weighted:
        weighted = [(profile.pacing.get(field, 0.0), 1.0) for profile in profiles]
    total = sum(weight for _, weight in weighted)
    return round(sum(value * weight for value, weight in weighted) / total, 4)


def build_story_dna(
    sources: Iterable[tuple[str, bytes, float]],
    *,
    name: str = "story-dna",
) -> StoryDNA:
    material = list(sources)
    profiles = [
        extract_story_pattern(filename, data, weight=weight)
        for filename, data, weight in material
    ]
    if not profiles:
        raise ValueError("Story DNA 至少需要一个参考文件")

    conflict_density: dict[str, float] = {}
    for key in _SIGNAL_PATTERNS:
        values = [
            (
                profile.conflict_signals.get(key, 0) / max(profile.total_char_count, 1) * 1000,
                profile.weight,
            )
            for profile in profiles
        ]
        total = sum(weight if weight > 0 else 1.0 for _, weight in values)
        conflict_density[key] = round(
            sum(value * (weight if weight > 0 else 1.0) for value, weight in values) / total,
            4,
        )

    aggregate = {
        "chapter_count_total": sum(profile.chapter_count for profile in profiles),
        "avg_chapter_chars": _weighted_mean(profiles, "avg_chapter_chars"),
        "chapter_chars_std": _weighted_mean(profiles, "chapter_chars_std"),
        "short_chapter_ratio": _weighted_mean(profiles, "short_chapter_ratio"),
        "long_chapter_ratio": _weighted_mean(profiles, "long_chapter_ratio"),
        "dialogue_ratio": _weighted_mean(profiles, "dialogue_ratio"),
        "opening_hook_ratio": round(
            sum(profile.opening_hook_ratio * (profile.weight if profile.weight > 0 else 1.0) for profile in profiles)
            / sum(profile.weight if profile.weight > 0 else 1.0 for profile in profiles),
            4,
        ),
        "cliffhanger_ratio": round(
            sum(profile.cliffhanger_ratio * (profile.weight if profile.weight > 0 else 1.0) for profile in profiles)
            / sum(profile.weight if profile.weight > 0 else 1.0 for profile in profiles),
            4,
        ),
        "conflict_density_per_1000_chars": conflict_density,
        "hook_types": sorted({hook for profile in profiles for hook in profile.opening_hook_types}),
    }

    recommendations: list[str] = []
    if aggregate["opening_hook_ratio"] >= 0.5:
        recommendations.append("章节开头通常较快进入问题或危险，可在新作中保留明确的开场钩子。")
    if aggregate["cliffhanger_ratio"] >= 0.5:
        recommendations.append("章节结尾存在较多未决信号，可把悬念推进作为候选节奏约束。")
    if aggregate["dialogue_ratio"] >= 0.18:
        recommendations.append("对话占比偏高，场景规划应为对话留出行动和信息变化位置。")
    if not recommendations:
        recommendations.append("当前信号不足以形成强节奏约束，需结合人工样本分析。")

    return StoryDNA(
        name=name,
        source_count=len(profiles),
        profiles=profiles,
        aggregate=aggregate,
        recommendations=recommendations,
        notes=[
            "Story DNA 只保存派生统计、信号和来源哈希，不保存参考小说正文。",
            "本版本是确定性基线；模型抽取和平台 Market DNA 将在后续适配器中加入。",
        ],
    )


def save_story_dna(dna: StoryDNA, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dna.model_dump_json(indent=2), encoding="utf-8")
    return target
