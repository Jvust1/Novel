"""Independent synthetic review of persisted sources and hidden-widget recovery.

All HTTP responses are local MockTransport responses or explicit offline stubs.
No real model, author material, external service, or private account is used.
"""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from test_memory_ui import accept
from test_memory_ui import fixture as memory_fixture

from novel_ai.author_workflow import outline_digest
from novel_ai.provider import OpenAICompatibleProvider
from novel_ai.storage import ProjectStore
from novel_ai.style_commit import (
    commit_style_bundle,
    load_style_bundle,
    prepare_style_addition,
)
from novel_ai.style_engine import analyze_style, build_reference_signature

APP = Path(__file__).resolve().parents[1] / 'app.py'
SAMPLE = '韩叶在旧钟楼找到一张空白纸条。她把纸条折好，放回木匣里。门外的脚步停了，随后又向下走去。' * 20

@pytest.mark.parametrize("route", ["immediate_refresh", "retry", "delayed_refresh"])
def test_failed_style_save_does_not_discard_unsaved_writing_edits(monkeypatch, tmp_path, route):
    monkeypatch.chdir(tmp_path)
    calls = []
    def offline(self, messages, **kwargs):
        calls.append(messages)
        return json.dumps({'chapter_title': '钟楼', 'chapter_promise': '核对纸条', 'scenes': []}, ensure_ascii=False)
    monkeypatch.setattr(OpenAICompatibleProvider, 'chat', offline)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    next(x for x in at.text_input if x.label == 'Base URL').set_value('http://offline.invalid')
    next(x for x in at.text_input if x.label == 'Model').set_value('synthetic')
    at.text_input(key='chapter_id').set_value('009')
    at.text_area(key='chapter_goal').set_value('独立的待写目标，尚未保存')
    at.text_area(key='chapter_notes').set_value('作者补充：不揭晓寄信人')
    at.button(key='btn_plan').click().run()
    assert not at.exception and len(calls) == 1
    edited = json.loads(at.text_area(key='plan_editor').value)
    edited['chapter_promise'] = '作者已手工改成只查看纸条，不拆封木匣'
    edited = json.dumps(edited, ensure_ascii=False)
    at.text_area(key='plan_editor').set_value(edited).run()
    before = {key: at.session_state[key] for key in ['chapter_id', 'chapter_goal', 'chapter_notes', 'plan_editor']}
    next(x for x in at.checkbox if x.label == '使用当前模型做语义文体分析').uncheck()
    next(x for x in at.text_area if x.label == '或粘贴参考文本').set_value(SAMPLE)
    original = ProjectStore._write
    failing = [True]
    def interrupted(self, path, content, **kwargs):
        if failing[0] and path.name == 'style_dna.json':
            raise OSError('synthetic second-file interruption')
        return original(self, path, content, **kwargs)
    monkeypatch.setattr(ProjectStore, '_write', interrupted)
    next(x for x in at.button if x.label == '分析并加入风格库').click().run()
    assert at.error and at.session_state['style_pending'] is not None
    failing[0] = False
    if route in {'retry', 'delayed_refresh'}:
        at.run()
    at.button(key='retry_style_save' if route == 'retry' else 'reload_saved_style').click().run()
    assert not at.exception
    after = {key: at.session_state[key] for key in before}
    assert after == before



MEMORY_SAMPLE = '江竹发现所有借书卡都缺了最后一行。她没有向管理员追问，只把借书日期抄进了小册子。窗外天色渐暗，门铃突然响了一声。' * 20

