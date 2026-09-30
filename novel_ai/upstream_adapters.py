from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .recall import RecallDocument, RecallHit

_INTERNAL_PREFIX = "_novel_"
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S | re.I)
_ALLOWED_SEVERITIES = {"low", "medium", "high"}


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    fenced = _JSON_BLOCK.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _object_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    json_dict = getattr(value, "json_dict", None)
    if isinstance(json_dict, Mapping):
        return dict(json_dict)
    pydantic_value = getattr(value, "pydantic", None)
    if pydantic_value is not None and hasattr(pydantic_value, "model_dump"):
        dumped = pydantic_value.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    for method_name in ("toDict", "model_dump"):
        method = getattr(value, method_name, None)
        if callable(method):
            dumped = method()
            if isinstance(dumped, Mapping):
                return dict(dumped)
    raw = getattr(value, "raw", None)
    parsed = _json_value(raw)
    if isinstance(parsed, Mapping):
        return dict(parsed)
    if hasattr(value, "__dict__"):
        data = {key: item for key, item in vars(value).items() if not key.startswith("_")}
        if data:
            return data
    return {}


def _normalize_issue_rows(value: Any) -> list[dict[str, str]]:
    value = _json_value(value)
    if isinstance(value, Mapping) and "issues" in value:
        value = value["issues"]
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason") or item.get("message") or "").strip()
        if not reason:
            continue
        severity = str(item.get("severity") or "medium").lower().strip()
        if severity not in _ALLOWED_SEVERITIES:
            severity = "medium"
        rows.append(
            {
                "category": str(item.get("category") or "外部审校").strip() or "外部审校",
                "severity": severity,
                "excerpt": str(item.get("excerpt") or "").strip(),
                "reason": reason,
                "suggestion": str(item.get("suggestion") or "人工复核后再决定是否修改。").strip(),
            }
        )
    return rows


