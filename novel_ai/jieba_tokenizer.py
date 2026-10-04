"""Bounded Chinese DAG tokenizer adapted from jieba.

Source: fxsjy/jieba, jieba/__init__.py at commit
67fa2e36e72f69d9134b8a1037b83fbb070b9775. See
third_party/jieba/LICENSE and provenance.json.

Novel keeps only the dictionary-prefix DAG and dynamic-programming route
selection. The default path remains dependency-free and deterministic; callers
provide a small project vocabulary when they want names and story terms kept
as multi-character tokens.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite, log
import re
from typing import Any


_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_TOKEN_RE = re.compile(r"[\u3400-\u9fff]+|[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")


def _is_cjk_word(value: str) -> bool:
    return len(value) >= 2 and all("\u3400" <= char <= "\u9fff" for char in value)


def _frequency_map(vocabulary: Iterable[str] | Mapping[str, Any]) -> tuple[dict[str, float], set[str], float]:
    frequencies: dict[str, float] = {}
    if isinstance(vocabulary, Mapping):
        items = vocabulary.items()
    else:
        items = ((word, 1.0) for word in vocabulary)

    for raw_word, raw_frequency in items:
        word = str(raw_word).strip()
        if not _is_cjk_word(word):
            continue
        try:
            frequency = float(raw_frequency)
        except (TypeError, ValueError):
            continue
        if not isfinite(frequency) or frequency <= 0:
            continue
        frequencies[word] = frequencies.get(word, 0.0) + frequency

    prefixes: set[str] = set()
    for word in frequencies:
        prefixes.update(word[:index] for index in range(1, len(word) + 1))
    total = sum(frequencies.values()) or 1.0
    return frequencies, prefixes, total


def segment_chinese(text: str, vocabulary: Iterable[str] | Mapping[str, Any] = ()) -> list[str]:
    """Segment one Chinese run using jieba's prefix-DAG route selection."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text:
        return []

    frequencies, prefixes, total = _frequency_map(vocabulary)
    if not frequencies:
        return list(text)

    dag: dict[int, list[int]] = {}
    length = len(text)
    for start in range(length):
        ends: list[int] = []
        end = start
        while end < length and text[start : end + 1] in prefixes:
            if text[start : end + 1] in frequencies:
                ends.append(end)
            end += 1
        dag[start] = ends or [start]

    route: list[tuple[float, int] | None] = [None] * (length + 1)
    route[length] = (0.0, length)
    log_total = log(total)
    for start in range(length - 1, -1, -1):
        route[start] = max(
            (
                log(frequencies.get(text[start : end + 1], 1.0))
                - log_total
                + route[end + 1][0],
                end,
            )
            for end in dag[start]
        )

    tokens: list[str] = []
    cursor = 0
    while cursor < length:
        end = route[cursor][1]  # type: ignore[index]
        tokens.append(text[cursor : end + 1])
        cursor = end + 1
    return tokens


def segment(text: str, vocabulary: Iterable[str] | Mapping[str, Any] = ()) -> list[str]:
    """Tokenize mixed Chinese/English prose with a bounded jieba-style core."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        value = match.group(0)
        if _CJK_RE.fullmatch(value):
            tokens.extend(segment_chinese(value, vocabulary))
        else:
            tokens.append(value.casefold())
    return tokens
