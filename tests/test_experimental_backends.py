from novel_ai.experimental_backends import (
    available_backends,
    choose_backend,
    experimental_backend_matrix,
)


def test_backend_matrix_shape():
    rows = experimental_backend_matrix()
    keys = {row["key"] for row in rows}
    assert {"mem0", "llama_index", "langchain", "haystack", "chroma", "dspy"} <= keys
    assert all(isinstance(row["available"], bool) for row in rows)


def test_choose_backend_never_enables_missing_implicitly():
    chosen = choose_backend(["definitely_missing_backend"], fallback="novel-core")
    assert chosen == "novel-core"


def test_available_backends_filters_category():
    rows = available_backends(category="orchestration")
    assert set(rows) <= {"llama_index", "langchain", "haystack", "crewai", "langgraph", "pydantic_ai", "agent_framework"}
