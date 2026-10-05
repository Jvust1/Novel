from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, Field

from .models import ChapterPlan

OutlineLevel = Literal["series", "volume", "arc", "chapter", "scene"]
_LEVEL_ORDER = {"series": 0, "volume": 1, "arc": 2, "chapter": 3, "scene": 4}


class OutlineNode(BaseModel):
    """One node in a DOC-style hierarchical outline."""

    id: str
    level: OutlineLevel
    title: str
    promise: str = ""
    conflict: str = ""
    outcome: str = ""
    children: list["OutlineNode"] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HierarchicalOutline(BaseModel):
    version: str = "0.1"
    title: str
    premise: str = ""
    root: OutlineNode
    notes: list[str] = Field(default_factory=list)

    def flatten(self) -> list[OutlineNode]:
        rows: list[OutlineNode] = []

        def walk(node: OutlineNode) -> None:
            rows.append(node)
            for child in node.children:
                walk(child)

        walk(self.root)
        return rows


def _stable_id(level: str, position: str, title: str) -> str:
    digest = hashlib.sha256(f"{level}:{position}:{title}".encode("utf-8")).hexdigest()[:8]
    return f"{level}-{position}-{digest}"


def _validate_node(node: OutlineNode, *, parent: OutlineNode | None, seen: set[str]) -> None:
    if node.id in seen:
        raise ValueError(f"大纲节点 id 重复: {node.id}")
    seen.add(node.id)
    if parent is not None and _LEVEL_ORDER[node.level] != _LEVEL_ORDER[parent.level] + 1:
        raise ValueError(
            f"层级不连续: {parent.level} -> {node.level} ({node.id})"
        )
    for child in node.children:
        _validate_node(child, parent=node, seen=seen)


def validate_outline(outline: HierarchicalOutline) -> HierarchicalOutline:
    """Fail closed on duplicate IDs or skipped hierarchy levels."""
    if outline.root.level != "series":
        raise ValueError("大纲根节点必须是 series")
    _validate_node(outline.root, parent=None, seen=set())
    return outline


def _chapter_node(plan: ChapterPlan, *, volume_no: int, chapter_no: int) -> OutlineNode:
    chapter_id = _stable_id("chapter", f"v{volume_no}-c{chapter_no}", plan.chapter_title)
    scenes: list[OutlineNode] = []
    for scene in plan.scenes:
        scene_id = _stable_id("scene", f"v{volume_no}-c{chapter_no}-s{scene.scene_no}", scene.objective)
        scenes.append(
            OutlineNode(
                id=scene_id,
                level="scene",
                title=f"场景 {scene.scene_no}",
                promise=scene.objective,
                conflict=scene.opposition,
                outcome=scene.state_change,
                metadata={
                    "pov": scene.pov,
                    "place": scene.place,
                    "time": scene.time,
                    "choice": scene.choice,
                    "cost": scene.cost,
                    "information_release": scene.information_release,
                    "foreshadowing": scene.foreshadowing,
                    "environment_function": scene.environment_function,
                    "end_hook": scene.end_hook,
                },
            )
        )
    outcome = plan.scenes[-1].state_change if plan.scenes else ""
    return OutlineNode(
        id=chapter_id,
        level="chapter",
        title=plan.chapter_title or f"第 {chapter_no} 章",
        promise=plan.chapter_promise,
        conflict=plan.tension_curve,
        outcome=outcome,
        children=scenes,
        metadata={"must_not_happen": plan.must_not_happen},
    )


def build_hierarchical_outline(
    title: str,
    premise: str,
    volumes: Sequence[tuple[str, Sequence[ChapterPlan]]],
    *,
    notes: Iterable[str] = (),
) -> HierarchicalOutline:
    """Convert accepted chapter plans into a stable series/volume/arc tree.

    The function only restructures existing plans; it does not invent prose or
    call a model. Each volume receives one default arc container so chapter
    plans can be expanded later without changing their IDs.
    """
    volume_nodes: list[OutlineNode] = []
    for volume_no, (volume_title, chapter_plans) in enumerate(volumes, start=1):
        chapters = [
            _chapter_node(plan, volume_no=volume_no, chapter_no=chapter_no)
            for chapter_no, plan in enumerate(chapter_plans, start=1)
        ]
        arc = OutlineNode(
            id=_stable_id("arc", f"v{volume_no}-main", volume_title),
            level="arc",
            title="主线推进",
            promise="让本卷章节围绕同一条主要冲突推进。",
            conflict="章节之间必须产生连续的目标、阻力与后果。",
            children=chapters,
            metadata={"source": "chapter_plans"},
        )
        volume_nodes.append(
            OutlineNode(
                id=_stable_id("volume", str(volume_no), volume_title),
                level="volume",
                title=volume_title or f"第 {volume_no} 卷",
                promise="本卷阶段性目标与读者期待。",
                children=[arc],
                metadata={"volume_no": volume_no},
            )
        )

    outline = HierarchicalOutline(
        title=title,
        premise=premise,
        root=OutlineNode(
            id=_stable_id("series", "root", title),
            level="series",
            title=title or "未命名长篇",
            promise=premise,
            children=volume_nodes,
        ),
        notes=list(notes)
        + [
            "层级大纲只重组已确认的 ChapterPlan，不自动生成正文或隐藏剧情。",
            "每个节点保存目标、冲突、结果和必要的场景元数据，便于逐层审阅。",
        ],
    )
    return validate_outline(outline)


def save_outline(outline: HierarchicalOutline, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(outline.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
