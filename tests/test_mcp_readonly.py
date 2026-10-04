from novel_ai.mcp_readonly import normalize_text, score_character, search_characters


def test_unicode_normalization_and_ranked_canonical_character_search():
    assert normalize_text("Élan") == "elan"
    characters = [
        {"name": "林夕", "aliases": ["小夕"], "role": "主角"},
        {"name": "林舟", "role": "配角"},
    ]
    results = search_characters(characters, "小夕")
    assert results[0]["character"]["name"] == "林夕"
    assert results[0]["score"] >= 700


def test_character_search_never_returns_nonmatching_records():
    character = {"name": "Mara", "role": "scout"}
    assert score_character(character, "unknown") == 0
    assert search_characters([character], "unknown") == []
