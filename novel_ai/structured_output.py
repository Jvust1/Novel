from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredExtractor(Protocol):
    """Optional schema-first extraction backend used by NovelEngine."""

    name: str

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
    ) -> ModelT: ...


class InstructorStructuredExtractor:
    """Use Instructor's validated structured-output API behind Novel's schema contract."""

    name = "instructor"

    def __init__(self, client: Any) -> None:
        create = getattr(getattr(getattr(client, "chat", None), "completions", None), "create", None)
        if not callable(create):
            raise TypeError("Instructor client 必须提供 chat.completions.create()")
        self._client = client

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
    ) -> ModelT:
        value = self._client.chat.completions.create(
            response_model=response_model,
            messages=messages,
            temperature=temperature,
        )
        if isinstance(value, response_model):
            return value
        if hasattr(value, "model_dump"):
            return response_model.model_validate(value.model_dump())
        return response_model.model_validate(value)


def create_instructor_extractor(
    provider: str,
    *,
    api_key: str | None = None,
    **kwargs: Any,
) -> InstructorStructuredExtractor:
    """Create Instructor lazily; Novel core never requires it."""
    if not provider.strip():
        raise ValueError("provider 不能为空")
    try:
        import instructor
    except ImportError as exc:
        raise RuntimeError(
            "缺少可选依赖 instructor；安装 requirements-extras/orchestration.txt 后再启用"
        ) from exc

    options = dict(kwargs)
    if api_key is not None:
        options["api_key"] = api_key
    client = instructor.from_provider(provider, **options)
    return InstructorStructuredExtractor(client)
