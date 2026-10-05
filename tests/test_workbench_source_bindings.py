"""Original synthetic AppTest and actual offline HTTP source-binding regressions."""
import json

import httpx
import pytest
from test_author_ui import configure_provider, import_outline, provider_stub, run_app

from novel_ai.storage import ProjectStore
from novel_ai.style_commit import (
    commit_style_bundle,
    load_style_bundle,
    prepare_style_addition,
)
from novel_ai.style_engine import analyze_style, build_reference_signature


def test_new_saved_outline_is_not_bypassed_by_refreshing_style(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    first = import_outline(run_app(monkeypatch, tmp_path))
    first.text_input(key='hierarchy_target_id').set_value('001')
    first.button(key='btn_load_hierarchy').click().run()
    configure_provider(first)
    first.button(key='btn_plan').click().run()
    assert not first.exception and len(calls) == 1

    second = run_app(monkeypatch, tmp_path)
    current = json.loads(second.text_area(key='hierarchy_editor').value)
    current['premise'] = '独立作者变更：灯塔已经拆除，本章不得再次进入旧灯室。'
    second.text_area(key='hierarchy_editor').set_value(json.dumps(current, ensure_ascii=False))
    second.button(key='btn_save_hierarchy').click().run()
    assert not second.exception

    store = ProjectStore(tmp_path / 'data')
    old = load_style_bundle(store, 'MyNovel')
    sample = '叶宁将旧铜牌交还门房。雨停了，她绕过已经封死的长廊，去桥头等船。' * 20
    files = prepare_style_addition(old, {'name': '新的原创参考', 'weight': 1.0,
        'fingerprint': analyze_style(sample).model_dump()}, build_reference_signature(sample))
    commit_style_bundle(store, 'MyNovel', files=files, expected_before=old['sha256'], request_id='b' * 32)

    first.run()
    assert first.error and len(calls) == 1  # Existing style guard correctly blocks the stale view.
    first.button(key='reload_saved_style').click().run()
    assert not first.exception and len(first.session_state['style_profiles']) == 1
    configure_provider(first)  # Early st.stop removed later widgets; explicitly choose offline quick-draft mode again.
    first.button(key='btn_draft').click().run()
    assert store.read_json('MyNovel', 'memory/hierarchical_outline.json')['premise'] == current['premise']
    # The saved outline changed, so the existing documented plan binding must refuse.
    # Old editable plan may be retained, but should not silently dispatch as current.
    assert len(calls) == 1, {
        'calls': len(calls), 'exception': [str(x.message) for x in first.exception],
        'stale_prompt_contains_new_premise': current['premise'] in calls[-1][-1]['content'],
        'saved_chapters': [x[0] for x in store.all_chapter_texts('MyNovel')],
    }

    # Refresh is read-only: preserve both editable JSON and the old pending plan.
    editor_before = first.text_area(key='hierarchy_editor').value
    plan_before = first.session_state['pending_plan_json']
    first.button(key='btn_reload_hierarchy').click().run()
    assert first.text_area(key='hierarchy_editor').value == editor_before
    assert first.session_state['pending_plan_json'] == plan_before
    assert first.session_state['hierarchy_data']['premise'] == current['premise']
    first.button(key='btn_draft').click().run()
    assert len(calls) == 1 and first.exception
    first.button(key='btn_load_hierarchy').click().run()
    configure_provider(first)
    first.button(key='btn_plan').click().run()
    assert not first.exception and current['premise'] in calls[-1][-1]['content']
    first.button(key='btn_draft').click().run()
    assert not first.exception and len(calls) == 3
    assert current['premise'] in calls[-1][-1]['content']
    assert len(store.all_chapter_texts('MyNovel')) == 1
    assert store.read_json('MyNovel', 'memory/hierarchical_outline.json') == current


@pytest.mark.parametrize('changed', ['outline', 'style'])
@pytest.mark.parametrize('stage', [1, 2, 3, 4, 5], ids=['plan', 'draft', 'review', 'repair', 'rereview'])
def test_actual_http_stages_stop_on_changed_saved_source(monkeypatch, tmp_path, changed, stage):
    calls = []
    review_count = 0
    store = ProjectStore(tmp_path / 'data')

    def serve(request):
        nonlocal review_count
        calls.append(request)
        system = json.loads(request.content)['messages'][0]['content']
        if len(calls) == stage:
            if changed == 'outline':
                actual = store.read_json('MyNovel', 'memory/hierarchical_outline.json')
                actual['premise'] = '当前保存的新设定：桥已拆除，旧路径不再存在。'
                store.write_json('MyNovel', 'memory/hierarchical_outline.json', actual)
            else:
                snapshot = load_style_bundle(store, 'MyNovel')
                sample = '闻舟把借据放回桌上。对方没有伸手，他便将窗推开一道缝。' * 20
                files = prepare_style_addition(snapshot, {'name': '新文风', 'weight': 1.0,
                    'fingerprint': analyze_style(sample).model_dump()}, build_reference_signature(sample))
                commit_style_bundle(store, 'MyNovel', files=files, expected_before=snapshot['sha256'], request_id='a' * 32)
        if '章节策划' in system:
            text = json.dumps({'chapter_title': '桥头', 'scenes': [{
                'scene_no': 1, 'objective': '核对渡船', 'opposition': '河水上涨',
                'choice': '向守桥人求助', 'cost': '留下行李', 'state_change': '取得渡船钥匙'}]}, ensure_ascii=False)
        elif '严苛的网络小说章节编辑' in system:
            review_count += 1
            text = json.dumps({'verdict': 'revise' if review_count == 1 else 'pass', 'issues': []})
        else:
            text = '闻舟把行李交给守桥人，接过钥匙，沿着石阶走向河岸。'
        return httpx.Response(200, json={'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})

    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(serve)))
    at = import_outline(run_app(monkeypatch, tmp_path))
    at.text_input(key='hierarchy_target_id').set_value('009')
    at.button(key='btn_load_hierarchy').click().run()
    before_plan = at.session_state['pending_plan_json']
    configure_provider(at)
    at.radio[0].set_value('精修')
    at.button(key='btn_oneshot').click().run()
    assert at.exception or at.error
    assert len(calls) == stage
    assert not store.all_chapter_texts('MyNovel')
    assert at.session_state['pending_plan_json'] == before_plan
    assert at.session_state['last_result'] is None
