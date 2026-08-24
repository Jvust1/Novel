from __future__ import annotations

from typing import Any

from .engine import ChapterResult, NovelEngine
from .models import Character, StoryBible, StyleFingerprint
from .orchestration import ProviderRouter, TaskKind


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
    ) -> ChapterResult:
        writer = NovelEngine(self.router.provider_for(TaskKind.DRAFT).provider)
        plan = writer.plan(bible, outline, chapter_goal, characters, recent_summaries)
        draft = writer.draft(
            bible,
            plan,
            characters,
            recent_summaries,
            style,
            target_chars,
            user_notes,
        )
        review_result = None
        if review:
            reviewer = NovelEngine(self.router.provider_for(TaskKind.REVIEW).provider)
            review_result = reviewer.review(bible, plan, characters, draft)
        revised = None
        if auto_repair and review_result and review_result.verdict == "revise":
            revised = writer.repair(draft, review_result, style)
        from .style_engine import detect_ai_flavor

        return ChapterResult(
            plan=plan,
            draft=draft,
            review=review_result,
            ai_flavor=detect_ai_flavor(draft),
            revised=revised,
        )
