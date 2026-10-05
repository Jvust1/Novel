from novel_ai.models import StyleFingerprint
from novel_ai.style_engine import (
    analyze_style,
    blend_styles,
    build_reference_signature,
    detect_ai_flavor,
    reference_overlap,
)


def test_analyze_style_extracts_basic_statistics():
    text = "他推开门。屋里没人。\n\n“你确定？”她问。\n\n风从走廊尽头灌进来，纸页翻了两下。"
    fp = analyze_style(text, "sample")
    assert fp.name == "sample"
    assert fp.avg_sentence_chars > 0
    assert fp.avg_paragraph_chars > 0
    assert 0 <= fp.dialogue_ratio <= 1


def test_blend_styles_respects_weights():
    a = StyleFingerprint(name="a", avg_sentence_chars=10)
    b = StyleFingerprint(name="b", avg_sentence_chars=30)
    merged = blend_styles([(a, 1), (b, 3)])
    assert merged.avg_sentence_chars == 25
    assert merged.source_count == 2


def test_reference_overlap_flags_exact_reuse():
    reference = "这是一个足够长的参考句子，用来测试连续片段是否被系统重复使用。" * 4
    hashes = build_reference_signature(reference, shingle_chars=18)
    assert hashes
    overlap = reference_overlap(reference, hashes, shingle_chars=18)
    assert overlap > 0


def test_ai_flavor_reports_repeated_patterns():
    text = "他微微一怔，仿佛明白了什么。" * 20
    report = detect_ai_flavor(text)
    assert report["pattern_hits"]["仿佛/似乎过密"] > 0
    assert report["pattern_hits"]["弱动作副词过密"] > 0
