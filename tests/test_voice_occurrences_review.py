"""Independent Voice DNA measurement regressions using only synthetic prose.

Existing fake-provider and explicit synthetic-acceptance helpers exercise the
real engine and archive boundaries. No network calls or manuscript corpus.
"""
from copy import deepcopy

import pytest
from test_accepted_archive_writing import archive
from test_final_text_reports import PATHS, digest_text, execute

from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION, attributed_dialogue
from novel_ai.gpt_story_state import (
    load_state,
    rebuild_accepted_history,
    source_fingerprint,
    state_fingerprint,
)
from novel_ai.longform_consistency import (
    aggregate_voice_baseline,
    character_voice_dna,
    voice_drift,
)
from novel_ai.models import Character


def baseline_metrics():
    return {
        "attribution_version": ATTRIBUTION_VERSION,
        "line_count": 4,
        "avg_line_chars": 40,
        "question_ratio": 0,
        "exclamation_ratio": 0,
        "ellipsis_ratio": 0,
        "short_line_ratio": 0,
    }


@pytest.mark.parametrize("text", [
    '林舟问：“你来吗？”\n林舟问：“你来吗？”',
    '“你来吗？”林舟问。\n“你来吗？”林舟问。',
    '林舟问："你来吗？"\n林舟问："你来吗？"',
])
def test_distinct_repeated_utterances_each_count_once(text):
    assert attributed_dialogue(text, ["林舟"]) == {"林舟": ["你来吗？", "你来吗？"]}
    metrics = character_voice_dna(text, ["林舟"])["林舟"]
    assert metrics["line_count"] == 2
    assert metrics["attribution_version"] == ATTRIBUTION_VERSION


def test_same_span_pre_and_post_tags_remain_one_occurrence():
    text = '林舟说：“先走吧。”林舟低声说。'
    assert attributed_dialogue(text, ["林舟", "林舟"]) == {"林舟": ["先走吧。"]}
    assert character_voice_dna(text, ["林舟"])["林舟"]["line_count"] == 1


def test_repeated_utterance_order_and_ambiguous_tag_controls():
    text = ('林舟说：“先走。”\n林舟说：“等一等。”\n林澄说：“先走。”\n'
            '林舟说：“先走。”\n林舟对林澄说：“这句不应归属。”')
    expected = {"林舟": ["先走。", "等一等。", "先走。"], "林澄": ["先走。"]}
    assert attributed_dialogue(text, ["林舟", "林澄"]) == expected
    assert attributed_dialogue(text, ["林澄", "林舟", "林舟"]) == expected


def test_repeated_occurrences_weight_voice_metrics_by_frequency():
    text = '林舟说：“走吧。”\n林舟说：“我已经把全部情况告诉你了。”\n林舟说：“走吧。”'
    metrics = character_voice_dna(text, ["林舟"])["林舟"]
    assert metrics["line_count"] == 3
    assert metrics["avg_line_chars"] == 6.33
    assert metrics["short_line_ratio"] == 0.6667
    assert metrics["first_person_density"] == 0.0526
    assert metrics["second_person_density"] == 0.0526
    assert metrics["ending_particles"] == {"吧": 2}


def test_two_repeated_current_lines_meet_voice_drift_minimum():
    current = character_voice_dna('林舟问：“你来吗？”\n林舟问：“你来吗？”', ["林舟"])
    alerts = voice_drift(current, {"林舟": baseline_metrics()})
    assert len(alerts) == 1
    assert alerts[0]["character"] == "林舟"
    assert alerts[0]["score"] == 0.58


def test_v2_and_unversioned_cache_are_retained_but_excluded_from_current_baseline():
    current = {**baseline_metrics(), "ending_particles": {"吧": 2}}
    legacy = {**current, "attribution_version": 2, "line_count": 20,
              "avg_line_chars": 90, "ending_particles": {"吗": 20}}
    history = [
        {"chapter_id": "v2", "voice_dna": {"林舟": legacy}},
        {"chapter_id": "old", "voice_dna": {"林舟": {"line_count": 30, "avg_line_chars": 99}}},
        {"chapter_id": "current", "voice_dna": {"林舟": current}},
    ]
    before = deepcopy(history)
    baseline = aggregate_voice_baseline(history)
    assert baseline["林舟"]["line_count"] == 4
    assert baseline["林舟"]["chapter_count"] == 1
    assert baseline["林舟"]["avg_line_chars"] == 40
    assert baseline["林舟"]["ending_particles"] == {"吧": 2}
    assert baseline["林舟"]["attribution_version"] == ATTRIBUTION_VERSION
    assert aggregate_voice_baseline(history[:2]) == {}
    assert history == before


