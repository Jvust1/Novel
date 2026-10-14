"""Engine/model-message wiring with offline scripted responses.

CI imports real repository dependencies. Local dependency-isolated execution,
when used, must be reported separately from full integration/quality testing.
"""
from collections import deque
from copy import deepcopy
import hashlib
import json

import pytest

from novel_ai.editorial_context import EDITORIAL_CONTEXT_MARKER
from novel_ai.engine import NovelEngine
from novel_ai.models import Character, ChapterPlan, ChapterReview, StoryBible, StyleFingerprint


DRAFT = "许宁把锅铲握在手里，请父亲尝味。父亲说还可以添一点盐，由她决定。"
REPAIRED = "许宁没放下锅铲，请父亲尝味。父亲尝过，说盐还可以添一点，仍由她决定。"
PASS = '{"verdict":"pass","issues":[]}'


class ScriptedProvider:
    def __init__(self, *replies):
        self.replies = deque(replies)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(deepcopy(messages))
        if not self.replies:
            raise AssertionError("unexpected model call")
        return self.replies.popleft()


def review_json(category="voice_flattening", severity="medium", verdict="revise"):
    return json.dumps({"verdict": verdict, "issues": [{
        "category": category, "severity": severity, "excerpt": "由她决定。",
        "reason": "应按现有应答保持父亲把决定留给女儿的语气。",
        "suggestion": "仅澄清已有应答，不新增动作或改变结果。",
    }]}, ensure_ascii=False)


def embedded(messages):
    text = messages[1]["content"].split(EDITORIAL_CONTEXT_MARKER + "\n", 1)[1]
    return json.JSONDecoder().raw_decode(text)[0]


@pytest.fixture
def inputs():
    return {
        "bible": StoryBible(genre="都市/日常", tone="温暖、诙谐"),
        "plan": ChapterPlan.model_validate({"chapter_promise": "接受帮助但保留自主", "scenes": [{
            "scene_no": 1, "pov": "许宁", "place": "厨房", "time": "晚上",
            "objective": "独立做完饭", "opposition": "需要父亲的经验但不愿被接管",
            "choice": "请父亲尝味但自己决定", "cost": "承认还需要指导",
            "state_change": "拒绝帮忙变为有边界地请教", "end_hook": "",
        }], "must_not_happen": ["不新增事故"]}),
        "characters": [Character(name="许宁", speech="直接，敢开玩笑", secret="private-secret-sentinel")],
        "user_notes": "保留热烈语气和必要的内心，不强改成冷峻短句。",
        "extra_context": "已提供的历史证据。",
        "target_chars": 120,
    }


@pytest.mark.parametrize("separate_reviewer", [False, True])
@pytest.mark.parametrize("with_style", [False, True])
def test_brief_survives_draft_review_repair_and_final_review(inputs, separate_reviewer, with_style):
    style = StyleFingerprint(name="暖色喜剧", custom_notes=["可以抒情，不套冷句"]) if with_style else None
    inputs["style"] = style
    before = deepcopy(inputs)
    if separate_reviewer:
        writer = ScriptedProvider(DRAFT, REPAIRED)
        editor = ScriptedProvider(review_json(), PASS)
        result = NovelEngine(writer).run_from_plan(**inputs, auto_repair=True, reviewer=NovelEngine(editor))
        draft_call, repair_call = writer.calls
        review_call, final_call = editor.calls
    else:
        writer = ScriptedProvider(DRAFT, review_json(), REPAIRED, PASS)
        result = NovelEngine(writer).run_from_plan(**inputs, auto_repair=True)
        draft_call, review_call, repair_call, final_call = writer.calls
    assert embedded(review_call) == embedded(final_call)
    for call in [review_call, repair_call, final_call]:
        data = embedded(call)
        assert data["user_notes"] == inputs["user_notes"]
        assert data["target_chars"] == 120
        assert inputs["user_notes"] not in call[0]["content"]
        assert inputs["extra_context"] in call[1]["content"]
    assert embedded(review_call)["style"] == (style.prompt_view() if style else None)
    assert embedded(repair_call)["chapter_plan"] == inputs["plan"].model_dump()
    assert embedded(repair_call)["characters"][0]["speech"] == "直接，敢开玩笑"
    assert "private-secret-sentinel" not in repair_call[1]["content"]
    assert inputs["user_notes"] in draft_call[1]["content"]
    assert result.final_text == REPAIRED
    assert result.final_report["author_acceptance"] == "pending"
    assert inputs == before


def test_review_disabled_does_not_add_editorial_messages(inputs):
    provider = ScriptedProvider(DRAFT)
    result = NovelEngine(provider).run_from_plan(**inputs, review=False, auto_repair=True)
    assert len(provider.calls) == 1
    assert EDITORIAL_CONTEXT_MARKER not in provider.calls[0][1]["content"]
    assert result.final_review is None


def test_nonautomatic_review_still_sees_current_brief(inputs):
    provider = ScriptedProvider(DRAFT, PASS)
    result = NovelEngine(provider).run_from_plan(**inputs, auto_repair=False)
    assert len(provider.calls) == 2
    assert embedded(provider.calls[1])["user_notes"] == inputs["user_notes"]
    assert result.revised is None


@pytest.mark.parametrize("severity,verdict", [("low", "pass"), ("high", "revise")])
def test_new_context_does_not_bypass_structural_replan(inputs, severity, verdict):
    provider = ScriptedProvider(DRAFT, review_json("story_structure_requires_replan", severity, verdict))
    result = NovelEngine(provider).run_from_plan(**inputs, auto_repair=True)
    assert len(provider.calls) == 2
    assert result.final_text == DRAFT
    assert result.final_report["story_revision_route"]["requires_replan"] is True
    assert result.final_review.verdict == "revise"


def test_current_notes_are_covered_by_final_report_binding(inputs):
    result = NovelEngine(ScriptedProvider(DRAFT, PASS)).run_from_plan(**inputs)
    digest = hashlib.sha256(inputs["user_notes"].encode("utf-8")).hexdigest()
    assert result.final_report["input_fingerprints"]["user_notes"] == digest
    result.final_report["input_fingerprints"]["user_notes"] = "changed"
    with pytest.raises(ValueError, match="report"):
        _ = result.final_text


def test_legacy_direct_repair_remains_valid_without_inventing_a_plan():
    provider = ScriptedProvider(REPAIRED)
    result = NovelEngine(provider).repair(DRAFT, ChapterReview.model_validate_json(review_json()), None, "旧式上下文")
    assert result == REPAIRED and len(provider.calls) == 1
    assert EDITORIAL_CONTEXT_MARKER not in provider.calls[0][1]["content"]
