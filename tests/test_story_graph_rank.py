from novel_ai.story_graph_rank import story_pagerank


def test_story_pagerank_prioritizes_incoming_story_relations():
    scores = story_pagerank(
        ["林默", "电话", "仓库"],
        [("林默", "电话"), ("仓库", "电话"), ("电话", "林默")],
    )
    assert scores["电话"] > scores["仓库"]
    assert round(sum(scores.values()), 6) == 1.0


def test_empty_graph_and_invalid_weight_are_safe():
    assert story_pagerank([], []) == {}
    try:
        story_pagerank(["a", "b"], [("a", "b", -1)])
    except ValueError:
        pass
    else:
        raise AssertionError("negative edge weight must be rejected")
