from novel_ai.longform_tools import build_story_graph, near_duplicate_chapters


def test_cross_chapter_duplicate_guard():
    current = "他推开门，桌上的电话正在响。" * 20
    previous = [("001", current), ("002", "大雪封山，商队三天后进城。" * 20)]
    rows = near_duplicate_chapters(current, previous, threshold=0.5)
    assert rows
    assert rows[0].chapter_id == "001"


def test_story_graph_contains_characters_and_foreshadowing():
    graph = build_story_graph(
        [{"name":"林舟","relationships":{"苏晚":"合作"}}],
        {"timeline":[{"chapter_id":"003","description":"夜访档案室"}],
         "foreshadowing":[{"id":"archive-gap","description":"档案空窗","status":"planted"}]},
    )
    ids = {n["id"] for n in graph["nodes"]}
    assert "character:林舟" in ids
    assert "foreshadow:archive-gap" in ids
