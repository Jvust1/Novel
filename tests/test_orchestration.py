from __future__ import annotations

from dataclasses import dataclass

import pytest

from novel_ai.orchestration import ProviderRouter, RouterConfig, TaskKind
from novel_ai.provider import ProviderConfig


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
