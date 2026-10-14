"""Real engine pipeline tests with scripted, offline model responses."""
from collections import deque
from copy import deepcopy
import json

import pytest

from novel_ai.engine import NovelEngine
from novel_ai.models import Character, ChapterPlan, ChapterReview, StoryBible
from novel_ai.story_revision import STORY_REPLAN_CATEGORY, StoryReplanRequired


DRAFT = "信使把信交给收信人，等他核对姓名。收信人确认无误，接过信。信使告辞离开。"
REPAIRED = "信使递出信，等收信人核对姓名。对方确认无误，他便告辞离开。"


class ScriptedProvider:
    def __init__(self, *replies):
        self.replies = deque(replies)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((deepcopy(messages), deepcopy(kwargs)))
        if not self.replies:
            raise AssertionError("unexpected extra model request")
        return self.replies.popleft()


def review_data(category=STORY_REPLAN_CATEGORY, severity="high", verdict="revise"):
    return {"verdict": verdict, "issues": [{
        "category": category, "severity": severity,
        "excerpt": "信使告辞离开。", "reason": "计划未交代送信对信使的私人意义。",
        "suggestion": "退回计划，待作者确认；不得擅自改变信的内容。",
    }]}


def encoded_review(**kwargs):
    return json.dumps(review_data(**kwargs), ensure_ascii=False)


@pytest.fixture
def inputs():
    return {
        "bible": StoryBible(title="交信", genre="奇幻", tone="轻快"),
        "plan": ChapterPlan.model_validate({
            "chapter_title": "交信", "chapter_promise": "完成交付",
            "scenes": [{"scene_no": 1, "pov": "信使", "place": "镇口", "time": "上午",
                        "objective": "把信交给本人", "opposition": "对方要求核对姓名",
                        "choice": "等候核对后交信", "cost": "花费时间",
                        "state_change": "未交付变为已交付", "end_hook": ""}],
        }),
        "characters": [Character(name="信使", current_goal="完成交信")],
        "target_chars": 100,
    }


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
@pytest.mark.parametrize("auto_repair", [False, True])
def test_structure_keeps_original_and_evidence_without_repair_call(inputs, severity, auto_repair):
    before = deepcopy(inputs)
    provider = ScriptedProvider(DRAFT, encoded_review(severity=severity, verdict="pass"))
    result = NovelEngine(provider).run_from_plan(**inputs, auto_repair=auto_repair)
    assert len(provider.calls) == 2
    assert result.final_text == DRAFT
    assert result.revised is None and result.review_after_repair is None
    assert result.final_review.verdict == "revise"
    route = result.final_report["story_revision_route"]
    assert route["status"] == "awaiting_plan_revision"
    assert route["structural_issue_indexes"] == [0]
    assert result.final_report["author_acceptance"] == "pending"
    assert result.initial_report == result.final_report
    assert inputs == before


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_direct_repair_raises_before_any_provider_call(severity):
    review = ChapterReview.model_validate(review_data(severity=severity, verdict="pass"))
    before = review.model_dump()
    provider = ScriptedProvider()
    with pytest.raises(StoryReplanRequired, match=STORY_REPLAN_CATEGORY):
        NovelEngine(provider).repair(DRAFT, review)
    assert provider.calls == []
    assert review.model_dump() == before


def test_mixed_structure_and_wording_never_invokes_overridden_repair(inputs):
    class NoRepairEngine(NovelEngine):
        def repair(self, *args, **kwargs):
            pytest.fail("pipeline must block before entering any repair implementation")

    review = review_data()
    review["issues"].extend(review_data(category="expression", severity="medium")["issues"])
    provider = ScriptedProvider(DRAFT, json.dumps(review, ensure_ascii=False))
    result = NoRepairEngine(provider).run_from_plan(**inputs, auto_repair=True)
    assert result.final_text == DRAFT
    assert len(provider.calls) == 2


def test_structure_from_external_hook_is_routed_after_merge(inputs):
    class StructureHook:
        def review_payload(self, **kwargs):
            return {"issues": review_data(severity="low")["issues"]}

    provider = ScriptedProvider(DRAFT, '{"verdict":"pass","issues":[]}')
    result = NovelEngine(provider, external_review_hooks=[StructureHook()]).run_from_plan(
        **inputs, auto_repair=True)
    assert len(provider.calls) == 2
    assert result.final_review.verdict == "revise"
    assert result.final_report["story_revision_route"]["requires_replan"] is True


def test_separate_reviewer_also_blocks_writer_repair(inputs):
    writer = ScriptedProvider(DRAFT)
    reviewer = ScriptedProvider(encoded_review())
    result = NovelEngine(writer).run_from_plan(
        **inputs, auto_repair=True, reviewer=NovelEngine(reviewer))
    assert len(writer.calls) == len(reviewer.calls) == 1
    assert result.final_text == DRAFT
    assert result.final_report["story_revision_route"]["requires_replan"] is True


def test_expression_repair_still_runs_once_and_rechecks_final_text(inputs):
    provider = ScriptedProvider(DRAFT, encoded_review(category="expression", severity="medium"),
                                REPAIRED, '{"verdict":"pass","issues":[]}')
    result = NovelEngine(provider).run_from_plan(**inputs, auto_repair=True)
    assert len(provider.calls) == 4
    assert result.final_text == REPAIRED
    assert result.review_after_repair is not None
    assert result.final_report["stage"] == "repaired"
    assert result.final_report["story_revision_route"]["requires_replan"] is False
    assert result.final_report["author_acceptance"] == "pending"
    assert result.initial_report["text_sha256"] != result.final_report["text_sha256"]


def test_structure_found_after_expression_repair_stays_unresolved(inputs):
    provider = ScriptedProvider(DRAFT, encoded_review(category="expression", severity="medium"),
                                REPAIRED, encoded_review())
    result = NovelEngine(provider).run_from_plan(**inputs, auto_repair=True)
    assert len(provider.calls) == 4
    assert result.final_text == REPAIRED
    assert result.final_review.verdict == "revise"
    assert result.final_report["story_revision_route"]["status"] == "awaiting_plan_revision"


def test_skipped_review_does_not_become_approval(inputs):
    provider = ScriptedProvider(DRAFT)
    result = NovelEngine(provider).run_from_plan(**inputs, review=False, auto_repair=True)
    assert len(provider.calls) == 1
    assert result.final_review is None
    assert result.final_report["story_revision_route"]["status"] == "review_not_run"
    assert result.final_report["author_acceptance"] == "pending"


def test_route_is_covered_by_existing_final_report_integrity_binding(inputs):
    result = NovelEngine(ScriptedProvider(DRAFT, encoded_review())).run_from_plan(**inputs)
    result.final_report["story_revision_route"]["requires_replan"] = False
    with pytest.raises(ValueError, match="report"):
        _ = result.final_text
