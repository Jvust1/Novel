from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .models import (
    Character,
    ChapterPlan,
    ChapterReview,
    ReviewIssue,
    MemoryExtraction,
    StoryBible,
    StyleFingerprint,
)
from .prompts import (
    draft_messages,
    memory_extraction_messages,
    plan_messages,
    repair_messages,
    review_messages,
    semantic_style_messages,
)
from .provider import OpenAICompatibleProvider
from .quality_gate import analyze_prose_quality, quality_review_payload
from .longform_consistency import (
    aggregate_voice_baseline,
    behavior_repetition,
    behavior_review_payload,
    character_voice_dna,
    voice_drift,
    voice_review_payload,
)
from .reference_similarity import analyze_reference_similarity, similarity_review_payload
from .style_engine import detect_ai_flavor
from .story_dna import story_dna_from_plan
from .story_dna_memory import compare_story_dna, story_dna_review_payload
from .workflow_guard import workflow_summary


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK.search(text)
    if not match:
        raise ValueError("模型没有返回可识别的 JSON 对象")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("模型 JSON 顶层不是对象")
    return value


def sample_reference_text(text: str, max_chars: int = 12000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    part = max_chars // 3
    middle_start = max((len(text) - part) // 2, part)
    return (
        text[:part]
        + "\n\n[中段抽样]\n\n"
        + text[middle_start : middle_start + part]
        + "\n\n[末段抽样]\n\n"
        + text[-part:]
    )


@dataclass
class ChapterResult:
    plan: ChapterPlan
    draft: str
    review: ChapterReview | None
    ai_flavor: dict[str, Any]
    quality_report: dict[str, Any] | None = None
    similarity_report: dict[str, Any] | None = None
    story_dna: dict[str, Any] | None = None
    workflow_report: dict[str, Any] | None = None
    story_dna_similarity_report: dict[str, Any] | None = None
    voice_dna_report: dict[str, Any] | None = None
    behavior_repetition_report: dict[str, Any] | None = None
    revised: str | None = None
    review_after_repair: ChapterReview | None = None

    @property
    def final_text(self) -> str:
        return self.revised or self.draft


def merge_quality_issues(review: ChapterReview | None, quality: dict[str, Any]) -> ChapterReview | None:
    """Merge deterministic prose-quality findings into model review."""
    if review is None:
        return None
    existing = {(i.category, i.reason) for i in review.issues}
    added = []
    for issue in quality.get("issues", []):
        key = (issue.get("category", ""), issue.get("reason", ""))
        if key in existing:
            continue
        added.append(
            ReviewIssue(
                category=issue.get("category", "文本质量"),
                severity=issue.get("severity", "low"),
                excerpt=issue.get("excerpt", ""),
                reason=issue.get("reason", ""),
                suggestion=issue.get("suggestion", ""),
            )
        )
    issues = [*review.issues, *added]
    verdict = review.verdict
    if any(i.severity in {"medium", "high"} for i in added):
        verdict = "revise"
    return review.model_copy(update={"issues": issues, "verdict": verdict})


def apply_external_review_hooks(
    review: ChapterReview | None,
    hooks: list[Any] | None,
    *,
    draft: str,
    plan: ChapterPlan,
    bible: StoryBible,
    characters: list[Character],
) -> ChapterReview | None:
    """Merge explicitly configured upstream review hooks into Novel's review.

    Hooks are opt-in and must expose review_payload(...)->dict with an issues
    list compatible with merge_quality_issues. No external framework is enabled
    unless the caller passes a hook instance.
    """
    if review is None or not hooks:
        return review
    current = review
    for hook in hooks:
        review_payload = getattr(hook, "review_payload", None)
        if not callable(review_payload):
            raise TypeError("external review hook 必须提供 review_payload()")
        payload = review_payload(
            draft=draft,
            plan=plan,
            bible=bible,
            characters=characters,
        )
        if not isinstance(payload, dict):
            raise TypeError("external review hook 必须返回 dict")
        current = merge_quality_issues(current, payload)
    return current


class NovelEngine:
    def __init__(self, provider: OpenAICompatibleProvider, structured_extractor: Any | None = None):
        self.provider = provider
        self.structured_extractor = structured_extractor

    def _structured(self, response_model: Any, messages: list[dict[str, str]], *, temperature: float) -> Any:
        if self.structured_extractor is not None:
            extract = getattr(self.structured_extractor, "extract", None)
            if not callable(extract):
                raise TypeError("structured_extractor 必须提供 extract()")
            value = extract(response_model=response_model, messages=messages, temperature=temperature)
            if isinstance(value, response_model):
                return value
            if hasattr(value, "model_dump"):
                return response_model.model_validate(value.model_dump())
            return response_model.model_validate(value)

        raw = self.provider.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return response_model.model_validate(parse_json_object(raw))

    def enrich_style(self, text: str, surface: StyleFingerprint) -> StyleFingerprint:
        """Add semantic, high-level style traits without storing or reproducing source prose."""
        sample = sample_reference_text(text)
        raw = self.provider.chat(
            semantic_style_messages(sample, surface),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        semantic = parse_json_object(raw)
        allowed = {
            "narrative_distance",
            "pov_preference",
            "action_psychology_environment_balance",
            "diction",
            "rhythm_notes",
            "emotion_expression",
            "imagery_notes",
            "avoid_patterns",
            "custom_notes",
        }
        updates = {k: v for k, v in semantic.items() if k in allowed}
        return surface.model_copy(update=updates)

    def plan(
        self,
        bible: StoryBible,
        outline: str,
        chapter_goal: str,
        characters: list[Character],
        recent_summaries: list[dict[str, Any]] | None = None,
        extra_context: str = "",
    ) -> ChapterPlan:
        return self._structured(
            ChapterPlan,
            plan_messages(bible, outline, chapter_goal, characters, recent_summaries or [], extra_context),
            temperature=0.45,
        )

    def draft(
        self,
        bible: StoryBible,
        plan: ChapterPlan,
        characters: list[Character],
        recent_summaries: list[dict[str, Any]] | None = None,
        style: StyleFingerprint | None = None,
        target_chars: int = 3500,
        user_notes: str = "",
        extra_context: str = "",
    ) -> str:
        return self.provider.chat(
            draft_messages(
                bible,
                plan.model_dump(),
                characters,
                recent_summaries or [],
                style,
                target_chars,
                user_notes,
                extra_context,
            ),
            temperature=0.86,
        ).strip()

    def review(
        self,
        bible: StoryBible,
        plan: ChapterPlan,
        characters: list[Character],
        draft: str,
        extra_context: str = "",
    ) -> ChapterReview:
        return self._structured(
            ChapterReview,
            review_messages(bible, plan.model_dump(), characters, draft, extra_context),
            temperature=0.25,
        )

    def repair(
        self,
        draft: str,
        review: ChapterReview,
        style: StyleFingerprint | None = None,
        extra_context: str = "",
    ) -> str:
        return self.provider.chat(
            repair_messages(draft, review.model_dump(), style, extra_context),
            temperature=0.72,
        ).strip()

    def extract_memory(
        self,
        bible: StoryBible,
        characters: list[Character],
        chapter_id: str,
        chapter_text: str,
    ) -> MemoryExtraction:
        """Extract structured memory deltas from an accepted chapter."""
        memory = self._structured(
            MemoryExtraction,
            memory_extraction_messages(bible, characters, chapter_id, chapter_text),
            temperature=0.2,
        )
        if not memory.chapter_id:
            memory = memory.model_copy(update={"chapter_id": chapter_id})
        return memory

    def run(
        self,
        *,
        bible: StoryBible,
        outline: str,
        chapter_goal: str,
        characters: list[Character],
        recent_summaries: list[dict[str, Any]] | None = None,
        style: StyleFingerprint | None = None,
        target_chars: int = 3500,
        user_notes: str = "",
        review: bool = True,
        auto_repair: bool = False,
        extra_context: str = "",
        reference_hashes: set[str] | None = None,
        historical_story_dna: list[dict[str, Any]] | None = None,
        historical_voice_dna: list[dict[str, Any]] | None = None,
        external_review_hooks: list[Any] | None = None,
    ) -> ChapterResult:
        plan = self.plan(bible, outline, chapter_goal, characters, recent_summaries, extra_context)
        story_dna_obj = story_dna_from_plan(plan)
        dna_similarity = compare_story_dna(story_dna_obj.to_dict(), historical_story_dna or [])
        behavior_report = behavior_repetition(story_dna_obj.to_dict(), historical_story_dna or [])
        draft_context = extra_context
        if dna_similarity.should_avoid:
            draft_context = (draft_context + "\n\n" + dna_similarity.avoid_context).strip()
        if behavior_report.get("should_avoid"):
            draft_context = (draft_context + "\n\n" + str(behavior_report.get("avoid_context", ""))).strip()
        draft = self.draft(
            bible,
            plan,
            characters,
            recent_summaries,
            style,
            target_chars,
            user_notes,
            draft_context,
        )
        local_signals = detect_ai_flavor(draft)
        voice_current = character_voice_dna(draft, [c.name for c in characters])
        voice_baseline = aggregate_voice_baseline(historical_voice_dna or [])
        voice_alerts = voice_drift(voice_current, voice_baseline)
        voice_report = {"current": voice_current, "baseline": voice_baseline, "alerts": voice_alerts}
        story_dna = story_dna_obj.to_dict()
        workflow_report = workflow_summary(plan, draft, target_chars=target_chars)
        quality = analyze_prose_quality(draft)
        quality_payload = quality_review_payload(quality)
        similarity_payload = similarity_review_payload(
            analyze_reference_similarity(draft, reference_hashes=reference_hashes)
        )
        review_result = self.review(bible, plan, characters, draft, draft_context) if review else None
        review_result = merge_quality_issues(review_result, quality_payload)
        review_result = merge_quality_issues(review_result, similarity_payload)
        review_result = merge_quality_issues(review_result, story_dna_review_payload(dna_similarity))
        review_result = merge_quality_issues(review_result, behavior_review_payload(behavior_report))
        review_result = merge_quality_issues(review_result, voice_review_payload(voice_alerts))
        review_result = apply_external_review_hooks(
            review_result,
            external_review_hooks,
            draft=draft,
            plan=plan,
            bible=bible,
            characters=characters,
        )
        revised = None
        review_after_repair = None
        if auto_repair and review_result and review_result.verdict == "revise":
            revised = self.repair(draft, review_result, style, draft_context)
            revised_quality = analyze_prose_quality(revised)
            revised_similarity = similarity_review_payload(
                analyze_reference_similarity(revised, reference_hashes=reference_hashes)
            )
            revised_voice = character_voice_dna(revised, [c.name for c in characters])
            revised_voice_alerts = voice_drift(revised_voice, voice_baseline)
            voice_report["revised"] = revised_voice
            voice_report["revised_alerts"] = revised_voice_alerts
            review_after_repair = self.review(bible, plan, characters, revised, draft_context)
            review_after_repair = merge_quality_issues(review_after_repair, quality_review_payload(revised_quality))
            review_after_repair = merge_quality_issues(review_after_repair, revised_similarity)
            review_after_repair = merge_quality_issues(review_after_repair, story_dna_review_payload(dna_similarity))
            review_after_repair = merge_quality_issues(review_after_repair, behavior_review_payload(behavior_report))
            review_after_repair = merge_quality_issues(review_after_repair, voice_review_payload(revised_voice_alerts))
            review_after_repair = apply_external_review_hooks(
                review_after_repair,
                external_review_hooks,
                draft=revised,
                plan=plan,
                bible=bible,
                characters=characters,
            )
        return ChapterResult(
            plan=plan,
            draft=draft,
            review=review_result,
            ai_flavor=local_signals,
            quality_report=quality_payload,
            similarity_report=similarity_payload,
            story_dna=story_dna,
            workflow_report=workflow_report,
            story_dna_similarity_report=dna_similarity.to_dict(),
            voice_dna_report=voice_report,
            behavior_repetition_report=behavior_report,
            revised=revised,
            review_after_repair=review_after_repair,
        )
