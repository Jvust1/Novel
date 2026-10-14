"""Route explicit review findings; do not infer literary quality from prose.

This module is deliberately dependency-free. Its input is the serialized,
validated ChapterReview used by the engine. None means review was not run.
The returned issue indexes are zero-based positions in that review's issues.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


STORY_REPLAN_CATEGORY = "story_structure_requires_replan"


class StoryReplanRequired(ValueError):
    """Local repair cannot resolve the current review without a new plan."""


def story_revision_route(review: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a new routing receipt, without changing review or accepting text.

    Only the explicit category field triggers structural routing. Quoted text,
    suggested commands and prose keywords cannot request a workflow transition.
    A structural finding wins over a mistakenly supplied pass or low severity.
    Unknown categories continue through the existing pass/revise workflow; this
    function does not invent a structural finding or replace editorial review.
    """
    structural: list[int] = []
    if review is None:
        status, next_action, local = "review_not_run", "review", False
    else:
        if not isinstance(review, Mapping):
            raise TypeError("review must be a mapping or None")
        verdict, issues = review.get("verdict"), review.get("issues")
        if verdict not in ("pass", "revise") or not isinstance(issues, list):
            raise ValueError("review requires pass/revise and an explicit issues list")
        for index, issue in enumerate(issues):
            if not isinstance(issue, Mapping) or not isinstance(issue.get("category"), str):
                raise ValueError("each issue requires a text category")
            if issue["category"].strip().casefold() == STORY_REPLAN_CATEGORY:
                structural.append(index)
        if structural:
            status, next_action, local = (
                "awaiting_plan_revision", "revise_plan_then_author_confirm", False,
            )
        elif verdict == "revise":
            status, next_action, local = (
                "local_repair_candidate", "local_repair_then_review", True,
            )
        else:
            status, next_action, local = "awaiting_author_review", "author_review", False
    return {
        "schema": "story-revision-route-v1",
        "status": status,
        "requires_replan": bool(structural),
        "local_repair_allowed": local,
        "structural_issue_indexes": structural,
        "next_action": next_action,
        "scope": "explicit review routing; not a quality score or author acceptance",
    }
