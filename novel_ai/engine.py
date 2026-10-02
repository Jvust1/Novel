from __future__ import annotations

import json
from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
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
from .output_policy import (
    DEFAULT_MAX_OUTPUT_BYTES, OutputPolicy, json_object_from_value,
    parse_json_object, positive_int, validate_output_text,
)
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
    initial_report: dict[str, Any] = field(default_factory=dict)
    final_report: dict[str, Any] = field(default_factory=dict)
    _binding: tuple[str, str, str, str, str] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.final_report:
            # Keep a separate immutable receipt. Clearing/editing the public
            # report must never turn a generated result into an unbound legacy
            # object. This is integrity evidence, not human authentication.
            self._binding = (
                self.final_report["text_sha256"], self.final_report["plan_sha256"],
                self.final_report["stage"], _data_digest(self.final_report),
                _data_digest(self.final_report.get("review")),
            )

    @property
    def final_text(self) -> str:
        text = self.revised if self.revised is not None else self.draft
        _require_manuscript(text)
        if self._binding is not None:
            text_sha, plan_sha, stage, report_sha, _ = self._binding
            if not self.final_report or _data_digest(self.final_report) != report_sha:
                raise ValueError("final report is missing or changed; re-review required")
            if stage != ("repaired" if self.revised is not None else "draft"):
                raise ValueError("final manuscript stage changed after its review")
            selected = self.review_after_repair if self.revised is not None else self.review
            if self._binding[4] != _data_digest(selected.model_dump() if selected else None):
                raise ValueError("review changed after the final report was bound")
            if text_sha != _text_digest(text):
                raise ValueError("final manuscript changed after its review; recompute before use")
            if plan_sha != _data_digest(self.plan.model_dump()):
                raise ValueError("chapter plan changed after its review; recompute before use")
            for key in ("ai_flavor", "quality_report", "similarity_report", "workflow_report"):
                if getattr(self, key) != self.final_report[key]:
                    raise ValueError("displayed diagnostics changed after final report binding")
            voice = self.voice_dna_report or {}
            current_key = "revised" if self.revised is not None else "current"
            alerts_key = "revised_alerts" if self.revised is not None else "alerts"
            if (voice.get("final") != self.final_report["voice"]
                    or voice.get("final_text_sha256") != text_sha
                    or voice.get(current_key) != self.final_report["voice"]["current"]
                    or voice.get(alerts_key) != self.final_report["voice"]["alerts"]):
                raise ValueError("displayed Voice evidence changed after final report binding")
            evidence = self.final_report["plan_evidence"]
            if (self.story_dna != evidence["story_dna"]
                    or self.story_dna_similarity_report != evidence["story_dna_similarity"]
                    or self.behavior_repetition_report != evidence["behavior_repetition"]):
                raise ValueError("displayed plan-derived evidence changed after final report binding")
        return text

    @property
    def final_review(self) -> ChapterReview | None:
        self.final_text  # Check text and plan binding before returning evidence.
        selected = self.review_after_repair if self.revised is not None else self.review
        if self._binding is not None and self._binding[4] != _data_digest(selected.model_dump() if selected else None):
            raise ValueError("review changed after the final report was bound")
        return selected


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _data_digest(value: Any) -> str:
    return _text_digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _require_manuscript(text: Any) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("model returned an empty or non-text manuscript; no candidate was published")
    text.encode("utf-8")
    return text


def merge_quality_issues(review: ChapterReview | None, quality: dict[str, Any]) -> ChapterReview | None:
    """Merge deterministic prose-quality findings into model review."""
    if review is None:
        return None
    if not isinstance(quality, dict) or not isinstance(quality.get("issues"), list):
        raise ValueError("review payload must contain an explicit issues list")
    # Revalidate even a model_copy/model_construct instance; neither is proof of
    # valid fields. On duplicate evidence retain its strongest severity.
    review = ChapterReview.model_validate(review.model_dump())
    ranks = {"low": 0, "medium": 1, "high": 2}
    merged: dict[tuple[str, str], ReviewIssue] = {}
    for raw in [*[i.model_dump() for i in review.issues], *quality["issues"]]:
        issue = ReviewIssue.model_validate(raw)
        key = (issue.category, issue.reason)
        if key not in merged or ranks[issue.severity] > ranks[merged[key].severity]:
            merged[key] = issue
    return ChapterReview.model_validate({**review.model_dump(), "issues": [i.model_dump() for i in merged.values()]})



