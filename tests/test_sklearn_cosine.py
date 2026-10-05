from novel_ai.sklearn_cosine import cosine_similarity_matrix


def test_cosine_matrix_matches_normalized_dot_product_semantics():
    scores = cosine_similarity_matrix([[0, 0], [1, 1]], [[1, 0], [1, 1]])
    assert scores == [[0.0, 0.0], [0.707107, 1.0]]


def test_zero_rows_and_dimension_validation_are_explicit():
    assert cosine_similarity_matrix([[0.0, 0.0]], [[1.0, 2.0]]) == [[0.0]]
    try:
        cosine_similarity_matrix([[1.0]], [[1.0, 2.0]])
    except ValueError:
        pass
    else:
        raise AssertionError("dimension mismatch must fail")
