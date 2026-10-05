"""Independent offline adversarial audit of local recall and writer-context use.

Encoders, provider, tokenizer and FAISS below are explicit test doubles. These
checks establish state/source/budget contracts, not semantic quality or speed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import math
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from novel_ai.context import ContextAssembler
from novel_ai.engine import NovelEngine
from novel_ai.models import StoryBible
from novel_ai.recall import RecallDocument, RecallHit
from novel_ai.recall_backends import LocalSemanticRecall
from novel_ai.semantic import vector_cosine
from novel_ai.semantic_history import select_semantic_history
from novel_ai.storage import ProjectStore
from novel_ai.token_budget import TokenCounter


class FixedEncoder:
    def __init__(self):
        self.calls = []
        self.override = None

    def encode(self, texts):
        self.calls.append(list(texts))
        if self.override is not None:
            return self.override(texts)
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture(autouse=True)
def no_optional_accelerator(monkeypatch):
    real_find_spec = __import__('importlib.util', fromlist=['find_spec']).find_spec
    monkeypatch.setattr(
        'novel_ai.recall_backends.importlib.util.find_spec',
        lambda name, *args, **kwargs: None if name == 'faiss' else real_find_spec(name, *args, **kwargs),
    )


def populate(store, project='audit'):
    for chapter_id, summary in [
        ('old-a', '蓝钥匙仍在靴底。'),
        ('old-b', '火车明日才开。'),
        ('recent', '此刻他在桥头等人。'),
    ]:
        store.save_extraction(project, {'chapter_id': chapter_id, 'chapter_title': chapter_id, 'summary': summary})
    store.save_story_state(project, {
        'facts': ['钥匙尚未交出。'], 'open_threads': ['证人何时出现'],
        'foreshadowing': [{'id': 'waiting', 'description': '桥头约定', 'status': 'planted'}],
    })


def snapshot(backend):
    return deepcopy((backend.ids, backend.texts, backend.metadata, backend.vectors))


def test_late_generator_failure_does_not_publish_part_of_an_update():
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['old'], ['old source'], [{'nested': {'versions': [1]}}])
    before = snapshot(backend)

    def failing_rows(texts):
        yield [0, 1]
        raise RuntimeError('second row unavailable')

    encoder.override = failing_rows
    with pytest.raises(ValueError, match='embedding'):
        backend.add(['new'], ['new source'])
    assert snapshot(backend) == before
    encoder.override = None
    assert backend.query('query')[0].text == 'old source'


def test_query_and_update_observe_complete_snapshots_in_both_directions():
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['old'], ['old source'])
    entered, release = Event(), Event()

    def blocked_update(texts):
        if texts == ['new source']:
            entered.set()
            assert release.wait(5), 'test failed to release blocked update'
        return [[1, 0] for _ in texts]

    encoder.override = blocked_update
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(backend.replace_documents, [RecallDocument('new', 'new source')])
        try:
            assert entered.wait(5)
            assert [(h.document_id, h.text) for h in backend.query('query')] == [('old', 'old source')]
        finally:
            release.set()
        pending.result(5)
    assert backend.ids == ['new']

    entered.clear()
    release.clear()

    def blocked_query(texts):
        if texts == ['slow query']:
            entered.set()
            assert release.wait(5), 'test failed to release blocked query'
            return [[1, 0]]
        return [[0, 0, 1] for _ in texts]

    encoder.override = blocked_query
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(backend.query, 'slow query')
        try:
            assert entered.wait(5)
            backend.replace_documents([])
            backend.replace_documents([RecallDocument('third', 'third source')])
        finally:
            release.set()
        hits = pending.result(5)
    assert [(h.document_id, h.text, h.score) for h in hits] == [('new', 'new source', 1.0)]
    assert backend.ids == ['third'] and backend.vectors == [[0.0, 0.0, 1.0]]


def test_recursive_index_callback_cannot_publish_a_nested_clear():
    encoder = FixedEncoder()

    class ReentrantIndexBackend(LocalSemanticRecall):
        recursive = False

        def _build_index(self, vectors):
            if self.recursive:
                self.replace_documents([])
            return None, None

    backend = ReentrantIndexBackend(encoder)
    backend.add(['old'], ['old source'])
    before = snapshot(backend)
    backend.recursive = True
    with pytest.raises(ValueError):
        backend.replace_documents([RecallDocument('new', 'new source')])
    assert snapshot(backend) == before
    backend.recursive = False
    backend.replace_documents([RecallDocument('new', 'new source')])
    assert backend.ids == ['new']


@pytest.mark.parametrize('scale', [1e308, 5e-324, 0.0])
def test_extreme_vectors_preserve_finite_bounded_scores_and_detached_results(scale):
    encoder = FixedEncoder()
    encoder.override = lambda texts: [[scale, -scale] for _ in texts]
    backend = LocalSemanticRecall(encoder)
    metadata = {'nested': {'versions': [1]}}
    backend.add(['z', 'a'], ['first', 'second'], [metadata, metadata])
    metadata['nested']['versions'].append(2)
    first = backend.query('query', limit=1)[0]
    assert first.document_id == 'a'
    assert first.score == (0.0 if scale == 0 else 1.0)
    assert math.isfinite(first.score)
    first.metadata['nested']['versions'].append(3)
    assert backend.query('query')[0].metadata == {'nested': {'versions': [1]}}
    assert vector_cosine([scale, -scale], [-scale, scale]) == (0.0 if scale == 0 else -1.0)


@pytest.mark.parametrize('bad', [None, 1, True, '12', {'x': 1}, {1, 2}, [], [1, 2, 3], [1, math.inf]])
def test_invalid_scalar_or_vector_shapes_preserve_old_corpus(bad):
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['old'], ['old source'])
    before = snapshot(backend)
    encoder.override = lambda texts: [bad]
    with pytest.raises(ValueError):
        backend.replace_documents([RecallDocument('new', 'new source')])
    assert snapshot(backend) == before


def stub_faiss(monkeypatch, output):
    np = pytest.importorskip('numpy')

    class Index:
        def __init__(self, dimension):
            self.d, self.ntotal = dimension, 0

        def add(self, matrix):
            self.ntotal = len(matrix)
            self.matrix = np.array(matrix, copy=True)

        def search(self, matrix, count):
            return output

    monkeypatch.setitem(sys.modules, 'faiss', SimpleNamespace(IndexFlatIP=Index))
    monkeypatch.setattr('novel_ai.recall_backends.importlib.util.find_spec', lambda name: object())


@pytest.mark.parametrize('output', [
    ([[1, 1]], [[0, 0]]),
    ([[1, 1]], [[0, -1]]),
    ([[1, 1]], [[0, 2]]),
    ([[1, 1]], [[0, False]]),
    ([[1, 1]], [[0, 1.0]]),
    ([[1, 1]], [[0]]),
    ([[1]], [[0, 1]]),
    ([[1, math.nan]], [[0, 1]]),
    ([[1, -1.01]], [[0, 1]]),
    ([[1, 1], [1, 1]], [[0, 1]]),
    ([[1, 1]], {'row': [0, 1]}),
    ([[1, 1]], [{0, 1}]),
])
def test_multirecord_malformed_faiss_outputs_fail_closed(monkeypatch, output):
    stub_faiss(monkeypatch, output)
    backend = LocalSemanticRecall(FixedEncoder())
    backend.add(['a', 'b'], ['first', 'second'])
    before, index = snapshot(backend), backend._index
    with pytest.raises(ValueError, match='FAISS'):
        backend.query('query')
    assert snapshot(backend) == before and backend._index is index


def test_recent_sources_are_never_encoded_as_older_recall(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    baseline = ContextAssembler(store, 'audit').assemble(recent_limit=1, recall_query='蓝钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    context = ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(recent_limit=1, recall_query='蓝钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    assert encoder.calls == [['蓝钥匙仍在靴底。', '火车明日才开。'], ['蓝钥匙']]
    assert {m['chapter_id'] for m in backend.metadata} == {'old-a', 'old-b'}
    assert context.canon_block == baseline.canon_block
    assert context.active_block == baseline.active_block
    assert context.recent_summaries == baseline.recent_summaries
    assert 'recent' not in context.recall_block
    assert context.recall_report['semantic_quality_validated'] is False


def test_no_query_keeps_chronological_default_without_encoder_calls(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    baseline = ContextAssembler(store, 'audit').assemble(recent_limit=1)
    context = ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(encoder)).assemble(recent_limit=1)
    assert context == baseline and encoder.calls == []
    assert context.recall_report is None
    assert context.recall_block.index('old-a') < context.recall_block.index('old-b')


def test_recent_only_project_clears_preexisting_foreign_index(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['foreign'], ['another book'])
    encoder.calls.clear()
    context = ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(recent_limit=100, recall_query='蓝钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    assert context.recall_block == '' and backend.ids == []
    assert encoder.calls == []
    assert context.recall_report['candidate_count'] == 0


@pytest.mark.parametrize('options', [
    {'recall_char_budget': 0}, {'recall_char_budget': -1},
    {'recall_summary_chars': 0}, {'recall_token_budget': 0},
])
def test_disabled_budget_clears_old_index_and_does_not_encode(tmp_path, options):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['stale'], ['stale source'])
    encoder.calls.clear()
    context = ContextAssembler(store, 'audit', local_semantic_recall=backend, **options).assemble(recent_limit=1, recall_query='蓝钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    assert backend.ids == [] and encoder.calls == [] and context.recall_block == ''
    assert context.recall_report['included_chapter_ids'] == []


class ByteEncoding:
    def encode(self, text):
        return list(text.encode('utf-8'))


def test_exact_char_and_token_budgets_include_entire_recall_wrapper(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction('audit', {'chapter_id': '旧章', 'summary': '蓝钥匙仍在靴底。'})
    backend = LocalSemanticRecall(FixedEncoder())
    counter = TokenCounter(ByteEncoding())
    unbounded = ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(recent_limit=0, recall_query='钥匙', history_chapter_ids=['旧章'])
    block = unbounded.recall_block
    assert block and counter.count(block) > len(block)
    for options, expected in [
        ({'recall_char_budget': len(block)}, block),
        ({'recall_char_budget': len(block) - 1}, ''),
        ({'recall_token_budget': counter.count(block)}, block),
        ({'recall_token_budget': counter.count(block) - 1}, ''),
    ]:
        context = ContextAssembler(store, 'audit', local_semantic_recall=backend, token_counter=counter, **options).assemble(recent_limit=0, recall_query='钥匙', history_chapter_ids=['旧章'])
        assert context.recall_block == expected
        assert context.recall_report['prompt_chars'] == len(expected)
        assert bool(context.recall_report['omitted_sources']) is not bool(expected)


@pytest.mark.parametrize('bad', [True, 0, -1, 1.1, '1', None])
def test_explicit_history_limit_rejected_before_replacement(bad):
    backend = LocalSemanticRecall(FixedEncoder())
    backend.add(['old'], ['old source'])
    with pytest.raises(ValueError):
        select_semantic_history(backend, 'query', [], project_scope='A', limit=bad)
    assert backend.ids == ['old']


@pytest.mark.parametrize('field,value', [
    ('schema', 'unknown-schema'), ('project_scope', 'other-project'),
    ('chapter_id', 'other-chapter'), ('source_fingerprint', 'other-version'),
])
def test_every_source_metadata_field_is_checked(field, value):
    class AlteredHitBackend(LocalSemanticRecall):
        def query(self, text, *, limit=5):
            hit = super().query(text, limit=limit)[0]
            return [RecallHit(hit.document_id, hit.score, hit.text, {**hit.metadata, field: value})]

    with pytest.raises(ValueError, match='source identity'):
        select_semantic_history(AlteredHitBackend(FixedEncoder()), '钥匙', [{'chapter_id': 'a', 'summary': '钥匙在靴底。'}], project_scope='A')


def test_semantic_excerpt_never_changes_a_question_into_a_fact():
    selected, _ = select_semantic_history(
        LocalSemanticRecall(FixedEncoder()), '钥匙',
        [{'chapter_id': 'a', 'summary': '蓝钥匙已经交给证人了吗？没有，钥匙仍在靴底。'}],
        project_scope='A', summary_chars=10,
    )
    assert all(row['recall_excerpt'] != '蓝钥匙已经交给证人了' for row in selected)
    assert all(not row['recall_excerpt'] or row['recall_excerpt'].rstrip('…').endswith(('。', '？', '！')) for row in selected)


def test_encoder_callback_cannot_change_source_identity_or_returned_records():
    rows = [{'chapter_id': 'original-id', 'summary': '钥匙在靴底。', 'extra': {'revision': 1}}]
    original = deepcopy(rows[0])
    encoder = FixedEncoder()

    def mutate_source(texts):
        rows[0]['chapter_id'] = 'forged-id'
        rows[0]['summary'] = '钥匙已交给证人。'
        rows[0]['extra']['revision'] = 2
        return [[1, 0] for _ in texts]

    encoder.override = mutate_source
    backend = LocalSemanticRecall(encoder)
    selected, report = select_semantic_history(backend, '钥匙', rows, project_scope='A')
    assert selected == [{**original, 'recall_excerpt': original['summary']}]
    assert report['selected_sources'][0]['chapter_id'] == 'original-id'
    selected[0]['extra']['revision'] = 3
    assert rows[0]['extra']['revision'] == 2


class RecordingProvider:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(deepcopy(messages))
        turn = len(self.calls)
        if turn == 1:
            return json.dumps({
                'chapter_title': '合成审计章', 'chapter_promise': '等待证人', 'tension_curve': '上升',
                'scenes': [{'scene_no': 1, 'objective': '等人', 'opposition': '车将开', 'choice': '留下', 'cost': '误车', 'state_change': '错过出发'}],
                'must_not_happen': [],
            }, ensure_ascii=False)
        if turn in (3, 5):
            return json.dumps({'verdict': 'revise', 'issues': []})
        return '他仍在桥头，手指隔着靴面按了按钥匙。'


def run_writer(assembler, provider):
    context = assembler.assemble(recent_limit=1, recall_query='钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    result = NovelEngine(provider).run(
        bible=StoryBible(), outline='测试纲', chapter_goal='等证人', characters=[],
        recent_summaries=context.recent_summaries, review=True, auto_repair=True,
        extra_context=context.prompt_sections(),
    )
    return context, result


def test_exact_context_flows_through_all_five_writer_stages_without_memory_mutation(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    before = deepcopy(store.load_story_state('audit'))
    provider = RecordingProvider()
    context, result = run_writer(ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(FixedEncoder())), provider)
    assert len(provider.calls) == 5 and result.review_after_repair is not None
    for messages in provider.calls:
        contents = '\n'.join(message['content'] for message in messages)
        assert context.prompt_sections() in contents
        assert context.canon_block in contents
        assert context.active_block in contents
        assert context.recall_block in contents
    assert store.load_story_state('audit') == before


@pytest.mark.parametrize('failure', ['replace', 'query'])
def test_failed_context_never_reaches_first_writer_stage_or_falls_back(tmp_path, failure):
    store = ProjectStore(tmp_path)
    populate(store)

    class FailingBackend(LocalSemanticRecall):
        fail = False

        def replace_documents(self, documents):
            if self.fail and failure == 'replace':
                raise ValueError('synthetic replacement failure')
            return super().replace_documents(documents)

        def query(self, text, *, limit=5):
            if self.fail and failure == 'query':
                raise ValueError('synthetic query failure')
            return super().query(text, limit=limit)

    backend = FailingBackend(FixedEncoder())
    assembler = ContextAssembler(store, 'audit', local_semantic_recall=backend)
    assembler.assemble(recent_limit=1, recall_query='钥匙', history_chapter_ids=['old-a', 'old-b', 'recent'])
    backend.fail = True
    provider = RecordingProvider()
    with pytest.raises(ValueError, match='synthetic'):
        run_writer(assembler, provider)
    assert provider.calls == []


@pytest.mark.parametrize('summary', [
    '蓝钥匙已经交给证人了吗？没有，钥匙仍在靴底。',
    '钥匙已经交给证人。这是旧记录的错误说法，钥匙其实仍在靴底。',
    'A source without punctuation is still preserved in full',
])
def test_semantic_source_is_whole_or_explicitly_omitted(summary):
    rows = [{'chapter_id': 'a', 'summary': summary}]
    backend = LocalSemanticRecall(FixedEncoder())
    selected, full = select_semantic_history(backend, '钥匙', rows, project_scope='A', summary_chars=len(summary))
    assert selected[0]['recall_excerpt'] == summary
    assert full['omitted_sources'] == []
    selected, omitted = select_semantic_history(backend, '钥匙', rows, project_scope='A', summary_chars=len(summary) - 1)
    assert selected == []
    assert len(omitted['selected_sources']) == 1
    assert omitted['omitted_sources'][0]['chapter_id'] == 'a'
    assert omitted['omitted_sources'][0]['source_fingerprint'] == full['selected_sources'][0]['source_fingerprint']
    assert 'complete' in omitted['omitted_sources'][0]['reason']
    assert omitted['corpus_fingerprint'] == full['corpus_fingerprint']


def test_no_counter_for_positive_semantic_token_budget_fails_before_encoding(tmp_path):
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    with pytest.raises(ValueError, match='token counter'):
        ContextAssembler(ProjectStore(tmp_path), 'audit', local_semantic_recall=backend, recall_token_budget=1)
    assert encoder.calls == []
    # Existing non-semantic default behavior is deliberately left unchanged.
    ContextAssembler(ProjectStore(tmp_path), 'audit', recall_token_budget=1)


def test_backend_cannot_change_expected_metadata_to_accept_foreign_hit():
    class MutatingBackend(LocalSemanticRecall):
        def replace_documents(self, documents):
            for document in documents:
                document.metadata['project_scope'] = 'foreign-project'
            return super().replace_documents(documents)

    with pytest.raises(ValueError, match='source identity'):
        select_semantic_history(MutatingBackend(FixedEncoder()), '钥匙', [{'chapter_id': 'a', 'summary': '钥匙在靴底。'}], project_scope='A')


def test_backend_callback_cannot_change_corpus_fingerprint_for_identical_sources():
    class MutatingBackend(LocalSemanticRecall):
        def replace_documents(self, documents):
            super().replace_documents(documents)
            for document in documents:
                document.metadata['source_fingerprint'] = 'changed-after-the-snapshot'

    rows = [{'chapter_id': 'a', 'summary': '钥匙在靴底。'}]
    expected_rows, expected = select_semantic_history(LocalSemanticRecall(FixedEncoder()), '钥匙', rows, project_scope='A')
    actual_rows, actual = select_semantic_history(MutatingBackend(FixedEncoder()), '钥匙', rows, project_scope='A')
    assert actual_rows == expected_rows
    assert actual == expected


def test_summary_omission_and_full_block_omission_each_retain_distinct_provenance(tmp_path):
    store = ProjectStore(tmp_path)
    summaries = [
        ('long', '钥匙已经交给证人了吗？没有，钥匙仍在靴底。'),
        ('short', '钥匙在靴底。'),
    ]
    for chapter_id, summary in summaries:
        store.save_extraction('audit', {'chapter_id': chapter_id, 'summary': summary})
    context = ContextAssembler(
        store, 'audit', local_semantic_recall=LocalSemanticRecall(FixedEncoder()),
        recall_summary_chars=10, recall_char_budget=2,
    ).assemble(recent_limit=0, recall_query='钥匙', history_chapter_ids=['long', 'short'])
    assert context.recall_block == ''
    report = context.recall_report
    assert {s['chapter_id'] for s in report['selected_sources']} == {'long', 'short'}
    omissions = {s['chapter_id']: s for s in report['omitted_sources']}
    assert set(omissions) == {'long', 'short'}
    assert 'complete source' in omissions['long']['reason']
    assert 'whole summary line' in omissions['short']['reason']
    for source in report['selected_sources']:
        assert omissions[source['chapter_id']]['source_fingerprint'] == source['source_fingerprint']


def test_future_chapters_and_stale_backend_rows_cannot_enter_any_writer_stage(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    store.save_extraction('audit', {'chapter_id': 'future', 'summary': '未来才揭晓的证人身份是钟匠。'})
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['stale-future'], ['旧索引保留的未来泄密。'])
    encoder.calls.clear()
    provider = RecordingProvider()
    context, _ = run_writer(ContextAssembler(store, 'audit', local_semantic_recall=backend), provider)
    assert context.recall_report['history_chapter_ids'] == ['old-a', 'old-b', 'recent']
    assert context.recall_report['excluded_out_of_scope_chapter_ids'] == ['future']
    assert {item['chapter_id'] for item in backend.metadata} == {'old-a', 'old-b'}
    assert encoder.calls == [['蓝钥匙仍在靴底。', '火车明日才开。'], ['钥匙']]
    assert len(provider.calls) == 5
    for messages in provider.calls:
        text = '\n'.join(message['content'] for message in messages)
        assert '钟匠' not in text and '未来泄密' not in text and 'future' not in text
        assert '钥匙尚未交出' in text


def test_explicit_history_order_controls_recent_split_not_storage_or_numeric_order(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    # A semantic history scope is author/caller order, not insertion/numeric order.
    scope = ['recent', 'old-b', 'old-a']
    context = ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(
        recent_limit=1, recall_query='钥匙', history_chapter_ids=scope,
    )
    assert context.recent_summaries[0]['chapter_id'] == 'old-a'
    assert {item['chapter_id'] for item in backend.metadata} == {'recent', 'old-b'}
    assert encoder.calls[0] == ['此刻他在桥头等人。', '火车明日才开。']
    assert context.recall_report['history_chapter_ids'] == scope
    context.recall_report['history_chapter_ids'].append('future')
    assert scope == ['recent', 'old-b', 'old-a']


@pytest.mark.parametrize('scope', [None, 'old-a', ('old-a',), {'old-a'}, ['old-a', 'old-a'], [''], [' '], [1], [True]])
def test_unconfirmed_or_malformed_history_scope_fails_before_backend_work(tmp_path, scope):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['old-index'], ['old index'])
    encoder.calls.clear()
    before = snapshot(backend)
    with pytest.raises(ValueError):
        ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(
            recall_query='钥匙', history_chapter_ids=scope,
        )
    assert encoder.calls == [] and snapshot(backend) == before


def test_missing_required_history_source_does_not_use_stale_index(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['missing'], ['缺少的章节在旧索引里仍存在。'])
    before = snapshot(backend)
    encoder.calls.clear()
    with pytest.raises(ValueError, match='source is missing'):
        ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(
            recent_limit=0, recall_query='钥匙', history_chapter_ids=['old-a', 'missing'],
        )
    assert snapshot(backend) == before and encoder.calls == []


def test_empty_confirmed_history_clears_index_and_excludes_all_recent_summaries(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['stale'], ['旧索引'])
    encoder.calls.clear()
    context = ContextAssembler(store, 'audit', local_semantic_recall=backend).assemble(
        recent_limit=1, recall_query='钥匙', history_chapter_ids=[],
    )
    assert backend.ids == [] and encoder.calls == []
    assert context.recent_summaries == [] and context.recall_block == ''
    assert '近章摘要' not in context.active_block
    assert context.recall_report['history_chapter_ids'] == []
    assert set(context.recall_report['excluded_out_of_scope_chapter_ids']) == {'old-a', 'old-b', 'recent'}
    assert '钥匙尚未交出' in context.canon_block


def test_conflicting_stored_history_versions_fail_before_indexing(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    encoder = FixedEncoder()
    rows = [
        {'chapter_id': 'a', 'summary': '钥匙在靴底。'},
        {'chapter_id': 'a', 'summary': '钥匙已交给证人。'},
    ]
    monkeypatch.setattr(store, 'all_chapter_summaries', lambda project: deepcopy(rows))
    with pytest.raises(ValueError, match='conflicting historical chapter versions'):
        ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(encoder)).assemble(
            recent_limit=0, recall_query='钥匙', history_chapter_ids=['a'],
        )
    assert encoder.calls == []


def test_encoder_callback_cannot_rewrite_confirmed_history_scope_report(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    scope = ['old-a']
    encoder = FixedEncoder()

    def mutate_scope(texts):
        scope.append('recent')
        return [[1, 0] for _ in texts]

    encoder.override = mutate_scope
    context = ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(encoder)).assemble(
        recent_limit=0, recall_query='钥匙', history_chapter_ids=scope,
    )
    assert context.recall_report['history_chapter_ids'] == ['old-a']
    assert set(context.recall_report['excluded_out_of_scope_chapter_ids']) == {'old-b', 'recent'}
    assert [s['chapter_id'] for s in context.recall_report['selected_sources']] == ['old-a']


def mode_context(store, mode, *, encoder=None, **options):
    backend = LocalSemanticRecall(encoder or FixedEncoder()) if mode == 'semantic' else None
    kwargs = {'recent_limit': 1}
    if mode in ('semantic', 'mmr'):
        kwargs['recall_query'] = '钥匙'
    if mode == 'semantic':
        kwargs['history_chapter_ids'] = ['old-a', 'old-b', 'recent']
    return ContextAssembler(store, 'audit', local_semantic_recall=backend, **options).assemble(**kwargs)


@pytest.mark.parametrize('mode', ['chronological', 'mmr', 'semantic'])
def test_whole_canon_exact_character_boundary_in_every_mode(tmp_path, mode):
    store = ProjectStore(tmp_path)
    populate(store)
    baseline = mode_context(store, mode).canon_block
    assert baseline.endswith('- 证人何时出现') and '钥匙尚未交出。' in baseline
    exact = mode_context(store, mode, canon_char_budget=len(baseline))
    assert exact.canon_block == baseline
    for budget in [len(baseline) - 1, 0, -1]:
        encoder = FixedEncoder()
        with pytest.raises(ValueError, match='required Canon'):
            mode_context(store, mode, encoder=encoder, canon_char_budget=budget)
        assert encoder.calls == []


@pytest.mark.parametrize('mode', ['chronological', 'mmr', 'semantic'])
def test_whole_canon_exact_token_boundary_in_every_mode(tmp_path, mode):
    store = ProjectStore(tmp_path)
    populate(store)
    counter = TokenCounter(ByteEncoding())
    baseline = mode_context(store, mode).canon_block
    exact_count = counter.count(baseline)
    assert exact_count > len(baseline)
    exact = mode_context(store, mode, token_counter=counter, canon_token_budget=exact_count)
    assert exact.canon_block == baseline
    for budget in [exact_count - 1, 0, -1]:
        encoder = FixedEncoder()
        with pytest.raises(ValueError, match='Canon exceeds its token budget'):
            mode_context(store, mode, encoder=encoder, token_counter=counter, canon_token_budget=budget)
        assert encoder.calls == []


@pytest.mark.parametrize('mode', ['chronological', 'mmr', 'semantic'])
def test_required_canon_token_budget_needs_counter_in_every_mode(tmp_path, mode):
    store = ProjectStore(tmp_path)
    populate(store)
    with pytest.raises(ValueError, match='Canon token budget requires a configured counter'):
        mode_context(store, mode, canon_token_budget=1000)


def test_empty_canon_permits_zero_budget_with_empty_history(tmp_path):
    encoder = FixedEncoder()
    context = ContextAssembler(
        ProjectStore(tmp_path), 'empty', local_semantic_recall=LocalSemanticRecall(encoder),
        canon_char_budget=0, canon_token_budget=0,
    ).assemble(recall_query='钥匙', history_chapter_ids=[])
    assert context.canon_block == context.active_block == context.recall_block == ''
    assert encoder.calls == []


def test_insufficient_canon_aborts_before_writer_or_retrieval_and_keeps_old_index(tmp_path):
    store = ProjectStore(tmp_path)
    populate(store)
    encoder = FixedEncoder()
    backend = LocalSemanticRecall(encoder)
    backend.add(['old-index'], ['旧索引'])
    before = snapshot(backend)
    encoder.calls.clear()
    provider = RecordingProvider()
    with pytest.raises(ValueError, match='required Canon'):
        run_writer(ContextAssembler(store, 'audit', local_semantic_recall=backend, canon_char_budget=1), provider)
    assert snapshot(backend) == before
    assert provider.calls == encoder.calls == []


def test_encoder_callback_cannot_mutate_active_or_canon_through_store_aliases(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    state = {
        'facts': ['钥匙尚未交出。'], 'open_threads': [],
        'foreshadowing': [{'id': 'wait', 'description': '桥头约定', 'status': 'planted'}],
    }
    rows = [
        {'chapter_id': 'old', 'summary': '钥匙在靴底。', 'extra': {'version': 1}},
        {'chapter_id': 'recent', 'summary': '桥头等待。', 'extra': {'version': 1}},
    ]
    monkeypatch.setattr(store, 'load_story_state', lambda project: state)
    monkeypatch.setattr(store, 'all_chapter_summaries', lambda project: rows)
    encoder = FixedEncoder()

    def mutate_store_aliases(texts):
        state['facts'][0] = '钥匙已交出。'
        state['foreshadowing'][0]['description'] = '未来身份泄密'
        rows[1]['summary'] = '未来章节的答案'
        rows[1]['extra']['version'] = 99
        return [[1, 0] for _ in texts]

    encoder.override = mutate_store_aliases
    context = ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(encoder)).assemble(
        recent_limit=1, recall_query='钥匙', history_chapter_ids=['old', 'recent'],
    )
    assert '钥匙尚未交出。' in context.canon_block and '钥匙已交出。' not in context.canon_block
    assert '桥头等待。' in context.active_block and '未来' not in context.active_block
    assert context.recent_summaries[0]['extra']['version'] == 1
    assert context.open_foreshadowing[0]['description'] == '桥头约定'
    context.recent_summaries[0]['extra']['version'] = 2
    assert rows[1]['extra']['version'] == 99


def test_encoder_callback_cannot_change_this_calls_budgets_project_or_health(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    populate(store)
    health = {
        'audit': {'guard_context': '本书的原始长篇一致性约束。'},
        'other': {'guard_context': '另一本书的未来信息。'},
    }
    reads = []

    def load_health(project):
        reads.append(project)
        return health[project]

    monkeypatch.setattr(store, 'load_longform_health', load_health)
    encoder = FixedEncoder()
    assembler = ContextAssembler(store, 'audit', local_semantic_recall=LocalSemanticRecall(encoder), recall_char_budget=2)

    def mutate_configuration(texts):
        assembler.project = 'other'
        assembler.recall_char_budget = 10_000
        assembler.recall_summary_chars = 10_000
        health['audit']['guard_context'] = '编码器后来注入的资料。'
        return [[1, 0] for _ in texts]

    encoder.override = mutate_configuration
    context = assembler.assemble(recent_limit=0, recall_query='钥匙', history_chapter_ids=['old-a'])
    assert reads == ['audit']
    assert context.recall_block == ''
    assert context.recall_report['omitted_sources'][0]['chapter_id'] == 'old-a'
    # Explicit history now omits every unbound cached guard, including this snapshot.
    assert context.longform_block == ''
    assert '另一本书' not in context.prompt_sections() and '注入' not in context.prompt_sections()
