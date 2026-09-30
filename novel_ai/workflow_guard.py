from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .models import ChapterPlan


@dataclass(frozen=True)
class WorkflowCheck:
    stage: str
    ok: bool
    issues: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_plan_stage(plan: ChapterPlan) -> WorkflowCheck:
    """Novel-owned phase gate inspired by multi-phase novelist workflows."""
    issues: list[str] = []
    if not plan.scenes:
        issues.append("场景计划为空")
    for scene in plan.scenes:
        if not scene.objective.strip():
            issues.append(f"场景 {scene.scene_no} 缺少目标")
        if not scene.opposition.strip():
            issues.append(f"场景 {scene.scene_no} 缺少阻力")
        if not scene.choice.strip():
            issues.append(f"场景 {scene.scene_no} 缺少选择")
        if not scene.state_change.strip():
            issues.append(f"场景 {scene.scene_no} 缺少状态变化")
    return WorkflowCheck("planning", not issues, issues)


def validate_draft_stage(text: str, *, target_chars: int = 3500) -> WorkflowCheck:
    compact = "".join(text.split())
    issues: list[str] = []
    if len(compact) < max(500, int(target_chars * 0.55)):
        issues.append("正文明显短于目标，可能存在场景未展开")
    if len(compact) > int(target_chars * 1.8):
        issues.append("正文明显超出目标，可能存在失控扩写")
    if not any(mark in text[-300:] for mark in ("？", "！", "……", "。", "”")):
        issues.append("章末缺少明确收束或钩子标记")
    return WorkflowCheck("draft", not issues, issues)


def workflow_summary(plan: ChapterPlan, text: str, *, target_chars: int = 3500) -> dict[str, Any]:
    checks = [validate_plan_stage(plan), validate_draft_stage(text, target_chars=target_chars)]
    return {
        "stages": [check.to_dict() for check in checks],
        "ready_for_review": all(check.ok for check in checks),
    }
