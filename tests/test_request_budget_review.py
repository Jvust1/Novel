"""Independent budget review: all wire calls use synthetic HTTPX MockTransport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import threading

import httpx
import pytest

from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.models import ChapterPlan, StoryBible, StyleFingerprint
from novel_ai.orchestration import RouterConfig
from novel_ai.output_policy import OutputPolicy, OutputValidationError
from novel_ai.provider import OpenAICompatibleProvider, ProviderConfig
from novel_ai.request_budget import RequestBudget, RequestBudgetExceeded, RequestBudgetLimits
from test_request_budget import PLAN, PROSE, MESSAGES, envelope, options, session_transport, transport


def _plan_options():
    args = options()
    args.pop('outline')
    args.pop('chapter_goal')
    args['plan'] = ChapterPlan.model_validate(PLAN)
    return args


@pytest.mark.parametrize('method', ['run', 'run_from_plan'])
@pytest.mark.parametrize('field,value', [('target_chars', False), ('target_chars', 0),
    ('target_chars', '200'), ('review', 'false'), ('review', 0), ('review', None),
    ('auto_repair', 'false'), ('auto_repair', 1), ('auto_repair', [])])
def test_malformed_flow_options_cannot_send_even_the_first_request(monkeypatch, method, field, value):
    session, calls = session_transport(monkeypatch)
    args = options() if method == 'run' else _plan_options()
    args[field] = value
    with pytest.raises((TypeError, ValueError)):
        getattr(session, method)(**args)
    assert calls == []
    assert session.budget_snapshot()['requests_reserved'] == 0


def test_bounded_session_snapshots_caller_owned_provider_configuration(monkeypatch):
    calls = []
    transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(200, json=envelope()))
    config = ProviderConfig('https://original-writer.invalid/v1', 'original-model', api_key='synthetic-original-key')
    session = BudgetedWritingSession(RouterConfig(local=config))
    config.base_url = 'https://changed-after-configuration.invalid/v1'
    config.model = 'changed-model'
    config.api_key = 'synthetic-changed-key'
    config.max_response_bytes = 1
    result = session.run_from_plan(bible=StoryBible(), plan=ChapterPlan.model_validate(PLAN),
                                   characters=[], review=False)
    assert result.final_text == PROSE
    assert len(calls) == 1
    assert calls[0].url.host == 'original-writer.invalid'
    assert json.loads(calls[0].content)['model'] == 'original-model'
    assert calls[0].headers['authorization'] == 'Bearer synthetic-original-key'


@pytest.mark.parametrize('limit_kind', ['requests', 'total_bytes', 'reserved_tokens'])
def test_parallel_real_transports_share_one_atomic_allowance(monkeypatch, limit_kind):
    calls = []
    lock = threading.Lock()
    def handler(req):
        with lock:
            calls.append(req)
        data = envelope('短')
        data['usage'] = {'completion_tokens': 0}
        return httpx.Response(200, json=data)
    transport(monkeypatch, handler)
    payload = {'model': 'same-model', 'messages': MESSAGES, 'temperature': .8, 'max_tokens': 7}
    size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode())
    limit = {'max_requests': 5} if limit_kind == 'requests' else (
        {'max_total_request_bytes': size * 5} if limit_kind == 'total_bytes' else {'max_reserved_output_tokens': 35})
    budget = RequestBudget(RequestBudgetLimits(max_requests=25, **limit) if limit_kind != 'requests' else RequestBudgetLimits(**limit))
    providers = [OpenAICompatibleProvider(ProviderConfig('https://' + role + '.invalid/v1', 'same-model'),
                                         request_budget=budget) for role in ['writer', 'reviewer']]
    start = threading.Barrier(20)
    def run(index):
        start.wait(timeout=10)
        try:
            providers[index % 2].chat(deepcopy(MESSAGES), max_tokens=7)
            return True
        except RequestBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=20) as pool:
        assert sum(pool.map(run, range(20))) == 5
    snap = budget.snapshot()
    assert len(calls) == snap['requests_reserved'] == 5
    assert snap['request_bytes_reserved'] == sum(len(req.content) for req in calls) == size * 5
    assert snap['output_tokens_reserved'] == 35
    assert all(row['status'] == 'succeeded' for row in snap['attempts'])
    assert sorted(row['request_sha256'] for row in snap['attempts']) == sorted(hashlib.sha256(req.content).hexdigest() for req in calls)
    assert snap['actual_tokens'] is None


def test_close_blocks_new_admission_without_refunding_inflight_request(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def handler(req):
        calls.append(req)
        entered.set()
        assert release.wait(timeout=10)
        return httpx.Response(200, json=envelope())
    transport(monkeypatch, handler)
    budget = RequestBudget()
    provider = OpenAICompatibleProvider(ProviderConfig('https://example.invalid/v1', 'model'), request_budget=budget)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(provider.chat, MESSAGES, max_tokens=10)
        assert entered.wait(timeout=10)
        budget.close()
        try:
            with pytest.raises(RequestBudgetExceeded, match='closed'):
                provider.chat(MESSAGES, max_tokens=10)
            assert budget.snapshot()['attempts'][0]['status'] == 'admitted'
        finally:
            release.set()
        assert pending.result(timeout=10) == PROSE
    snapshot = budget.snapshot()
    assert len(calls) == snapshot['requests_reserved'] == 1
    assert snapshot['output_tokens_reserved'] == 10
    assert snapshot['closed'] and snapshot['attempts'][0]['status'] == 'succeeded'


@pytest.mark.parametrize('boundary', ['bytes_exact', 'bytes_short', 'tokens_exact', 'tokens_short'])
def test_format_downgrade_reserves_full_body_and_cap_under_aggregate_limits(monkeypatch, boundary):
    calls = []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(422, json={'error': {'param': 'response_format', 'code': 'unsupported_parameter'}})
        return httpx.Response(200, json=envelope())
    transport(monkeypatch, handler)
    plain = {'model': 'model', 'messages': MESSAGES, 'temperature': .8, 'max_tokens': 7}
    first = {**plain, 'response_format': {'type': 'json_object'}}
    total = sum(len(json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()) for item in [plain, first])
    limits = (RequestBudgetLimits(max_total_request_bytes=total - int(boundary.endswith('short')))
              if boundary.startswith('bytes') else RequestBudgetLimits(max_reserved_output_tokens=14 - int(boundary.endswith('short'))))
    budget = RequestBudget(limits)
    provider = OpenAICompatibleProvider(ProviderConfig('https://example.invalid/v1', 'model'), request_budget=budget)
    if boundary.endswith('short'):
        with pytest.raises(RequestBudgetExceeded):
            provider.chat(MESSAGES, max_tokens=7, response_format={'type': 'json_object'})
    else:
        assert provider.chat(MESSAGES, max_tokens=7, response_format={'type': 'json_object'}) == PROSE
    expected = 1 if boundary.endswith('short') else 2
    snapshot = budget.snapshot()
    assert len(calls) == snapshot['requests_reserved'] == expected
    assert snapshot['output_tokens_reserved'] == expected * 7
    assert snapshot['request_bytes_reserved'] == sum(len(req.content) for req in calls)
    assert snapshot['attempts'][0]['status'] == 'failed'


@pytest.mark.parametrize('failed_call', [1, 2, 3, 4, 5])
def test_every_stage_failure_remains_spent_on_repeated_session(monkeypatch, failed_call):
    def override(stage, count):
        if count != failed_call:
            return None
        if stage in {'plan', 'review'}:
            return httpx.Response(200, json=envelope('not valid structured JSON'))
        return httpx.Response(503, content=b'synthetic unavailable')
    session, calls = session_transport(monkeypatch, RequestBudgetLimits(max_requests=failed_call), override=override)
    with pytest.raises((ValueError, httpx.HTTPError)):
        session.run(**options())
    after_failure = session.budget_snapshot()
    assert after_failure['requests_reserved'] == len(calls) == failed_call
    assert after_failure['output_tokens_reserved'] == sum(row['payload']['max_tokens'] for row in calls)
    with pytest.raises(RequestBudgetExceeded):
        session.run(**options())
    assert session.budget_snapshot() == after_failure
    assert len(calls) == failed_call


def test_style_memory_and_repeated_plan_runs_share_allowance_without_acceptance(monkeypatch):
    session, calls = session_transport(monkeypatch, RequestBudgetLimits(max_requests=8))
    result = session.run(**options())
    bible, surface = StoryBible(title='Synthetic immutable title'), StyleFingerprint(name='synthetic style')
    original = (bible.model_dump(), surface.model_dump())
    memory = session.extract_memory(bible, [], 'c', PROSE)
    style = session.enrich_style(PROSE, surface)
    args = _plan_options()
    args.update(review=False, auto_repair=False)
    second = session.run_from_plan(**args)
    assert len(calls) == 8
    assert [row['stage'] for row in calls[-3:]] == ['memory', 'style', 'draft']
    assert (bible.model_dump(), surface.model_dump()) == original
    assert memory.chapter_id == 'c' and style.name == surface.name
    assert result.final_report['author_acceptance'] == second.final_report['author_acceptance'] == 'pending'
    with pytest.raises(RequestBudgetExceeded):
        session.extract_memory(bible, [], 'c', PROSE)
    assert len(calls) == 8


@pytest.mark.parametrize('method', ['run', 'run_from_plan'])
@pytest.mark.parametrize('key', ['reviewer', 'external_review_hooks', 'structured_extractor'])
def test_both_flow_entries_reject_opaque_execution_before_transport(monkeypatch, method, key):
    session, calls = session_transport(monkeypatch)
    args = options() if method == 'run' else _plan_options()
    args[key] = object()
    with pytest.raises(ValueError, match='externally supplied'):
        getattr(session, method)(**args)
    assert calls == []
    assert session.budget_snapshot()['requests_reserved'] == 0


@pytest.mark.parametrize('reported', [0, 7, 8, -1, True, '1'])
def test_reported_usage_never_refunds_reserved_cap(monkeypatch, reported):
    calls = []
    def handler(req):
        calls.append(req)
        data = envelope('短')
        data['usage'] = {'completion_tokens': reported}
        return httpx.Response(200, json=data)
    transport(monkeypatch, handler)
    budget = RequestBudget(RequestBudgetLimits(max_reserved_output_tokens=7))
    provider = OpenAICompatibleProvider(ProviderConfig('https://example.invalid/v1', 'model'), request_budget=budget)
    if type(reported) is int and 0 <= reported <= 7:
        assert provider.chat(MESSAGES, max_tokens=7) == '短'
    else:
        with pytest.raises(OutputValidationError):
            provider.chat(MESSAGES, max_tokens=7)
    with pytest.raises(RequestBudgetExceeded):
        provider.chat(MESSAGES, max_tokens=1)
    assert len(calls) == 1 and budget.snapshot()['output_tokens_reserved'] == 7
    assert budget.snapshot()['actual_tokens'] is None


@pytest.mark.parametrize('copy_kind', ['shallow', 'deep'])
@pytest.mark.parametrize('boundary', ['totals', 'closed'])
def test_copying_live_ledger_cannot_duplicate_or_desynchronize_allowance(copy_kind, boundary):
    from copy import copy
    budget = RequestBudget(RequestBudgetLimits(max_requests=4, max_total_request_bytes=2,
                                               max_reserved_output_tokens=1))
    try:
        copied = copy(budget) if copy_kind == 'shallow' else deepcopy(budget)
    except TypeError:
        return  # Explicitly noncopyable live ledgers are safe.
    if boundary == 'closed':
        budget.close()
        with pytest.raises(RequestBudgetExceeded):
            copied.admit(b'{}', max_tokens=1)
    else:
        ticket = budget.admit(b'{}', max_tokens=1)
        budget.finish(ticket, succeeded=True)
        with pytest.raises(RequestBudgetExceeded):
            copied.admit(b'{}', max_tokens=1)
        snap = budget.snapshot()
        assert snap['request_bytes_reserved'] == sum(row['request_bytes'] for row in snap['attempts'])
        assert snap['output_tokens_reserved'] == sum(row['reserved_output_tokens'] for row in snap['attempts'])


def test_mutation_during_format_fallback_cannot_redirect_endpoint_or_expand_response_caps(monkeypatch):
    calls = []
    budget = RequestBudget()
    provider = OpenAICompatibleProvider(ProviderConfig('https://original.invalid/v1', 'original'), request_budget=budget)
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            provider.config.base_url = 'https://mutated.invalid/v1'
            provider.config.model = 'mutated-model'
            provider.config.max_response_bytes = 1
            return httpx.Response(400, json={'error': {'param': 'response_format', 'code': 'unsupported_parameter'}})
        return httpx.Response(200, json=envelope())
    transport(monkeypatch, handler)
    assert provider.chat(MESSAGES, max_tokens=7, response_format={'type': 'json_object'}) == PROSE
    assert [req.url.host for req in calls] == ['original.invalid', 'original.invalid']
    assert all(json.loads(req.content)['model'] == 'original' for req in calls)
    with pytest.raises(ValueError, match='configuration changed'):
        provider.chat(MESSAGES, max_tokens=7)
    assert budget.snapshot()['requests_reserved'] == len(calls) == 2


@pytest.mark.parametrize('interruption', [KeyboardInterrupt, SystemExit])
def test_non_exception_interruptions_still_finish_reserved_attempt(monkeypatch, interruption):
    calls = []
    def handler(req):
        calls.append(req)
        raise interruption('synthetic interruption')
    transport(monkeypatch, handler)
    budget = RequestBudget(RequestBudgetLimits(max_requests=1))
    provider = OpenAICompatibleProvider(ProviderConfig('https://example.invalid/v1', 'model'), request_budget=budget)
    with pytest.raises(interruption):
        provider.chat(MESSAGES, max_tokens=7)
    assert budget.snapshot()['attempts'][0]['status'] == 'failed'
    with pytest.raises(RequestBudgetExceeded):
        provider.chat(MESSAGES, max_tokens=7)
    assert len(calls) == 1


def test_shallow_session_copy_still_shares_original_live_allowance(monkeypatch):
    from copy import copy
    session, calls = session_transport(monkeypatch, RequestBudgetLimits(max_requests=2))
    copied = copy(session)
    args = _plan_options()
    args.update(review=False, auto_repair=False)
    session.run_from_plan(**args)
    copied.run_from_plan(**args)
    assert session.budget_snapshot() == copied.budget_snapshot()
    assert len(calls) == 2
    with pytest.raises(RequestBudgetExceeded):
        copied.run_from_plan(**args)
    session.close()
    assert copied.budget_snapshot()['closed']


def test_missing_required_reviewer_route_is_detected_before_planning_request(monkeypatch):
    calls = []
    transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(200, json=envelope(json.dumps(PLAN))))
    session = BudgetedWritingSession(RouterConfig(colab=ProviderConfig('https://colab.invalid/v1', 'colab-model')))
    with pytest.raises(RuntimeError, match='review provider'):
        session.run(**options())
    assert calls == []
    assert session.budget_snapshot()['requests_reserved'] == 0
