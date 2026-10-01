"""Adversarial, fully offline checks for the shared final-text review boundary.

Every manuscript and reference below is original synthetic fixture text. Provider
and hook doubles never perform I/O; actual AppTest writes only beneath tmp_path.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_ai.engine import ChapterResult, NovelEngine, merge_quality_issues
from novel_ai.models import Character, ChapterPlan, ChapterReview, ReviewIssue, StoryBible
from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION
from novel_ai.longform_consistency import character_voice_dna
from novel_ai.orchestration import TaskKind
from novel_ai.quality_gate import analyze_prose_quality, quality_review_payload
from novel_ai.reference_similarity import analyze_reference_similarity, similarity_review_payload
from novel_ai.routed_engine import RoutedNovelEngine
from novel_ai.story_dna import story_dna_from_plan
from novel_ai.style_engine import build_reference_signature, detect_ai_flavor
from novel_ai.workflow_guard import workflow_summary

PATHS = ("single", "routed", "from_plan")
REPEATED = "他缓缓推开仓房的门。\n" * 230 + "这一刻，他终于明白。"
REFERENCE = "柜门里藏着一本蓝色账册，沈青把纸页一张张摊开，林澄在窗边逐项核对那些模糊的日期。"
CLEAN = "雨停之后，沈青把空信封放在桌角。\n林澄说：“明早再来。”\n他点头，绕过积水走向码头。"
EVIDENCE = "【合成历史】沈青不知道仓房密码；账册由林澄保管。"


def digest_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_plan(plan):
    raw = json.dumps(plan.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return digest_text(raw)


def make_plan():
    return ChapterPlan.model_validate({
        "chapter_title": "核账", "chapter_promise": "找回缺失页码", "tension_curve": "上升",
        "scenes": [{"scene_no": 1, "pov": "沈青", "objective": "核对账册", "opposition": "页码被墨迹遮住",
                    "choice": "去仓房比对旧册", "cost": "错过渡船", "state_change": "账册归还保管人",
                    "end_hook": "谁先翻动过旧册？"}],
    })


class ScriptedProvider:
    def __init__(self, *, plan, draft, repaired, reviews, calls, name="writer", on_call=None):
        self.plan = plan
        self.draft = draft
        self.repaired = repaired
        self.reviews = reviews
        self.calls = calls
        self.name = name
        self.review_index = 0
        self.on_call = on_call

    def chat(self, messages, **kwargs):
        system = messages[0]["content"]
        stage = ("plan" if "章节策划" in system else "review" if "严苛的网络小说章节编辑" in system
                 else "repair" if "局部修订编辑" in system else "draft")
        self.calls.append({"provider": self.name, "stage": stage, "messages": deepcopy(messages), "kwargs": deepcopy(kwargs)})
        if self.on_call:
            self.on_call(stage)
        if stage == "plan":
            return self.plan.model_dump_json()
        if stage == "review":
            value = self.reviews[min(self.review_index, len(self.reviews) - 1)]
            self.review_index += 1
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return self.repaired if stage == "repair" else self.draft


class Router:
    def __init__(self, writer, reviewer):
        self.writer, self.reviewer = writer, reviewer
        self.roles = []

    def provider_for(self, kind):
        self.roles.append(kind)
        return SimpleNamespace(provider=self.reviewer if kind == TaskKind.REVIEW else self.writer)


def execute(path, *, draft=REPEATED, repaired=CLEAN, reviews=None, **kwargs):
    calls = []
    plan = kwargs.pop("plan", make_plan())
    on_call = kwargs.pop("on_call", None)
    reviews = reviews or [{"verdict": "revise", "issues": []}, {"verdict": "pass", "issues": []}]
    provider_args = dict(plan=plan, draft=draft, repaired=repaired, reviews=reviews, calls=calls, on_call=on_call)
    writer = ScriptedProvider(**provider_args)
    reviewer = ScriptedProvider(**{**provider_args, "name": "reviewer"})
    router = Router(writer, reviewer)
    options = dict(bible=StoryBible(title="合成测试"), characters=[Character(name="沈青"), Character(name="林澄")],
                   target_chars=3500, auto_repair=True, extra_context=EVIDENCE)
    options.update(kwargs)
    if path == "from_plan":
        result = NovelEngine(writer).run_from_plan(plan=plan, **options)
    elif path == "routed":
        result = RoutedNovelEngine(router).run(outline="合成总纲", chapter_goal="核对缺页", **options)
    else:
        result = NovelEngine(writer).run(outline="合成总纲", chapter_goal="核对缺页", **options)
    return result, calls, router


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("introduces_overlap", (True, False))
def test_repair_reports_follow_exact_final_text_and_preserve_original(path, introduces_overlap):
    draft, repaired = (REPEATED, REFERENCE) if introduces_overlap else (REFERENCE, REPEATED)
    signatures = build_reference_signature(REFERENCE)
    result, calls, _ = execute(path, draft=draft, repaired=repaired, reference_hashes=signatures)
    assert result.final_text == repaired
    assert result.initial_report["stage"] == "draft"
    assert result.final_report["stage"] == "repaired"
    for text, report, review in ((draft, result.initial_report, result.review),
                                (repaired, result.final_report, result.review_after_repair)):
        assert report["text_sha256"] == digest_text(text)
        assert report["plan_sha256"] == digest_plan(result.plan)
        assert report["schema"] == "final-text-analysis-v1"
        assert report["quality_report"] == quality_review_payload(analyze_prose_quality(text))
        assert report["ai_flavor"] == detect_ai_flavor(text)
        assert report["workflow_report"] == workflow_summary(result.plan, text, target_chars=3500)
        expected = similarity_review_payload(analyze_reference_similarity(text, reference_hashes=signatures))
        assert report["similarity_report"]["metrics"] == expected["metrics"]
        assert report["similarity_report"]["issues"] == expected["issues"]
        assert report["review"] == review.model_dump()
        assert report["author_acceptance"] == "pending"
    assert result.initial_report["quality_report"] != result.final_report["quality_report"]
    assert result.initial_report["similarity_report"] != result.final_report["similarity_report"]
    assert result.ai_flavor == result.final_report["ai_flavor"]
    assert result.quality_report == result.final_report["quality_report"]
    assert result.similarity_report == result.final_report["similarity_report"]
    assert result.workflow_report == result.final_report["workflow_report"]
    assert result.final_review.model_dump() == result.final_report["review"]
    final_overlap = any(issue.category == "参考片段重合" for issue in result.final_review.issues)
    assert final_overlap is introduces_overlap
    assert [row["stage"] for row in calls] == (["plan"] if path != "from_plan" else []) + ["draft", "review", "repair", "review"]
    for row in calls:
        assert EVIDENCE in row["messages"][1]["content"]
    if path == "routed":
        assert [row["provider"] for row in calls] == ["writer", "writer", "reviewer", "writer", "reviewer"]


@pytest.mark.parametrize("path", PATHS)
def test_clean_pass_is_still_pending_author_acceptance_and_report_snapshots_are_independent(path):
    result, calls, _ = execute(path, draft=CLEAN, reviews=[{"verdict": "pass", "issues": []}])
    assert result.revised is None and result.review_after_repair is None
    assert result.final_review.verdict == "pass"
    assert result.final_report["author_acceptance"] == "pending"
    assert result.initial_report == result.final_report
    before = deepcopy(result.final_report)
    result.initial_report["voice"]["baseline"]["injected"] = {"line_count": 999}
    result.initial_report["review"]["verdict"] = "revise"
    assert result.final_review.verdict == "pass"
    result.ai_flavor["warnings"].append("caller edit")
    result.quality_report["issues"].append({"reason": "caller edit"})
    result.similarity_report["coverage"]["event_sequences"] = "caller edit"
    result.voice_dna_report["final"]["alerts"].append({"reason": "caller edit"})
    assert result.final_report == before
    with pytest.raises(ValueError):
        _ = result.final_review
    assert [row["stage"] for row in calls].count("repair") == 0


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("bad_repair", ("", " \t\n", None, [], b"not text"))
def test_blank_or_nontext_repair_never_becomes_a_reviewed_candidate(path, bad_repair):
    observed_stages = []
    with pytest.raises((ValueError, TypeError)):
        execute(path, repaired=bad_repair, on_call=observed_stages.append)
    assert observed_stages == (["plan"] if path != "from_plan" else []) + ["draft", "review", "repair"]


@pytest.mark.parametrize("path", PATHS)
def test_persistent_rereview_problem_stops_after_one_repair(path):
    result, calls, _ = execute(path, repaired=REFERENCE, reference_hashes=build_reference_signature(REFERENCE))
    assert result.final_review.verdict == "revise"
    assert result.final_report["author_acceptance"] == "pending"
    assert [row["stage"] for row in calls].count("repair") == 1
    assert [row["stage"] for row in calls].count("review") == 2


@pytest.mark.parametrize("path", PATHS)
def test_quick_draft_is_explicitly_unreviewed_and_never_calls_hook_or_reviewer(path):
    class ForbiddenHook:
        def review_payload(self, **kwargs):
            pytest.fail("quick draft called external hook")
    result, calls, router = execute(path, review=False, auto_repair=True, external_review_hooks=[ForbiddenHook()])
    assert result.final_review is None
    assert result.revised is None and result.review_after_repair is None
    assert result.final_report["review"] is None
    assert result.final_report["review_status"] == "skipped"
    assert result.final_report["external_hooks"] == "skipped"
    assert result.final_report["external_hook_count"] == 0
    assert result.final_report["author_acceptance"] == "pending"
    assert [row["stage"] for row in calls] == (["plan"] if path != "from_plan" else []) + ["draft"]
    assert TaskKind.REVIEW not in router.roles


def issue(severity="medium", *, reason="同一证据", suggestion="局部修订"):
    return {"category": "合成审校", "severity": severity, "reason": reason, "suggestion": suggestion, "excerpt": "合成定位"}


@pytest.mark.parametrize("order", (("low", "high", "medium"), ("high", "low", "medium"), ("medium", "low", "high")))
def test_duplicate_evidence_retains_strongest_severity_and_does_not_mutate_inputs(order):
    existing = ChapterReview(verdict="pass", issues=[ReviewIssue(**issue("low"))])
    payload = {"issues": [issue(level, suggestion=level) for level in order]}
    before_review, before_payload = existing.model_dump(), deepcopy(payload)
    result = merge_quality_issues(existing, payload)
    assert result.verdict == "revise"
    assert len(result.issues) == 1
    assert result.issues[0].severity == "high" and result.issues[0].suggestion == "high"
    assert existing.model_dump() == before_review and payload == before_payload


def test_forged_pass_with_existing_high_issue_is_revalidated():
    existing = ChapterReview(verdict="revise", issues=[ReviewIssue(**issue("high"))])
    forged = existing.model_copy(update={"verdict": "pass"})
    result = merge_quality_issues(forged, {"issues": []})
    assert result.verdict == "revise"
    assert forged.verdict == "pass"
    assert merge_quality_issues(ChapterReview(verdict="revise"), {"issues": []}).verdict == "revise"


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("malformed", ({"verdict": "approved", "issues": []}, {"verdict": "pass", "issues": [issue("critical")]},
                                       {"verdict": "pass", "issues": "not a list"}, "{\"verdict\":"))
def test_malformed_model_review_cannot_produce_a_final_report(path, malformed):
    with pytest.raises((ValueError, TypeError)):
        execute(path, draft=CLEAN, reviews=[malformed])


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("payload", ([], {}, {"issues": None}, {"issues": {}}, {"issues": [None]},
                                    {"issues": [issue("critical")]}, {"issues": [{"category": "x", "severity": "high"}]}))
def test_malformed_hook_payload_is_not_a_clean_completed_check(path, payload):
    class BrokenHook:
        def review_payload(self, **kwargs):
            return deepcopy(payload)
    with pytest.raises((ValueError, TypeError)):
        execute(path, draft=CLEAN, reviews=[{"verdict": "pass", "issues": []}], external_review_hooks=[BrokenHook()])


@pytest.mark.parametrize("path", PATHS)
def test_hook_failure_during_rereview_is_surfaced_without_another_repair(path):
    class FailingSecondHook:
        def __init__(self): self.texts = []
        def review_payload(self, **kwargs):
            self.texts.append(kwargs["draft"])
            if len(self.texts) == 2:
                raise RuntimeError("synthetic hook unavailable")
            return {"issues": []}
    hook = FailingSecondHook()
    with pytest.raises(RuntimeError, match="synthetic hook unavailable"):
        execute(path, external_review_hooks=[hook])
    assert hook.texts == [REPEATED, CLEAN]


@pytest.mark.parametrize("path", PATHS)
def test_hooks_receive_isolated_inputs_and_output_aliases_cannot_rewrite_review(path):
    seen = []
    shared_payload = {"issues": [issue("low", reason="hook observation")]}
    class MutatingHook:
        def review_payload(self, **kwargs):
            seen.append(("mutator", kwargs["draft"], kwargs["plan"].chapter_title, kwargs["bible"].title))
            kwargs["plan"].chapter_title = "hook changed plan"
            kwargs["plan"].scenes[0].choice = "hook changed choice"
            kwargs["bible"].locked_facts.append("hook changed fact")
            kwargs["characters"][0].knows.append("hook invented knowledge")
            return shared_payload
    class CheckingHook:
        def review_payload(self, **kwargs):
            seen.append(("checker", kwargs["draft"], kwargs["plan"].chapter_title, kwargs["bible"].title))
            assert kwargs["plan"].chapter_title == "核账"
            assert kwargs["plan"].scenes[0].choice == "去仓房比对旧册"
            assert kwargs["bible"].locked_facts == []
            assert kwargs["characters"][0].knows == []
            return {"issues": []}
    result, _, _ = execute(path, external_review_hooks=[MutatingHook(), CheckingHook()])
    before = deepcopy(result.final_report)
    shared_payload["issues"][0]["reason"] = "late external mutation"
    assert result.final_report == before
    assert result.final_review.model_dump() == before["review"]
    assert result.plan.chapter_title == "核账"
    assert [row[:2] for row in seen] == [("mutator", REPEATED), ("checker", REPEATED), ("mutator", CLEAN), ("checker", CLEAN)]
    assert result.final_report["external_hooks"] == "completed"
    assert result.final_report["external_hook_count"] == 2


@pytest.mark.parametrize("path", PATHS)
def test_caller_mutation_during_hook_does_not_change_inflight_source_snapshots(path):
    supplied_plan = make_plan()
    characters = [Character(name="沈青"), Character(name="林澄")]
    bible = StoryBible(title="合成测试")
    hashes = build_reference_signature(REFERENCE)
    baseline = [{"chapter_id": "old", "voice_dna": {}}]
    class CallerMutationHook:
        def review_payload(self, **kwargs):
            supplied_plan.chapter_title = "caller changed title"
            characters[0].name = "caller changed name"
            bible.title = "caller changed book"
            hashes.clear()
            baseline[0]["voice_dna"]["foreign"] = {"line_count": 999}
            return {"issues": []}
    expected_plan_sha = digest_plan(supplied_plan)
    result, _, _ = execute(path, plan=supplied_plan, bible=bible, characters=characters, repaired=REFERENCE,
                           reference_hashes=hashes, historical_voice_dna=baseline, external_review_hooks=[CallerMutationHook()])
    assert result.plan.chapter_title == "核账"
    assert result.final_report["plan_sha256"] == expected_plan_sha
    assert result.final_report["similarity_report"]["coverage"]["reference_hashes"] == "checked"
    assert any(item.category == "参考片段重合" for item in result.final_review.issues)
    assert "foreign" not in result.final_report["voice"]["baseline"]


@pytest.mark.parametrize("mutation", ("text", "plan", "selected_review", "review_snapshot"))
def test_result_mutation_refuses_stale_final_evidence(mutation):
    result, _, _ = execute("from_plan")
    if mutation == "text":
        result.revised += "又添了一句。"
    elif mutation == "plan":
        result.plan.scenes[0].choice = "改变批准计划"
    elif mutation == "selected_review":
        result.review_after_repair.issues.append(ReviewIssue(**issue("high")))
    else:
        result.final_report["review"]["verdict"] = "revise"
    with pytest.raises(ValueError):
        _ = result.final_review


@pytest.mark.parametrize("path", PATHS)
def test_report_scopes_remain_plan_derived_unverified_history_and_unchecked_reference_layers(path):
    result, _, _ = execute(path, draft=CLEAN, repaired="沈青烧掉了账册，放弃了渡船。林澄转身走远。")
    assert result.story_dna == story_dna_from_plan(result.plan).to_dict()
    for report in (result.initial_report, result.final_report):
        evidence = report["plan_evidence"]
        assert evidence["source"] == "chapter_plan"
        assert evidence["plan_sha256"] == digest_plan(result.plan)
        assert evidence["story_dna"] == result.story_dna
        assert evidence["prose_event_extraction"].startswith("not_run")
        assert "caller supplied" in evidence["historical_source_provenance"]
        assert "not authenticated" in evidence["historical_source_provenance"]
        assert "caller supplied" in report["voice"]["baseline_provenance"]
        assert set(report["similarity_report"]["coverage"].values()) == {"not_configured"}
        assert report["similarity_report"]["originality_verdict"] is None
        assert report["author_acceptance"] == "pending"
        assert "advisory" in report["ai_flavor_scope"]


@pytest.mark.parametrize("confirmed_plan", (True, False))
def test_actual_workbench_persists_and_displays_the_same_final_report(monkeypatch, tmp_path, confirmed_plan):
    from streamlit.testing.v1 import AppTest
    from novel_ai.provider import OpenAICompatibleProvider
    calls = []
    fake = ScriptedProvider(plan=make_plan(), draft=REPEATED, repaired=REFERENCE,
                            reviews=[{"verdict": "revise", "issues": []}, {"verdict": "pass", "issues": []}], calls=calls)
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", lambda self, messages, **kwargs: fake.chat(messages, **kwargs))
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.session_state["reference_hashes"] = build_reference_signature(REFERENCE)
    if confirmed_plan:
        app.session_state["pending_plan_json"] = make_plan().model_dump_json()
        app.session_state["plan_new"] = True
    app.run()
    for field in app.text_input:
        if field.label == "Base URL": field.set_value("http://never-called.invalid")
        if field.label == "Model": field.set_value("synthetic")
    app.radio[0].set_value("精修")
    app.button(key="btn_draft" if confirmed_plan else "btn_oneshot").click().run()
    assert not app.exception
    result = app.session_state["last_result"]
    assert result.final_text == REFERENCE
    assert result.final_report["text_sha256"] == digest_text(REFERENCE)
    assert result.similarity_report == result.final_report["similarity_report"]
    assert result.final_review.verdict == "revise"
    assert result.final_report["author_acceptance"] == "pending"
    assert next(area.value for area in app.text_area if area.label == "正文") == REFERENCE
    visible_json = [json.loads(item.value) for item in app.json]
    binding = {key: result.final_report[key] for key in (
        "stage", "text_sha256", "plan_sha256", "review_status", "external_hooks", "author_acceptance")}
    assert binding in visible_json
    assert result.initial_report in visible_json
    assert result.quality_report in visible_json
    assert result.ai_flavor in visible_json
    assert result.similarity_report in visible_json
    meta = app.session_state["last_result_meta"]
    saved = tmp_path / "data" / "projects" / "MyNovel" / "chapters" / (meta["chapter_id"] + ".md")
    assert saved.read_text(encoding="utf-8") == REFERENCE + "\n"
    assert [row["stage"] for row in calls] == (["plan"] if not confirmed_plan else []) + ["draft", "review", "repair", "review"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("introduces_drift", (True, False))
def test_repaired_voice_matches_final_speaker_without_replacing_initial_voice(path, introduces_drift):
    initial = ('林舟明问：“为什么你现在才来，仓库早已经封门了？”\n'
               '林舟明问：“你昨天走过城门的时候，难道没有听见钟声吗？”')
    repaired = initial.replace("林舟明", "林舟")
    if not introduces_drift:
        initial, repaired = repaired, initial
    characters = [Character(name="林舟"), Character(name="林舟明")]
    baseline = [{"chapter_id": "old", "voice_dna": {"林舟": {
        "attribution_version": ATTRIBUTION_VERSION, "line_count": 12,
        "avg_line_chars": 3, "question_ratio": 0, "short_line_ratio": 1,
        "exclamation_ratio": 1, "ellipsis_ratio": 1,
    }}}]
    result, _, _ = execute(path, draft=initial, repaired=repaired, characters=characters, historical_voice_dna=baseline)
    initial_voice = character_voice_dna(initial, [c.name for c in characters])
    final_voice = character_voice_dna(repaired, [c.name for c in characters])
    assert result.voice_dna_report["current"] == initial_voice
    assert result.initial_report["voice"]["current"] == initial_voice
    assert result.voice_dna_report["revised"] == final_voice
    assert result.voice_dna_report["final"] == result.final_report["voice"]
    assert result.final_report["voice"]["current"] == final_voice
    assert result.voice_dna_report["initial_text_sha256"] == digest_text(initial)
    assert result.voice_dna_report["final_text_sha256"] == digest_text(repaired)
    assert bool(result.voice_dna_report["revised_alerts"]) is introduces_drift
    assert any(i.category == "人物口吻漂移" for i in result.final_review.issues) is introduces_drift
    assert result.final_report["author_acceptance"] == "pending"


@pytest.mark.parametrize("tampering", ("clear_report", "rewrite_text_digest", "rewrite_plan_digest", "rewrite_review_snapshot"))
def test_public_report_mutation_cannot_rebind_generated_evidence(tampering):
    result, _, _ = execute("from_plan")
    if tampering == "clear_report":
        result.final_report.clear()
        result.revised += "未经审阅的新正文。"
    elif tampering == "rewrite_text_digest":
        result.revised += "未经审阅的新正文。"
        result.final_report["text_sha256"] = digest_text(result.revised)
    elif tampering == "rewrite_plan_digest":
        result.plan.scenes[0].choice = "未经确认的新选择"
        result.final_report["plan_sha256"] = digest_plan(result.plan)
    else:
        result.review_after_repair.issues.append(ReviewIssue(**issue("high")))
        result.final_report["review"] = result.review_after_repair.model_dump()
    with pytest.raises(ValueError):
        _ = result.final_review


@pytest.mark.parametrize("display_field", ("final", "revised", "revised_alerts", "final_text_sha256"))
def test_changed_final_voice_display_is_refused(display_field):
    result, _, _ = execute("from_plan")
    bound = deepcopy(result.final_report)
    if display_field == "final":
        result.voice_dna_report["final"]["alerts"].append({"character": "伪造角色", "score": 1.0})
    elif display_field == "revised":
        result.voice_dna_report["revised"].clear()
    elif display_field == "revised_alerts":
        result.voice_dna_report["revised_alerts"].append({"character": "伪造角色", "score": 1.0})
    else:
        result.voice_dna_report["final_text_sha256"] = "0" * 64
    assert result.final_report == bound
    with pytest.raises(ValueError):
        _ = result.final_review


def test_changed_unrepaired_voice_warning_is_refused():
    result, _, _ = execute("from_plan", draft=CLEAN, reviews=[{"verdict": "pass", "issues": []}])
    assert result.revised is None
    result.voice_dna_report["alerts"].append({"character": "伪造角色", "score": 1.0})
    with pytest.raises(ValueError):
        _ = result.final_review
