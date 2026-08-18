from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    role: str = ""
    identity: str = ""
    core_desire: str = ""
    current_goal: str = ""
    fear: str = ""
    flaw: str = ""
    self_deception: str = ""
    secret: str = ""
    speech: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    knows: list[str] = Field(default_factory=list)
    does_not_know: list[str] = Field(default_factory=list)
    false_beliefs: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    status: dict[str, str] = Field(default_factory=dict)
    recent_change: str = ""


class StoryBible(BaseModel):
    title: str = "未命名小说"
    genre: str = ""
    audience: str = ""
    tone: str = ""
    premise: str = ""
    themes: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    locked_facts: list[str] = Field(default_factory=list)
    forbidden_moves: list[str] = Field(default_factory=list)


class SceneBeat(BaseModel):
    scene_no: int
    pov: str = ""
    place: str = ""
    time: str = ""
    objective: str
    opposition: str
    choice: str
    cost: str
    state_change: str
    information_release: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    environment_function: str = ""
    end_hook: str = ""


class ChapterPlan(BaseModel):
    chapter_title: str = ""
    chapter_promise: str = ""
    tension_curve: str = ""
    scenes: list[SceneBeat] = Field(default_factory=list)
    must_not_happen: list[str] = Field(default_factory=list)


class StyleFingerprint(BaseModel):
    name: str = "default"
    source_count: int = 1
    avg_sentence_chars: float = 0.0
    sentence_std: float = 0.0
    short_sentence_ratio: float = 0.0
    long_sentence_ratio: float = 0.0
    avg_paragraph_chars: float = 0.0
    paragraph_std: float = 0.0
    dialogue_ratio: float = 0.0
    exclamation_density: float = 0.0
    ellipsis_density: float = 0.0
    metaphor_marker_density: float = 0.0
    lexical_diversity: float = 0.0
    narrative_distance: str = ""
    pov_preference: str = ""
    action_psychology_environment_balance: str = ""
    diction: str = ""
    rhythm_notes: str = ""
    emotion_expression: str = ""
    imagery_notes: str = ""
    avoid_patterns: list[str] = Field(default_factory=list)
    custom_notes: list[str] = Field(default_factory=list)

    def prompt_view(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ReviewIssue(BaseModel):
    category: str
    severity: str = "medium"
    excerpt: str = ""
    reason: str
    suggestion: str


class ChapterReview(BaseModel):
    verdict: str = "revise"
    issues: list[ReviewIssue] = Field(default_factory=list)
    continuity_updates: list[str] = Field(default_factory=list)
    character_updates: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
