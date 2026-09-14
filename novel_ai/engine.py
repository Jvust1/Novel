from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .models import (
    Character,
    ChapterPlan,
    ChapterReview,
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
from .style_engine import detect_ai_flavor


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
    revised: str | None = None


class NovelEngine:
    def __init__(self, provider: OpenAICompatibleProvider):
        self.provider = provider

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
        raw = self.provider.chat(
            plan_messages(bible, outline, chapter_goal, characters, recent_summaries or [], extra_context),
            temperature=0.45,
            response_format={"type": "json_object"},
        )
        return ChapterPlan.model_validate(parse_json_object(raw))

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
    ) -> ChapterReview:
        raw = self.provider.chat(
            review_messages(bible, plan.model_dump(), characters, draft),
            temperature=0.25,
            response_format={"type": "json_object"},
        )
        return ChapterReview.model_validate(parse_json_object(raw))

    def repair(
        self,
        draft: str,
        review: ChapterReview,
        style: StyleFingerprint | None = None,
    ) -> str:
        return self.provider.chat(
            repair_messages(draft, review.model_dump(), style),
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
        raw = self.provider.chat(
            memory_extraction_messages(bible, characters, chapter_id, chapter_text),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        data = parse_json_object(raw)
        data.setdefault("chapter_id", chapter_id)
        return MemoryExtraction.model_validate(data)

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
    ) -> ChapterResult:
        plan = self.plan(bible, outline, chapter_goal, characters, recent_summaries, extra_context)
        draft = self.draft(
            bible,
            plan,
            characters,
            recent_summaries,
            style,
            target_chars,
            user_notes,
            extra_context,
        )
        local_signals = detect_ai_flavor(draft)
        review_result = self.review(bible, plan, characters, draft) if review else None
        revised = None
        if auto_repair and review_result and review_result.verdict == "revise":
            revised = self.repair(draft, review_result, style)
        return ChapterResult(
            plan=plan,
            draft=draft,
            review=review_result,
            ai_flavor=local_signals,
            revised=revised,
        )
