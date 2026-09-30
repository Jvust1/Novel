from __future__ import annotations

from dataclasses import dataclass

import pytest

from novel_ai.orchestration import ProviderRouter, RouterConfig, TaskKind
from novel_ai.provider import LiteLLMConfig, ProviderConfig


@dataclass
class FakeProvider:
    name: str

    def chat(self, *_args, **_kwargs) -> str:
        return self.name


def test_task_routes_prefer_the_expected_provider() -> None:
    config = RouterConfig(
        local=ProviderConfig("http://local", "local-model"),
        colab=ProviderConfig("http://colab", "colab-model"),
        v4=ProviderConfig("http://v4", "v4-model"),
        reviewer=ProviderConfig("http://review", "review-model"),
    )
    router = ProviderRouter(config)
    assert router.available == ("local", "colab", "v4", "reviewer")
    assert router.provider_for(TaskKind.DRAFT).name == "local"
    assert router.provider_for(TaskKind.REVIEW).name == "reviewer"
    assert router.provider_for(TaskKind.BENCHMARK).name == "colab"


def test_missing_provider_reports_runtime_configuration() -> None:
    router = ProviderRouter(RouterConfig())
    with pytest.raises(RuntimeError, match="没有可用的 review provider"):
        router.provider_for(TaskKind.REVIEW)



def test_litellm_target_is_available_as_router_fallback(monkeypatch) -> None:
    class FakeLiteLLMProvider:
        def __init__(self, config):
            self.config = config

        def chat(self, *_args, **_kwargs):
            return "gateway"

    monkeypatch.setattr("novel_ai.orchestration.LiteLLMProvider", FakeLiteLLMProvider)
    router = ProviderRouter(
        RouterConfig(litellm=LiteLLMConfig(models=("openai/a", "anthropic/b")))
    )
    assert router.available == ("litellm",)
    assert router.provider_for(TaskKind.DRAFT).name == "litellm"
    assert router.provider_for(TaskKind.REVIEW).name == "litellm"


def test_router_config_reads_litellm_models_from_env(monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_LITELLM_MODELS", "openai/a, anthropic/b")
    monkeypatch.setenv("NOVEL_LITELLM_API_BASE", "https://gateway.example/v1")
    config = RouterConfig.from_env()
    assert config.litellm is not None
    assert config.litellm.models == ("openai/a", "anthropic/b")
    assert config.litellm.api_base == "https://gateway.example/v1"
