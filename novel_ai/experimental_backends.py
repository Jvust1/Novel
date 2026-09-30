from __future__ import annotations

from dataclasses import dataclass, asdict
import importlib.util
from typing import Any


@dataclass(frozen=True)
class ExperimentalBackend:
    key: str
    import_name: str
    category: str
    role: str

    @property
    def available(self) -> bool:
        try:
            return importlib.util.find_spec(self.import_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["available"] = self.available
        return data


EXPERIMENTAL_BACKENDS: tuple[ExperimentalBackend, ...] = (
    ExperimentalBackend("mem0", "mem0", "memory", "memory extraction / retrieval experiment"),
    ExperimentalBackend("llama_index", "llama_index", "orchestration", "index / retriever abstraction"),
    ExperimentalBackend("langchain", "langchain", "orchestration", "retriever / tool composition"),
    ExperimentalBackend("haystack", "haystack", "orchestration", "pipeline composition"),
    ExperimentalBackend("chroma", "chromadb", "vector_store", "local vector store experiment"),
    ExperimentalBackend("dspy", "dspy", "prompt_optimization", "benchmark-driven prompt/program optimization"),
    ExperimentalBackend("crewai", "crewai", "orchestration", "optional second-pass editorial Crew/Flow"),
    ExperimentalBackend("instructor", "instructor", "structured_output", "validated Pydantic extraction"),
    ExperimentalBackend("langgraph", "langgraph", "orchestration", "durable stateful editorial workflow"),
    ExperimentalBackend("pydantic_ai", "pydantic_ai", "orchestration", "typed editorial agent"),
)


def experimental_backend_matrix() -> list[dict[str, Any]]:
    return [item.to_dict() for item in EXPERIMENTAL_BACKENDS]


def available_backends(*, category: str | None = None) -> list[str]:
    items = EXPERIMENTAL_BACKENDS
    if category:
        items = tuple(item for item in items if item.category == category)
    return [item.key for item in items if item.available]


def choose_backend(
    preferred: list[str],
    *,
    category: str | None = None,
    fallback: str = "novel-core",
) -> str:
    """Select the first installed backend from an explicit preference order.

    Nothing is enabled implicitly: callers must pass an ordered preference
    list. The deterministic Novel core remains the default fallback.
    """
    allowed = {
        item.key: item
        for item in EXPERIMENTAL_BACKENDS
        if category is None or item.category == category
    }
    for key in preferred:
        item = allowed.get(key)
        if item and item.available:
            return key
    return fallback
