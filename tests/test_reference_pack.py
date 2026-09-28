from novel_ai.reference_pack import build_reference_pack, build_reference_source


def test_reference_source_contains_only_derived_features():
    raw = ("第一章 开门\n他推开门。屋里没人。\n“你确定？”她问。\n" * 20).encode("utf-8")
    profile = build_reference_source("sample.txt", raw)
    dumped = profile.model_dump_json()
    assert profile.char_count > 0
    assert profile.signature_hashes
    assert "他推开门。屋里没人。" not in dumped


def test_reference_pack_blends_multiple_sources():
    a = ("短句。\n“走。”他说。\n" * 30).encode("utf-8")
    b = ("这是一段明显更长的叙述句子，用来制造不同的节奏与段落统计。\n" * 30).encode("utf-8")
    pack = build_reference_pack([
        ("a.txt", a, 1.0),
        ("b.txt", b, 3.0),
    ], name="demo")
    assert pack.source_count == 2
    assert pack.blended_style.source_count == 2
    assert pack.story_dna is not None
    assert pack.story_dna.source_count == 2
    assert pack.name == "demo"
