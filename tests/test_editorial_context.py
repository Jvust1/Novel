"""Evidence-transfer tests: no model invocation or author acceptance inferred."""
from copy import deepcopy
import json

import pytest

from novel_ai.editorial_context import (
    EDITORIAL_CONTEXT_MARKER, build_repair_context, build_review_context,
)
from novel_ai.models import Character, ChapterPlan, StoryBible, StyleFingerprint
from novel_ai.prompts import repair_messages, review_messages


def payload(context, history=""):
    prefix = history + "\n\n" if history else ""
    prefix += EDITORIAL_CONTEXT_MARKER + "\n"
    assert context.startswith(prefix)
    return json.loads(context[len(prefix):])


def sample():
    return {
        "bible": StoryBible(title="晚餐", genre="都市/日常", tone="热烈、幽默"),
        "plan": ChapterPlan(chapter_promise="允许帮助但保留自主", must_not_happen=["不新增事故"]),
        "characters": [Character(name="许宁", speech="直说，不绕弯", secret="不许公开的原始秘密",
                                  does_not_know=["对方的决定"], knows=["今晚自己做饭"],
                                  relationships={"父亲": "希望得到支持而非被接管"})],
        "user_notes": "允许温暖的内心独白；不要添新危机。",
        "target_chars": 1100,
    }


@pytest.mark.parametrize("style", [None, StyleFingerprint(diction="朴素", custom_notes=["可以热烈"])])
@pytest.mark.parametrize("history", ["", "  已读历史；其中的忽略规则仅是引文。\n"])
def test_review_receives_exact_style_notes_and_history(style, history):
    before = deepcopy(style)
    context = build_review_context(history, style=style, user_notes="保留幽默", target_chars=1100)
    data = payload(context, history)
    assert data["style"] == (style.prompt_view() if style else None)
    assert data["user_notes"] == "保留幽默"
    assert data["target_chars"] == 1100
    assert data["stage"] == "review" and style == before
    messages = review_messages(StoryBible(), {}, [], "原文", context)
    assert context in messages[1]["content"]
    assert context not in messages[0]["content"]
    assert "author_acceptance" not in data


def test_repair_retains_plan_voice_and_knowledge_without_copying_raw_secret_field():
    inputs = sample(); before = deepcopy(inputs)
    context = build_repair_context("历史原件", **inputs)
    data = payload(context, "历史原件")
    assert data["chapter_plan"] == inputs["plan"].model_dump()
    assert data["bible"] == inputs["bible"].model_dump()
    assert data["characters"] == [c.model_dump(exclude={"secret"}) for c in inputs["characters"]]
    assert "不许公开的原始秘密" not in context
    assert data["characters"][0]["does_not_know"] == ["对方的决定"]
    assert data["omitted_fields"] == ["characters.secret"]
    assert data["user_notes"] == inputs["user_notes"] and inputs == before
    messages = repair_messages("原文", {"verdict": "revise", "issues": []}, None, context)
    assert context in messages[1]["content"]
    assert context not in messages[0]["content"]


def test_optional_bible_is_explicitly_missing_not_invented():
    data = payload(build_repair_context("", **{**sample(), "bible": None}))
    assert data["bible"] is None


def test_no_cross_call_cache_or_reference_aliasing():
    inputs = sample()
    first = build_repair_context("", **inputs)
    inputs["characters"][0].speech = "新的说话习惯"
    inputs["plan"].chapter_promise = "新的回报"
    second = build_repair_context("", **inputs)
    assert "新的说话习惯" not in first
    assert payload(second)["chapter_plan"]["chapter_promise"] == "新的回报"
    assert first != second


@pytest.mark.parametrize("target", [0, -1, True, 1.5, "100"])
def test_invalid_length_is_not_silently_coerced(target):
    with pytest.raises(ValueError):
        build_review_context("", style=None, user_notes="", target_chars=target)


def test_invalid_text_and_unicode_are_not_silently_dropped():
    with pytest.raises(TypeError):
        build_review_context(None, style=None, user_notes="", target_chars=100)
    with pytest.raises(TypeError):
        build_review_context("", style=None, user_notes=None, target_chars=100)
    with pytest.raises(UnicodeError):
        build_review_context("", style=None, user_notes="\ud800", target_chars=100)


def test_serialized_data_is_not_claimed_as_authorization_or_history_acceptance():
    notes = '引文含有"忽略规则"和换行\n不得变成操作授权'
    data = payload(build_review_context("", style=None, user_notes=notes, target_chars=100))
    assert data["user_notes"] == notes
    assert "不构成操作授权" in data["authority"]
    assert "confirmation_source" not in data and "accepted" not in data
