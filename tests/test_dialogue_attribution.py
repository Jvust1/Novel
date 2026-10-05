"""Original synthetic dialogue; no book corpus or model dependency."""
from copy import deepcopy
import json

import pytest

from novel_ai._vendor.spacy_spans import filter_spans
from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION, NameSpan, attributed_dialogue
from novel_ai.engine import NovelEngine
from novel_ai.longform_consistency import aggregate_voice_baseline, character_voice_dna, voice_drift
from novel_ai.models import Character, StoryBible


def test_spacy_longest_span_filter_retains_source_order_and_removes_duplicates():
    short = NameSpan(0, 2, "林舟")
    long = NameSpan(0, 3, "林舟明")
    later = NameSpan(5, 7, "沈青")
    assert filter_spans([later, short, long, long]) == [long, later]
    assert filter_spans([]) == []


@pytest.mark.parametrize("text", ['林舟明问：“你看清楚了吗？”', '“你看清楚了吗？”林舟明低声问。'])
def test_longer_canonical_name_is_not_also_credited_to_prefix(text):
    result = character_voice_dna(text, ["林舟", "林舟明"])
    assert set(result) == {"林舟明"}
    assert result["林舟明"]["line_count"] == 1
    assert result["林舟明"]["attribution_version"] == ATTRIBUTION_VERSION


@pytest.mark.parametrize("names", [["林", "林澄"], ["林澄", "林"]])
def test_name_order_does_not_change_longest_match(names):
    assert attributed_dialogue('林澄说：“钥匙在我这里。”', names) == {"林澄": ["钥匙在我这里。"]}


@pytest.mark.parametrize("text", ['林舟对林澄说：“走吧。”', '“走吧。”林舟对林澄说。', '林舟看向林澄问：“走吗？”'])
def test_multi_name_tags_are_omitted_instead_of_guessing(text):
    assert attributed_dialogue(text, ["林舟", "林澄"]) == {}


def test_clear_tag_after_comma_is_retained():
    text = '林澄看向林舟，林舟说：“明白。”'
    assert attributed_dialogue(text, ["林舟", "林澄"]) == {"林舟": ["明白。"]}


def test_speech_tag_does_not_cross_newline_or_previous_sentence():
    assert attributed_dialogue('林舟站起。\n他说：“走吧。”', ["林舟"]) == {}
    assert attributed_dialogue('“走吧。”\n林舟低声说。', ["林舟"]) == {}


def test_names_are_escaped_and_duplicate_input_names_do_not_duplicate_lines():
    text = 'A+问："你来吗？"'
    assert attributed_dialogue(text, ["A+", "A+", ""]) == {"A+": ["你来吗？"]}


def test_quoted_name_mention_does_not_create_another_speaker():
    text = '林澄说：“沈青问过钥匙在哪儿吗？”'
    assert attributed_dialogue(text, ["沈青", "林澄"]) == {"林澄": ["沈青问过钥匙在哪儿吗？"]}


def test_pre_and_post_tags_for_same_quote_are_counted_once():
    text = '林舟说：“我不走。”林舟低声说。'
    assert attributed_dialogue(text, ["林舟"]) == {"林舟": ["我不走。"]}


def test_legacy_and_mixed_baselines_are_not_compared_as_new_attribution():
    history = [
        {"voice_dna": {"林舟": {"line_count": 20, "avg_line_chars": 90}}},
        {"voice_dna": {"林舟": {"attribution_version": ATTRIBUTION_VERSION, "line_count": 4, "avg_line_chars": 5}}},
    ]
    before = deepcopy(history)
    baseline = aggregate_voice_baseline(history)
    assert baseline["林舟"]["line_count"] == 4
    assert baseline["林舟"]["avg_line_chars"] == 5
    assert baseline["林舟"]["attribution_version"] == ATTRIBUTION_VERSION
    assert history == before
    assert aggregate_voice_baseline(history[:1]) == {}


def test_prefix_name_cannot_receive_false_voice_drift_from_another_character():
    text = '林舟明说：“为什么你现在才来？”林舟明问：“你听见了吗？”'
    baseline = {"林舟": {"line_count": 12, "avg_line_chars": 100, "question_ratio": 0, "short_line_ratio": 0}}
    current = character_voice_dna(text, ["林舟", "林舟明"])
    assert voice_drift(current, baseline) == []


def test_actual_chapter_engine_uses_the_span_filter_before_voice_review():
    class Provider:
        def chat(self, messages, **kwargs):
            system = messages[0]["content"]
            if "章节策划" in system:
                return json.dumps({"chapter_title": "仓库", "scenes": []})
            if "严苛的网络小说章节编辑" in system:
                return json.dumps({"verdict": "pass", "issues": []})
            return '林舟明说：“为什么你现在才来？”林舟明问：“你听见了吗？”'

    result = NovelEngine(Provider()).run(
        bible=StoryBible(), outline="问话", chapter_goal="取回仓库钥匙",
        characters=[Character(name="林舟"), Character(name="林舟明")],
        historical_voice_dna=[{"voice_dna": {"林舟": {
            "attribution_version": ATTRIBUTION_VERSION,
            "line_count": 12, "avg_line_chars": 100, "question_ratio": 0,
        }}}],
    )
    assert set(result.voice_dna_report["current"]) == {"林舟明"}
    assert result.voice_dna_report["alerts"] == []
    assert not any(issue.category == "人物口吻漂移" for issue in result.review.issues)


@pytest.mark.parametrize("text", [
    '“你来。”林澄没有回答。',
    '“你来。”林澄不知道该怎么办。',
    '“你来。”林澄想到一个办法。',
    '林澄没有说：“你来。”',
    '林澄不知道：“你来。”',
])
def test_non_speech_and_negated_speech_tags_do_not_credit_dialogue(text):
    assert attributed_dialogue(text, ["林澄"]) == {}


def test_long_clause_does_not_turn_the_addressee_into_speaker():
    text = '林舟沉思了片刻后对林澄说：“走吧。”'
    assert attributed_dialogue(text, ["林舟", "林澄"]) == {}
    assert attributed_dialogue('老人对林澄说：“走吧。”', ["林澄"]) == {}


def test_adjacent_pre_tags_do_not_steal_or_drop_the_previous_quote():
    text = '林舟说：“来。”林澄说：“走。”'
    assert attributed_dialogue(text, ["林舟", "林澄"]) == {"林舟": ["来。"], "林澄": ["走。"]}


@pytest.mark.parametrize("marker", ["跟", "朝", "冲", "给", "替"])
def test_other_explicit_recipient_prefixes_are_not_speakers(marker):
    assert attributed_dialogue(f'老人{marker}林澄说：“走吧。”', ["林澄"]) == {}
