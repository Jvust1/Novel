from __future__ import annotations
from dataclasses import asdict, dataclass
import importlib.util
from typing import Any, Sequence
from .quality_gate import analyze_prose_quality
from .reference_similarity import analyze_reference_similarity
from .longform_tools import near_duplicate_chapters

@dataclass(frozen=True)
class ReleaseQualitySnapshot:
    prose_score: int
    reference_similarity_score: int
    prior_chapter_similarity: list[dict[str, Any]]
    external_evaluators: dict[str, bool]
    warnings: list[str]
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def external_evaluator_capabilities() -> dict[str,bool]:
    return {"deepeval":importlib.util.find_spec("deepeval") is not None,"ragas":importlib.util.find_spec("ragas") is not None}

def build_release_quality_snapshot(text: str, *, reference_hashes: set[str]|None=None, previous_chapters: Sequence[tuple[str,str]]|None=None) -> ReleaseQualitySnapshot:
    prose=analyze_prose_quality(text)
    sim=analyze_reference_similarity(text,reference_hashes=reference_hashes)
    dup=near_duplicate_chapters(text,list(previous_chapters or []))
    warnings=[i.reason for i in prose.issues]+[i.reason for i in sim.issues]
    if dup: warnings.append("与历史章节存在较高近似："+ "、".join(f"{x.chapter_id}={x.score:.1%}" for x in dup[:3]))
    return ReleaseQualitySnapshot(prose.score,sim.score,[asdict(x) for x in dup],external_evaluator_capabilities(),warnings)
