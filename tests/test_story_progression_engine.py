"""Real shared-pipeline tests with offline scripted replies; no live quality claim."""
from collections import deque
from copy import deepcopy
import hashlib
import json

import pytest

from novel_ai.editorial_context import EDITORIAL_CONTEXT_MARKER
from novel_ai.engine import NovelEngine
from novel_ai.models import Character, ChapterPlan, StoryBible


DRAFT = "陈澄按约带来门禁原件。保管人把账本放在桌上，两人开始核对，谁也没有先下结论。"
REPAIRED = "陈澄带来门禁原件，保管人把账本放在桌上。两人按约核对，暂不判断哪份记录有错。"
HISTORY = [{"chapter_id": "c10", "revision": "r2", "summary": "双方已约定共同复核原件。",
            "new_facts": ["复核机会已经取得"], "open_threads": ["时间冲突尚未解释"]}]
PASS = '{"verdict":"pass","issues":[]}'
EXPRESSION = json.dumps({"verdict": "revise", "issues": [{
    "category": "expression", "severity": "medium", "excerpt": "两人开始核对",
    "reason": "重组已有动作即可更明确地表达按约核对，不改变事件。", "suggestion": "保留共同复核及未定论。",
}]}, ensure_ascii=False)
STRUCTURE = json.dumps({"verdict": "pass", "issues": [{
    "category": "story_structure_requires_replan", "severity": "low", "excerpt": "两人开始核对",
    "reason": "测试用结构问题；需要改计划而非局部修句。", "suggestion": "退回计划等待作者确认。",
}]}, ensure_ascii=False)


class Replies:
    def __init__(self, *replies):
        self.replies = deque(replies)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((deepcopy(messages), deepcopy(kwargs)))
        if not self.replies:
            raise AssertionError("unexpected model request")
        return self.replies.popleft()


def inputs(bible=True):
    return {
        "bible": StoryBible(genre="悬疑") if bible else None,
        "plan": ChapterPlan.model_validate({"chapter_promise": "落实复核", "scenes": [{
            "scene_no": 1, "pov": "陈澄", "objective": "共同核对原件", "opposition": "两份时间不同",
            "choice": "先核对不先指控", "cost": "花费复核时间", "state_change": "从约定到实际核对",
        }]}),
        "characters": [Character(name="陈澄", knows=["已经取得复核机会"])],
        "recent_summaries": deepcopy(HISTORY), "target_chars": 100,
    }


def editorial_payload(call):
    messages = call[0]
    text = messages[1]["content"]
    start = text.index(EDITORIAL_CONTEXT_MARKER + "\n") + len(EDITORIAL_CONTEXT_MARKER + "\n")
    data, _ = json.JSONDecoder().raw_decode(text, start)
    assert HISTORY[0]["summary"] not in messages[0]["content"]
    return data


@pytest.mark.parametrize("separate_reviewer", [False, True])
@pytest.mark.parametrize("has_bible", [False, True])
def test_history_reaches_both_reviews_and_repair_without_extra_calls(separate_reviewer, has_bible):
    args = inputs(has_bible)
    before = deepcopy(args)
    if separate_reviewer:
        writer = Replies(DRAFT, REPAIRED)
        critic = Replies(EXPRESSION, PASS)
        result = NovelEngine(writer).run_from_plan(**args, auto_repair=True, reviewer=NovelEngine(critic))
        review_calls, repair_call = critic.calls, writer.calls[1]
        assert len(writer.calls) == len(critic.calls) == 2
    else:
        writer = Replies(DRAFT, EXPRESSION, REPAIRED, PASS)
        result = NovelEngine(writer).run_from_plan(**args, auto_repair=True)
        review_calls, repair_call = [writer.calls[1], writer.calls[3]], writer.calls[2]
        assert len(writer.calls) == 4
    for call in [*review_calls, repair_call]:
        data = editorial_payload(call)
        assert data["recent_summaries"] == HISTORY
        assert data["history_scope"]["acceptance_verification"] == "not_performed_here"
    assert args == before
    assert result.final_text == REPAIRED
    assert result.final_report["author_acceptance"] == "pending"
    digest = hashlib.sha256(json.dumps(HISTORY, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    assert result.final_report["input_fingerprints"]["recent_summaries"] == digest


def test_structure_still_stops_repair_with_history_present():
    provider = Replies(DRAFT, STRUCTURE)
    result = NovelEngine(provider).run_from_plan(**inputs(), auto_repair=True)
    assert len(provider.calls) == 2
    assert editorial_payload(provider.calls[1])["recent_summaries"] == HISTORY
    assert result.revised is None
    assert result.final_text == DRAFT
    assert result.final_review.verdict == "revise"
    assert result.final_report["story_revision_route"]["requires_replan"] is True


def test_no_review_does_not_create_an_editor_request():
    provider = Replies(DRAFT)
    result = NovelEngine(provider).run_from_plan(**inputs(), review=False, auto_repair=True)
    assert len(provider.calls) == 1
    assert result.final_review is None
    assert result.final_report["story_revision_route"]["status"] == "review_not_run"


def test_empty_history_is_not_claimed_to_cover_the_book():
    args = inputs()
    args["recent_summaries"] = []
    provider = Replies(DRAFT, PASS)
    NovelEngine(provider).run_from_plan(**args, auto_repair=False)
    data = editorial_payload(provider.calls[1])
    assert data["recent_summaries"] == []
    assert data["history_scope"]["status"] == "provided_empty"
    assert len(provider.calls) == 2


def test_later_caller_mutation_does_not_change_editor_snapshot():
    args = inputs()
    before = deepcopy(args["recent_summaries"])

    class MutatingCaller(Replies):
        def chat(self, messages, **kwargs):
            if not self.calls:
                args["recent_summaries"][0]["summary"] = "调用方在起草期间改了摘要"
            return super().chat(messages, **kwargs)

    provider = MutatingCaller(DRAFT, PASS)
    result = NovelEngine(provider).run_from_plan(**args)
    assert editorial_payload(provider.calls[1])["recent_summaries"] == before
    assert result.final_report["author_acceptance"] == "pending"
