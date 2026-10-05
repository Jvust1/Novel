from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Protocol


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    input: str
    actual_output: str
    expected_output: str = ""
    context: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricScore:
    metric: str
    score: float
    threshold: float
    passed: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    metrics: tuple[MetricScore, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.metrics)


@dataclass(frozen=True)
class EvaluationReport:
    cases: tuple[CaseEvaluation, ...]

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 1.0
        return sum(case.passed for case in self.cases) / len(self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "cases": [
                {
                    "case_id": case.case_id,
                    "passed": case.passed,
                    "metrics": [asdict(metric) for metric in case.metrics],
                }
                for case in self.cases
            ],
        }


class EvaluationMetric(Protocol):
    name: str

    def evaluate(self, case: EvaluationCase) -> MetricScore: ...


class DeepEvalMetricAdapter:
    """Wrap a configured DeepEval metric behind Novel's evaluation contract."""

    def __init__(
        self,
        metric: Any,
        *,
        name: str | None = None,
        threshold: float | None = None,
        test_case_factory: Any | None = None,
    ) -> None:
        if not callable(getattr(metric, "measure", None)):
            raise TypeError("DeepEval metric 必须提供 measure()")
        self.metric = metric
        self.name = name or metric.__class__.__name__
        raw_threshold = threshold if threshold is not None else getattr(metric, "threshold", 0.0)
        self.threshold = float(raw_threshold or 0.0)
        self._test_case_factory = test_case_factory

    def _build_test_case(self, case: EvaluationCase) -> Any:
        if self._test_case_factory is not None:
            return self._test_case_factory(case)
        try:
            from deepeval.test_case import LLMTestCase
        except ImportError as exc:
            raise RuntimeError(
                "缺少可选依赖 deepeval；安装 requirements-extras/eval.txt 后再启用"
            ) from exc
        kwargs: dict[str, Any] = {
            "input": case.input,
            "actual_output": case.actual_output,
        }
        if case.expected_output:
            kwargs["expected_output"] = case.expected_output
        if case.context:
            kwargs["retrieval_context"] = list(case.context)
        return LLMTestCase(**kwargs)

    def evaluate(self, case: EvaluationCase) -> MetricScore:
        test_case = self._build_test_case(case)
        measured = self.metric.measure(test_case)
        raw_score = getattr(self.metric, "score", measured)
        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise ValueError("DeepEval metric 没有返回可解析的数值 score") from exc
        success = getattr(self.metric, "success", None)
        passed = bool(success) if success is not None else score >= self.threshold
        return MetricScore(
            metric=self.name,
            score=score,
            threshold=self.threshold,
            passed=passed,
            reason=str(getattr(self.metric, "reason", "") or ""),
        )


class CallableMetricAdapter:
    """Small adapter for deterministic Novel-specific metrics."""

    def __init__(self, name: str, func: Any, *, threshold: float = 0.0) -> None:
        if not name.strip():
            raise ValueError("name 不能为空")
        if not callable(func):
            raise TypeError("func 必须可调用")
        self.name = name
        self.func = func
        self.threshold = float(threshold)

    def evaluate(self, case: EvaluationCase) -> MetricScore:
        result = self.func(case)
        if isinstance(result, Mapping):
            score = float(result.get("score", 0.0))
            reason = str(result.get("reason", ""))
            passed = bool(result.get("passed", score >= self.threshold))
        else:
            score = float(result)
            reason = ""
            passed = score >= self.threshold
        return MetricScore(
            metric=self.name,
            score=score,
            threshold=self.threshold,
            passed=passed,
            reason=reason,
        )


def run_evaluation(
    cases: Iterable[EvaluationCase],
    metrics: Iterable[EvaluationMetric],
) -> EvaluationReport:
    metric_list = list(metrics)
    if not metric_list:
        raise ValueError("至少需要一个 evaluation metric")
    evaluated: list[CaseEvaluation] = []
    seen: set[str] = set()
    for case in cases:
        if not case.case_id.strip():
            raise ValueError("case_id 不能为空")
        if case.case_id in seen:
            raise ValueError(f"重复 case_id: {case.case_id}")
        seen.add(case.case_id)
        scores = tuple(metric.evaluate(case) for metric in metric_list)
        evaluated.append(CaseEvaluation(case_id=case.case_id, metrics=scores))
    return EvaluationReport(cases=tuple(evaluated))


def promptfoo_config(
    cases: Iterable[EvaluationCase],
    *,
    providers: list[str],
    prompt: str = "{{input}}",
) -> dict[str, Any]:
    """Export Novel regression cases to Promptfoo's prompts/providers/tests shape."""
    if not providers:
        raise ValueError("providers 不能为空")
    tests: list[dict[str, Any]] = []
    for case in cases:
        row: dict[str, Any] = {
            "vars": {
                "case_id": case.case_id,
                "input": case.input,
                "expected_output": case.expected_output,
            },
            "metadata": dict(case.metadata),
        }
        assertions = case.metadata.get("promptfoo_assert")
        if assertions is not None:
            if not isinstance(assertions, list):
                raise ValueError("metadata.promptfoo_assert 必须是 list")
            row["assert"] = assertions
        tests.append(row)
    return {
        "description": "Novel frozen regression export",
        "prompts": [prompt],
        "providers": providers,
        "tests": tests,
    }


class LangfuseScoreSink:
    """Write Novel metric scores to Langfuse Python SDK v4 using create_score()."""

    def __init__(self, client: Any) -> None:
        if not callable(getattr(client, "create_score", None)):
            raise TypeError("Langfuse client 必须提供 create_score()")
        self.client = client

    def record_case(
        self,
        case: CaseEvaluation,
        *,
        trace_id: str,
    ) -> None:
        if not trace_id.strip():
            raise ValueError("trace_id 不能为空")
        for metric in case.metrics:
            self.client.create_score(
                name=metric.metric,
                value=float(metric.score),
                trace_id=trace_id,
                data_type="NUMERIC",
                comment=metric.reason or None,
                metadata={
                    "novel_case_id": case.case_id,
                    "threshold": metric.threshold,
                    "passed": metric.passed,
                },
            )


def create_langfuse_score_sink() -> LangfuseScoreSink:
    try:
        from langfuse import get_client
    except ImportError as exc:
        raise RuntimeError(
            "缺少可选依赖 langfuse；安装 requirements-extras/eval.txt 后再启用"
        ) from exc
    return LangfuseScoreSink(get_client())
