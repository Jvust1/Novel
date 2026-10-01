"""Explicit writing entry with one shared request allowance across all roles.

Uses the existing engine, router and stage output caps. This entry deliberately
does not admit opaque SDK extractors or external review hooks whose internal
requests cannot be counted by the owned HTTP transport.
"""
from __future__ import annotations

from typing import Any

from .engine import ChapterResult, NovelEngine
from .orchestration import ProviderRouter, RouterConfig, TaskKind
from .output_policy import OutputPolicy, positive_int
from .request_budget import RequestBudget, RequestBudgetLimits
from .routed_engine import RoutedNovelEngine


class BudgetedWritingSession:
    """One explicitly configured process-local writing session, no persistence.

    Repeated calls share the same monotone allowance; there is no hidden reset
    on run(), exception or retry. A new session is an explicit new allowance.
    Configure only endpoints already authorized for the manuscript. Merely
    constructing this object neither contacts them nor authorizes paid calls.
    """

    def __init__(self, config: RouterConfig, *, limits: RequestBudgetLimits | None = None,
                 output_policy: OutputPolicy | None = None):
        if type(config) is not RouterConfig:
            raise TypeError("explicit RouterConfig required; no implicit environment routing")
        if output_policy is not None and type(output_policy) is not OutputPolicy:
            raise TypeError("output_policy must be OutputPolicy")
        self._budget = RequestBudget(limits)
        self._router = ProviderRouter(config, request_budget=self._budget)
        self._output_policy = output_policy or OutputPolicy()

    def _engine(self, role: TaskKind) -> NovelEngine:
        return NovelEngine(self._router.provider_for(role).provider, output_policy=self._output_policy)

    @staticmethod
    def _check_options(options: dict[str, Any]) -> None:
        for name, default in (("review", True), ("auto_repair", False)):
            if type(options.get(name, default)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        positive_int(options.get("target_chars", 3500), name="target_chars")
        if "reviewer" in options or "external_review_hooks" in options or "structured_extractor" in options:
            raise ValueError("bounded session does not support externally supplied execution paths")

    def run(self, **options: Any) -> ChapterResult:
        """Plan, draft, review, repair and re-review under the same allowance."""
        self._check_options(options)
        # Discover a known missing role before spending on the plan.
        self._router.provider_for(TaskKind.DRAFT)
        if options.get("review", True):
            self._router.provider_for(TaskKind.REVIEW)
        return RoutedNovelEngine(self._router, output_policy=self._output_policy).run(**options)

    def run_from_plan(self, **options: Any) -> ChapterResult:
        """Execute the already chosen plan without generating a replacement."""
        self._check_options(options)
        writer = self._engine(TaskKind.DRAFT)
        reviewer = self._engine(TaskKind.REVIEW) if options.get("review", True) else None
        return writer.run_from_plan(**options, reviewer=reviewer)

    def extract_memory(self, *args: Any, **options: Any) -> Any:
        """Produce a memory candidate only; this function does not apply it."""
        return self._engine(TaskKind.MEMORY).extract_memory(*args, **options)

    def enrich_style(self, *args: Any, **options: Any) -> Any:
        return self._engine(TaskKind.REVIEW).enrich_style(*args, **options)

    def close(self) -> None:
        self._budget.close()

    def budget_snapshot(self) -> dict[str, Any]:
        """Detached metadata only; no prompt, response, credentials or endpoint."""
        return self._budget.snapshot()
