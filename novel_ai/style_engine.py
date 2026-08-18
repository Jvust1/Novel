from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from statistics import mean, pstdev

from .models import StyleFingerprint


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])")
_DIALOGUE = re.compile(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"")

_AI_PATTERNS: dict[str, re.Pattern[str]] = {
    "仿佛/似乎过密": re.compile(r"仿佛|似乎|宛如|如同"),
    "弱动作副词过密": re.compile(r"微微|缓缓|轻轻|淡淡|悄然|默默"),
    "模板化心理": re.compile(r"不由得|心中一动|心头一震|心里咯噔|心底(?:泛起|升起)"),
    "模板化眼神": re.compile(r"眼底|眸中|眼中闪过|目光微微|眼神复杂"),
    "总结式转折": re.compile(r"不是.{0,24}而是"),
    "解释性收束": re.compile(r"这一刻|那一刻|他终于明白|她终于明白|这意味着"),
}


def _clean_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _nonspace_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _safe_std(values: list[int]) -> float:
    return float(pstdev(values)) if len(values) > 1 else 0.0


def _ratio(count: float, total: float) -> float:
    return round(count / total, 4) if total else 0.0


def _bigram_diversity(text: str) -> float:
    chars = [c for c in re.sub(r"\s+", "", text) if c not in "，。！？；：、…“”‘’()（）"]
    if len(chars) < 2:
        return 0.0
    bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    return round(len(set(bigrams)) / len(bigrams), 4)


def analyze_style(text: str, name: str = "reference") -> StyleFingerprint:
    """Extract reversible-free, explainable surface style statistics.

    This function intentionally does not store source prose. The caller may store the
    returned fingerprint and a hashed reference signature instead.
    """
    text = _clean_text(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]

    sentence_lengths = [_nonspace_len(s) for s in sentences] or [0]
    paragraph_lengths = [_nonspace_len(p) for p in paragraphs] or [0]
    total_chars = max(_nonspace_len(text), 1)
    dialogue_chars = sum(_nonspace_len(m.group(0)) for m in _DIALOGUE.finditer(text))

    metaphor_count = len(re.findall(r"仿佛|似乎|宛如|如同|像是|好像", text))
    punctuation_count = len(re.findall(r"[，。！？；：、…]", text))

    return StyleFingerprint(
        name=name,
        avg_sentence_chars=round(mean(sentence_lengths), 2),
        sentence_std=round(_safe_std(sentence_lengths), 2),
        short_sentence_ratio=_ratio(sum(1 for n in sentence_lengths if n <= 12), len(sentence_lengths)),
        long_sentence_ratio=_ratio(sum(1 for n in sentence_lengths if n >= 36), len(sentence_lengths)),
        avg_paragraph_chars=round(mean(paragraph_lengths), 2),
        paragraph_std=round(_safe_std(paragraph_lengths), 2),
        dialogue_ratio=_ratio(dialogue_chars, total_chars),
        exclamation_density=_ratio(text.count("！") + text.count("!"), total_chars) * 1000,
        ellipsis_density=_ratio(text.count("……") + text.count("..."), total_chars) * 1000,
        metaphor_marker_density=round(metaphor_count / total_chars * 1000, 3),
        lexical_diversity=_bigram_diversity(text),
        rhythm_notes=(
            "短句偏多" if _ratio(sum(1 for n in sentence_lengths if n <= 12), len(sentence_lengths)) > 0.35
            else "长短句混合"
        ),
        custom_notes=[f"标点密度约 {round(punctuation_count / total_chars * 1000, 1)} / 千字"],
    )


