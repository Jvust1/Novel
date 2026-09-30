from novel_ai.quality_gate import (
    build_manifest,
    check_critic,
    content_sha256,
    duplicate_paragraphs,
    prose_units,
    run_quality_gate,
)


def test_prose_units_counts_chinese_without_spaces():
    assert prose_units("他推开门。风很冷。") >= 7
    assert prose_units("alpha beta 123") == 3


def test_critic_requires_matching_hash_and_locations():
    chapter = "第一段。" + ("这是正文内容。" * 80)
    digest = content_sha256(chapter)
    critic = (
        f"chapter_hash: {digest}\n"
        + ("审校内容需要足够具体。" * 40)
        + "\n第1段存在节奏问题。"
        + "\n“这是正文内容。这是正文内容。”这里有重复。"
    )
    result = check_critic(critic, chapter)
    assert result.status == "PASS"
    assert result.has_matching_chapter_hash is True


def test_stale_critic_hash_fails():
    chapter = "正文。" * 100
    critic = (
        "chapter_hash: "
        + ("0" * 64)
        + "\n第1段问题。"
        + ("具体说明。" * 80)
    )
    result = check_critic(critic, chapter)
    assert result.status == "FAIL"
    assert "missing_or_stale_chapter_hash" in result.reasons


def test_duplicate_paragraphs_block():
    repeated = "这是一个足够长的重复段落。" * 20
    chapters = {
        "01": repeated + "\n\n" + ("不同内容。" * 20),
        "02": repeated + "\n\n" + ("另外内容。" * 20),
    }
    assert duplicate_paragraphs(chapters)
    assert run_quality_gate(chapters, min_chapter_units=1)["status"] == "FAIL"


def test_manifest_changes_when_content_changes():
    first = build_manifest({"01": "甲" * 100})["manifest_sha256"]
    second = build_manifest({"01": "乙" * 100})["manifest_sha256"]
    assert first != second
