from novel_ai.rapidfuzz_similarity import levenshtein_distance, normalized_similarity


def test_normalized_similarity_matches_edit_distance_semantics():
    assert levenshtein_distance("lewenstein", "levenshtein") == 2
    assert normalized_similarity("abc", "abc") == 1.0
    assert normalized_similarity("abc", "xyz") == 0.0


def test_empty_and_none_inputs_are_safe():
    assert normalized_similarity("", "") == 1.0
    assert normalized_similarity(None, "abc") == 0.0
