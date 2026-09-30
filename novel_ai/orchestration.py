from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .provider import LiteLLMConfig, LiteLLMProvider, OpenAICompatibleProvider, ProviderConfig


class TaskKind(str, Enum):
    DRAFT = "draft"
    PLAN = "plan"
    REVIEW = "review"
    MEMORY = "memory"
    BENCHMARK = "benchmark"


@dataclass(frozen=True)
class ProviderTarget:
    name: str
    provider: Any


@dataclass(frozen=True)
class RouterConfig:
    local: ProviderConfig | None = None
    colab: ProviderConfig | None = None
    v4: ProviderConfig | None = None
    reviewer: ProviderConfig | None = None
    litellm: LiteLLMConfig | None = None

    @classmethod
    def from_env(cls) -> "RouterConfig":
        def read(prefix: str) -> ProviderConfig | None:
            base_url = os.getenv(f"{prefix}_BASE_URL", "").strip()
            model = os.getenv(f"{prefix}_MODEL", "").strip()
            if not base_url or not model:
                return None
            return ProviderConfig(
                base_url=base_url,
                model=model,
                api_key=os.getenv(f"{prefix}_API_KEY", ""),
                timeout=float(os.getenv("NOVEL_PROVIDER_TIMEOUT", "180")),
            )

        raw_models = os.getenv("NOVEL_LITELLM_MODELS", "").strip()
        litellm = None
        if raw_models:
            models = tuple(item.strip() for item in raw_models.split(",") if item.strip())
            if models:
                litellm = LiteLLMConfig(
                    models=models,
                    api_key=os.getenv("NOVEL_LITELLM_API_KEY", ""),
                    api_base=os.getenv("NOVEL_LITELLM_API_BASE", ""),
                    timeout=float(os.getenv("NOVEL_PROVIDER_TIMEOUT", "180")),
                )

        return cls(
            local=read("NOVEL_LOCAL"),
            colab=read("NOVEL_COLAB"),
            v4=read("NOVEL_V4"),
            reviewer=read("NOVEL_REVIEW"),
            litellm=litellm,
        )


class ProviderRouter:
    """Route work by role while keeping every endpoint OpenAI-compatible.

    The router never stores credentials. Config is read from runtime environment
    variables or passed explicitly by the server.
    """

    _ORDER: dict[TaskKind, tuple[str, ...]] = {
        TaskKind.DRAFT: ("local", "litellm", "v4", "colab"),
        TaskKind.PLAN: ("local", "litellm", "v4", "colab"),
        TaskKind.REVIEW: ("reviewer", "litellm", "local", "v4"),
        TaskKind.MEMORY: ("local", "litellm", "colab", "v4"),
        TaskKind.BENCHMARK: ("colab", "litellm", "local", "v4"),
    }

    def __init__(self, config: RouterConfig | None = None):
        config = config or RouterConfig.from_env()
        self._targets: dict[str, ProviderTarget] = {}
        for name, provider_config in (
            ("local", config.local),
            ("colab", config.colab),
            ("v4", config.v4),
            ("reviewer", config.reviewer),
        ):
            if provider_config is not None:
                self._targets[name] = ProviderTarget(
                    name=name,
                    provider=OpenAICompatibleProvider(provider_config),
                )
        if config.litellm is not None:
            self._targets["litellm"] = ProviderTarget(
                name="litellm",
                provider=LiteLLMProvider(config.litellm),
            )

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(self._targets)

    def provider_for(self, task: TaskKind) -> ProviderTarget:
        for name in self._ORDER[task]:
            target = self._targets.get(name)
            if target is not None:
                return target
        expected = ", ".join(self._ORDER[task])
        raise RuntimeError(
            f"没有可用的 {task.value} provider。请配置以下任一运行时变量组：{expected}"
        )

    def chat(
        self,
        task: TaskKind,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.8,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        target = self.provider_for(task)
        return target.provider.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
