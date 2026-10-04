from novel_ai.lexical_richness import lexical_richness_report, mattr, mtld, ttr


def test_ttr_and_mattr_are_deterministic():
    tokens = ["a", "b", "a", "c", "b", "d"]
    assert ttr(tokens) == 4 / 6
    assert mattr(tokens, window_size=3) == (2 / 3 + 1 + 1 + 1) / 4


def test_mtld_is_bidirectional_and_finite_for_repetitive_text():
    report = lexical_richness_report("猫 追 鼠。猫 追 鼠。 " * 80)
    assert report["token_count"] > 180
    assert report["mtld"] > 0
    assert report["advisory_only"] is True


def test_empty_text_has_zero_safe_metrics():
    report = lexical_richness_report("")
    assert report["token_count"] == 0
    assert report["ttr"] == 0.0
    assert report["mattr"] == 0.0
    assert report["mtld"] == 0.0
