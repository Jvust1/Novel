"""Maximal-match text segmentation adapted from OpenCC.

Source: BYVoid/OpenCC, src/MaxMatchSegmentation.cpp at commit
3ac34aa439a9908dd49fa92b5174b46314787ac2. See
third_party/opencc/LICENSE and provenance.json.

Novel keeps the bounded prefix lookup and longest-match scan, while accepting
an explicit caller-owned conversion dictionary. No OpenCC dictionaries or
runtime dependency are bundled.
"""
from __future__ import annotations

from collections.abc import Mapping


def _ordered_keys(mapping: Mapping[str, str]) -> tuple[str, ...]:
    if not isinstance(mapping, Mapping):
        raise TypeError("mapping must be a mapping")
    keys = {
        str(key): str(value)
        for key, value in mapping.items()
        if str(key) and str(value) != ""
    }
    return tuple(sorted(keys, key=lambda item: (-len(item), item)))


def max_match_segments(text: str, mapping: Mapping[str, str]) -> list[str]:
    """Split text with OpenCC-style longest dictionary-prefix matching."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    keys = _ordered_keys(mapping)
    if not text or not keys:
        return [text] if text else []

    segments: list[str] = []
    cursor = 0
    while cursor < len(text):
        matched = next((key for key in keys if text.startswith(key, cursor)), None)
        if matched is None:
            segments.append(text[cursor])
            cursor += 1
        else:
            segments.append(matched)
            cursor += len(matched)
    return segments


def convert_with_dictionary(text: str, mapping: Mapping[str, str]) -> str:
    """Apply explicit phrase/character replacements after max-match scanning."""
    return "".join(str(mapping.get(segment, segment))
                   for segment in max_match_segments(text, mapping))
