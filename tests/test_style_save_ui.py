"""Actual Style Lab saves, retries, restart, clear and stale-session tests."""
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from novel_ai.storage import ProjectStore
from novel_ai.style_commit import load_style_bundle, prepare_style_addition
from novel_ai.style_engine import analyze_style, build_reference_signature
from novel_ai.style_ui import (
    commit_pending_style,
    freeze_style_request,
    refresh_saved_styles,
    style_input_binding,
)

ROOT = Path(__file__).resolve().parents[1]
TEXT = '原创样本。周宁把钥匙放回抽屉，听见院外有人问路。她没有开门，只把灯拨亮了一点。' * 20


def run_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    next(c for c in at.checkbox if c.label == '使用当前模型做语义文体分析').uncheck()
    next(t for t in at.text_area if t.label == '或粘贴参考文本').set_value(TEXT)
    return at


def analyze(at):
    next(b for b in at.button if b.label == '分析并加入风格库').click().run()


def test_actual_failed_save_keeps_session_and_retry_does_not_analyze_again(monkeypatch, tmp_path):
    from novel_ai import style_engine
    at = run_app(monkeypatch, tmp_path)
    original_write = ProjectStore._write
    fail = [True]
    calls = []
    original_analyze = style_engine.analyze_style

    def counted(*args, **kwargs):
        calls.append(True)
        return original_analyze(*args, **kwargs)

    def interrupted(self, path, content, **kwargs):
        if path.name == 'style_dna.json' and fail[0]:
            raise OSError('synthetic style disk interruption')
        return original_write(self, path, content, **kwargs)

    monkeypatch.setattr(style_engine, 'analyze_style', counted)
    monkeypatch.setattr(ProjectStore, '_write', interrupted)
    analyze(at)
    assert at.error or at.exception
    assert len(at.session_state['style_profiles']) == 0
    assert at.session_state['style'] is None and at.session_state['reference_hashes'] == set()
    assert at.session_state['style_pending'] is not None and len(calls) == 1
    fail[0] = False
    at.run()
    at.button(key='retry_style_save').click().run()
    assert not at.exception
    assert len(at.session_state['style_profiles']) == 1 and len(calls) == 1
    assert at.session_state['style_pending'] is None
    fresh = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert len(fresh.session_state['style_profiles']) == 1
    assert fresh.session_state['style'] == at.session_state['style']
    assert fresh.session_state['reference_hashes'] == at.session_state['reference_hashes']


def test_actual_clear_is_saved_and_stays_empty_after_restart(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    analyze(at)
    assert not at.exception and len(at.session_state['style_profiles']) == 1
    next(b for b in at.button if b.label == '清空并保存当前项目风格库').click().run()
    assert not at.exception and at.session_state['style_profiles'] == []
    fresh = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert fresh.session_state['style_profiles'] == []
    assert fresh.session_state['style'] is None and fresh.session_state['reference_hashes'] == set()


def test_stale_actual_session_stops_before_analysis(monkeypatch, tmp_path):
    from novel_ai import style_engine
    first = run_app(monkeypatch, tmp_path)
    second = run_app(monkeypatch, tmp_path)
    analyze(first)
    def forbidden(*args, **kwargs):
        pytest.fail('stale session reached analysis')
    monkeypatch.setattr(style_engine, 'analyze_style', forbidden)
    analyze(second)
    assert second.error and not second.exception
    assert second.session_state['style_profiles'] == []
    second.button(key='reload_saved_style').click().run()
    assert len(second.session_state['style_profiles']) == 1


@pytest.mark.parametrize('changed', ['project', 'source', 'name', 'weight', 'encoding', 'semantic', 'notes'])
def test_changed_inputs_cannot_reuse_frozen_request(tmp_path, changed):
    store = ProjectStore(tmp_path)
    state = {}
    snapshot = refresh_saved_styles(state, store, 'P')
    args = {'project': 'P', 'source': ['x.txt', 'digest'], 'name': 'Reference', 'weight': 1.0,
            'encoding': 'UTF-8', 'semantic': False, 'notes': ''}
    binding = style_input_binding(**args)
    files = prepare_style_addition(snapshot, {'name': 'Reference', 'weight': 1.0,
                                  'fingerprint': analyze_style(TEXT).model_dump()}, build_reference_signature(TEXT))
    freeze_style_request(state, store, 'P', files=files, expected_before=snapshot['sha256'], binding=binding, kind='add')
    before = deepcopy(state)
    args[changed] = {'project': 'Other', 'source': ['x.txt', 'newbytes'], 'name': 'Renamed', 'weight': 2.0,
                     'encoding': 'GB18030', 'semantic': True, 'notes': 'New notes'}[changed]
    with pytest.raises(ValueError):
        commit_pending_style(state, store, 'P', binding=style_input_binding(**args))
    assert state == before
    assert load_style_bundle(store, 'P')['profiles'] == []


def test_saved_request_nonce_is_frozen_and_detached(tmp_path):
    store = ProjectStore(tmp_path)
    state = {}
    snap = refresh_saved_styles(state, store, 'P')
    files = prepare_style_addition(snap, {'name': 'Original', 'weight': 1.0,
                                  'fingerprint': analyze_style(TEXT).model_dump()}, build_reference_signature(TEXT))
    freeze_style_request(state, store, 'P', files=files, expected_before=snap['sha256'], binding='binding', kind='add')
    nonce = state['style_pending']['request_id']
    files.clear()
    snap['sha256'].clear()
    result = commit_pending_style(state, store, 'P', binding='binding')
    assert result['receipt']['request_id'] == nonce
    assert len(state['style_profiles']) == 1


@pytest.mark.parametrize('route', ['oneshot', 'plan'])
def test_style_change_during_model_generation_stops_manuscript_publication(monkeypatch, tmp_path, route):
    from test_author_ui import configure_provider, provider_stub

    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.style_commit import commit_style_bundle

    at = run_app(monkeypatch, tmp_path)
    provider_stub(monkeypatch)
    original_chat = OpenAICompatibleProvider.chat
    store = ProjectStore(tmp_path / 'data')
    changed = []

    def concurrent_update(self, messages, **kwargs):
        result = original_chat(self, messages, **kwargs)
        if '章节策划' not in messages[0]['content'] and not changed:
            snapshot = load_style_bundle(store, 'MyNovel')
            files = prepare_style_addition(snapshot, {'name': 'Other session', 'weight': 1.0,
                                          'fingerprint': analyze_style(TEXT).model_dump()}, build_reference_signature(TEXT))
            commit_style_bundle(store, 'MyNovel', files=files, expected_before=snapshot['sha256'], request_id='f' * 32)
            changed.append(True)
        return result

    monkeypatch.setattr(OpenAICompatibleProvider, 'chat', concurrent_update)
    configure_provider(at)
    if route == 'plan':
        at.button(key='btn_plan').click().run()
        assert not at.exception
    at.button(key='btn_oneshot' if route == 'oneshot' else 'btn_draft').click().run()
    assert changed and at.exception
    assert not list((store.project_dir('MyNovel') / 'chapters').glob('*.md'))
    assert len(load_style_bundle(store, 'MyNovel')['profiles']) == 1
