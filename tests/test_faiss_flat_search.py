from novel_ai.faiss_flat_search import flat_search


def test_inner_product_and_l2_ranking_are_stable():
    assert flat_search([1, 0], [[0, 1], [1, 0], [2, 0]], k=2) == [(2, 2.0), (1, 1.0)]
    assert flat_search([0, 0], [[0, 2], [0, 1]], metric="l2") == [(1, 1.0), (0, 4.0)]


def test_flat_search_rejects_bad_metric_and_dimension():
    try:
        flat_search([1], [[1]], metric="cosine")
    except ValueError:
        pass
    else:
        raise AssertionError
    try:
        flat_search([1], [[1, 2]])
    except ValueError:
        pass
    else:
        raise AssertionError
