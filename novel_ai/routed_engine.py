from __future__ import annotations

from typing import Any

from .engine import ChapterResult, NovelEngine
from .models import Character, StoryBible, StyleFingerprint
from .quality_gate import analyze_prose_quality, quality_review_payload
from .reference_similarity import analyze_reference_similarity, similarity_review_payload
from .orchestration import ProviderRouter, TaskKind
from .story_dna import story_dna_from_plan
from .story_dna_memory import compare_story_dna, story_dna_review_payload


class RoutedNovelEngine:
    """Use separate provider roles without changing the existing engine contract."""

    def __init__(self, router: ProviderRouter):
        self.router = router

    def enrich_style(self, text: str, surface: StyleFingerprint) -> StyleFingerprint:
        reviewer = NovelEngine(self.router.provider_for(TaskKind.REVIEW).provider)
        return reviewer.enrich_style(text, surface)

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
    ) -> ChapterResult:
        writer = NovelEngine(self.router.provider_for(TaskKind.DRAFT).provider)
        plan = writer.plan(bible, outline, chapter_goal, characters, recent_summaries, extra_context)
        story_dna = story_dna_from_plan(plan)
        dna_similarity = compare_story_dna(story_dna.to_dict(), historical_story_dna or [])
        draft_context = extra_context
        if dna_similarity.should_avoid:
            draft_context = (extra_context + "\n\n" + dna_similarity.avoid_context).strip()
        draft = writer.draft(
            bible,
            plan,
            characters,
            recent_summaries,
            style,
            target_chars,
            user_notes,
            draft_context,
        )
        review_result = None
        if review:
            reviewer = NovelEngine(self.router.provider_for(TaskKind.REVIEW).provider)
            review_result = reviewer.review(bible, plan, characters, draft)
            from .engine import merge_quality_issues
            review_result = merge_quality_issues(review_result, quality_review_payload(analyze_prose_quality(draft)))
            review_result = merge_quality_issues(
                review_result,
                similarity_review_payload(analyze_reference_similarity(draft, reference_hashes=reference_hashes)),
            )
            review_result = merge_quality_issues(review_result, story_dna_review_payload(dna_similarity))
        revised = None
        if auto_repair and review_result and review_result.verdict == "revise":
            revised = writer.repair(draft, review_result, style)
        from .style_engine import detect_ai_flavor
        quality_payload = quality_review_payload(analyze_prose_quality(draft))
        similarity_payload = similarity_review_payload(
            analyze_reference_similarity(draft, reference_hashes=reference_hashes)
        )

        return ChapterResult(
            plan=plan,
            draft=draft,
            review=review_result,
            ai_flavor=detect_ai_flavor(draft),
            quality_report=quality_payload,
            similarity_report=similarity_payload,
            story_dna=story_dna.to_dict(),
            story_dna_similarity_report=dna_similarity.to_dict(),
            revised=revised,
        )
