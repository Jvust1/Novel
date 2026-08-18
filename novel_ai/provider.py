from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


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

        with httpx.Client(timeout=self.config.timeout) as client:
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
