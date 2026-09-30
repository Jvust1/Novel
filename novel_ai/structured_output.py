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


class OutlinesStructuredExtractor:
    """Use an Outlines-compatible callable for constrained Pydantic generation."""

    name = "outlines"

    def __init__(self, model: Any) -> None:
        if not callable(model):
            raise TypeError("Outlines model 必须可调用")
        self._model = model

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
    ) -> ModelT:
        prompt = "\n\n".join(
            f"[{item.get('role', 'user')}] {item.get('content', '')}"
            for item in messages
        )
        try:
            value = self._model(prompt, response_model, temperature=temperature)
        except TypeError:
            value = self._model(prompt, response_model)
        if isinstance(value, response_model):
            return value
        if isinstance(value, str):
            return response_model.model_validate_json(value)
        if hasattr(value, "model_dump"):
            return response_model.model_validate(value.model_dump())
        return response_model.model_validate(value)



class GuidanceStructuredExtractor:
    """Use Guidance constrained JSON generation behind Novel's schema contract."""

    name = "guidance"

    def __init__(self, model: Any, *, json_factory: Any | None = None) -> None:
        if not hasattr(model, "__iadd__") and not hasattr(model, "__add__"):
            raise TypeError("Guidance model must support lm += ...")
        if json_factory is None:
            try:
                from guidance import json as json_factory
            except ImportError as exc:
                raise RuntimeError(
                    "Guidance is optional; install requirements-extras/orchestration.txt before enabling it"
                ) from exc
        if not callable(json_factory):
            raise TypeError("json_factory must be callable")
        self._model = model
        self._json_factory = json_factory

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
    ) -> ModelT:
        prompt = "\n\n".join(
            f"[{item.get('role', 'user')}] {item.get('content', '')}"
            for item in messages
        )
        lm = self._model
        lm += prompt
        lm += self._json_factory(
            name="novel_structured_output",
            schema=response_model,
            temperature=temperature,
        )
        value = lm["novel_structured_output"]
        if isinstance(value, response_model):
            return value
        if isinstance(value, str):
            return response_model.model_validate_json(value)
        if hasattr(value, "model_dump"):
            return response_model.model_validate(value.model_dump())
        return response_model.model_validate(value)



class FallbackStructuredExtractor:
    """Try multiple StructuredExtractor backends in order until one validates."""

    name = "fallback-chain"

    def __init__(self, extractors: list[Any] | tuple[Any, ...]) -> None:
        self.extractors = tuple(extractors)
        if not self.extractors:
            raise ValueError("at least one structured extractor is required")
        for extractor in self.extractors:
            if not callable(getattr(extractor, "extract", None)):
                raise TypeError("every structured extractor must provide extract()")

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
    ) -> ModelT:
        failures: list[str] = []
        for extractor in self.extractors:
            try:
                value = extractor.extract(
                    response_model=response_model,
                    messages=messages,
                    temperature=temperature,
                )
                if isinstance(value, response_model):
                    return value
                if hasattr(value, "model_dump"):
                    return response_model.model_validate(value.model_dump())
                return response_model.model_validate(value)
            except Exception as exc:
                name = str(getattr(extractor, "name", extractor.__class__.__name__))
                failures.append(f"{name}: {exc.__class__.__name__}")
        raise RuntimeError(
            "all structured extractors failed: " + ", ".join(failures)
        )


def chain_structured_extractors(*extractors: Any) -> FallbackStructuredExtractor:
    return FallbackStructuredExtractor(extractors)
