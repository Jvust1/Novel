"""Configured review failures cannot normalize into zero findings."""
from types import SimpleNamespace
import pytest
from novel_ai.models import ChapterPlan, StoryBible
from novel_ai.upstream_adapters import DSPyReviewHook, CrewAIReviewHook, LangGraphReviewHook, PydanticAIReviewHook, GuardrailsReviewHook

ARGS=dict(draft='原创合成正文。',plan=ChapterPlan(),bible=StoryBible(),characters=[])


def hook(kind,payload):
    if kind=='dspy':return DSPyReviewHook(lambda **kw:payload)
    if kind=='crewai':return CrewAIReviewHook(SimpleNamespace(kickoff=lambda **kw:payload))
    if kind=='langgraph':return LangGraphReviewHook(SimpleNamespace(invoke=lambda *a:payload))
    return PydanticAIReviewHook(SimpleNamespace(run_sync=lambda prompt:SimpleNamespace(output=payload)))


@pytest.mark.parametrize('kind',['dspy','crewai','langgraph','pydantic'])
@pytest.mark.parametrize('payload',[{}, {'issues':None}, {'issues':'not JSON'}, {'issues':[None]}, {'issues':[{'reason':'','severity':'high'}]}, {'issues':[{'reason':'问题','severity':'critical'}]}, {'issues_json':'{"issues":[],"issues":null}'}])
def test_malformed_configured_check_fails(kind,payload):
    with pytest.raises((ValueError,TypeError)):hook(kind,payload).review_payload(**ARGS)


@pytest.mark.parametrize('kind',['dspy','crewai','langgraph','pydantic'])
def test_explicit_empty_findings_are_valid(kind):
    assert hook(kind,{'issues':[]}).review_payload(**ARGS)=={'issues':[]}


@pytest.mark.parametrize('passed',[None,'true',1])
def test_guardrails_requires_explicit_boolean_outcome(passed):
    guard=SimpleNamespace(validate=lambda draft:SimpleNamespace(validation_passed=passed,validated_output='looks okay'))
    with pytest.raises(ValueError):GuardrailsReviewHook(guard).review_payload(**ARGS)