def _external_review_inputs(
    *,
    draft: str,
    plan: Any,
    bible: Any,
    characters: list[Any],
) -> dict[str, str]:
    def ready(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return ready(value.model_dump())
        if isinstance(value, Mapping):
            return {str(key): ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [ready(item) for item in value]
        return value

    def dump(value: Any) -> str:
        return json.dumps(ready(value), ensure_ascii=False, sort_keys=True, default=str)

    return {
        "draft": draft,
        "plan_json": dump(plan),
        "story_bible_json": dump(bible),
        "characters_json": dump(characters),
    }


class Mem0RecallBackend:
    """Opt-in Mem0 adapter implementing Novel's RecallBackend contract.

    The adapter writes accepted Novel memory items with ``infer=False`` so the
    original structured memory remains authoritative. Mem0 is an experimental
    retrieval layer only; Canon/Active/Recall stays the default path.
    """

    name = "mem0"

    def __init__(self, memory: Any, *, namespace: str = "novel") -> None:
        if not namespace.strip():
            raise ValueError("namespace 不能为空")
        if not callable(getattr(memory, "add", None)):
            raise TypeError("memory 必须提供 add()")
        if not callable(getattr(memory, "search", None)):
            raise TypeError("memory 必须提供 search()")
        self._memory = memory
        self._namespace = namespace

    @property
    def namespace(self) -> str:
        return self._namespace

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        for document in documents:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents 必须包含 RecallDocument")
            if not document.document_id.strip():
                raise ValueError("RecallDocument.document_id 不能为空")
            if not document.text.strip():
                raise ValueError("RecallDocument.text 不能为空")
            metadata = dict(document.metadata)
            metadata.update(
                {
                    "_novel_schema": "novel-mem0-recall-v1",
                    "_novel_document_id": document.document_id,
                }
            )
            messages = [{"role": "user", "content": document.text}]
            try:
                self._memory.add(
                    messages,
                    user_id=self._namespace,
                    infer=False,
                    metadata=metadata,
                )
            except TypeError:
                self._memory.add(
                    messages,
                    user_id=self._namespace,
                    metadata=metadata,
                )

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit 必须至少为 1")
        if not isinstance(text, str) or not text.strip():
            return []
        try:
            response = self._memory.search(
                query=text,
                filters={"user_id": self._namespace},
                top_k=limit,
            )
        except TypeError:
            response = self._memory.search(
                query=text,
                user_id=self._namespace,
                limit=limit,
            )
        if isinstance(response, Mapping):
            rows = response.get("results", [])
        else:
            rows = response
        if not isinstance(rows, list):
            raise ValueError("Mem0 search 返回结构无法识别")

        hits: list[RecallHit] = []
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            metadata_raw = row.get("metadata", {})
            metadata = dict(metadata_raw) if isinstance(metadata_raw, Mapping) else {}
            document_id = str(
                metadata.get("_novel_document_id")
                or row.get("id")
                or f"mem0:{index}"
            )
            stored_text = row.get("memory") or row.get("text") or row.get("data") or ""
            if not isinstance(stored_text, str) or not stored_text.strip():
                continue
            raw_score = row.get("score", row.get("similarity", 0.0))
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0
            public_metadata = {
                key: value for key, value in metadata.items() if not key.startswith(_INTERNAL_PREFIX)
            }
            hits.append(
                RecallHit(
                    document_id=document_id,
                    score=score,
                    text=stored_text,
                    metadata=public_metadata,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.document_id))
        return hits[:limit]


def create_mem0_recall_backend(
    *,
    namespace: str = "novel",
    config: dict[str, Any] | None = None,
) -> Mem0RecallBackend:
    """Create the optional OSS Mem0 client lazily without changing defaults."""
    try:
        from mem0 import Memory
    except ImportError as exc:
        raise RuntimeError(
            "缺少可选依赖 mem0ai；安装 requirements-extras/memory.txt 后再启用"
        ) from exc

    if config is None:
        memory = Memory()
    elif callable(getattr(Memory, "from_config", None)):
        memory = Memory.from_config(config)
    else:
        memory = Memory(config=config)
    return Mem0RecallBackend(memory, namespace=namespace)


class DSPyReviewHook:
    """Adapt a DSPy program to Novel's external review-hook contract."""

    name = "dspy-review"

    def __init__(self, program: Any, *, issue_field: str = "issues_json") -> None:
        if not callable(program):
            raise TypeError("DSPy program 必须可调用")
        self._program = program
        self._issue_field = issue_field

    def review_payload(
        self,
        *,
        draft: str,
        plan: Any,
        bible: Any,
        characters: list[Any],
    ) -> dict[str, Any]:
        prediction = self._program(
            **_external_review_inputs(
                draft=draft,
                plan=plan,
                bible=bible,
                characters=characters,
            )
        )
        data = _object_mapping(prediction)
        issues = data.get(self._issue_field, data.get("issues", []))
        return {"issues": _normalize_issue_rows(issues)}


def create_dspy_review_hook(
    signature: str = "draft, plan_json, story_bible_json, characters_json -> issues_json",
) -> DSPyReviewHook:
    """Create a lazy DSPy Predict reviewer; caller configures LM/optimizer explicitly."""
    try:
        import dspy
    except ImportError as exc:
        raise RuntimeError(
            "缺少可选依赖 dspy；安装 requirements-extras/orchestration.txt 后再启用"
        ) from exc
    return DSPyReviewHook(dspy.Predict(signature))


class CrewAIReviewHook:
    """Adapt a configured CrewAI Crew/Flow to Novel's external review hook."""

    name = "crewai-review"

    def __init__(self, crew: Any) -> None:
        if not callable(getattr(crew, "kickoff", None)):
            raise TypeError("crew 必须提供 kickoff(inputs=...)")
        self._crew = crew

    def review_payload(
        self,
        *,
        draft: str,
        plan: Any,
        bible: Any,
        characters: list[Any],
    ) -> dict[str, Any]:
        result = self._crew.kickoff(
            inputs=_external_review_inputs(
                draft=draft,
                plan=plan,
                bible=bible,
                characters=characters,
            )
        )
        data = _object_mapping(result)
        issues = data.get("issues")
        if issues is None:
            issues = data.get("issues_json")
        if issues is None:
            raw = getattr(result, "raw", None)
            parsed = _json_value(raw)
            if isinstance(parsed, list):
                issues = parsed
            elif isinstance(parsed, Mapping):
                issues = parsed.get("issues", parsed.get("issues_json", []))
        return {"issues": _normalize_issue_rows(issues or [])}


class LangGraphReviewHook:
    """Adapt a compiled LangGraph graph to Novel's external review hook."""

    name = "langgraph-review"

    def __init__(self, graph: Any, *, config: dict[str, Any] | None = None) -> None:
        if not callable(getattr(graph, "invoke", None)):
            raise TypeError("graph 必须提供 invoke()")
        self._graph = graph
        self._config = config

    def review_payload(self, *, draft: str, plan: Any, bible: Any, characters: list[Any]) -> dict[str, Any]:
        inputs = _external_review_inputs(draft=draft, plan=plan, bible=bible, characters=characters)
        if self._config is None:
            result = self._graph.invoke(inputs)
        else:
            result = self._graph.invoke(inputs, self._config)
        data = _object_mapping(result)
        issues = data.get("issues", data.get("issues_json", []))
        return {"issues": _normalize_issue_rows(issues)}


class PydanticAIReviewHook:
    """Adapt a configured PydanticAI Agent to Novel's external review hook."""

    name = "pydantic-ai-review"

    def __init__(self, agent: Any) -> None:
        if not callable(getattr(agent, "run_sync", None)):
            raise TypeError("agent 必须提供 run_sync()")
        self._agent = agent

    def review_payload(self, *, draft: str, plan: Any, bible: Any, characters: list[Any]) -> dict[str, Any]:
        inputs = _external_review_inputs(draft=draft, plan=plan, bible=bible, characters=characters)
        prompt = (
            "请作为小说二次审校器检查以下结构化输入。"
            "只返回你已配置的结构化审校输出，不要改写正文。\n"
            + json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        )
        result = self._agent.run_sync(prompt)
        output = getattr(result, "output", result)
        data = _object_mapping(output)
        issues = data.get("issues", data.get("issues_json", []))
        return {"issues": _normalize_issue_rows(issues)}


class GuardrailsReviewHook:
    """Adapt a configured Guardrails Guard into Novel's review issue contract."""

    name = "guardrails-review"

    def __init__(self, guard: Any, *, category: str = "Guardrails") -> None:
        if not callable(getattr(guard, "validate", None)):
            raise TypeError("guard 必须提供 validate()")
        self._guard = guard
        self._category = category

    def review_payload(self, *, draft: str, plan: Any, bible: Any, characters: list[Any]) -> dict[str, Any]:
        outcome = self._guard.validate(draft)
        passed = getattr(outcome, "validation_passed", None)
        validated = getattr(outcome, "validated_output", None)
        if passed is not False and validated is not None:
            return {"issues": []}
        error = getattr(outcome, "error", None) or getattr(outcome, "error_message", None)
        reason = str(error or "Guardrails validation failed").strip()
        return {
            "issues": [
                {
                    "category": self._category,
                    "severity": "medium",
                    "excerpt": "",
                    "reason": reason,
                    "suggestion": "根据 Guardrails 校验结果人工复核并修订。",
                }
            ]
        }


class AgentFrameworkReviewHook:
    """Adapt a configured Microsoft Agent Framework agent to Novel's review hook."""

    name = "agent-framework-review"

    def __init__(self, agent: Any) -> None:
        if not callable(getattr(agent, "run", None)):
            raise TypeError("agent 必须提供 async run()")
        self._agent = agent

    def review_payload(self, *, draft: str, plan: Any, bible: Any, characters: list[Any]) -> dict[str, Any]:
        inputs = _external_review_inputs(draft=draft, plan=plan, bible=bible, characters=characters)
        prompt = (
            "请作为小说二次审校器检查以下输入，只返回 JSON 对象，顶层字段为 issues。\n"
            + json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(self._agent.run(prompt))
        else:
            raise RuntimeError("同步 NovelEngine 中不能直接运行 Agent Framework async agent；请在线程或异步边界外调用")
        raw = getattr(result, "text", None) or getattr(result, "content", None) or str(result)
        parsed = _json_value(raw)
        if isinstance(parsed, Mapping):
            issues = parsed.get("issues", [])
        else:
            issues = []
        return {"issues": _normalize_issue_rows(issues)}
