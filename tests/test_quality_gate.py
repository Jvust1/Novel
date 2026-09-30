from novel_ai.quality_gate import analyze_prose_quality, normalize_chinese, quality_review_payload


def test_quality_gate_detects_repeated_sentences():
    text = ("他推开门。屋里没人。\n" * 12) + "她在楼下等着。"
    report = analyze_prose_quality(text)
    assert report.repeated_sentence_ratio > 0
    assert any(i.category == "重复句" for i in report.issues)
    assert report.score < 100


def test_quality_gate_clean_text_has_metrics():
    text = "雨停之后，他没有立刻回去。\n\n“再等十分钟。”她说。\n\n楼道里传来钥匙碰撞的轻响。"
    report = analyze_prose_quality(text)
    assert report.char_count > 0
    assert report.sentence_count >= 3
    assert 0 <= report.bigram_diversity <= 1
    assert "tokenizer" in report.lexical_metrics


def test_normalize_chinese_is_safe_without_optional_backend():
    text = "人物說話要符合身份。"
    normalized, backend = normalize_chinese(text)
    assert normalized
    assert backend in {"identity", "opencc-t2s"}


def test_quality_review_payload_is_compact_and_serializable():
    report = analyze_prose_quality("他看了她一眼。她没有回答。")
    payload = quality_review_payload(report)
    assert "score" in payload
    assert "metrics" in payload
    assert "issues" in payload


def test_bigram_diversity_counts_unique_hashable_pairs():
    from novel_ai.quality_gate import _bigram_diversity

    assert _bigram_diversity("") == 0.0
    assert _bigram_diversity("甲") == 0.0
    assert _bigram_diversity("甲乙丙") == 1.0
    assert _bigram_diversity("甲乙甲乙") == 0.6667
    assert _bigram_diversity("甲，乙\n甲，乙。") == 0.6667
