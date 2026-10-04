"""Dependency-free lexical diversity metrics adapted from LexicalRichness.

Source: LSYS/LexicalRichness, ``lexicalrichness/lexicalrichness.py`` at
commit 69e6b8f381d6b86ec826911c3f0bb2fb298aac25. See
``third_party/lexicalrichness/LICENSE`` and ``provenance.json``.

The implementation keeps only deterministic TTR, MATTR and MTLD primitives and
uses Novel's own conservative tokenization. It is diagnostic evidence, never an
acceptance gate and never an instruction to mechanically replace words.
"""
from __future__ import annotations

from collections.abc import Iterable
import re
from statistics import mean
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[一-鿿]|\d+")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English prose without an external dependency."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return [match.group(0).casefold() for match in _TOKEN_RE.finditer(text)]


def _validated_tokens(tokens: Iterable[str]) -> list[str]:
    result = [str(token).casefold() for token in tokens if str(token).strip()]
    return result


def ttr(tokens: Iterable[str]) -> float:
    """Type-token ratio, ``unique tokens / total tokens``."""
    words = _validated_tokens(tokens)
    return len(set(words)) / len(words) if words else 0.0


def mattr(tokens: Iterable[str], window_size: int = 100) -> float:
    """Moving-average TTR adapted from LexicalRichness.MATTR."""
    words = _validated_tokens(tokens)
    if type(window_size) is not int or window_size < 1:
        raise ValueError("window_size must be a positive integer")
    if not words:
        return 0.0
    if window_size > len(words):
        window_size = len(words)
    scores = [
        len(set(words[index:index + window_size])) / window_size
        for index in range(len(words) - window_size + 1)
    ]
    return mean(scores) if scores else 0.0


def mtld(tokens: Iterable[str], threshold: float = 0.72) -> float:
    """Bidirectional MTLD adapted from LexicalRichness.MTLD."""
    words = _validated_tokens(tokens)
    if not words:
        return 0.0
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")

    def sub_measure(sequence: Iterable[str]) -> float:
        terms: set[str] = set()
        word_count = 0
        factor_count = 0.0
        last_ttr = 1.0
        for word in sequence:
            word_count += 1
            terms.add(word)
            last_ttr = len(terms) / word_count
            if last_ttr <= threshold:
                word_count = 0
                terms = set()
                factor_count += 1.0
        if word_count > 0:
            factor_count += (1.0 - last_ttr) / (1.0 - threshold)
        if factor_count == 0.0:
            whole_ttr = len(set(words)) / len(words)
            factor_count = 1.0 if whole_ttr == 1.0 else (1.0 - whole_ttr) / (1.0 - threshold)
        return len(words) / factor_count

    return mean((sub_measure(words), sub_measure(reversed(words))))


def lexical_richness_report(text: str, *, window_size: int = 100,
                            threshold: float = 0.72) -> dict[str, Any]:
    """Return bounded, JSON-safe lexical diversity evidence for review reports."""
    words = tokenize(text)
    return {
        "schema": "lexical-richness-v1",
        "backend": "lexicalrichness-port",
        "source": {
            "repository": "LSYS/LexicalRichness",
            "path": "lexicalrichness/lexicalrichness.py",
            "commit": "69e6b8f381d6b86ec826911c3f0bb2fb298aac25",
            "license": "MIT",
        },
        "token_count": len(words),
        "unique_token_count": len(set(words)),
        "ttr": round(ttr(words), 4),
        "mattr": round(mattr(words, window_size), 4),
        "mtld": round(mtld(words, threshold), 4),
        "advisory_only": True,
    }


def lexical_richness_review_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Expose a conservative issue only for sufficiently long low-diversity text."""
    count = int(report.get("token_count", 0))
    issues: list[dict[str, str]] = []
    if count >= 180 and float(report.get("mattr", 1.0)) < 0.28:
        issues.append({
            "category": "词汇多样性",
            "severity": "low",
            "excerpt": "",
            "reason": f"滑动窗口词汇多样性为 {report['mattr']:.3f}，可能存在较多无意重复。",
            "suggestion": "核对高频实词是否承载不同语义；不要为了提高指标机械替换词语。",
        })
    return {"issues": issues}
