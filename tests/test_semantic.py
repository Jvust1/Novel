from novel_ai.semantic import char_ngram_similarity, max_reference_similarity, semantic_similarity


def test_exact_text_is_more_similar_than_unrelated_text():
    target = "他推开门，屋里没人，桌上的电话却正在响。"
    close = "他推开门，屋里没有人，桌上的电话正在响。"
    far = "山谷里下了一夜的大雪，商队明天才会进城。"
    assert semantic_similarity(target, close) > semantic_similarity(target, far)


def test_reference_risk_returns_best_index():
    result = max_reference_similarity("甲乙丙丁甲乙丙丁", ["完全不同", "甲乙丙丁甲乙丙丁"])
    assert result["reference_index"] == 1
    assert result["max_similarity"] == 1.0


def test_empty_similarity_is_zero():
    assert char_ngram_similarity("", "abc") == 0.0
