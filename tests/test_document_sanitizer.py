import pytest

from novel_ai.document_sanitizer import is_invisible_codepoint, sanitize_extracted_text


def test_removes_zero_width_bidi_tag_and_annotation_payload_controls():
    raw = "正常\u200b隐形\u202e倒序\U000e0061标签\ufff9注释"
    clean, removed = sanitize_extracted_text(raw)
    assert clean == "正常隐形倒序标签注释"
    assert removed == 4


def test_visible_prose_and_arabic_letters_are_preserved():
    raw = "中文与 العربية text 🙂"
    clean, removed = sanitize_extracted_text(raw)
    assert clean == raw
    assert removed == 0


def test_known_invisible_codepoints_and_invalid_input():
    assert is_invisible_codepoint(0x2066)
    assert is_invisible_codepoint(0xFE0F)
    with pytest.raises(TypeError):
        sanitize_extracted_text(None)
