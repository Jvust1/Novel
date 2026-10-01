"""Bounded model calls, shared by providers and writing stages.

Per-attempt output caps remain separate from a full-input guard and the
cumulative retry/fallback allowance. The input counter is an engineering guard,
not a claim about a provider's proprietary chat template or billed tokens.
Strict serialization follows ProjectStore's existing ``allow_nan=False`` and
UTF-8 round-trip contract, additionally refusing duplicate object keys.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from typing import Any

DEFAULT_MAX_TOKENS = 16384
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class OutputValidationError(ValueError):
    """A model output is missing, incomplete, ambiguous, or over its allowance."""


def positive_int(value: Any, *, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class OutputPolicy:
    """Explicit stage caps; target_chars remains a separate, soft prose goal."""

    plan_tokens: int = 8192
    draft_tokens: int = 16384
    review_tokens: int = 8192
    repair_tokens: int = 16384
    style_tokens: int = 4096
    memory_tokens: int = 8192
    max_input_tokens: int = 65536
    max_attempts_per_stage: int = 3
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        for field in fields(self):
            positive_int(getattr(self, field.name), name=field.name)

    def tokens_for(self, stage: str) -> int:
        if stage not in {"plan", "draft", "review", "repair", "style", "memory"}:
            raise ValueError("unknown model-output stage")
        return getattr(self, f"{stage}_tokens")

    def total_output_tokens_for(self, stage: str) -> int:
        """Cumulative reservation ceiling across retries/fallbacks for one stage."""
        return self.tokens_for(stage) * self.max_attempts_per_stage


def validate_output_text(value: Any, *, max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES) -> str:
    """Validate without trimming, coercing, clipping, or echoing private output."""
    positive_int(max_bytes, name="max_bytes")
    if not isinstance(value, str):
        raise OutputValidationError("model output must be a string")
    if not value.strip():
        raise OutputValidationError("model output is blank")
    # Avoid a second oversized allocation for an already oversized string.
    if len(value) > max_bytes:
        raise OutputValidationError("model output exceeds its byte allowance")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise OutputValidationError("model output is not valid UTF-8") from None
    if size > max_bytes:
        raise OutputValidationError("model output exceeds its byte allowance")
    return value


def _reject_constant(_value: str) -> None:
    raise OutputValidationError("nonfinite JSON constant refused")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OutputValidationError("duplicate JSON object key refused")
        result[key] = value
    return result


def _serializable(value: Any) -> None:
    # Matches the local storage boundary, including 1e999 and lone surrogates.
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise OutputValidationError("JSON contains unsupported values") from None


def strict_json_object(text: str, *, max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES) -> dict[str, Any]:
    """Decode exactly one strict JSON object, without any commentary wrappers."""
    text = validate_output_text(text, max_bytes=max_bytes)
    try:
        value = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except OutputValidationError:
        raise
    except (ValueError, RecursionError, OverflowError):
        raise OutputValidationError("model JSON is malformed or incomplete") from None
    if not isinstance(value, dict):
        raise OutputValidationError("model JSON top level must be an object")
    _serializable(value)
    return value


def _plain_commentary(text: str) -> bool:
    """A wrapper may contain prose, never JSON/fence syntax or another value."""
    if any(char in text for char in '{}[]"`'):
        return False
    stripped = text.strip()
    if not stripped:
        return True
    # Do not salvage an object from a scalar/sequence, e.g. true {..} or 1 {..}.
    return stripped[0].isalpha() and not re.match(
        r"(?:true|false|null|NaN|Infinity)\b", stripped, re.I
    )


def parse_json_object(text: str, *, max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES) -> dict[str, Any]:
    """Accept a complete object, a single JSON fence, or simple prose framing.

    Plain prefix/suffix prose may not contain JSON structural/string syntax,
    fences or start with a JSON scalar. Arrays, scalar roots, multiple objects,
    partial objects/fences and automatic closing/repair are always rejected.
    raw_decode, rather than a brace regex, preserves nested/escaped braces.
    """
    text = validate_output_text(text, max_bytes=max_bytes).strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```", text, re.I)
        if not match:
            raise OutputValidationError("model JSON fence is incomplete or ambiguous")
        return strict_json_object(match.group(1), max_bytes=max_bytes)
    if text.startswith("{"):
        # A suffix is allowed only under the same restricted prose-framing rule.
        start = 0
    else:
        start = text.find("{")
        if start < 0 or not _plain_commentary(text[:start]):
            raise OutputValidationError("model JSON top level must be an object")
    try:
        decoder = json.JSONDecoder(parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        value, end = decoder.raw_decode(text, start)
    except OutputValidationError:
        raise
    except (ValueError, RecursionError, OverflowError):
        raise OutputValidationError("model JSON is malformed or incomplete") from None
    if not isinstance(value, dict) or not _plain_commentary(text[end:]):
        raise OutputValidationError("model JSON contains ambiguous trailing content")
    _serializable(value)
    return value


def json_object_from_value(value: Any, *, max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES) -> dict[str, Any]:
    """Validate structured adapter results using the same strict JSON boundary."""
    if isinstance(value, str):
        return parse_json_object(value, max_bytes=max_bytes)
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python", warnings=False)
    if not isinstance(value, dict):
        raise OutputValidationError("structured output must be an object")
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise OutputValidationError("structured output contains unsupported values") from None
    return strict_json_object(text, max_bytes=max_bytes)


def _field(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def completion_text(response: Any, *, max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
                    allow_tool_call: bool = False, max_tokens: int | None = None) -> str:
    """Require affirmative completion metadata; missing finish_reason fails shut.

    OpenAI-compatible/LiteLLM legacy servers omitting finish_reason must fix
    their response adapter. A nonblank string alone cannot establish completion.
    Instructor can opt into one complete tool call; plain chat cannot.
    """
    if max_tokens is not None:
        positive_int(max_tokens, name="max_tokens")
        usage = _field(response, "usage")
        used = _field(usage, "completion_tokens")
        # Usage is optional in compatible APIs. Check it when supplied; no
        # local tokenizer or exact token-count assertion is fabricated.
        if used is not None and (type(used) is not int or used < 0 or used > max_tokens):
            raise OutputValidationError("model completion usage exceeds or invalidates its token allowance")
    choices = _field(response, "choices")
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        raise OutputValidationError("model completion must contain exactly one choice")
    choice = choices[0]
    message = _field(choice, "message")
    if message is None:
        raise OutputValidationError("model completion is missing its message")
    refusal = _field(message, "refusal")
    if refusal is not None and refusal != "":
        raise OutputValidationError("model refused the requested output")
    finish_reason = _field(choice, "finish_reason")
    if allow_tool_call and finish_reason == "tool_calls":
        calls = _field(message, "tool_calls")
        if not isinstance(calls, (list, tuple)) or len(calls) != 1:
            raise OutputValidationError("structured completion must contain one tool call")
        function = _field(calls[0], "function")
        return validate_output_text(_field(function, "arguments"), max_bytes=max_bytes)
    if finish_reason != "stop":
        # Never include an untrusted reason (or response body) in the exception.
        raise OutputValidationError("model completion is incomplete or lacks a confirmed stop")
    if _field(message, "tool_calls") or _field(message, "function_call"):
        raise OutputValidationError("unexpected tool call in a text completion")
    return validate_output_text(_field(message, "content"), max_bytes=max_bytes)
