from __future__ import annotations

from novel_ai.orchestration import ProviderRouter, RouterConfig
from novel_ai.provider import ProviderConfig
from novel_ai.routed_engine import RoutedNovelEngine


def test_routed_engine_can_be_constructed_from_role_config() -> None:
    router = ProviderRouter(
        RouterConfig(
            local=ProviderConfig("http://local", "local-model"),
            reviewer=ProviderConfig("http://review", "review-model"),
        )
    )
    engine = RoutedNovelEngine(router)
    assert engine.router.available == ("local", "reviewer")
