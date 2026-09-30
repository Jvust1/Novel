from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

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


class OpenAICompatibleProvider:
    """Small provider adapter for OpenAI-compatible chat completion APIs."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.8,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
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
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        with httpx.Client(
            timeout=self.config.timeout,
            trust_env=not is_loopback_url(endpoint),
        ) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            if response.status_code >= 400 and response_format:
                fallback = dict(payload)
                fallback.pop("response_format", None)
                response = client.post(endpoint, json=fallback, headers=headers)
            response.raise_for_status()
            data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型返回格式无法识别: {data}") from exc



@dataclass(frozen=True)
class LiteLLMConfig:
    models: tuple[str, ...]
    api_key: str = ""
    api_base: str = ""
    timeout: float = 180.0

    def __post_init__(self) -> None:
        if not self.models or any(not model.strip() for model in self.models):
            raise ValueError("LiteLLM 至少需要一个非空模型名")


class LiteLLMProvider:
    """Optional LiteLLM adapter using Novel's existing provider chat contract.

    The first model is primary; remaining models are passed as LiteLLM fallbacks.
    LiteLLM stays optional and is imported lazily.
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
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.config.models[0],
            "messages": messages,
            "temperature": temperature,
            "timeout": self.config.timeout,
        }
        if len(self.config.models) > 1:
            kwargs["fallbacks"] = list(self.config.models[1:])
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            kwargs["api_base"] = self.config.api_base
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = self._completion(**kwargs)
        try:
            if isinstance(response, dict):
                content = response["choices"][0]["message"]["content"]
            else:
                choices = getattr(response, "choices")
                message = choices[0].message
                content = message["content"] if isinstance(message, dict) else message.content
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"LiteLLM 返回格式无法识别: {response!r}") from exc
        if not isinstance(content, str):
            raise RuntimeError("LiteLLM 返回 content 不是字符串")
        return content


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
