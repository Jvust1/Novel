from __future__ import annotations

import inspect
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .token_budget import ModelBudgetExceeded, ModelCallBudget
from .output_policy import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_TOKENS,
    OutputValidationError,
    completion_text,
    json_object_from_value,
    parse_json_object,
    positive_int,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class UnsupportedOutputBound(OutputValidationError):
    """The selected adapter cannot preserve an explicit output allowance."""


class StructuredExtractor(Protocol):
    """Bound-aware schema extraction; never discard an unsupported allowance."""

    name: str

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> ModelT: ...


def _limits(max_tokens: int, max_output_bytes: int) -> None:
    positive_int(max_tokens, name="max_tokens")
    positive_int(max_output_bytes, name="max_output_bytes")


def _validate(response_model: type[ModelT], value: Any, max_output_bytes: int) -> ModelT:
    # Dump and revalidate even a native model: model_construct/model_copy can
    # bypass field validation. Strict JSON also catches nonfinite nested data.
    value = json_object_from_value(value, max_bytes=max_output_bytes)
    try:
        return response_model.model_validate(value)
    except ValidationError:
        raise OutputValidationError("structured output does not match the requested schema") from None


def _check_keywords(function: Any, *args: Any, **kwargs: Any) -> None:
    """Check inspectable APIs before calling; no execution-and-TypeError retry."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        raise UnsupportedOutputBound("cannot verify the adapter's output-bound API") from None
    try:
        signature.bind(*args, **kwargs)
    except TypeError:
        raise UnsupportedOutputBound("adapter does not support the requested bounded call") from None


class InstructorStructuredExtractor:
    """Use Instructor's raw-completion API with one bounded attempt.

    Only OpenAI-compatible stop/tool_calls metadata is supported here. Other
    provider response shapes fail closed, rather than pretending completion
    evidence exists. SDK transport buffering is outside this adapter's control.
    """

    name = "instructor"

    def __init__(self, client: Any) -> None:
        completions = getattr(getattr(client, "chat", None), "completions", None)
        create = getattr(completions, "create_with_completion", None)
        if not callable(create):
            raise UnsupportedOutputBound("Instructor client must provide create_with_completion()")
        self._create = create

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> ModelT:
        _limits(max_tokens, max_output_bytes)
        kwargs = dict(response_model=response_model, messages=messages,
                      temperature=temperature, max_tokens=max_tokens, max_retries=0)
        _check_keywords(self._create, **kwargs)
        try:
            result = self._create(**kwargs)
        except Exception as exc:
            raise RuntimeError(f"Instructor extraction failed ({type(exc).__name__})") from None
        if not isinstance(result, tuple) or len(result) != 2:
            raise OutputValidationError("Instructor did not return completion evidence")
        value, completion = result
        raw = completion_text(completion, max_bytes=max_output_bytes,
                              allow_tool_call=True, max_tokens=max_tokens)
        from_raw = _validate(response_model, parse_json_object(raw, max_bytes=max_output_bytes), max_output_bytes)
        from_model = _validate(response_model, value, max_output_bytes)
        if from_model.model_dump(mode="json") != from_raw.model_dump(mode="json"):
            raise OutputValidationError("Instructor result does not match its raw completion")
        return from_raw


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
    """A constrained-JSON adapter with an explicit backend token-cap keyword.

    Outlines forwards backend-specific generation kwargs: e.g. Transformers
    uses max_new_tokens, hosted APIs may use max_tokens. An unknown mapping is
    refused before inference. A complete strict JSON object and schema are
    checked; the callable exposes neither stop metadata nor transport bytes.
    """

    name = "outlines"

    def __init__(self, model: Any, *, token_limit_parameter: str | None = None) -> None:
        if not callable(model):
            raise TypeError("Outlines model 必须可调用")
        if token_limit_parameter not in {None, "max_tokens", "max_new_tokens"}:
            raise ValueError("unsupported Outlines token-limit parameter")
        self._model = model
        self._token_limit_parameter = token_limit_parameter

    def extract(
        self,
        *,
        response_model: type[ModelT],
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> ModelT:
        _limits(max_tokens, max_output_bytes)
        if self._token_limit_parameter is None:
            raise UnsupportedOutputBound("Outlines backend token_limit_parameter must be configured explicitly")
        prompt = "\n\n".join(
            f"[{item.get('role', 'user')}] {item.get('content', '')}" for item in messages
        )
        kwargs = {"temperature": temperature, self._token_limit_parameter: max_tokens}
        _check_keywords(self._model, prompt, response_model, **kwargs)
        try:
            value = self._model(prompt, response_model, **kwargs)
        except Exception as exc:
            raise RuntimeError(f"Outlines extraction failed ({type(exc).__name__})") from None
        return _validate(response_model, value, max_output_bytes)


class GuidanceStructuredExtractor:
    """Bounded Guidance JSON capture, validated for strict syntax and schema.

    Guidance's json(max_tokens=...) limits generation. The capture interface
    has no provider finish_reason: successful strict/schema validation proves
    object completeness only, not transport-stop or pre-buffer byte evidence.
    """

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
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> ModelT:
        _limits(max_tokens, max_output_bytes)
        kwargs = dict(name="novel_structured_output", schema=response_model,
                      temperature=temperature, max_tokens=max_tokens)
        _check_keywords(self._json_factory, **kwargs)
        prompt = "\n\n".join(
            f"[{item.get('role', 'user')}] {item.get('content', '')}" for item in messages
        )
        try:
            lm = self._model
            lm += prompt
            lm += self._json_factory(**kwargs)
            value = lm["novel_structured_output"]
        except Exception as exc:
            raise RuntimeError(f"Guidance extraction failed ({type(exc).__name__})") from None
        return _validate(response_model, value, max_output_bytes)


class FallbackStructuredExtractor:
    """Try selected backends in order under one optional cumulative allowance.

    NovelEngine supplies a shared ModelCallBudget. Each real backend attempt
    reserves from it before execution; exhaustion propagates instead of silently
    falling through to another provider. Direct legacy callers without a budget
    retain the previous per-attempt behavior.
    """

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
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        budget: ModelCallBudget | None = None,
    ) -> ModelT:
        _limits(max_tokens, max_output_bytes)
        failures: list[str] = []
        for extractor in self.extractors:
            try:
                attempt_tokens = budget.claim(messages, max_tokens) if budget is not None else max_tokens
                kwargs = dict(response_model=response_model, messages=messages,
                              temperature=temperature, max_tokens=attempt_tokens,
                              max_output_bytes=max_output_bytes)
                _check_keywords(extractor.extract, **kwargs)
                value = extractor.extract(**kwargs)
                return _validate(response_model, value, max_output_bytes)
            except ModelBudgetExceeded:
                raise
            except Exception as exc:
                name = str(getattr(extractor, "name", extractor.__class__.__name__))
                failures.append(f"{name}: {exc.__class__.__name__}")
        raise RuntimeError("all structured extractors failed: " + ", ".join(failures))


def chain_structured_extractors(*extractors: Any) -> FallbackStructuredExtractor:
    return FallbackStructuredExtractor(extractors)
