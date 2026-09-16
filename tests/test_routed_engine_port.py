from __future__ import annotations

import json

from novel_ai.orchestration import ProviderRouter, ProviderTarget, RouterConfig, TaskKind
from novel_ai.provider import ProviderConfig
from novel_ai.routed_engine import RoutedNovelEngine


class RecordingProvider:
    """Scripted provider that records which endpoint received each call."""

    def __init__(self, name: str, calls: list[tuple[str, str]]):
        self.name = name
        self._calls = calls

    def chat(self, messages, *, temperature=0.8, max_tokens=None, response_format=None):
        system = messages[0]["content"]
        kind = "plan" if "章节策划编辑" in system else "review" if "严苛的网络小说章节编辑" in system else "draft"
        self._calls.append((self.name, kind))
        if response_format:
            if "章节策划" in system:
                return json.dumps(
                    {
                        "chapter_title": "t",
                        "chapter_promise": "p",
                        "tension_curve": "c",
                        "scenes": [
                            {
                                "scene_no": 1,
                                "objective": "o",
                                "opposition": "op",
                                "choice": "ch",
                                "cost": "co",
                                "state_change": "st",
                            }
                        ],
                        "must_not_happen": [],
                    },
                    ensure_ascii=False,
                )
            return "{}"
        return "草稿正文"


def make_router(calls: list[tuple[str, str]]) -> ProviderRouter:
    config = RouterConfig(
        local=ProviderConfig("http://local", "local-model"),
        reviewer=ProviderConfig("http://review", "review-model"),
    )
    router = ProviderRouter(config)
    for target_name in ("local", "reviewer"):
        router._targets[target_name] = ProviderTarget(
            name=target_name, provider=RecordingProvider(target_name, calls)
        )
    return router


def test_routed_run_splits_writer_and_reviewer_and_passes_context():
    calls: list[tuple[str, str]] = []
    engine = RoutedNovelEngine(make_router(calls))
    result = engine.run(
        bible=None,
        outline="纲",
        chapter_goal="目标",
        characters=[],
        recent_summaries=[],
        review=True,
        auto_repair=False,
        extra_context="【Canon 长期记忆（硬约束，不得矛盾）】\n- 测试事实",
    )
    assert result.draft == "草稿正文"
    assert result.review is not None
    # plan+draft 走 local（writer），review 走 reviewer
    assert [(name, kind) for name, kind in calls] == [
        ("local", "plan"),
        ("local", "draft"),
        ("reviewer", "review"),
    ]


def test_router_falls_back_when_reviewer_missing():
    config = RouterConfig(local=ProviderConfig("http://local", "local-model"))
    router = ProviderRouter(config)
    # reviewer 未配置时按顺序回退到 local
    assert router.provider_for(TaskKind.REVIEW).name == "local"
