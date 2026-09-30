from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, asdict
import importlib.util
import re
from statistics import mean, pstdev
from typing import Any


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])")
_PUNCT = "，。！？；：、…“”‘’（）()"


@dataclass
class QualityIssue:
    category: str
    severity: str
    reason: str
    suggestion: str
    excerpt: str = ""


@dataclass
class ProseQualityReport:
    char_count: int
    sentence_count: int
    paragraph_count: int
    unique_char_ratio: float
    bigram_diversity: float
    sentence_length_mean: float
    sentence_length_std: float
    paragraph_length_cv: float
    repeated_sentence_ratio: float
    repeated_paragraph_openings: dict[str, int] = field(default_factory=dict)
    lexical_metrics: dict[str, float | int | str] = field(default_factory=dict)
    optional_backends: dict[str, bool] = field(default_factory=dict)
    correction_samples: list[dict[str, str]] = field(default_factory=list)
    issues: list[QualityIssue] = field(default_factory=list)
    score: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _safe_std(values: list[int]) -> float:
    return float(pstdev(values)) if len(values) > 1 else 0.0


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s.strip()]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]


def _bigram_diversity(text: str) -> float:
    chars = [c for c in _compact(text) if c not in _PUNCT]
    if len(chars) < 2:
        return 0.0
    grams = [chars[i : i + 2] for i in range(len(chars) - 1)]
    return round(len(set(grams)) / len(grams), 4)


def _tokenize(text: str) -> tuple[list[str], str]:
    # Prefer pkuseg for Chinese if installed, then jieba, then a dependency-free
    # character fallback. Optional packages are never required for the core path.
    if importlib.util.find_spec("pkuseg") is not None:
        try:
            import pkuseg
            seg = pkuseg.pkuseg()
            return [t.strip() for t in seg.cut(text) if t.strip()], "pkuseg"
        except Exception:
            pass
    if importlib.util.find_spec("jieba") is not None:
        try:
            import jieba
            return [t.strip() for t in jieba.lcut(text) if t.strip()], "jieba"
        except Exception:
            pass
    return [c for c in _compact(text) if c not in _PUNCT], "char-fallback"


def normalize_chinese(text: str) -> tuple[str, str]:
    """Normalize Chinese script when OpenCC is installed.

    Novel defaults to simplified Chinese. If OpenCC is unavailable or fails,
    return the input unchanged and report the fallback.
    """
    if importlib.util.find_spec("opencc") is None:
        return text, "identity"
    try:
        from opencc import OpenCC
        return OpenCC("t2s").convert(text), "opencc-t2s"
    except Exception:
        return text, "identity"


def _lexical_metrics(text: str) -> dict[str, float | int | str]:
    tokens, backend = _tokenize(text)
    meaningful = [t for t in tokens if t and not all(c in _PUNCT for c in t)]
    n = len(meaningful)
    unique = len(set(meaningful))
    data: dict[str, float | int | str] = {
        "tokenizer": backend,
        "token_count": n,
        "unique_token_count": unique,
        "type_token_ratio": round(unique / n, 4) if n else 0.0,
    }

    if importlib.util.find_spec("lexicalrichness") is not None:
        try:
            from lexicalrichness import LexicalRichness
            # Feed pre-tokenized text so Chinese does not depend on whitespace.
            lex = LexicalRichness(" ".join(meaningful))
            data.update({
                "lexicalrichness": 1,
                "ttr": round(float(lex.ttr), 4),
                "rttr": round(float(lex.rttr), 4),
                "cttr": round(float(lex.cttr), 4),
            })
        except Exception:
            data["lexicalrichness"] = 0
    else:
        data["lexicalrichness"] = 0
    return data


def _pycorrector_samples(text: str, limit: int = 8) -> list[dict[str, str]]:
    if importlib.util.find_spec("pycorrector") is None:
        return []
    try:
        import pycorrector
        corrected, details = pycorrector.correct(text)
        if corrected == text:
            return []
        samples: list[dict[str, str]] = []
        for item in list(details)[:limit]:
            samples.append({"detail": str(item)})
        if not samples:
            samples.append({"detail": "pycorrector 检测到可疑文本差异"})
        return samples
    except Exception:
        return []


def _spacy_signals(text: str) -> dict[str, int | bool]:
    if importlib.util.find_spec("spacy") is None:
        return {"available": False}
    # Do not download models or silently choose an English model for Chinese.
    # If a Chinese pipeline is present the caller may add it later; availability
    # is surfaced now for capability probing.
    return {"available": True}


