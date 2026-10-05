from __future__ import annotations

from dataclasses import dataclass, asdict
import importlib.util
from typing import Any, Sequence

from .models import ChapterPlan


@dataclass(frozen=True)
class StoryBeatDNA:
    scene_no: int
    pov: str
    objective: str
    opposition: str
    choice: str
    cost: str
    state_change: str
    end_hook: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoryDNAProfile:
    chapter_title: str
    promise: str
    tension_curve: str
    beats: list[StoryBeatDNA]
    event_sequence: list[str]
    hook_count: int
    choice_count: int
    cost_count: int
    state_change_count: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["beats"] = [beat.to_dict() for beat in self.beats]
        return data


def story_dna_from_plan(plan: ChapterPlan) -> StoryDNAProfile:
    """Create a deterministic Story DNA profile from the approved chapter plan."""
    beats = [
        StoryBeatDNA(
            scene_no=s.scene_no,
            pov=s.pov,
            objective=s.objective,
            opposition=s.opposition,
            choice=s.choice,
            cost=s.cost,
            state_change=s.state_change,
            end_hook=s.end_hook,
        )
        for s in plan.scenes
    ]
    events = [
        " | ".join(part for part in (s.objective, s.opposition, s.choice, s.cost, s.state_change) if part)
        for s in plan.scenes
    ]
    return StoryDNAProfile(
        chapter_title=plan.chapter_title,
        promise=plan.chapter_promise,
        tension_curve=plan.tension_curve,
        beats=beats,
        event_sequence=events,
        hook_count=sum(bool(s.end_hook.strip()) for s in plan.scenes),
        choice_count=sum(bool(s.choice.strip()) for s in plan.scenes),
        cost_count=sum(bool(s.cost.strip()) for s in plan.scenes),
        state_change_count=sum(bool(s.state_change.strip()) for s in plan.scenes),
    )


class PaddleInformationExtractor:
    """Explicit opt-in PaddleNLP UIE adapter for Chinese story structure extraction."""

    DEFAULT_SCHEMA = ["人物", "地点", "事件", "目标", "阻力", "选择", "代价", "伏笔"]

    def __init__(self, schema: Sequence[str] | None = None):
        try:
            from paddlenlp import Taskflow
        except ImportError as exc:
            raise RuntimeError("需要 PaddleNLP；该重后端不会由 Novel 自动安装或下载模型") from exc
        self.schema = list(schema or self.DEFAULT_SCHEMA)
        self._task = Taskflow("information_extraction", schema=self.schema)

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("paddlenlp") is not None

    def extract(self, text: str) -> Any:
        return self._task(text)


def story_graph_to_kag_records(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert Novel's portable Story Graph into neutral records consumable by KAG pipelines."""
    records: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        records.append({
            "record_type": "node",
            "id": node.get("id", ""),
            "label": node.get("label", ""),
            "node_type": node.get("type", ""),
            "properties": {k: v for k, v in node.items() if k not in {"id", "label", "type"}},
        })
    for edge in graph.get("edges", []):
        records.append({
            "record_type": "edge",
            "source": edge.get("source", ""),
            "target": edge.get("target", ""),
            "edge_type": edge.get("type", ""),
            "label": edge.get("label", ""),
        })
    return records


def story_structure_capabilities() -> dict[str, bool]:
    return {
        "paddlenlp": importlib.util.find_spec("paddlenlp") is not None,
        "kag": importlib.util.find_spec("kag") is not None,
        "deepke": importlib.util.find_spec("deepke") is not None,
    }