@pytest.mark.parametrize('route', ['saved', 'retry', 'refresh'])
def test_style_transition_keeps_old_memory_confirmation_from_writing(monkeypatch, tmp_path, route):
    at, store, calls, cards = memory_fixture(monkeypatch, tmp_path)
    at.button(key='btn_memory_propose').click().run()
    assert not at.exception and len(calls) == 1
    proposal = at.session_state['memory_candidate_json']
    next(x for x in at.checkbox if x.label == '我接受这一版正文作为记忆来源').check().run()
    next(x for x in at.checkbox if x.label == '我已查看并接受这份记忆变更').check().run()
    next(x for x in at.checkbox if x.label == '使用当前模型做语义文体分析').uncheck()
    next(x for x in at.text_area if x.label == '或粘贴参考文本').set_value(MEMORY_SAMPLE)
    original = ProjectStore._write
    failing = [route != 'saved']
    def interrupted(self, path, content, **kwargs):
        if failing[0] and path.name == 'style_dna.json':
            raise OSError('synthetic second-file interruption')
        return original(self, path, content, **kwargs)
    monkeypatch.setattr(ProjectStore, '_write', interrupted)
    next(x for x in at.button if x.label == '分析并加入风格库').click().run()
    if route != 'saved':
        assert at.error and at.session_state['style_pending'] is not None
        failing[0] = False
        at.run()
        at.button(key='retry_style_save' if route == 'retry' else 'reload_saved_style').click().run()
    assert not at.exception
    assert at.session_state['memory_candidate_json'] == proposal
    before = {p.relative_to(store.root).as_posix(): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    accept(at)
    assert at.exception and 'context changed' in str(at.exception[0].message)
    after = {p.relative_to(store.root).as_posix(): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert before == after
    assert store.read_json('MyNovel', 'memory/characters.json') == cards
    assert len(calls) == 1


# All transport responses below are served in-process by httpx.MockTransport.
# The public provider's guard, format fallback and response handling still run.



OUTLINE = '''# 刻钟房
每个钟表必须有真实出处
## 雨季
所有钟表都留在馆内
### 借物线
用收据核对寄存物
#### 空白收据
韩叶寻找收据缺失的一行
##### 柜台
韩叶询问值班员
'''
PLAN = {
    'chapter_title': '空白收据', 'chapter_promise': '核对收据',
    'scenes': [{'scene_no': 1, 'pov': '韩叶', 'objective': '核对日期', 'opposition': '字迹褪色',
                'choice': '询问值班员', 'cost': '错过末班车', 'state_change': '确认寄存日期'}],
}
PROSE = '韩叶把收据递到柜台里。值班员指着模糊的日期，她记下来，听见末班车从街角驶过。'


def _button(at, label):
    return next(item for item in at.button if item.label == label)


def _configure(at):
    next(item for item in at.text_input if item.label == 'Base URL').set_value('http://synthetic.invalid/v1')
    next(item for item in at.text_input if item.label == 'Model').set_value('offline-only')
    at.radio[0].set_value('快速草稿')


def _wire(monkeypatch, callback=None):
    calls = []
    original = httpx.Client

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if callback is not None:
            response = callback(payload, len(calls))
            if response is not None:
                return response
        system = payload['messages'][0]['content']
        text = json.dumps(PLAN, ensure_ascii=False) if '章节策划' in system else PROSE
        return httpx.Response(200, json={'choices': [
            {'message': {'content': text}, 'finish_reason': 'stop'},
        ]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return calls


def _bound_workspace(monkeypatch, tmp_path, *, callback=None):
    monkeypatch.chdir(tmp_path)
    calls = _wire(monkeypatch, callback)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.text_area(key='hierarchy_markdown').set_value(OUTLINE)
    at.button(key='btn_parse_hierarchy').click().run()
    at.button(key='btn_save_hierarchy').click().run()
    assert not at.exception and not at.error
    at.text_input(key='hierarchy_target_id').set_value('007')
    at.button(key='btn_load_hierarchy').click().run()
    _configure(at)
    at.button(key='btn_plan').click().run()
    assert not at.exception and len(calls) == 1
    return at, ProjectStore(tmp_path / 'data'), calls


def _change_outline(store, *, project='MyNovel', promise='作者更新：本章只检查门外收据，不进刻钟房'):
    changed = store.read_json(project, 'memory/hierarchical_outline.json')
    changed['premise'] = promise
    store.write_json(project, 'memory/hierarchical_outline.json', changed)
    return changed


def _change_style(store, *, project='MyNovel'):
    snapshot = load_style_bundle(store, project)
    files = prepare_style_addition(snapshot, {
        'name': '另一次原创参考', 'weight': 1.0,
        'fingerprint': analyze_style(SAMPLE).model_dump(),
    }, build_reference_signature(SAMPLE))
    return commit_style_bundle(store, project, files=files,
        expected_before=snapshot['sha256'], request_id=uuid4().hex)


@pytest.mark.parametrize('action', ['btn_plan', 'btn_draft', 'btn_oneshot', 'btn_load_hierarchy'])
def test_saved_outline_change_cannot_be_unblocked_by_style_refresh(monkeypatch, tmp_path, action):
    at, store, calls = _bound_workspace(monkeypatch, tmp_path)
    saved_plan = at.text_area(key='plan_editor').value
    original_binding = deepcopy(at.session_state['pending_plan_meta'])
    updated = _change_outline(store)
    _change_style(store)
    at.run()
    assert at.error and len(calls) == 1
    at.button(key='reload_saved_style').click().run()
    assert not at.exception
    assert at.text_area(key='plan_editor').value == saved_plan
    assert at.session_state['pending_plan_meta'] == original_binding
    _configure(at)
    at.button(key=action).click().run()
    assert at.exception or at.error
    assert len(calls) == 1
    assert store.all_chapter_texts('MyNovel') == []
    assert store.read_json('MyNovel', 'memory/hierarchical_outline.json') == updated


@pytest.mark.parametrize('damage', ['deleted', 'invalid_json', 'wrong_shape', 'invalid_outline'])
@pytest.mark.parametrize('action', ['btn_draft', 'btn_load_hierarchy'])
def test_missing_or_damaged_saved_outline_never_uses_cached_copy(monkeypatch, tmp_path, damage, action):
    at, store, calls = _bound_workspace(monkeypatch, tmp_path)
    root = store.project_dir('MyNovel')
    path = root / 'memory/hierarchical_outline.json'
    old_editor = at.text_area(key='hierarchy_editor').value
    if damage == 'deleted':
        path.unlink()
        changed_bytes = None
    elif damage == 'invalid_json':
        path.write_text('{"unfinished":', encoding='utf-8')
        changed_bytes = path.read_bytes()
    else:
        store.write_json('MyNovel', 'memory/hierarchical_outline.json', [] if damage == 'wrong_shape' else {'root': {}})
        changed_bytes = path.read_bytes()
    at.button(key=action).click().run()
    assert at.exception or at.error
    assert len(calls) == 1 and store.all_chapter_texts('MyNovel') == []
    at.button(key='btn_reload_hierarchy').click().run()
    assert at.error
    assert at.text_area(key='hierarchy_editor').value == old_editor
    assert (path.read_bytes() if path.exists() else None) == changed_bytes


def test_second_session_save_cannot_be_overwritten_and_reload_keeps_author_edits(monkeypatch, tmp_path):
    first, store, calls = _bound_workspace(monkeypatch, tmp_path)
    second = AppTest.from_file(str(APP), default_timeout=30).run()
    first_editor = json.loads(first.text_area(key='hierarchy_editor').value)
    first_editor['premise'] = 'A的未保存手工编辑'
    first_text = json.dumps(first_editor, ensure_ascii=False)
    first.text_area(key='hierarchy_editor').set_value(first_text).run()
    edited_plan = json.loads(first.text_area(key='plan_editor').value)
    edited_plan['chapter_promise'] = 'A的未确认计划修改'
    plan_text = json.dumps(edited_plan, ensure_ascii=False)
    first.text_area(key='plan_editor').set_value(plan_text).run()
    old_pending = first.session_state['pending_plan_json']
    old_meta = deepcopy(first.session_state['pending_plan_meta'])
    second_editor = json.loads(second.text_area(key='hierarchy_editor').value)
    second_editor['premise'] = 'B已保存的新来源'
    second.text_area(key='hierarchy_editor').set_value(json.dumps(second_editor, ensure_ascii=False))
    second.button(key='btn_save_hierarchy').click().run()
    assert not second.error and not second.exception
    current_bytes = (store.project_dir('MyNovel') / 'memory/hierarchical_outline.json').read_bytes()
    first.button(key='btn_save_hierarchy').click().run()
    assert first.error and '其他会话' in first.error[0].value
    assert (store.project_dir('MyNovel') / 'memory/hierarchical_outline.json').read_bytes() == current_bytes
    assert first.text_area(key='hierarchy_editor').value == first_text
    first.button(key='btn_reload_hierarchy').click().run()
    assert not first.exception
    assert first.session_state['hierarchy_data']['premise'] == second_editor['premise']
    assert first.text_area(key='hierarchy_editor').value == first_text
    assert first.text_area(key='plan_editor').value == plan_text
    assert first.session_state['pending_plan_json'] == old_pending
    assert first.session_state['pending_plan_meta'] == old_meta
    first.button(key='btn_draft').click().run()
    assert first.exception and len(calls) == 1
    first.text_input(key='hierarchy_target_id').set_value('007')
    first.button(key='btn_load_hierarchy').click().run()
    assert not first.exception
    assert first.session_state['pending_plan_meta']['outline_sha256'] == outline_digest(second_editor)
    assert first.text_area(key='plan_editor').value != plan_text
    assert first.session_state['last_result'] is None
    assert len(calls) == 1 and store.all_chapter_texts('MyNovel') == []


def test_preserved_hidden_fields_remain_project_scoped(monkeypatch, tmp_path):
    at, store, calls = _bound_workspace(monkeypatch, tmp_path)
    edited = json.loads(at.text_area(key='plan_editor').value)
    edited['chapter_promise'] = 'A尚未保存的计划'
    edited = json.dumps(edited, ensure_ascii=False)
    at.text_area(key='plan_editor').set_value(edited)
    at.text_area(key='chapter_goal').set_value('A未保存目标').run()
    at.text_input(key='new_char_name').set_value('A的未保存人物')
    _button(at, '添加人物').click().run()
    saved_cards = deepcopy(at.session_state['characters'])
    assert store.read_json('MyNovel', 'memory/characters.json', []) == []
    _change_style(store)
    at.run()
    assert at.error
    at.text_input(key='project_name').set_value('OtherBook').run()
    assert not at.exception
    assert at.session_state['pending_plan_json'] == ''
    assert at.session_state['characters'] == []
    assert at.text_input(key='new_char_name').value == ''
    assert at.text_area(key='chapter_goal').value == ''
    at.text_area(key='chapter_goal').set_value('B独立未保存目标').run()
    at.text_input(key='project_name').set_value('MyNovel').run()
    assert not at.exception
    assert at.text_area(key='plan_editor').value == edited
    assert at.session_state['characters'] == saved_cards
    assert at.text_input(key='new_char_name').value == 'A的未保存人物'
    assert at.text_area(key='chapter_goal').value == 'A未保存目标'
    assert at.text_input(key='chapter_id').value == '007'
    at.text_input(key='project_name').set_value('OtherBook').run()
    assert at.text_area(key='chapter_goal').value == 'B独立未保存目标'
    assert len(calls) == 1
    assert store.all_chapter_texts('MyNovel') == store.all_chapter_texts('OtherBook') == []


@pytest.mark.parametrize('action', ['btn_plan', 'btn_draft', 'btn_oneshot'])
@pytest.mark.parametrize('update_live_cache', [False, True])
def test_guard_retains_original_source_snapshot_during_actual_response(monkeypatch, tmp_path, action, update_live_cache):
    holder = {}
    armed = [False]

    def change(_payload, _count):
        if armed[0]:
            armed[0] = False
            changed = _change_outline(holder['store'])
            if update_live_cache:
                st.session_state.hierarchy_data = changed
                st.session_state.pending_plan_meta['outline_sha256'] = outline_digest(changed)

    at, store, calls = _bound_workspace(monkeypatch, tmp_path, callback=change)
    holder['store'] = store
    original_plan = at.session_state['pending_plan_json']
    armed[0] = True
    at.button(key=action).click().run()
    assert at.exception and len(calls) == 2
    assert store.all_chapter_texts('MyNovel') == []
    assert at.session_state['last_result'] is None
    assert at.session_state['pending_plan_json'] == original_plan


@pytest.mark.parametrize('when', ['first_response', 'between_attempts'])
def test_format_fallback_cannot_send_after_bound_outline_changes(monkeypatch, tmp_path, when):
    holder = {}
    armed = [False]

    class ChangeOnClose(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps({'error': {'param': 'response_format', 'code': 'unsupported_parameter',
                'message': 'response_format is not supported'}}).encode()

        def close(self):
            _change_outline(holder['store'])

    def fallback(_payload, _count):
        if not armed[0]:
            return None
        armed[0] = False
        if when == 'between_attempts':
            return httpx.Response(400, stream=ChangeOnClose())
        _change_outline(holder['store'])
        return httpx.Response(400, json={'error': {'param': 'response_format',
            'code': 'unsupported_parameter', 'message': 'response_format is not supported'}})

    at, store, calls = _bound_workspace(monkeypatch, tmp_path, callback=fallback)
    holder['store'] = store
    armed[0] = True
    old_plan = at.session_state['pending_plan_json']
    at.button(key='btn_plan').click().run()
    assert at.exception and len(calls) == 2
    assert 'response_format' in calls[-1]
    assert at.session_state['pending_plan_json'] == old_plan
    assert store.all_chapter_texts('MyNovel') == []


@pytest.mark.parametrize('route', ['btn_draft', 'btn_oneshot'])
@pytest.mark.parametrize('refresh_live_cache', [False, True])
def test_saved_source_rechecked_after_last_response_before_publication(monkeypatch, tmp_path, route, refresh_live_cache):
    from novel_ai import style_engine

    at, store, calls = _bound_workspace(monkeypatch, tmp_path)
    original = style_engine.reference_overlap
    changes = []

    def change_after_generation(*args, **kwargs):
        value = original(*args, **kwargs)
        changed = _change_outline(store)
        changes.append(changed)
        if refresh_live_cache:
            st.session_state.hierarchy_data = changed
            st.session_state.pending_plan_meta['outline_sha256'] = outline_digest(changed)
        return value

    monkeypatch.setattr(style_engine, 'reference_overlap', change_after_generation)
    at.button(key=route).click().run()
    assert changes and at.exception
    assert len(calls) == (2 if route == 'btn_draft' else 3)
    assert store.all_chapter_texts('MyNovel') == []
    assert at.session_state['last_result'] is None
