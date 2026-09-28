import json

import pytest

from novel_ai.market_eval import MarketChapter, MarketCorpus
from novel_ai.release_pack import MarketProfile, build_release_pack, load_release_pack, save_release_pack


def make_corpus():
    return MarketCorpus(
        project="novel",
        stage="opening_3",
        chapters=[
            MarketChapter(number=i, title=f"第{i}章", text=f"章节{i}正文")
            for i in range(1, 4)
        ],
    )


def make_profile():
    return MarketProfile(
        genre="都市悬疑",
        audience="喜欢快节奏悬疑的成年读者",
        tone="冷峻、克制",
        comparable_tags=["悬疑", "都市", "调查"],
    )


def test_release_pack_binds_metadata_to_corpus_without_text(tmp_path):
    corpus = make_corpus()
    pack = build_release_pack(
        corpus,
        make_profile(),
        title="夜班回声",
        one_line_hook="每晚接到死者电话的值班员，必须先找出下一个来电者。",
        short_blurb="一通深夜电话，把旧案和新的失踪案连在一起。",
        tags=["悬疑", "都市"],
    )
    assert pack.chapter_count == 3
    assert pack.corpus_sha256 == corpus.fingerprint()
    serialized = json.dumps(pack.model_dump(), ensure_ascii=False)
    assert "章节1正文" not in serialized

    path = save_release_pack(pack, tmp_path / "release.json")
    loaded = load_release_pack(path)
    assert loaded.title == "夜班回声"
    assert loaded.source_stage == "opening_3"


def test_release_pack_requires_explicit_copy_and_market_fields():
    with pytest.raises(ValueError, match="genre 和 audience"):
        MarketProfile(genre="", audience="")
    with pytest.raises(ValueError, match="one_line_hook"):
        build_release_pack(
            make_corpus(),
            make_profile(),
            title="标题",
            one_line_hook="",
            short_blurb="简介",
        )


def test_profile_tags_and_pack_tags_are_deduplicated_or_rejected():
    with pytest.raises(ValueError, match="不得重复"):
        MarketProfile(genre="都市", audience="读者", comparable_tags=["悬疑", "悬疑"])
    pack = build_release_pack(
        make_corpus(),
        make_profile(),
        title="标题",
        one_line_hook="钩子",
        short_blurb="简介",
        tags=["悬疑", "悬疑", "都市"],
    )
    assert pack.tags == ["悬疑", "都市"]
