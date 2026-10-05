from novel_ai.opencc_maxmatch import convert_with_dictionary, max_match_segments


def test_longest_phrase_wins_before_single_character_fallback():
    mapping = {"發": "发", "發電": "发电", "電": "电"}
    assert max_match_segments("發電站", mapping) == ["發電", "站"]
    assert convert_with_dictionary("發電站", mapping) == "发电站"


def test_empty_and_invalid_inputs_are_explicit():
    assert max_match_segments("", {"甲": "乙"}) == []
    assert max_match_segments("abc", {}) == ["abc"]
    try:
        convert_with_dictionary(None, {})
    except TypeError:
        pass
    else:
        raise AssertionError("text must be validated")


def test_reference_reader_accepts_explicit_normalization_map():
    from novel_ai.reading import extract_reference_text

    assert extract_reference_text(
        "ref.txt", "繁體 電話".encode("utf-8"),
        normalization_map={"繁體": "简体", "電話": "电话"},
    ) == "简体 电话"
