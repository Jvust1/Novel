from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .token_budget import ModelBudgetExceeded, ModelCallBudget
from .output_policy import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_TOKENS,
    OutputValidationError,
    completion_text,
    positive_int,
    strict_json_object,
)

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_loopback_url(url: str) -> bool:
    """True for localhost endpoints, which must bypass any system proxy.

    httpx >= 0.28 honors the Windows system proxy (registry) in addition to
    env vars; a local proxy typically refuses to forward to loopback targets
    and answers 503, which silently broke local Ollama calls.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOOPBACK_HOSTS


@dataclass
class ProviderConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout: float = 180.0
    default_max_tokens: int = DEFAULT_MAX_TOKENS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        positive_int(self.default_max_tokens, name="default_max_tokens")
        positive_int(self.max_response_bytes, name="max_response_bytes")
        positive_int(self.max_output_bytes, name="max_output_bytes")


def _read_bounded_response(response: httpx.Response, max_bytes: int) -> bytes:
    """Bound accepted body bytes before JSON parsing, including error bodies.

    Request identity encoding and reject compressed responses before iteration
    so HTTPX cannot inflate an unbounded compressed chunk ahead of our check.
    This is a body-size bound, not a universal transport/process-memory limit.
    """
    positive_int(max_bytes, name="max_response_bytes")
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"", "identity"}:
        raise OutputValidationError("compressed model HTTP responses are not supported")
    declared = response.headers.get("content-length", "")
    if declared.isascii() and declared.isdecimal():
        # Avoid converting an arbitrarily long, untrusted integer header.
        normalized = declared.lstrip("0") or "0"
        if len(normalized) > len(str(max_bytes)) or int(normalized) > max_bytes:
            raise OutputValidationError("model HTTP response exceeds its byte allowance")
    content = bytearray()
    for chunk in response.iter_bytes(chunk_size=min(65536, max_bytes + 1)):
        if len(content) + len(chunk) > max_bytes:
            raise OutputValidationError("model HTTP response exceeds its byte allowance")
        content.extend(chunk)
    return bytes(content)


def _unsupported_response_format(status: int, content: bytes) -> bool:
    """Only an explicit unsupported-format error permits one downgrade."""
    if status not in {400, 422}:
        return False
    try:
        data = strict_json_object(content.decode("utf-8"), max_bytes=len(content))
    except (ValueError, UnicodeError):
        return False
    error = data.get("error")
    if not isinstance(error, dict):
        return False
    parameter = error.get("param")
    code = error.get("code")
    message = error.get("message")
    parameter_matches = isinstance(parameter, str) and (
        parameter == "response_format" or parameter.startswith("response_format.")
    )
    if parameter is not None and not parameter_matches:
        return False
    if parameter_matches and isinstance(code, str) and code in {
        "unsupported_parameter", "unsupported_value", "not_supported", "unknown_parameter"
    }:
        return True
    if not isinstance(message, str):
        return False
    # Match an unsupported statement about this exact option. Mentioning it
    # elsewhere in a model/schema/auth error does not authorize a downgrade.
    return bool(re.search(
        r"(?:\b(?:unsupported|unknown|unrecognized)\s+(?:parameter|argument|field|value)\s*[:=]?\s*[\"'`]?response_format\b"
        r"|\bresponse_format[\"'`]?\s+(?:(?:is|parameter is)\s+)?(?:not supported|unsupported)\b"
        r"|\b(?:does not support|doesn't support)\s+(?:the\s+)?[\"'`]?response_format\b)",
        message,
        re.I,
    ))



class OpenAICompatibleProvider:
    """Bounded chat adapter; missing/unknown finish_reason fails closed.

    A legacy server must supply an affirmative ``stop`` completion. Responses
    are streamed under an identity-encoded body-byte limit, then validated without
    clipping. Only explicit response_format-unsupported errors are retried.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.8,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        budget: ModelCallBudget | None = None,
    ) -> str:
        base = self.config.base_url.rstrip("/")
        if not base:
            raise ValueError("Base URL 不能为空")
        endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        payload["max_tokens"] = positive_int(
            self.config.default_max_tokens if max_tokens is None else max_tokens,
            name="max_tokens",
        )
        positive_int(self.config.max_output_bytes, name="max_output_bytes")
        positive_int(self.config.max_response_bytes, name="max_response_bytes")
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json", "Accept-Encoding": "identity"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        with httpx.Client(
            timeout=self.config.timeout,
            trust_env=not is_loopback_url(endpoint),
        ) as client:
            # Every request is individually bounded. When NovelEngine supplies
            # a stage budget, the one format-downgrade retry also reserves from
            # the same cumulative allowance. No other retry is performed.
            for attempt in range(2):
                attempt_payload = dict(payload)
                if budget is not None:
                    attempt_payload["max_tokens"] = budget.claim(messages, payload["max_tokens"])
                with client.stream("POST", endpoint, json=attempt_payload, headers=headers) as response:
                    content = _read_bounded_response(response, self.config.max_response_bytes)
                    if (attempt == 0 and response_format is not None
                            and _unsupported_response_format(response.status_code, content)):
                        payload = dict(payload)
                        payload.pop("response_format", None)
                        continue
                    if not response.is_success:
                        raise httpx.HTTPStatusError(
                            f"model endpoint returned HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    try:
                        data = strict_json_object(
                            content.decode("utf-8"), max_bytes=self.config.max_response_bytes
                        )
                    except UnicodeError:
                        raise OutputValidationError("model HTTP response is not valid UTF-8") from None
                    return completion_text(data, max_bytes=self.config.max_output_bytes,
                                           max_tokens=attempt_payload["max_tokens"])
        raise RuntimeError("model request did not produce a completion")


@dataclass(frozen=True)
class LiteLLMConfig:
    models: tuple[str, ...]
    api_key: str = ""
    api_base: str = ""
    timeout: float = 180.0
    default_max_tokens: int = DEFAULT_MAX_TOKENS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        positive_int(self.default_max_tokens, name="default_max_tokens")
        positive_int(self.max_output_bytes, name="max_output_bytes")
        if not self.models or any(not model.strip() for model in self.models):
            raise ValueError("LiteLLM 至少需要一个非空模型名")


class LiteLLMProvider:
    """Optional LiteLLM adapter using Novel's existing provider chat contract.

    The first model is primary. Legacy direct callers may still pass remaining
    models to LiteLLM as fallbacks. When NovelEngine supplies a cumulative
    budget, fallbacks are expanded into explicit sequential zero-retry calls so
    each attempt is visible to the shared allowance. The SDK still buffers
    responses; only returned content bytes are bounded here, not transport
    allocation. Missing finish_reason is rejected just as in the HTTPX adapter.
    """

    def __init__(self, config: LiteLLMConfig, *, completion_func: Any | None = None):
        self.config = config
        if completion_func is None:
            try:
                from litellm import completion as completion_func
            except ImportError as exc:
                raise RuntimeError(
                    "缺少可选依赖 litellm；安装 requirements-extras/provider.txt 后再启用"
                ) from exc
        if not callable(completion_func):
            raise TypeError("completion_func 必须可调用")
        self._completion = completion_func

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.8,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        budget: ModelCallBudget | None = None,
    ) -> str:
        requested_tokens = positive_int(
            self.config.default_max_tokens if max_tokens is None else max_tokens,
            name="max_tokens",
        )
        positive_int(self.config.max_output_bytes, name="max_output_bytes")

        def kwargs_for(model: str, attempt_tokens: int, *, include_fallbacks: bool) -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "timeout": self.config.timeout,
                "num_retries": 0,
                "max_tokens": attempt_tokens,
            }
            if include_fallbacks and len(self.config.models) > 1:
                kwargs["fallbacks"] = list(self.config.models[1:])
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base
            if response_format is not None:
                kwargs["response_format"] = response_format
            return kwargs

        if budget is None:
            kwargs = kwargs_for(self.config.models[0], requested_tokens, include_fallbacks=True)
            try:
                response = self._completion(**kwargs)
            except Exception as exc:
                # SDK exceptions can contain request bodies, credentials and raw
                # completions; retain only the exception class as a safe diagnostic.
                raise RuntimeError(f"LiteLLM completion failed ({type(exc).__name__})") from None
            return completion_text(response, max_bytes=self.config.max_output_bytes,
                                   max_tokens=kwargs["max_tokens"])

        failures: list[str] = []
        for model in self.config.models:
            attempt_tokens = budget.claim(messages, requested_tokens)
            kwargs = kwargs_for(model, attempt_tokens, include_fallbacks=False)
            try:
                response = self._completion(**kwargs)
                return completion_text(response, max_bytes=self.config.max_output_bytes,
                                       max_tokens=attempt_tokens)
            except ModelBudgetExceeded:
                raise
            except Exception as exc:
                failures.append(type(exc).__name__)
        raise RuntimeError("LiteLLM completion failed across configured models (" +
                           ", ".join(failures) + ")") from None


def sglang_provider_config(
    base_url: str,
    model: str,
    *,
    api_key: str = "",
    timeout: float = 180.0,
) -> ProviderConfig:
    """Build a ProviderConfig for an SGLang OpenAI-compatible server."""
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("SGLang base_url 不能为空")
    if not model.strip():
        raise ValueError("SGLang model 不能为空")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return ProviderConfig(
        base_url=base,
        model=model.strip(),
        api_key=api_key,
        timeout=timeout,
    )
