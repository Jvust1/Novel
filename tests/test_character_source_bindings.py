"""Actual offline HTTP stages freeze the current local character source."""
import json
from copy import deepcopy

import httpx
import pytest
from test_author_ui import configure_provider, run_app

from novel_ai.storage import ProjectStore

OLD = [{'name': '赵苔', 'speech': '只说简短陈述，不推测未知事项。', 'locked': False}]
NEW = [{'name': '赵苔', 'speech': '先提问题，再解释完整理由。', 'locked': True}]
PLAN = {'chapter_title': '雨棚', 'scenes': [{'scene_no': 1, 'pov': '赵苔',
    'objective': '归还量尺', 'opposition': '工匠不在', 'choice': '等待',
    'cost': '错过渡船', 'state_change': '收到留言'}]}
PROSE = '赵苔把量尺放在长凳上。她抖落袖口的水，坐下等工匠回来。'


def offline(monkeypatch, tmp_path, changed_stage=None):
    store = ProjectStore(tmp_path / 'data')
    store.write_json('MyNovel', 'memory/characters.json', OLD)
    calls = []
    review_calls = []
    client = httpx.Client

    def serve(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == changed_stage:
            store.write_json('MyNovel', 'memory/characters.json', NEW)
        system = payload['messages'][0]['content']
        if '章节策划' in system:
            text = json.dumps(PLAN, ensure_ascii=False)
        elif '严苛的网络小说章节编辑' in system:
            review_calls.append(payload)
            text = json.dumps({'verdict': 'revise' if len(review_calls) == 1 else 'pass', 'issues': []})
        else:
            text = PROSE
        return httpx.Response(200, json={'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})

    monkeypatch.setattr(httpx, 'Client', lambda **kw: client(**kw, transport=httpx.MockTransport(serve)))
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.radio[0].set_value('精修')
    return at, store, calls


@pytest.mark.parametrize('stage', [1, 2, 3, 4, 5], ids=['plan', 'draft', 'review', 'repair', 'rereview'])
def test_saved_character_change_stops_each_actual_http_stage(monkeypatch, tmp_path, stage):
    at, store, calls = offline(monkeypatch, tmp_path, stage)
    at.button(key='btn_oneshot').click().run()
    assert at.exception or at.error
    assert len(calls) == stage
    assert store.all_chapter_texts('MyNovel') == []
    assert store.read_json('MyNovel', 'memory/characters.json') == NEW
    assert at.session_state['characters'] == OLD
    assert at.session_state['last_result'] is None
    assert not (store.project_dir('MyNovel') / 'memory/commits').exists()


def test_final_locked_publication_rechecks_character_source(monkeypatch, tmp_path):
    import novel_ai.longform_tools as longform
    at, store, calls = offline(monkeypatch, tmp_path)
    original = longform.near_duplicate_chapters

    def changed_after_result(*args, **kwargs):
        result = original(*args, **kwargs)
        store.write_json('MyNovel', 'memory/characters.json', NEW)
        return result

    monkeypatch.setattr(longform, 'near_duplicate_chapters', changed_after_result)
    at.button(key='btn_oneshot').click().run()
    assert len(calls) == 5
    assert at.exception or at.error
    assert not store.all_chapter_texts('MyNovel')
    assert at.session_state['last_result'] is None
    assert at.session_state['characters'] == OLD
    assert store.read_json('MyNovel', 'memory/characters.json') == NEW


def test_local_character_edit_invalidates_old_plan_but_explicit_replan_is_possible(monkeypatch, tmp_path):
    at, store, calls = offline(monkeypatch, tmp_path)
    at.radio[0].set_value('快速草稿')
    at.button(key='btn_plan').click().run()
    assert not at.exception and len(calls) == 1
    old_plan = at.session_state['pending_plan_json']
    changed = deepcopy(at.session_state['characters'])
    changed[0]['speech'] = '作者本会话未保存的新说话方式。'
    at.session_state['characters'] = changed
    at.button(key='btn_draft').click().run()
    assert at.exception and len(calls) == 1
    assert at.session_state['pending_plan_json'] == old_plan
    assert at.session_state['characters'] == changed
    at.button(key='btn_plan').click().run()
    assert not at.exception and len(calls) == 2
    at.button(key='btn_draft').click().run()
    assert not at.exception and len(calls) == 3
    assert changed[0]['speech'] in json.dumps(calls[-1], ensure_ascii=False)
    assert len(store.all_chapter_texts('MyNovel')) == 1
    assert store.read_json('MyNovel', 'memory/characters.json') == OLD
