"""Original synthetic archives through the actual bounded HTTP writing entry."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import itertools
import json

import httpx
import pytest

from novel_ai import accepted_writing as writing
from novel_ai import gpt_story_state as state
from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.orchestration import RouterConfig
from novel_ai.provider import ProviderConfig
from novel_ai.request_budget import RequestBudgetExceeded, RequestBudgetLimits
from test_request_budget import envelope, transport

COUNT = itertools.count()
PLAN = {
    "chapter_title": "An original lamp", "chapter_promise": "Choose a route", "tension_curve": "rising",
    "scenes": [{"scene_no": 1, "pov": "林青", "objective": "Find the lamp", "opposition": "The hall is closed",
                "choice": "Ask the keeper", "cost": "Leave a token", "state_change": "The door opens",
                "end_hook": "A bell rings"}],
}
DRAFT = '林青说：“先等一下吧。”\n林青问：“你带灯了吗？”\n木禾说：“灯在门边。”'
CURRENT_DRAFT = '林青喊：“这句未接受草稿绝不进入历史！”'



def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def art(text, name):
    return state.artifact(text, source_id=name, location="https://unread.invalid/" + name, revision=1)

def confirm(value, scope):
    p = value.progress
    result = {"confirmed_by": "author", "confirmation_source": "synthetic-test://simulated-author-message",
              "story_id": value.story_id, "story_revision": p.base_story_revision,
              "chapter_id": p.chapter_id, "plan_revision": p.plan_revision,
              "plan_source_fingerprint": state.source_fingerprint(p.plan)}
    if scope in {"chapter", "memory"}:
        result.update(draft_revision=p.draft_revision, draft_source_fingerprint=state.source_fingerprint(p.draft))
    if scope == "memory":
        result["memory_update_id"] = p.memory_update_id
    return result

def step(value, action, payload):
    return state.transition(value, {"action": action, "story_id": value.story_id,
        "base_story_revision": value.revision, "operation_id": f"synthetic-{next(COUNT)}",
        "expected_state_sha256": state.state_fingerprint(value), "payload": payload})

def archive(tmp_path, plan=None, *, characters=None, draft=DRAFT, current_draft=True):
    value = state.create_state("synthetic-story", template={
        "canon": {"characters": characters if characters is not None else [
            {"id": "lin", "name": "林青", "aliases": ["小青"], "knows": [], "voice": "short"},
            {"id": "mu", "name": "木禾", "knows": []}]},
        "style_profile": {"distance": "close", "optional": {"rhythm": "varied"}}})
    value = step(value, "start_chapter", {"chapter_id": "ch-1"})
    value = step(value, "set_plan", {"artifact": art(json.dumps(PLAN, ensure_ascii=False) if plan is None else plan, "plan-1").model_dump(mode="json")})
    value = step(value, "accept_plan", {"confirmation": confirm(value, "plan")})
    value = step(value, "set_draft", {"artifact": art(draft, "draft-1").model_dump(mode="json")})
    value = step(value, "review", {"draft_revision": 1, "issues": [], "source": art("Synthetic review", "review-1").source.model_dump(mode="json")})
    value = step(value, "accept_chapter", {"confirmation": confirm(value, "chapter")})
    value = step(value, "propose_memory", {"changes": []})
    value = step(value, "accept_memory", {"confirmation": confirm(value, "memory")})
    value = step(value, "apply_memory", {"memory_update_id": value.progress.memory_update_id})
    path = tmp_path / "private-story.json"
    saved = state.save_state(path, value)
    value = state.load_state(path, expected_story_id=value.story_id, expected_sha256=saved.sha256)
    value = step(value, "start_chapter", {"chapter_id": "ch-2"})
    value = step(value, "set_plan", {"artifact": art("Current plan is arbitrary accepted text", "plan-2").model_dump(mode="json")})
    value = step(value, "accept_plan", {"confirmation": confirm(value, "plan")})
    if current_draft:
        value = step(value, "set_draft", {"artifact": art(CURRENT_DRAFT, "draft-2").model_dump(mode="json")})
        # The existing protocol deliberately retains this unaccepted draft here.
        value = step(value, "set_plan", {"artifact": art("Current replacement plan", "plan-2b").model_dump(mode="json")})
        value = step(value, "accept_plan", {"confirmation": confirm(value, "plan")})
    state.save_state(path, value, expected_disk_revision=1, expected_disk_sha256=saved.sha256)
    return path

def ready_archive(tmp_path, *, bad_plan=None):
    path=archive(tmp_path,current_draft=True)
    value=state.load_state(path,expected_story_id='synthetic-story')
    plan=deepcopy(PLAN)
    plan['chapter_title']='Next original scene'
    plan['must_not_happen']=['不可让林青凭空知道门后人的姓名']
    # Full custom data lives in the real source context and must not vanish.
    raw=json.dumps(plan,ensure_ascii=False) if bad_plan is None else bad_plan
    value=step(value,'set_plan',{'artifact':art(raw,'current-confirmed-plan').model_dump(mode='json')})
    value=step(value,'accept_plan',{'confirmation':confirm(value,'plan')})
    state.save_state(path,value,expected_disk_revision=1,expected_disk_sha256=digest(path))
    return path

def restore(path):
    return writing.restore_source(path, expected_story_id='synthetic-story', expected_revision=1,
                                  expected_sha256=digest(path))


def session(monkeypatch, callback=None, *, limits=None):
    calls = []
    reviews = 0
    def handler(req):
        nonlocal reviews
        calls.append(req)
        if callback:
            response = callback(req, len(calls))
            if response is not None:
                return response
        payload = json.loads(req.content)
        system = payload['messages'][0]['content']
        if '严苛的网络小说章节编辑' in system:
            reviews += 1
            text = json.dumps({'verdict': 'revise' if reviews == 1 else 'pass', 'issues': []})
        elif '局部修订编辑' in system:
            text = '林青把灯交给木禾，沿着空墙摸索出口。'
        else:
            text = '林青举起灯，木禾把门推开了一条缝。'
        return httpx.Response(200, json=envelope(text))
    transport(monkeypatch, handler)
    value = BudgetedWritingSession(RouterConfig(
        local=ProviderConfig('https://synthetic-writer.invalid/v1', 'writer'),
        reviewer=ProviderConfig('https://synthetic-reviewer.invalid/v1', 'reviewer')), limits=limits)
    return value, calls


def run(value, source, **options):
    return value.run_from_accepted_archive(source, current_chapter_id='ch-2', **options)


def test_four_actual_stages_use_accepted_history_same_budget_and_leave_archive_unchanged(tmp_path, monkeypatch):
    path = ready_archive(tmp_path); before = path.read_bytes(); source = restore(path)
    expected = state.rebuild_accepted_history(source.state)['accepted_history_sha256']
    value, calls = session(monkeypatch)
    result = run(value, source, auto_repair=True, recall_chapter_ids=['ch-1'], required_chapter_ids=['ch-1'])
    assert len(calls) == 4
    assert [r.url.host for r in calls] == ['synthetic-writer.invalid','synthetic-reviewer.invalid','synthetic-writer.invalid','synthetic-reviewer.invalid']
    for req in calls:
        text = req.content.decode()
        assert '灯在门边' in text and '这句未接受草稿绝不进入历史' not in text
        assert 'rhythm' in text and 'varied' in text and '不可让林青凭空知道' in text
        assert expected in text
    report = result.report()
    assert report['authority']['accepted_history_sha256'] == expected
    assert report['history_chapter_ids'] == ['ch-1']
    assert result.final_text == '林青把灯交给木禾，沿着空墙摸索出口。'
    assert result.result.final_report['voice']['baseline']['林青']['line_count'] == 2
    assert value.budget_snapshot()['requests_reserved'] == 4
    assert value.budget_snapshot()['request_bytes_reserved'] == sum(len(r.content) for r in calls)
    assert path.read_bytes() == before and source.state.progress.chapter_acceptance is None
    assert source.state.progress.memory_acceptance is None


@pytest.mark.parametrize('stage', [1, 2, 3, 4])
def test_source_change_in_each_actual_stage_blocks_next_send_or_result(tmp_path, monkeypatch, stage):
    path = ready_archive(tmp_path)
    def change(req, count):
        if count == stage:
            path.write_bytes(path.read_bytes() + b' ')
    value, calls = session(monkeypatch, change)
    with pytest.raises(ValueError, match='archive'):
        run(value, restore(path), auto_repair=True)
    assert len(calls) == stage
    assert value.budget_snapshot()['requests_reserved'] == stage
    assert value.budget_snapshot()['attempts'][-1]['status'] == 'failed'


def test_changed_source_on_unsupported_format_response_blocks_fallback(tmp_path, monkeypatch):
    path = ready_archive(tmp_path)
    def fallback(req, count):
        if count == 2:
            assert 'response_format' in json.loads(req.content)
            path.write_bytes(path.read_bytes() + b' ')
            return httpx.Response(400, json={'error': {'param': 'response_format', 'code': 'unsupported_parameter'}})
    value, calls = session(monkeypatch, fallback)
    with pytest.raises(ValueError, match='archive'):
        run(value, restore(path), auto_repair=True)
    assert len(calls) == 2 and value.budget_snapshot()['requests_reserved'] == 2


def test_allowed_format_fallback_shares_budget_and_source_guard(tmp_path, monkeypatch):
    path = ready_archive(tmp_path)
    def fallback(req, count):
        if count == 2:
            return httpx.Response(400, json={'error': {'param': 'response_format', 'code': 'unsupported_parameter'}})
    value, calls = session(monkeypatch, fallback)
    result = run(value, restore(path), auto_repair=True)
    assert len(calls) == 5 and value.budget_snapshot()['requests_reserved'] == 5
    assert 'response_format' not in json.loads(calls[2].content)
    assert result.report()['budget_after'] == value.budget_snapshot()


@pytest.mark.parametrize('stage', [1, 2, 3, 4])
def test_http_failure_at_each_stage_stays_charged_and_leaves_author_state(tmp_path, monkeypatch, stage):
    path = ready_archive(tmp_path); before = path.read_bytes()
    def fail(req, count):
        return httpx.Response(503, json={'error': 'synthetic unavailable'}) if count == stage else None
    value, calls = session(monkeypatch, fail)
    with pytest.raises(httpx.HTTPStatusError):
        run(value, restore(path), auto_repair=True)
    assert len(calls) == stage and value.budget_snapshot()['requests_reserved'] == stage
    assert path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('target_chars',False),('review','true'),('auto_repair',1),
    ('budget_bytes',0),('reserve_bytes',-1),('history_source_limit',True),
    ('recall_chapter_ids',['ch-2']),('required_chapter_ids',['future']),('recall_chapter_ids',['ch-1','ch-1'])])
def test_bad_options_cannot_dispatch(tmp_path,monkeypatch,field,value):
    path=ready_archive(tmp_path); flow,calls=session(monkeypatch)
    with pytest.raises((ValueError,TypeError)):
        run(flow,restore(path),**{field:value})
    assert calls==[] and flow.budget_snapshot()['requests_reserved']==0


@pytest.mark.parametrize('bad', ['{}','{"scenes":[]}','{"scenes":[{"scene_no":1}]}','not JSON',
    '{"scenes":[],"scenes":[]}', '{"chapter_plan":{},"extra":"must not disappear"}'])
def test_incomplete_or_ambiguous_plan_refuses_before_dispatch(tmp_path,monkeypatch,bad):
    path=ready_archive(tmp_path,bad_plan=bad);flow,calls=session(monkeypatch)
    with pytest.raises(ValueError):run(flow,restore(path))
    assert calls==[]


@pytest.mark.parametrize('change', ['unknown','nested_unknown','blank','bool_number','str_number','zero_number','duplicate'])
def test_plan_adaptation_does_not_silently_coerce_or_drop_fields(tmp_path,monkeypatch,change):
    plan=deepcopy(PLAN)
    if change=='unknown':plan['custom']='keep me'
    elif change=='nested_unknown':plan['scenes'][0]['custom']='keep me'
    elif change=='blank':plan['scenes'][0]['cost']=' '
    elif change=='duplicate':plan['scenes'].append(deepcopy(plan['scenes'][0]))
    else:plan['scenes'][0]['scene_no']={'bool_number':True,'str_number':'1','zero_number':0}[change]
    path=ready_archive(tmp_path,bad_plan=json.dumps(plan));flow,calls=session(monkeypatch)
    with pytest.raises(ValueError):run(flow,restore(path))
    assert calls==[]


def test_exact_native_plan_wrapper_is_supported(tmp_path,monkeypatch):
    path=ready_archive(tmp_path,bad_plan=json.dumps({'chapter_plan':PLAN}));flow,calls=session(monkeypatch)
    result=run(flow,restore(path),review=False)
    assert result.final_text and len(calls)==1


def test_restore_expectations_and_source_mutation_are_not_cached(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);source=restore(path);flow,calls=session(monkeypatch)
    for bad in (replace(source,story_id='other'),replace(source,revision=0),replace(source,state_sha256='0'*64),replace(source,file_sha256='0'*64)):
        with pytest.raises(ValueError):run(flow,bad,review=False)
    source.state.style_profile['forged']='does not mutate source'
    assert 'forged' not in source.state.style_profile
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):run(flow,source,review=False)
    assert calls==[]


def test_candidate_only_saved_change_keeps_native_history_but_invalidates_execution_handle(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);source=restore(path);flow,calls=session(monkeypatch)
    result=run(flow,source,review=False)
    old=state.rebuild_accepted_history(source.state)['accepted_history_sha256']
    value=step(source.state,'set_draft',{'artifact':art('另一份未接受的原创新稿','new-candidate').model_dump(mode='json')})
    state.save_state(path,value,expected_disk_revision=1,expected_disk_sha256=digest(path))
    current=state.load_state(path,expected_story_id='synthetic-story')
    assert state.rebuild_accepted_history(current)['accepted_history_sha256']==old
    with pytest.raises(ValueError):result.report()
    with pytest.raises(ValueError):result.final_text


def test_authority_footer_reserved_before_optional_history(tmp_path):
    source=restore(ready_archive(tmp_path))
    options=dict(current_chapter_id='ch-2',history_source_limit=0)
    essential=writing.prepare_accepted_context(source,**options)
    size=essential['preflight']['used_bytes']
    preview=writing.prepare_accepted_context(source,**options,recall_chapter_ids=['ch-1'],budget_bytes=size)
    assert preview['preflight']['used_bytes']==size
    assert preview['preflight']['dropped_sources'] and not preview['preflight']['selected_sources']
    assert '不可让林青凭空知道' in preview['preflight']['context_text']
    with pytest.raises(ValueError):writing.prepare_accepted_context(source,**options,budget_bytes=size-1)


def test_whole_wire_budget_blocks_before_dispatch_without_truncating_archive(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);before=path.read_bytes()
    flow,calls=session(monkeypatch,limits=RequestBudgetLimits(max_request_bytes=10))
    with pytest.raises(RequestBudgetExceeded):run(flow,restore(path))
    assert calls==[] and path.read_bytes()==before


def test_repeated_calls_and_repair_share_session_limit_without_reset(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);flow,calls=session(monkeypatch,limits=RequestBudgetLimits(max_requests=2))
    run(flow,restore(path),review=False)
    run(flow,restore(path),review=False)
    with pytest.raises(RequestBudgetExceeded):run(flow,restore(path),review=False)
    assert len(calls)==2 and flow.budget_snapshot()['requests_reserved']==2


def test_result_report_cannot_be_rebound_or_recreated_as_observed_execution(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);flow,calls=session(monkeypatch)
    result=run(flow,restore(path),review=False)
    with pytest.raises(ValueError):replace(result).report()
    report=result.report();report['authority']['accepted_history_sha256']='0'*64
    assert result.report()['authority']!=report['authority']
    object.__setattr__(result,'_evidence_json',json.dumps(report).encode())
    with pytest.raises(ValueError):result.final_text


def test_nested_final_report_mutation_invalidates_source_bound_result(tmp_path,monkeypatch):
    path=ready_archive(tmp_path);flow,calls=session(monkeypatch)
    result=run(flow,restore(path),review=False)
    result.result.final_report['input_fingerprints']['extra_context']='forged'
    with pytest.raises(ValueError):result.report()


def test_explicit_author_accept_then_restart_continues_next_chapter_only_from_new_history(tmp_path, monkeypatch):
    path = ready_archive(tmp_path); source = restore(path); flow, calls = session(monkeypatch)
    first = run(flow, source, review=False)
    candidate = first.final_text
    assert source.state.progress.chapter_acceptance is None
    value = step(source.state, 'set_draft', {'artifact': art(candidate, 'accepted-second-draft').model_dump(mode='json')})
    value = step(value, 'review', {'draft_revision': value.progress.draft_revision, 'issues': [],
        'source': art('Explicit synthetic review of this exact candidate', 'second-review').source.model_dump(mode='json')})
    value = step(value, 'accept_chapter', {'confirmation': confirm(value, 'chapter')})
    value = step(value, 'propose_memory', {'changes': []})
    value = step(value, 'accept_memory', {'confirmation': confirm(value, 'memory')})
    value = step(value, 'apply_memory', {'memory_update_id': value.progress.memory_update_id})
    saved = state.save_state(path, value, expected_disk_revision=1, expected_disk_sha256=digest(path))
    with pytest.raises(ValueError): first.report()
    value = state.load_state(path, expected_story_id='synthetic-story', expected_revision=2, expected_sha256=saved.sha256)
    value = step(value, 'start_chapter', {'chapter_id': 'ch-3'})
    plan = deepcopy(PLAN); plan['chapter_title'] = 'The next original doorway'
    value = step(value, 'set_plan', {'artifact': art(json.dumps(plan, ensure_ascii=False), 'third-plan').model_dump(mode='json')})
    value = step(value, 'accept_plan', {'confirmation': confirm(value, 'plan')})
    state.save_state(path, value, expected_disk_revision=2, expected_disk_sha256=digest(path))
    fresh = writing.restore_source(path, expected_story_id='synthetic-story', expected_revision=2, expected_sha256=digest(path))
    before = path.read_bytes()
    second = flow.run_from_accepted_archive(fresh, current_chapter_id='ch-3', required_chapter_ids=['ch-2'], review=False)
    assert second.report()['history_chapter_ids'] == ['ch-1', 'ch-2']
    assert candidate in calls[-1].content.decode()
    assert '这句未接受草稿绝不进入历史' not in calls[-1].content.decode()
    assert path.read_bytes() == before
    assert len(calls) == flow.budget_snapshot()['requests_reserved'] == 2
    assert fresh.state.progress.chapter_acceptance is None
