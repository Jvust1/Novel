"""Offline provenance checks for cached longform guard/context admission.

Synthetic encoders/provider only. The real ContextAssembler -> NovelEngine five
stage boundary is exercised; no optional model, FAISS, or provider call is made.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from novel_ai.context import ContextAssembler
from novel_ai.engine import NovelEngine
from novel_ai.models import StoryBible
from novel_ai.recall_backends import LocalSemanticRecall
from novel_ai.storage import ProjectStore


class Encoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture(autouse=True)
def no_accelerator(monkeypatch):
    real_find_spec = __import__('importlib.util', fromlist=['find_spec']).find_spec
    monkeypatch.setattr(
        'novel_ai.recall_backends.importlib.util.find_spec',
        lambda name, *args, **kwargs: None if name == 'faiss' else real_find_spec(name, *args, **kwargs),
    )


def seed(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_story_state('audit', {
        'facts': ['钥匙尚未交出。', '主人公不知道证人的真名。'],
        'open_threads': ['证人何时到达'],
        'foreshadowing': [{'id': 'wait', 'description': '桥头约定', 'status': 'planted'}],
    })
    for chapter_id, summary in [
        ('old', '蓝钥匙仍在靴底。'),
        ('recent', '他在桥头等人。'),
        ('future', '未来章节才说明证人是钟匠。'),
    ]:
        store.save_extraction('audit', {'chapter_id': chapter_id, 'summary': summary})
    return store


def assemble(store, mode, *, scope=('old', 'recent'), query='钥匙', **options):
    backend = LocalSemanticRecall(Encoder()) if mode == 'semantic' else None
    kwargs = {'recent_limit': 1, 'recall_query': query}
    if scope is not None:
        kwargs['history_chapter_ids'] = list(scope)
    return ContextAssembler(store, 'audit', local_semantic_recall=backend, **options).assemble(**kwargs)


UNBOUND_CACHES = [
    {'guard_context': '未来才揭晓：钟匠其实是证人。', 'source_chapter_ids': ['future']},
    {'guard_context': '旧版本误写：钥匙早已交给证人。', 'source_chapter_ids': ['deleted'], 'revision': 'stale'},
    {'guard_context': '另一本书的主人公是藏刀人。', 'project': 'other-project', 'project_scope': 'other-project'},
    {'guard_context': '自报已验证仍不能构成来源绑定。', 'history_chapter_ids': ['old', 'recent'], 'verified': True},
]


@pytest.mark.parametrize('mode', ['semantic', 'mmr'])
@pytest.mark.parametrize('cache', UNBOUND_CACHES)
def test_explicit_history_omits_future_stale_wrong_project_and_self_claimed_guard(tmp_path, mode, cache):
    store = seed(tmp_path)
    expected = assemble(store, mode)
    before = deepcopy(store.load_story_state('audit'))
    store.save_longform_health('audit', cache)
    actual = assemble(store, mode)
    assert actual.longform_block == ''
    assert cache['guard_context'] not in actual.prompt_sections()
    assert actual.longform_report['status'] == 'omitted_unverified_scope'
    assert actual.longform_report['history_chapter_ids'] == ['old', 'recent']
    assert 'no verified' in actual.longform_report['reason']
    assert cache['guard_context'] not in json.dumps(actual.longform_report, ensure_ascii=False)
    assert actual.canon_block == expected.canon_block
    assert actual.active_block == expected.active_block
    assert actual.recall_block == expected.recall_block
    assert actual.recent_summaries == expected.recent_summaries
    assert store.load_story_state('audit') == before
    assert store.load_longform_health('audit') == cache


@pytest.mark.parametrize('mode', ['semantic', 'mmr'])
@pytest.mark.parametrize('scope', [[], ['old'], ['old', 'recent']])
@pytest.mark.parametrize('query', ['', '钥匙'])
def test_every_explicit_scope_omits_cache_even_without_query_or_recall_budget(tmp_path, mode, scope, query):
    store = seed(tmp_path)
    cache = {'guard_context': '缓存里的未来秘密不能绕过空 Recall。'}
    store.save_longform_health('audit', cache)
    actual = assemble(store, mode, scope=scope, query=query, recall_char_budget=0)
    assert actual.longform_block == ''
    assert cache['guard_context'] not in actual.prompt_sections()
    assert actual.longform_report['status'] == 'omitted_unverified_scope'
    assert actual.longform_report['history_chapter_ids'] == scope
    assert '钥匙尚未交出。' in actual.canon_block


@pytest.mark.parametrize('mode', ['semantic', 'mmr'])
def test_overlong_scoped_guard_is_omitted_whole_not_prefix_clipped(tmp_path, mode):
    store = seed(tmp_path)
    guard = '钟匠身份已经揭晓。' + '旧判断。' * 500 + '前述判断并不成立，尚不能揭晓。'
    store.save_longform_health('audit', {'guard_context': guard})
    context = assemble(store, mode)
    assert context.longform_block == ''
    assert '钟匠身份已经揭晓' not in context.prompt_sections()
    assert context.longform_report['status'] == 'omitted_unverified_scope'


@pytest.mark.parametrize('mode', ['chronological', 'mmr'])
@pytest.mark.parametrize('length', [80, 1399, 1400, 1401, 1800])
def test_legacy_unscoped_guard_is_whole_or_omitted_and_disclosed(tmp_path, mode, length):
    store = seed(tmp_path)
    guard = '原' * (length - 3) + '未成立'
    store.save_longform_health('audit', {'guard_context': guard})
    context = assemble(store, mode, scope=None, query='' if mode == 'chronological' else '钥匙')
    expected_status = 'legacy_unscoped' if length <= 1400 else 'omitted_legacy_budget'
    assert context.longform_report['status'] == expected_status
    expected_reason = ('legacy caller supplied no history scope; cached guard provenance is not verified'
                       if length <= 1400 else 'unverified legacy guard exceeds its whole-text budget; do not truncate qualifiers')
    assert context.longform_report['reason'] == expected_reason
    # Unscoped provenance remains unverified, but qualification is never cut away.
    expected = '【Longform 长篇一致性】\n' + guard if length <= 1400 else ''
    assert context.longform_block == expected
    assert '……' not in context.longform_block


class Provider:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(deepcopy(messages))
        turn = len(self.calls)
        if turn == 1:
            return json.dumps({
                'chapter_title': '合成守门测试', 'chapter_promise': '等待证人', 'tension_curve': '上升',
                'scenes': [{'scene_no': 1, 'objective': '等人', 'opposition': '车将开', 'choice': '留下', 'cost': '误车', 'state_change': '继续等待'}],
                'must_not_happen': [],
            }, ensure_ascii=False)
        if turn in (3, 5):
            return json.dumps({'verdict': 'revise', 'issues': []})
        return '他留在桥头，隔着靴面按住了钥匙。'


@pytest.mark.parametrize('mode', ['semantic', 'mmr'])
def test_unbound_guard_cannot_reach_any_of_five_real_writer_stages(tmp_path, mode):
    store = seed(tmp_path)
    guard = '禁止提前透露的缓存秘密：钟匠是证人，藏刀人是他兄弟。'
    store.save_longform_health('audit', {'guard_context': guard, 'project': 'other-project', 'source_chapter_ids': ['future']})
    before = deepcopy(store.load_story_state('audit'))
    context = assemble(store, mode)
    provider = Provider()
    result = NovelEngine(provider).run(
        bible=StoryBible(), outline='合成纲', chapter_goal='继续等待', characters=[],
        recent_summaries=context.recent_summaries, review=True, auto_repair=True,
        extra_context=context.prompt_sections(),
    )
    assert len(provider.calls) == 5 and result.review_after_repair is not None
    assert context.longform_block == ''
    assert context.longform_report['status'] == 'omitted_unverified_scope'
    for messages in provider.calls:
        content = '\n'.join(message['content'] for message in messages)
        assert '钟匠' not in content and '藏刀人' not in content
        assert context.canon_block in content
        assert '钥匙尚未交出。' in content and '主人公不知道证人的真名。' in content
        assert context.active_block in content and context.recall_block in content
    assert store.load_story_state('audit') == before


@pytest.mark.parametrize('mode', ['semantic', 'mmr'])
@pytest.mark.parametrize('guard', [None, '', ' \n\t '])
def test_missing_or_blank_scoped_guard_is_reported_absent(tmp_path, mode, guard):
    store = seed(tmp_path)
    store.save_longform_health('audit', {'guard_context': guard})
    context = assemble(store, mode)
    assert context.longform_block == ''
    assert context.longform_report == {
        'status': 'absent', 'reason': 'no cached guard',
        'history_chapter_ids': ['old', 'recent'],
    }


def test_scoped_omission_report_has_detached_scope_and_no_cached_prose(tmp_path):
    store = seed(tmp_path)
    guard = '只可存在于缓存原件的未来秘密。'
    store.save_longform_health('audit', {'guard_context': guard})
    scope = ['old', 'recent']
    context = ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(Encoder())).assemble(
        recent_limit=1, recall_query='钥匙', history_chapter_ids=scope,
    )
    assert context.longform_report['status'] == 'omitted_unverified_scope'
    assert guard not in json.dumps(context.longform_report, ensure_ascii=False)
    context.longform_report['history_chapter_ids'].append('future')
    assert scope == ['old', 'recent']
    assert context.recall_report['history_chapter_ids'] == ['old', 'recent']
