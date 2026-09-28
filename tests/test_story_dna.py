from novel_ai.story_dna import build_story_dna, extract_story_pattern


def test_story_pattern_is_derived_only_and_detects_chapters():
    raw = (
        "第一章 门外的电话\n"
        "电话突然响起，他必须在十分钟内做出选择。\n"
        "她质问他是否隐瞒了真相。\n\n"
        "第二章 代价\n"
        "他发现证据，却发现门外传来脚步声。\n"
    ).encode("utf-8")
    profile = extract_story_pattern("reference.txt", raw)
    dumped = profile.model_dump_json()

    assert profile.chapter_count == 2
    assert profile.opening_hook_ratio == 1.0
    assert profile.conflict_signals["goal_pressure"] >= 1
    assert profile.evidence_counts["chapter_markers"] == 2
    assert "电话突然响起" not in dumped


def test_story_dna_aggregates_sources_and_returns_safe_recommendations():
    a = ("第一章 开始\n他决定出发。门外传来脚步声。\n" * 20).encode("utf-8")
    b = ("第一章 对话\n“你必须告诉我真相。”她说。\n第二章 选择\n他拒绝了交易。\n" * 20).encode("utf-8")
    dna = build_story_dna([("a.txt", a, 1.0), ("b.txt", b, 2.0)], name="demo")

    assert dna.source_count == 2
    assert dna.aggregate["chapter_count_total"] == 60
    assert dna.aggregate["conflict_density_per_1000_chars"]["goal_pressure"] > 0
    assert dna.recommendations
    assert all("他决定出发" not in note for note in dna.notes + dna.recommendations)


def test_story_dna_rejects_empty_sources():
    try:
        build_story_dna([])
    except ValueError as exc:
        assert "至少需要一个参考文件" in str(exc)
    else:
        raise AssertionError("empty Story DNA input must fail closed")