@pytest.mark.parametrize("suffix", ["", "。", "？", "！", "?!", "……", "...", "．", "。  ", "\u3000？\u00a0"])
def test_ending_particles_ignore_terminal_punctuation_without_changing_other_metrics(suffix):
    speech = "走吧" + suffix
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {"吧": 1}
    assert metrics["avg_line_chars"] == len("".join(speech.split()))
    assert metrics["question_ratio"] == int("？" in suffix or "?" in suffix)
    assert metrics["exclamation_ratio"] == int("！" in suffix or "!" in suffix)
    assert metrics["ellipsis_ratio"] == int("……" in suffix or "..." in suffix)


@pytest.mark.parametrize("speech", [
    "……？！", "吧台在门边。", "你呢，先把门关上。", "走吧，", "走吧：", "走吧——",
])
def test_punctuation_only_or_interior_particles_are_not_endings(speech):
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {}


def test_long_internal_punctuation_is_preserved_before_final_particle():
    speech = "啊" + "." * 8192 + "吧"
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {"吧": 1}
    assert metrics["avg_line_chars"] == len(speech)
    assert metrics["ellipsis_ratio"] == 1
    assert metrics["line_count"] == 1


def test_long_terminal_punctuation_and_unicode_whitespace_leave_metrics_intact():
    speech = "走吧" + "。！\u3000？\u00a0" * 2048
    metrics = character_voice_dna(f'林舟说：“{speech}”', ["林舟"])["林舟"]
    assert metrics["ending_particles"] == {"吧": 1}
    assert metrics["avg_line_chars"] == len("".join(speech.split()))
    assert metrics["question_ratio"] == 1
    assert metrics["exclamation_ratio"] == 1
    assert metrics["ellipsis_ratio"] == 0
    assert metrics["line_count"] == 1


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("introduces_drift", [True, False])
def test_all_engine_paths_review_occurrences_in_draft_and_repair(path, introduces_drift):
    questioning = '林舟问：“你来吗？”\n林舟问：“你来吗？”'
    statement = '林舟说：“我把上次离开仓房时见到的事情从头到尾重新讲了一遍，账册一直留在门边的旧木箱里。”'
    declarative = statement + "\n" + statement
    draft, repaired = (declarative, questioning) if introduces_drift else (questioning, declarative)
    history = [{"chapter_id": "old", "voice_dna": {"林舟": baseline_metrics()}}]
    before = deepcopy(history)
    result, calls, _ = execute(path, draft=draft, repaired=repaired,
                              characters=[Character(name="林舟")], historical_voice_dna=history)
    assert bool(result.voice_dna_report["alerts"]) is not introduces_drift
    assert bool(result.voice_dna_report["revised_alerts"]) is introduces_drift
    for text, report, review in ((draft, result.initial_report, result.review),
                                (repaired, result.final_report, result.review_after_repair)):
        assert report["voice"]["current"]["林舟"]["line_count"] == 2
        assert report["voice"]["current"]["林舟"]["attribution_version"] == ATTRIBUTION_VERSION
        assert report["text_sha256"] == digest_text(text)
        assert any(issue.category == "人物口吻漂移" for issue in review.issues) is (text == questioning)
        assert report["author_acceptance"] == "pending"
    assert [row["stage"] for row in calls] == (["plan"] if path != "from_plan" else []) + [
        "draft", "review", "repair", "review",
    ]
    assert history == before


def test_accepted_history_rebuild_recomputes_occurrences_without_changing_source(tmp_path):
    text = '林青问：“你来吗？”\n林青问：“你来吗？”'
    path = archive(tmp_path, draft=text)
    before_bytes = path.read_bytes()
    value = load_state(path, expected_story_id="synthetic-story")
    before_state = value.model_dump(mode="json")
    before_state_sha = state_fingerprint(value)
    draft = value.accepted_chapters[0]["draft"]
    before_source = source_fingerprint(draft)
    history = rebuild_accepted_history(value)
    assert history["history_chapter_ids"] == ["ch-1"]
    accepted = history["accepted_chapters"][0]
    assert accepted["voice_dna"]["林青"]["line_count"] == 2
    assert accepted["voice_dna"]["林青"]["attribution_version"] == ATTRIBUTION_VERSION
    assert history["voice_baseline"]["林青"]["line_count"] == 2
    assert accepted["draft_source_fingerprint"] == before_source
    assert source_fingerprint(value.accepted_chapters[0]["draft"]) == before_source
    assert state_fingerprint(value) == before_state_sha
    assert value.model_dump(mode="json") == before_state
    assert path.read_bytes() == before_bytes
    assert rebuild_accepted_history(value, expected_history_sha256=history["accepted_history_sha256"]) == history
