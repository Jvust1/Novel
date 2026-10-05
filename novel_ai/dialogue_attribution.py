"""Conservative named-speaker attribution with licensed spaCy span filtering.

Only known character names and explicit speech verbs are considered. This is
not a semantic dialogue model: ambiguous/multi-name attributions are omitted.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Sequence

from ._vendor.spacy_spans import filter_spans


ATTRIBUTION_VERSION = 2
_SPEECH_VERBS = r"(?:冷笑道|笑道|说道|回答|反问|嘀咕|说|问|答|道|喊|叫)"
_SPEECH_ADVERB = r"(?:(?:低声|轻声|小声|大声|高声|沉声|厉声|缓缓|轻轻|冷冷|平静|笑着|冷笑着|叹息着)(?:地)?)?"


@dataclass(frozen=True)
class NameSpan:
    start: int
    end: int
    name: str


def attributed_dialogue(text: str, names: Sequence[str]) -> dict[str, list[str]]:
    """Assign a quote only when exactly one registered name matches its tag."""
    canonical = list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))
    spans = filter_spans(
        NameSpan(match.start(), match.end(), name)
        for name in canonical
        for match in re.finditer(re.escape(name), text)
    )
    allowed = {(span.start, span.end, span.name) for span in spans}
    candidates: dict[tuple[int, int], set[str]] = defaultdict(set)
    for name in canonical:
        n = re.escape(name)
        patterns = [
            rf'(?P<name>{n}){_SPEECH_ADVERB}{_SPEECH_VERBS}[：:]?[“"](?P<speech>[^”"]+)[”"]',
            rf'[“"](?P<speech>[^”"]+)[”"][，,]?[ \t]*(?P<name>{n}){_SPEECH_ADVERB}{_SPEECH_VERBS}(?=[。！？\n，,：:“”" \t]|$)(?![：:]?[ \t]*[“"])',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                start, end = match.span("name")
                if (start, end, name) in allowed:
                    speech_start, speech_end = match.span("speech")
                    if start < speech_start:
                        # Include the complete local clause, so a distant actor
                        # cannot make its addressee look like the only speaker.
                        tag_start = max((text.rfind(mark, 0, start) for mark in '。！？\n，,“”"'), default=-1) + 1
                        tag_end = speech_start
                        if text[:start].rstrip().endswith(("对", "向", "跟", "朝", "冲", "给", "替")):
                            continue
                    else:
                        tag_start, tag_end = speech_end, match.end()
                    tag_names = {span.name for span in spans if span.start >= tag_start and span.end <= tag_end}
                    candidates[(speech_start, speech_end)].update(tag_names)
    result: dict[str, list[str]] = defaultdict(list)
    for (start, end), speakers in sorted(candidates.items()):
        if len(speakers) != 1:
            continue
        name = next(iter(speakers))
        dialogue = text[start:end].strip()
        if dialogue and dialogue not in result[name]:
            result[name].append(dialogue)
    return dict(result)
