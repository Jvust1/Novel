from novel_ai.jieba_tokenizer import segment, segment_chinese


def test_dag_route_keeps_story_terms_as_tokens():
    vocabulary = {"旧仓库": 100, "电话": 90, "仓库": 10}
    assert segment("他赶到旧仓库接到电话", vocabulary) == ["他", "赶", "到", "旧仓库", "接", "到", "电话"]


def test_mixed_text_and_invalid_frequency_are_deterministic():
    assert segment("ABC 与夜雨 2026", {"夜雨": "bad", "雨": -1}) == ["abc", "与", "夜", "雨", "2026"]
    assert segment_chinese("", {"夜雨": 1}) == []


def test_lexical_report_accepts_character_vocabulary():
    from novel_ai.lexical_richness import lexical_richness_report

    report = lexical_richness_report("林默走进旧仓库。林默听见电话。", vocabulary=["林默", "旧仓库", "电话"])
    assert report["tokenizer_backend"] == "jieba-dag-port"
    assert report["vocabulary_size"] == 3
    assert report["token_count"] < 20
