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


def test_repair_is_reviewed_again(monkeypatch):
    from novel_ai.models import ChapterPlan, ChapterReview
    calls=[]
    class FakeEngine:
        def __init__(self,provider):pass
        def plan(self,*args):return ChapterPlan()
        def draft(self,*args):return "draft"
        def review(self,*args):
            calls.append(args[-1]);return ChapterReview(verdict="revise" if args[-1]=="draft" else "pass")
        def repair(self,*args):return "repaired"
    monkeypatch.setattr("novel_ai.routed_engine.NovelEngine",FakeEngine)
    router=ProviderRouter(RouterConfig(local=ProviderConfig("http://127.0.0.1:11434/v1","test")))
    result=RoutedNovelEngine(router).run(bible=None,outline="",chapter_goal="",characters=[],auto_repair=True)
    assert calls==["draft","repaired"]
    assert result.review_after_repair.verdict=="pass"