def analyze_prose_quality(text: str) -> ProseQualityReport:
    normalized, normalization_backend = normalize_chinese(text)
    compact = _compact(normalized)
    sentences = _sentences(normalized)
    paragraphs = _paragraphs(normalized)
    sentence_lengths = [len(_compact(s)) for s in sentences]
    para_lengths = [len(_compact(p)) for p in paragraphs]

    repeated_sentence_count = 0
    sentence_counter = Counter(s for s in sentences if len(_compact(s)) >= 6)
    for count in sentence_counter.values():
        if count > 1:
            repeated_sentence_count += count - 1

    openings = Counter()
    for p in paragraphs:
        clean = re.sub(r'^[“‘"（(\s]+', "", p)
        if clean:
            openings[clean[:5]] += 1
    repeated_openings = {k: v for k, v in openings.items() if v >= 3}

    sentence_mean = mean(sentence_lengths) if sentence_lengths else 0.0
    sentence_std = _safe_std(sentence_lengths)
    para_mean = mean(para_lengths) if para_lengths else 0.0
    para_std = _safe_std(para_lengths)
    paragraph_cv = para_std / para_mean if para_mean else 0.0

    char_set = [c for c in compact if c not in _PUNCT]
    unique_char_ratio = len(set(char_set)) / len(char_set) if char_set else 0.0
    repeated_sentence_ratio = repeated_sentence_count / len(sentences) if sentences else 0.0

    lexical = _lexical_metrics(normalized)
    corrections = _pycorrector_samples(normalized)

    issues: list[QualityIssue] = []
    if repeated_sentence_ratio >= 0.04:
        issues.append(QualityIssue(
            category="重复句",
            severity="high" if repeated_sentence_ratio >= 0.08 else "medium",
            reason=f"重复完整句比例约 {repeated_sentence_ratio:.1%}，容易产生模板化和机械复用感。",
            suggestion="只改重复出现的句子，保留情节事实和人物信息不变。",
        ))
    if repeated_openings:
        sample = "、".join(list(repeated_openings)[:4])
        issues.append(QualityIssue(
            category="段落起句重复",
            severity="medium",
            excerpt=sample,
            reason="多个段落使用相同开头，节奏可能显得机械。",
            suggestion="改变部分段落的进入方式：动作、对白、感官或直接叙述交替使用。",
        ))
    if len(para_lengths) >= 5 and paragraph_cv < 0.28:
        issues.append(QualityIssue(
            category="段落节奏过均匀",
            severity="medium",
            reason=f"段落长度变异系数仅 {paragraph_cv:.2f}。",
            suggestion="根据场景功能拉开段落长度，不要为了变化而随机切段。",
        ))
    if lexical.get("type_token_ratio", 1.0) < 0.28 and int(lexical.get("token_count", 0)) >= 180:
        issues.append(QualityIssue(
            category="词汇重复偏高",
            severity="medium",
            reason=f"分词后的 type-token ratio 为 {lexical['type_token_ratio']}。",
            suggestion="检查高频实词和固定搭配，只替换无意重复，不做同义词机械轮换。",
        ))
    if sentence_mean and sentence_std / sentence_mean < 0.35 and len(sentences) >= 12:
        issues.append(QualityIssue(
            category="句长变化不足",
            severity="low",
            reason=f"句长均值 {sentence_mean:.1f}、标准差 {sentence_std:.1f}，长短句变化偏小。",
            suggestion="按信息密度和动作速度自然调整句长，不要人为随机化。",
        ))
    if corrections:
        issues.append(QualityIssue(
            category="中文纠错候选",
            severity="low",
            reason=f"pycorrector 返回 {len(corrections)} 个候选提示。",
            suggestion="逐项核对后再修；小说中的人名、口语和方言不得自动改写。",
        ))

    penalty = {"low": 4, "medium": 9, "high": 16}
    score = max(0, 100 - sum(penalty.get(i.severity, 5) for i in issues))

    return ProseQualityReport(
        char_count=len(compact),
        sentence_count=len(sentences),
        paragraph_count=len(paragraphs),
        unique_char_ratio=round(unique_char_ratio, 4),
        bigram_diversity=_bigram_diversity(normalized),
        sentence_length_mean=round(sentence_mean, 2),
        sentence_length_std=round(sentence_std, 2),
        paragraph_length_cv=round(paragraph_cv, 4),
        repeated_sentence_ratio=round(repeated_sentence_ratio, 4),
        repeated_paragraph_openings=repeated_openings,
        lexical_metrics=lexical,
        optional_backends={
            "opencc": normalization_backend.startswith("opencc"),
            "pkuseg": lexical.get("tokenizer") == "pkuseg",
            "jieba": lexical.get("tokenizer") == "jieba",
            "lexicalrichness": bool(lexical.get("lexicalrichness")),
            "pycorrector": importlib.util.find_spec("pycorrector") is not None,
            "spacy": bool(_spacy_signals(normalized).get("available")),
        },
        correction_samples=corrections,
        issues=issues,
        score=score,
    )


def quality_review_payload(report: ProseQualityReport) -> dict[str, Any]:
    """Small prompt-safe view; never includes the whole source text."""
    return {
        "score": report.score,
        "metrics": {
            "bigram_diversity": report.bigram_diversity,
            "sentence_length_mean": report.sentence_length_mean,
            "sentence_length_std": report.sentence_length_std,
            "paragraph_length_cv": report.paragraph_length_cv,
            "repeated_sentence_ratio": report.repeated_sentence_ratio,
            "lexical": report.lexical_metrics,
        },
        "issues": [asdict(i) for i in report.issues],
    }
