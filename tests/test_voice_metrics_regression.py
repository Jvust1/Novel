"""Synthetic regression inputs; no author manuscripts or network calls."""
import json
from copy import deepcopy

import pytest

from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION, attributed_dialogue
from novel_ai.engine import NovelEngine
from novel_ai.longform_consistency import (
    aggregate_voice_baseline,
    character_voice_dna,
    voice_drift,
)
from novel_ai.models import Character, StoryBible


@pytest.mark.parametrize("text", [
    '林舟说：“走吧。”\n林舟说：“走吧。”',
    '“走吧。”林舟说。\n“走吧。”林舟说。',
])
def test_repeated_utterances_count_distinct_source_occurrences(text):
    assert attributed_dialogue(text, ["林舟", "林舟"]) == {"林舟": ["走吧。", "走吧。"]}


def test_one_quote_with_both_tags_is_still_one_occurrence():
    assert attributed_dialogue('林舟说：“走吧。”林舟低声说。', ["林舟"]) == {"林舟": ["走吧。"]}


def test_repetition_retains_source_order_and_actual_question_ratio():
    text = '林舟说：“走吧。”\n林舟问：“你来吗？”\n林舟说：“走吧。”'
    assert attributed_dialogue(text, ["林舟"]) == {"林舟": ["走吧。", "你来吗？", "走吧。"]}
    metrics = character_voice_dna(text, ["林舟"])["林舟"]
    assert metrics["line_count"] == 3
    assert metrics["question_ratio"] == pytest.approx(1 / 3, abs=0.0001)
    assert metrics["ending_particles"] == {"吧": 2, "吗": 1}


@pytest.mark.parametrize("suffix", ["。", "？", "！", ".", "?", "!", "……", "...", "？！", "！  ", "\u3000", "，", ",", "；", ";", "：", ":"])
def test_ending_particle_is_detected_before_terminal_punctuation(suffix):
    metrics = character_voice_dna(f'林舟说：“好吧{suffix}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {"吧": 1}


@pytest.mark.parametrize("speech", ["好吧", "好吧？！", "好吧\u3000！ \t"])
def test_terminal_particle_with_or_without_punctuation(speech):
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {"吧": 1}


@pytest.mark.parametrize("speech", ["？！……", "吧台关门了。", "你吗？我不信。", "去酒吧（旁边）。", "好吧—"])
def test_no_particle_is_invented_from_punctuation_or_internal_words(speech):
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {}


def test_version_two_aggregate_is_preserved_but_not_mixed_with_new_metrics():
    assert ATTRIBUTION_VERSION == 3
    history = [
        {"voice_dna": {"林舟": {"attribution_version": 2, "line_count": 10, "avg_line_chars": 80}}},
        {"voice_dna": character_voice_dna('林舟说：“好吧。”\n林舟说：“好吧。”', ["林舟"])},
    ]
    original = deepcopy(history)
    baseline = aggregate_voice_baseline(history)["林舟"]
    assert baseline["line_count"] == 2
    assert baseline["ending_particles"] == {"吧": 2}
    assert baseline["attribution_version"] == 3
    assert history == original


def _metrics(version, *, old):
    result = {
        "line_count": 8,
        "avg_line_chars": 100 if old else 3,
        "question_ratio": 1 if old else 0,
        "exclamation_ratio": 1 if old else 0,
        "ellipsis_ratio": 1 if old else 0,
        "short_line_ratio": 0 if old else 1,
    }
    if version is not None:
        result["attribution_version"] = version
    return result


@pytest.mark.parametrize("current_version,old_version", [(3, 2), (3, None), (2, 3), (None, 3), (2, 2), (None, None)])
def test_direct_voice_comparison_rejects_incompatible_metric_versions(current_version, old_version):
    now = {"林舟": _metrics(current_version, old=False)}
    old = {"林舟": _metrics(old_version, old=True)}
    before = deepcopy((now, old))
    assert voice_drift(now, old) == []
    assert (now, old) == before


def test_current_version_voice_comparison_still_reports_drift():
    assert ATTRIBUTION_VERSION == 3
    assert voice_drift({"林舟": _metrics(3, old=False)}, {"林舟": _metrics(3, old=True)})


def test_engine_final_voice_report_uses_occurrences_and_terminal_particles():
    class Provider:
        def chat(self, messages, **kwargs):
            system = messages[0]["content"]
            if "章节策划" in system:
                return json.dumps({"chapter_title": "合成测试", "scenes": []})
            if "严苛的网络小说章节编辑" in system:
                return json.dumps({"verdict": "pass", "issues": []})
            return '林舟说：“走吧。”\n林舟说：“走吧。”'

    result = NovelEngine(Provider()).run(
        bible=StoryBible(), outline="离开", chapter_goal="动身",
        characters=[Character(name="林舟")],
    )
    metrics = result.voice_dna_report["current"]["林舟"]
    assert metrics["line_count"] == 2
    assert metrics["ending_particles"] == {"吧": 2}
    assert metrics["attribution_version"] == 3
