from copy import deepcopy

from novel_ai.context import ContextAssembler
from novel_ai.project_session import switch_project
from novel_ai.storage import ProjectStore


def test_project_cache_isolates_drafts_and_preserves_unsaved_work(tmp_path):
    store = ProjectStore(tmp_path)
    store.write_json('B', 'memory/characters.json', [{'name': 'OnlyB'}])
    store.write_json('B', 'memory/story_bible.json', {'title': 'BookB'})
    state = {'api_key': 'synthetic-not-a-real-key'}
    switch_project(state, store, 'A')
    state.update(characters=[{'name': 'OnlyA'}], pending_plan_json='A plan',
                 pending_plan_meta={'extra': 'A history'}, last_result={'draft': 'A draft'},
                 chapter_goal='A goal', chapter_id='007', reference_hashes={'a-hash'},
                 last_self_similarity=[{'chapter_id': '006'}], diverse_recall=True)
    switch_project(state, store, 'B')
    assert state['title'] == 'BookB'
    assert state['characters'] == [{'name': 'OnlyB'}]
    assert state['pending_plan_json'] == '' and state['last_result'] is None
    assert state['reference_hashes'] == set()
    assert state['last_self_similarity'] == []
    assert state['diverse_recall'] is False
    assert 'api_key' not in state['_project_drafts']['A']
    state['characters'][0]['name'] = 'EditedB'
    switch_project(state, store, 'A')
    assert state['characters'] == [{'name': 'OnlyA'}]
    assert state['chapter_goal'] == 'A goal'
    assert state['chapter_id'] == '007'
    assert state['pending_plan_meta'] == {'extra': 'A history'}
    assert state['last_result'] == {'draft': 'A draft'}
    assert state['diverse_recall'] is True
    assert store.read_json('A', 'memory/characters.json') is None
    # Cache and restored current state must not share nested mutable objects.
    state['characters'][0]['name'] = 'EditedA'
    assert state['_project_drafts']['A']['characters'][0]['name'] == 'OnlyA'


def test_same_project_does_not_reset_active_edits(tmp_path):
    state = {}
    store = ProjectStore(tmp_path)
    switch_project(state, store, 'P')
    state['characters'] = [{'name': 'Unsaved'}]
    before = deepcopy(state)
    switch_project(state, store, 'P')
    assert state == before


def test_editing_old_summary_preserves_actual_recent_memory(tmp_path):
    store = ProjectStore(tmp_path)
    for chapter in ['001', '002', '003', '004', '005', '006']:
        store.save_extraction('P', {'chapter_id': chapter, 'summary': f'{chapter}章仓库钥匙在沈青手里。'})
    store.save_extraction('P', {'chapter_id': '001', 'summary': '仓库钥匙留在沈青家里。'})
    assert [row['chapter_id'] for row in store.all_chapter_summaries('P')] == ['001', '002', '003', '004', '005', '006']
    context = ContextAssembler(store, 'P').assemble(recent_limit=2, recall_query='沈青家里的仓库钥匙')
    assert [row['chapter_id'] for row in context.recent_summaries] == ['005', '006']
    assert '001' in context.recall_report['included_chapter_ids']
    assert '仓库钥匙留在沈青家里' in context.recall_block


def test_old_duplicate_summary_rows_are_collapsed_in_place(tmp_path):
    store = ProjectStore(tmp_path)
    for chapter in ['001', '002', '001', '003']:
        store.append_jsonl('P', 'memory/chapter_summaries.jsonl', {'chapter_id': chapter, 'summary': '原摘要'})
    store.save_extraction('P', {'chapter_id': '001', 'summary': '新摘要'})
    rows = store.all_chapter_summaries('P')
    assert [row['chapter_id'] for row in rows] == ['001', '002', '003']
    assert rows[0]['summary'] == '新摘要'
    assert store.recent_chapter_summaries('P', 0) == []
    assert store.recent_chapter_summaries('P', -1) == []


def test_failed_target_load_keeps_current_book_and_unsaved_drafts(tmp_path):
    import pytest
    store = ProjectStore(tmp_path)
    state = {}
    switch_project(state, store, 'A')
    state.update(characters=[{'name': 'UnsavedA'}], pending_plan_json='unsaved plan')
    before = deepcopy(state)
    broken = store.project_dir('Broken') / 'memory/story_bible.json'
    broken.write_text('{broken JSON', encoding='utf-8')
    with pytest.raises(ValueError):
        switch_project(state, store, 'Broken')
    assert {key: value for key, value in state.items() if not key.startswith('_')} == {
        key: value for key, value in before.items() if not key.startswith('_')
    }
    switch_project(state, store, 'A')
    assert state['characters'] == [{'name': 'UnsavedA'}]
    assert state['pending_plan_json'] == 'unsaved plan'


def test_blank_project_name_keeps_its_draft_when_switching(tmp_path):
    store = ProjectStore(tmp_path)
    state = {}
    switch_project(state, store, '')
    state.update(chapter_goal='空白项目的未保存目标', characters=[{'name': 'BlankBook'}])
    switch_project(state, store, 'B')
    switch_project(state, store, '')
    assert state['chapter_goal'] == '空白项目的未保存目标'
    assert state['characters'] == [{'name': 'BlankBook'}]