def blend_styles(weighted: list[tuple[StyleFingerprint, float]], name: str = "composite") -> StyleFingerprint:
    valid = [(fp, max(float(w), 0.0)) for fp, w in weighted if w > 0]
    if not valid:
        return StyleFingerprint(name=name)
    total_w = sum(w for _, w in valid)

    numeric_fields = [
        "avg_sentence_chars",
        "sentence_std",
        "short_sentence_ratio",
        "long_sentence_ratio",
        "avg_paragraph_chars",
        "paragraph_std",
        "dialogue_ratio",
        "exclamation_density",
        "ellipsis_density",
        "metaphor_marker_density",
        "lexical_diversity",
    ]
    values: dict[str, float] = {}
    for field in numeric_fields:
        values[field] = round(sum(getattr(fp, field) * w for fp, w in valid) / total_w, 4)

    return StyleFingerprint(
        name=name,
        source_count=sum(fp.source_count for fp, _ in valid),
        **values,
        rhythm_notes="；".join(fp.rhythm_notes for fp, _ in valid if fp.rhythm_notes),
        narrative_distance="；".join(fp.narrative_distance for fp, _ in valid if fp.narrative_distance),
        pov_preference="；".join(fp.pov_preference for fp, _ in valid if fp.pov_preference),
        action_psychology_environment_balance="；".join(
            fp.action_psychology_environment_balance for fp, _ in valid if fp.action_psychology_environment_balance
        ),
        diction="；".join(fp.diction for fp, _ in valid if fp.diction),
        emotion_expression="；".join(fp.emotion_expression for fp, _ in valid if fp.emotion_expression),
        imagery_notes="；".join(fp.imagery_notes for fp, _ in valid if fp.imagery_notes),
        avoid_patterns=list(dict.fromkeys(p for fp, _ in valid for p in fp.avoid_patterns)),
        custom_notes=list(dict.fromkeys(n for fp, _ in valid for n in fp.custom_notes)),
    )


def build_reference_signature(text: str, shingle_chars: int = 18, max_hashes: int = 6000) -> set[str]:
    """Build non-reversible hashes used to flag suspiciously close reuse."""
    compact = re.sub(r"\s+", "", _clean_text(text))
    if len(compact) < shingle_chars:
        return set()
    step = max(1, math.ceil((len(compact) - shingle_chars + 1) / max_hashes))
    hashes: set[str] = set()
    for i in range(0, len(compact) - shingle_chars + 1, step):
        chunk = compact[i : i + shingle_chars]
        hashes.add(hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:20])
    return hashes


def reference_overlap(text: str, reference_hashes: set[str], shingle_chars: int = 18) -> float:
    compact = re.sub(r"\s+", "", _clean_text(text))
    if len(compact) < shingle_chars or not reference_hashes:
        return 0.0
    hashes = {
        hashlib.sha256(compact[i : i + shingle_chars].encode("utf-8")).hexdigest()[:20]
        for i in range(len(compact) - shingle_chars + 1)
    }
    return round(len(hashes & reference_hashes) / max(len(hashes), 1), 4)


def detect_ai_flavor(text: str) -> dict:
    """Heuristic prose signals. These are warnings, not a binary AI detector."""
    text = _clean_text(text)
    total_chars = max(_nonspace_len(text), 1)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    para_lengths = [_nonspace_len(p) for p in paragraphs]

    pattern_hits = {
        label: len(pattern.findall(text))
        for label, pattern in _AI_PATTERNS.items()
    }
    density = {label: round(count / total_chars * 1000, 3) for label, count in pattern_hits.items()}

    repeated_openings = Counter()
    for p in paragraphs:
        clean = re.sub(r"^[“‘\"（(\s]+", "", p)
        if clean:
            repeated_openings[clean[:4]] += 1
    repeated = {k: v for k, v in repeated_openings.items() if v >= 3}

    uniformity = 0.0
    if len(para_lengths) >= 4 and mean(para_lengths) > 0:
        uniformity = round(1 - min(_safe_std(para_lengths) / mean(para_lengths), 1), 3)

    warnings: list[str] = []
    if sum(pattern_hits.values()) / total_chars * 1000 > 6:
        warnings.append("模板词/弱化词密度偏高，建议只修高密度段落，不要全局禁词。")
    if uniformity > 0.72:
        warnings.append("段落长度过于均匀，节奏可能呈现模型化排布。")
    if repeated:
        warnings.append("多个段落出现相同开头，建议检查机械性重复。")

    return {
        "pattern_hits": pattern_hits,
        "density_per_1000_chars": density,
        "paragraph_uniformity": uniformity,
        "repeated_paragraph_openings": repeated,
        "warnings": warnings,
    }
