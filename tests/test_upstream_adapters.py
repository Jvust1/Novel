import json
from types import SimpleNamespace

from novel_ai.engine import apply_external_review_hooks
from novel_ai.models import ChapterPlan, ChapterReview, StoryBible
from novel_ai.recall import RecallDocument
from novel_ai.upstream_adapters import (
    CrewAIReviewHook,
    DSPyReviewHook,
    LangGraphReviewHook,
    Mem0RecallBackend,
    PydanticAIReviewHook,
)


class FakeMemory:
    def __init__(self):
        self.added = []

    def add(self, messages, **kwargs):
        self.added.append((messages, kwargs))

    def search(self, **kwargs):
        return {
            "results": [
                {
                    "id": "mem0-id",
                    "memory": "林默在值班室接到旧案电话。",
                    "score": 0.91,
                    "metadata": {
                        "_novel_schema": "novel-mem0-recall-v1",
                        "_novel_document_id": "chapter-7",
                        "layer": "active",
                    },
                }
            ]
        }


def _issue(reason="节奏重复"):
    return {
        "category": "节奏",
        "severity": "medium",
        "excerpt": "重复动作",
        "reason": reason,
        "suggestion": "压缩重复段落",
    }


def test_mem0_adapter_preserves_novel_document_identity_without_inference():
    memory = FakeMemory()
    backend = Mem0RecallBackend(memory, namespace="novel-test")
    backend.upsert([RecallDocument("chapter-7", "旧案电话", {"layer": "active"})])

    messages, kwargs = memory.added[0]
    assert messages[0]["content"] == "旧案电话"
    assert kwargs["user_id"] == "novel-test"
    assert kwargs["infer"] is False
    assert kwargs["metadata"]["_novel_document_id"] == "chapter-7"

    hits = backend.query("旧案", limit=3)
    assert hits[0].document_id == "chapter-7"
    assert hits[0].score == 0.91
    assert hits[0].metadata == {"layer": "active"}


def test_dspy_hook_normalizes_prediction_payload():
    class Program:
        def __call__(self, **kwargs):
            assert "draft" in kwargs
            return {"issues_json": json.dumps([_issue()], ensure_ascii=False)}

    payload = DSPyReviewHook(Program()).review_payload(
        draft="正文",
        plan=ChapterPlan(),
        bible=StoryBible(),
        characters=[],
    )
    assert payload["issues"][0]["reason"] == "节奏重复"


def test_crewai_hook_normalizes_crew_output():
    class Crew:
        def kickoff(self, *, inputs):
            assert inputs["draft"] == "正文"
            return SimpleNamespace(raw=json.dumps({"issues": [_issue("人物反应跳跃")]}, ensure_ascii=False))

    payload = CrewAIReviewHook(Crew()).review_payload(
        draft="正文",
        plan=ChapterPlan(),
        bible=StoryBible(),
        characters=[],
    )
    assert payload["issues"][0]["reason"] == "人物反应跳跃"


def test_external_review_hook_is_merged_into_core_review():
    class Hook:
        def review_payload(self, **kwargs):
            return {"issues": [_issue()]}

    review = apply_external_review_hooks(
        ChapterReview(verdict="pass"),
        [Hook()],
        draft="正文",
        plan=ChapterPlan(),
        bible=StoryBible(),
        characters=[],
    )
    assert review is not None
    assert review.verdict == "revise"
    assert any(issue.category == "节奏" for issue in review.issues)


def test_langgraph_hook_normalizes_graph_state():
    class Graph:
        def invoke(self, inputs, config=None):
            assert inputs["draft"] == "正文"
            return {"issues": [_issue("时间线跳跃")]}

    payload = LangGraphReviewHook(Graph()).review_payload(
        draft="正文", plan=ChapterPlan(), bible=StoryBible(), characters=[]
    )
    assert payload["issues"][0]["reason"] == "时间线跳跃"


def test_pydantic_ai_hook_normalizes_agent_output():
    class Result:
        output = {"issues": [_issue("角色目标漂移")]}

    class Agent:
        def run_sync(self, prompt):
            assert "正文" in prompt
            return Result()

    payload = PydanticAIReviewHook(Agent()).review_payload(
        draft="正文", plan=ChapterPlan(), bible=StoryBible(), characters=[]
    )
    assert payload["issues"][0]["reason"] == "角色目标漂移"
