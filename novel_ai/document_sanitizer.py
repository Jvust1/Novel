"""Remove invisible Unicode controls from extracted reference documents.

Adapted from book_to_skill/sanitize.py in book-to-skill (MIT).
See third_party/book-to-skill/LICENSE and provenance-sanitizer.json.
The port keeps the upstream code-point groups used for hidden-text and
bidirectional spoofing attacks; it does not rewrite visible prose.
"""

from __future__ import annotations


_ZERO_WIDTH = frozenset({
    0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD,
    0x034F, 0x180E, 0x2061, 0x2062, 0x2063, 0x2064,
})
_BIDI_CONTROLS = frozenset({
    0x200E, 0x200F, 0x061C, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
})
_INVISIBLE_LETTERS = frozenset({0x115F, 0x1160, 0x3164, 0xFFA0})
_ANNOTATION_CONTROLS = frozenset({0xFFF9, 0xFFFA, 0xFFFB})
_TAG_BLOCK = (0xE0000, 0xE007F)
_VARIATION_SELECTORS = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))
_MUSICAL_CONTROLS = (0x1D173, 0x1D17A)


def is_invisible_codepoint(codepoint: int) -> bool:
    """Return whether a code point can hide or reorder extracted text."""
    if codepoint in _ZERO_WIDTH | _BIDI_CONTROLS | _INVISIBLE_LETTERS | _ANNOTATION_CONTROLS:
        return True
    ranges = (_TAG_BLOCK, *_VARIATION_SELECTORS, _MUSICAL_CONTROLS, (0x206A, 0x206F))
    return any(low <= codepoint <= high for low, high in ranges)


def sanitize_extracted_text(text: str) -> tuple[str, int]:
    """Strip invisible controls and report how many were removed."""
    if not isinstance(text, str):
        raise TypeError("extracted text must be a string")
    kept: list[str] = []
    removed = 0
    for char in text:
        if is_invisible_codepoint(ord(char)):
            removed += 1
        else:
            kept.append(char)
    return "".join(kept), removed