def apply_external_review_hooks(
    review: ChapterReview | None,
    hooks: list[Any] | None,
    *,
    draft: str,
    plan: ChapterPlan,
    bible: StoryBible,
    characters: list[Character],
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
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
            plan=plan.model_copy(deep=True),
            bible=deepcopy(bible),
            characters=deepcopy(characters),
        )
        if not isinstance(payload, dict):
            raise TypeError("external review hook 必须返回 dict")
        payload = json_object_from_value(payload, max_bytes=max_output_bytes)
        current = merge_quality_issues(current, payload)
    return current


class NovelEngine:
    def __init__(self, provider: OpenAICompatibleProvider, structured_extractor: Any | None = None,
                 *, output_policy: OutputPolicy | None = None, external_review_hooks: list[Any] | None = None):
        self.provider = provider
        self.structured_extractor = structured_extractor
        if output_policy is not None and not isinstance(output_policy, OutputPolicy):
            raise TypeError("output_policy must be OutputPolicy")
        self.output_policy = output_policy or OutputPolicy()
        self.external_review_hooks = list(external_review_hooks or [])

    def _structured(self, response_model: Any, messages: list[dict[str, str]], *, temperature: float, stage: str) -> Any:
        if self.structured_extractor is not None:
            extract = getattr(self.structured_extractor, "extract", None)
            if not callable(extract):
                raise TypeError("structured_extractor 必须提供 extract()")
            value = extract(response_model=response_model, messages=messages, temperature=temperature,
                            max_tokens=self.output_policy.tokens_for(stage),
                            max_output_bytes=self.output_policy.max_output_bytes)
            # Native model objects and schema adapters are not exempt from the
            # same byte/finite/Unicode boundary or model revalidation.
            parsed = json_object_from_value(value, max_bytes=self.output_policy.max_output_bytes)
            return response_model.model_validate(parsed)

        raw = self.provider.chat(
            messages,
            temperature=temperature,
            max_tokens=self.output_policy.tokens_for(stage),
            response_format={"type": "json_object"},
        )
        return response_model.model_validate(parse_json_object(raw, max_bytes=self.output_policy.max_output_bytes))

    def enrich_style(self, text: str, surface: StyleFingerprint) -> StyleFingerprint:
        """Add semantic, high-level style traits without storing or reproducing source prose."""
        sample = sample_reference_text(text)
        raw = self.provider.chat(
            semantic_style_messages(sample, surface),
            temperature=0.2,
            max_tokens=self.output_policy.tokens_for("style"),
            response_format={"type": "json_object"},
        )
        semantic = parse_json_object(raw, max_bytes=self.output_policy.max_output_bytes)
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
        return StyleFingerprint.model_validate({**surface.model_dump(), **updates})

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
            temperature=0.45, stage="plan",
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
        positive_int(target_chars, name="target_chars")
        raw = self.provider.chat(
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
            max_tokens=self.output_policy.tokens_for("draft"),
        )
        return validate_output_text(raw, max_bytes=self.output_policy.max_output_bytes).strip()

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
            temperature=0.25, stage="review",
        )

    def repair(
        self,
        draft: str,
        review: ChapterReview,
        style: StyleFingerprint | None = None,
        extra_context: str = "",
    ) -> str:
        raw = self.provider.chat(
            repair_messages(draft, review.model_dump(), style, extra_context),
            temperature=0.72,
            max_tokens=self.output_policy.tokens_for("repair"),
        )
        return validate_output_text(raw, max_bytes=self.output_policy.max_output_bytes).strip()

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
            temperature=0.2, stage="memory",
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
        return self.run_from_plan(
            bible=bible, plan=plan, characters=characters, recent_summaries=recent_summaries,
            style=style, target_chars=target_chars, user_notes=user_notes, review=review,
            auto_repair=auto_repair, extra_context=extra_context, reference_hashes=reference_hashes,
            historical_story_dna=historical_story_dna, historical_voice_dna=historical_voice_dna,
            external_review_hooks=external_review_hooks,
        )

    def run_from_plan(
        self, *, bible: StoryBible, plan: ChapterPlan, characters: list[Character],
        recent_summaries: list[dict[str, Any]] | None = None,
        style: StyleFingerprint | None = None, target_chars: int = 3500,
        user_notes: str = "", review: bool = True, auto_repair: bool = False,
        extra_context: str = "", reference_hashes: set[str] | None = None,
        historical_story_dna: list[dict[str, Any]] | None = None,
        historical_voice_dna: list[dict[str, Any]] | None = None,
        external_review_hooks: list[Any] | None = None,
        reviewer: "NovelEngine | None" = None,
    ) -> ChapterResult:
        """One post-plan pipeline for confirmed-plan, single and routed writers.

        A failure propagates before a result can be persisted. One repair at
        most. Neither a model pass nor these diagnostics accepts the manuscript.
        """
        plan = ChapterPlan.model_validate(plan.model_dump()).model_copy(deep=True)
        positive_int(target_chars, name="target_chars")
        bible = deepcopy(bible)
        characters = deepcopy(characters)
        recent_summaries = deepcopy(recent_summaries or [])
        style = deepcopy(style)
        hashes = set(reference_hashes or ())
        dna_history = deepcopy(historical_story_dna or [])
        voice_history = deepcopy(historical_voice_dna or [])
        hooks = list(self.external_review_hooks if external_review_hooks is None else external_review_hooks)
        reviewer = reviewer or self
        plan_sha = _data_digest(plan.model_dump())
        input_fingerprints = {
            "bible": _data_digest(bible.model_dump() if bible is not None else None),
            "characters": _data_digest([c.model_dump() for c in characters]),
            "style": _data_digest(style.model_dump() if style is not None else None),
            "recent_summaries": _data_digest(recent_summaries),
            "extra_context": _text_digest(extra_context),
            "reference_hashes": _data_digest(sorted(hashes)),
            "historical_story_dna": _data_digest(dna_history),
            "historical_voice_dna": _data_digest(voice_history),
            "target_chars": target_chars,
        }
        story_dna = story_dna_from_plan(plan).to_dict()
        dna_similarity = compare_story_dna(story_dna, dna_history)
        behavior_report = behavior_repetition(story_dna, dna_history)
        voice_baseline = aggregate_voice_baseline(voice_history)
        draft_context = extra_context
        if dna_similarity.should_avoid:
            draft_context = (draft_context + "\n\n" + dna_similarity.avoid_context).strip()
        if behavior_report.get("should_avoid"):
            draft_context = (draft_context + "\n\n" + str(behavior_report.get("avoid_context", ""))).strip()
        plan_evidence = {
            "source": "chapter_plan", "plan_sha256": plan_sha,
            "story_dna": story_dna, "story_dna_similarity": dna_similarity.to_dict(),
            "behavior_repetition": behavior_report,
            "prose_event_extraction": "not_run; plan-derived evidence is not final-prose verification",
            "historical_source_provenance": "caller supplied; accepted text revisions not authenticated here",
        }

        def analyze(text: str, stage: str) -> tuple[dict[str, Any], ChapterReview | None]:
            _require_manuscript(text)
            similarity = analyze_reference_similarity(text, reference_hashes=hashes)
            similarity_payload = similarity_review_payload(similarity)
            similarity_payload.update({
                "backends": similarity.backends,
                "coverage": {"reference_hashes": "checked" if hashes else "not_configured",
                             "fuzzy_passages": "not_configured", "semantic_passages": "not_configured",
                             "event_sequences": "not_configured"},
                "originality_verdict": None,
            })
            voice_current = character_voice_dna(text, [c.name for c in characters])
            alerts = voice_drift(voice_current, voice_baseline)
            report = {
                "schema": "final-text-analysis-v1", "stage": stage,
                "text_sha256": _text_digest(text), "plan_sha256": plan_sha,
                "input_fingerprints": deepcopy(input_fingerprints),
                "publishability_verdict": None,
                "ai_flavor": detect_ai_flavor(text),
                "ai_flavor_scope": "advisory linguistic signals; not an AI detector or acceptance gate",
                "quality_report": quality_review_payload(analyze_prose_quality(text)),
                "similarity_report": similarity_payload,
                "workflow_report": workflow_summary(plan, text, target_chars=target_chars),
                "voice": {"current": voice_current, "baseline": voice_baseline, "alerts": alerts,
                          "baseline_provenance": "caller supplied; not accepted-manuscript revision validation"},
                "plan_evidence": deepcopy(plan_evidence),
                "review_status": "reviewed" if review else "skipped",
                "external_hooks": "completed" if review and hooks else "not_requested" if review else "skipped",
                "external_hook_count": len(hooks) if review else 0,
                "author_acceptance": "pending",
            }
            selected_review = reviewer.review(bible, plan, characters, text, draft_context) if review else None
            if review and not isinstance(selected_review, ChapterReview):
                raise TypeError("configured reviewer did not return a ChapterReview")
            if review:
                selected_review = ChapterReview.model_validate(json_object_from_value(
                    selected_review, max_bytes=self.output_policy.max_output_bytes))
            for payload in (report["quality_report"], similarity_payload,
                            story_dna_review_payload(dna_similarity), behavior_review_payload(behavior_report),
                            voice_review_payload(alerts)):
                selected_review = merge_quality_issues(selected_review, payload)
            selected_review = apply_external_review_hooks(
                selected_review, hooks, draft=text, plan=plan, bible=bible, characters=characters,
                max_output_bytes=self.output_policy.max_output_bytes)
            report["review"] = selected_review.model_dump() if selected_review else None
            return report, selected_review

        draft = validate_output_text(self.draft(
            bible, plan, characters, recent_summaries, style, target_chars, user_notes, draft_context),
            max_bytes=self.output_policy.max_output_bytes)
        initial, review_result = analyze(draft, "draft")
        final, revised, review_after_repair = initial, None, None
        if auto_repair and review_result and review_result.verdict == "revise":
            revised = validate_output_text(self.repair(draft, review_result, style, draft_context),
                                           max_bytes=self.output_policy.max_output_bytes)
            final, review_after_repair = analyze(revised, "repaired")
        voice_report = deepcopy(initial["voice"])
        voice_report["initial_text_sha256"] = initial["text_sha256"]
        voice_report["final"] = deepcopy(final["voice"])
        voice_report["final_text_sha256"] = final["text_sha256"]
        if revised is not None:
            voice_report.update(revised=deepcopy(final["voice"]["current"]),
                                revised_alerts=deepcopy(final["voice"]["alerts"]))
        result = ChapterResult(
            plan=plan, draft=draft, review=review_result,
            ai_flavor=deepcopy(final["ai_flavor"]), quality_report=deepcopy(final["quality_report"]),
            similarity_report=deepcopy(final["similarity_report"]), story_dna=story_dna,
            workflow_report=deepcopy(final["workflow_report"]),
            story_dna_similarity_report=dna_similarity.to_dict(), voice_dna_report=voice_report,
            behavior_repetition_report=behavior_report, revised=revised,
            review_after_repair=review_after_repair, initial_report=deepcopy(initial), final_report=deepcopy(final),
        )
        result.final_text
        result.final_review
        return result
