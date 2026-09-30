from novel_ai.reference_similarity import (
    analyze_reference_similarity,
    event_sequence_similarity,
    fuzzy_similarity,
)
from novel_ai.style_engine import build_reference_signature


def test_exact_reuse_is_flagged_by_hashes():
    ref = "他推开门，桌上的电话正在响，而走廊里没有任何脚步声。" * 8
    report = analyze_reference_similarity(ref, reference_hashes=build_reference_signature(ref))
    assert report.shingle_overlap > 0
    assert report.issues


def test_fuzzy_similarity_prefers_close_text():
    a = "他推开门，桌上的电话正在响。"
    assert fuzzy_similarity(a, "他推开门，桌上电话正在响。") > fuzzy_similarity(a, "大雪封山，商队三天后进城。")


def test_event_sequence_similarity_rewards_same_order():
    a = ["收到匿名电话", "前往旧仓库", "找到一把钥匙"]
    b = ["接到匿名来电", "赶到旧仓库", "发现一把钥匙"]
    c = ["城外下雪", "商队进城", "酒馆争吵"]
    assert event_sequence_similarity(a, b) > event_sequence_similarity(a, c)
