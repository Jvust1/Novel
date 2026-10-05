"""spaCy filter_spans, adapted to lightweight character-offset span objects.

Copyright (C) 2016-2024 ExplosionAI GmbH, 2016 spaCy GmbH, 2015 Matthew Honnibal.
MIT License: see third_party/spacy/LICENSE.
Source: explosion/spaCy @ 26b4d1dc04a812f426e4bef3e8a1b6f159d6f048,
spacy/util.py:filter_spans. Only type annotations and the explanatory docstring
are adapted; longest-first selection and overlap removal are unchanged.
"""

from typing import Iterable, Protocol, TypeVar


class Span(Protocol):
    start: int
    end: int


SpanT = TypeVar("SpanT", bound=Span)


def filter_spans(spans: Iterable[SpanT]) -> list[SpanT]:
    """Prefer the first longest span when spans overlap; retain source order."""
    get_sort_key = lambda span: (span.end - span.start, -span.start)
    sorted_spans = sorted(spans, key=get_sort_key, reverse=True)
    result = []
    seen_tokens: set[int] = set()
    for span in sorted_spans:
        # Check for end - 1 here because boundaries are inclusive
        if span.start not in seen_tokens and span.end - 1 not in seen_tokens:
            result.append(span)
            seen_tokens.update(range(span.start, span.end))
    result = sorted(result, key=lambda span: span.start)
    return result
