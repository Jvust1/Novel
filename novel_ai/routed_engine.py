from __future__ import annotations

from typing import Any

from .engine import ChapterResult, NovelEngine
from .models import Character, StoryBible, StyleFingerprint
from .orchestration import ProviderRouter, TaskKind
from .output_policy import OutputPolicy



class RoutedNovelEngine:
    """Use separate provider roles without changing the existing engine contract."""

    def __init__(self, router: ProviderRouter, *, output_policy: OutputPolicy | None = None,
                 external_review_hooks: list[Any] | None = None):
        self.router = router
        self.output_policy = output_policy
        self.external_review_hooks = list(external_review_hooks or [])

    def enrich_style(self, text: str, surface: StyleFingerprint) -> StyleFingerprint:
        reviewer = NovelEngine(self.router.provider_for(TaskKind.REVIEW).provider, output_policy=self.output_policy)
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
        historical_voice_dna: list[dict[str, Any]] | None = None,
        external_review_hooks: list[Any] | None = None,
    ) -> ChapterResult:
        writer = NovelEngine(self.router.provider_for(TaskKind.DRAFT).provider, output_policy=self.output_policy,
                             external_review_hooks=self.external_review_hooks)
        plan = writer.plan(bible, outline, chapter_goal, characters, recent_summaries, extra_context)
        reviewer = NovelEngine(self.router.provider_for(TaskKind.REVIEW).provider, output_policy=self.output_policy) if review else None
        return writer.run_from_plan(
            bible=bible, plan=plan, characters=characters, recent_summaries=recent_summaries,
            style=style, target_chars=target_chars, user_notes=user_notes, review=review,
            auto_repair=auto_repair, extra_context=extra_context, reference_hashes=reference_hashes,
            historical_story_dna=historical_story_dna, historical_voice_dna=historical_voice_dna,
            external_review_hooks=external_review_hooks, reviewer=reviewer,
        )
