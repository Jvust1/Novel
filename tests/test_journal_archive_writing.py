"""Original synthetic author amendments through real, mocked journal continuation."""
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from novel_ai import accepted_writing as writing
from novel_ai import gpt_story_journal as journal
from novel_ai import gpt_story_state as state
from novel_ai.request_budget import RequestBudgetExceeded, RequestBudgetLimits
from test_accepted_archive_writing import PLAN, art, digest, ready_archive, session
from test_gpt_story_journal import (
    accept_proposal, chapter_confirmation, confirm, propose, reconcile, review,
    story as journal_story,
)

STYLE = {'genre': 'fantasy', 'distance': 'close', 'optional': {'rhythm': 'varied'},
         'character_voice': {'林青': 'short declarative speech'}, 'custom_marker': 'keep_journal_style_marker'}


def save_load(path, value):
    old_sha = digest(path) if path.exists() else None
    saved = journal.save_journal(path, value, expected_disk_sha256=old_sha)
    return journal.load_journal(path, expected_story_id='synthetic-story', expected_sha256=saved['sha256'])


def identity(path, value):
    projection = journal.project_journal(value)
    return {'expected_story_id': value.story_id, 'expected_revision': projection.story['revision'],
            'expected_context_revision': projection.context_revision,
            'expected_journal_sha256': journal.journal_fingerprint(value), 'expected_file_sha256': digest(path)}


def restore(path):
    value = journal.load_journal(path, expected_story_id='synthetic-story')
    return writing.restore_journal_source(path, **identity(path, value))


def replan(path, value):
    value = save_load(path, value)
    plan = deepcopy(PLAN)
    plan['chapter_title'] = 'An original journal continuation'
    plan['must_not_happen'] = ['不可让林青凭空知道门后人的姓名']
    value = journal_story(value, 'set_plan', {'artifact': art(json.dumps(plan, ensure_ascii=False), 'journal-current-plan').model_dump(mode='json')})
    value = journal_story(value, 'accept_plan', {'confirmation': chapter_confirmation(value, 'plan')})
    return save_load(path, value)


def journal_ready(tmp_path, *, stage='ready', new_style=STYLE):
    v1_path = ready_archive(tmp_path)
    value = state.load_state(v1_path, expected_story_id='synthetic-story')
    origin = art(value.model_dump_json(), 'actual-migration-origin')
    value = journal.migrate_state(origin, confirm({'scope': 'migrate', 'story_id': value.story_id,
        'origin_source_fingerprint': state.source_fingerprint(origin)}))
    path = tmp_path / 'private-author-journal.json'
    value = save_load(path, value)
    if stage == 'migrated':
        return path, value
    value = propose(value, deepcopy(new_style))
    if stage == 'proposal':
        return path, save_load(path, value)
    value = accept_proposal(value)
    if stage == 'accepted':
        return path, save_load(path, value)
    if stage in {'partial_review', 'requires_revision'}:
        value = review(value, 'chapter:ch-1')
        if stage == 'requires_revision':
            value = review(value, 'derived_context', 'requires_revision')
        return path, save_load(path, value)
    value = reconcile(value)
    if stage == 'reconciled_unsaved':
        return path, value
    if stage == 'reconciled':
        return path, save_load(path, value)
    return path, replan(path, value)


def test_reconciled_owned_journal_drives_four_stages_with_existing_budget(tmp_path, monkeypatch):
    path, value = journal_ready(tmp_path); source = restore(path)
    before = path.read_bytes(); events = deepcopy(value.events)
    flow, calls = session(monkeypatch)
    result = flow.run_from_accepted_archive(source, current_chapter_id='ch-2', auto_repair=True,
        required_chapter_ids=['ch-1'])
    assert len(calls) == flow.budget_snapshot()['requests_reserved'] == 4
    assert result.report()['source']['source_kind'] == 'author_journal'
    assert result.report()['source']['context_revision'] == 1
    assert result.report()['history_chapter_ids'] == ['ch-1']
    for req in calls:
        text = req.content.decode()
        assert 'keep_journal_style_marker' in text and 'fantasy' in text and 'rhythm' in text
        assert '灯在门边' in text and '不可让林青凭空知道' in text
        assert '这句未接受草稿绝不进入历史' not in text
        assert source.journal_sha256 in text
    assert result.final_text == '林青把灯交给木禾，沿着空墙摸索出口。'
    assert path.read_bytes() == before and source.journal.events == events
    owned = source.state
    assert owned.journal_owner['journal_sha256'] == source.journal_sha256
    assert owned.progress.chapter_acceptance is None and owned.progress.memory_acceptance is None
    assert owned.write_receipt == {'status': 'pending'} and owned.readback_receipt == {'status': 'pending'}


@pytest.mark.parametrize('stage', ['proposal','accepted','partial_review','requires_revision'])
def test_saved_but_unreconciled_journal_never_reaches_transport(tmp_path, monkeypatch, stage):
    path, value = journal_ready(tmp_path, stage=stage); before=path.read_bytes(); flow,calls=session(monkeypatch)
    with pytest.raises(ValueError, match='pending|review'):
        source=restore(path)
        flow.run_from_accepted_archive(source,current_chapter_id='ch-2')
    assert calls==[] and path.read_bytes()==before


def test_compatible_reviews_and_resume_do_not_forge_current_readback(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path,stage='reconciled_unsaved')
    kwargs=identity(path,value)
    assert value._observed_readback is None
    value.readback_receipt={'status':'verified','journal_sha256':journal.journal_fingerprint(value),
        'file_sha256':digest(path),'location':str(path)}
    with pytest.raises(ValueError,match='actual'):
        journal.rebuild_journal_accepted_history(value,**kwargs)
    loaded=save_load(path,value)
    assert loaded._observed_readback is not None
    assert journal.rebuild_journal_accepted_history(loaded,**identity(path,loaded))['history_chapter_ids']==['ch-1']
    flow,calls=session(monkeypatch)
    with pytest.raises(ValueError,match='accepted plan|ready_to_draft'):
        flow.run_from_accepted_archive(restore(path),current_chapter_id='ch-2')
    assert calls==[]
    value=replan(path,loaded)
    result=flow.run_from_accepted_archive(restore(path),current_chapter_id='ch-2',review=False)
    assert result.final_text and len(calls)==1


@pytest.mark.parametrize('clone', ['dict','model_validate','validate_journal'])
def test_roundtripped_journal_receipts_do_not_become_live_observation(tmp_path,clone):
    path,value=journal_ready(tmp_path);args=identity(path,value)
    supplied={'dict':lambda:value.model_dump(mode='json'),
        'model_validate':lambda:journal.Journal.model_validate_json(value.model_dump_json()),
        'validate_journal':lambda:journal.validate_journal(value)}[clone]()
    with pytest.raises(ValueError,match='actual'):
        journal.rebuild_journal_accepted_history(supplied,**args)
    assert journal.rebuild_journal_accepted_history(value,**args)['readback_scope']=='actual_author_journal_envelope'


@pytest.mark.parametrize('field,bad', [('expected_story_id','different-story'),('expected_revision',0),
    ('expected_context_revision',0),('expected_revision',True),('expected_context_revision',True),
    ('expected_journal_sha256','0'*64),('expected_file_sha256','0'*64)])
def test_resume_identity_versions_cannot_be_guessed_or_coerced(tmp_path,monkeypatch,field,bad):
    path,value=journal_ready(tmp_path);args=identity(path,value);args[field]=bad;flow,calls=session(monkeypatch)
    with pytest.raises(ValueError):
        source=writing.restore_journal_source(path,**args)
        flow.run_from_accepted_archive(source,current_chapter_id='ch-2')
    assert calls==[]


@pytest.mark.parametrize('stage',[1,2,3,4])
def test_each_journal_writer_stage_checks_actual_envelope_bytes(tmp_path,monkeypatch,stage):
    path,value=journal_ready(tmp_path)
    def change(req,count):
        if count==stage:path.write_bytes(path.read_bytes()+b' ')
    flow,calls=session(monkeypatch,change)
    with pytest.raises(ValueError,match='archive'):
        flow.run_from_accepted_archive(restore(path),current_chapter_id='ch-2',auto_repair=True)
    assert len(calls)==flow.budget_snapshot()['requests_reserved']==stage
    assert flow.budget_snapshot()['attempts'][-1]['status']=='failed'


def test_journal_changes_on_format_rejection_prevent_second_send(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path)
    def change(req,count):
        if count==2:
            path.write_bytes(path.read_bytes()+b' ')
            return httpx.Response(400,json={'error':{'param':'response_format','code':'unsupported_parameter'}})
    flow,calls=session(monkeypatch,change)
    with pytest.raises(ValueError,match='archive'):
        flow.run_from_accepted_archive(restore(path),current_chapter_id='ch-2',auto_repair=True)
    assert len(calls)==2 and flow.budget_snapshot()['requests_reserved']==2


def test_candidate_only_event_keeps_native_history_but_invalidates_old_execution(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path);source=restore(path);flow,calls=session(monkeypatch)
    history=journal.rebuild_journal_accepted_history(value,**identity(path,value))
    result=flow.run_from_accepted_archive(source,current_chapter_id='ch-2',review=False)
    value=journal_story(value,'set_draft',{'artifact':art('另一个待审的原创候选','new-unaccepted-candidate').model_dump(mode='json')})
    value=save_load(path,value)
    newer=journal.rebuild_journal_accepted_history(value,**identity(path,value))
    assert newer['accepted_history_sha256']==history['accepted_history_sha256']
    assert newer['journal_binding']!=history['journal_binding']
    with pytest.raises(ValueError):result.report()
    with pytest.raises(ValueError):result.final_text
    assert restore(path).state.progress.chapter_acceptance is None


def test_exact_context_reversal_cannot_revive_an_earlier_execution_source(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path,stage='migrated');source=restore(path)
    original_style=deepcopy(source.state.style_profile)
    first_history=journal.rebuild_journal_accepted_history(value,**identity(path,value))
    flow,calls=session(monkeypatch)
    result=flow.run_from_accepted_archive(source,current_chapter_id='ch-2',review=False)
    value=replan(path,reconcile(accept_proposal(propose(value,deepcopy(STYLE)))))
    changed=journal.rebuild_journal_accepted_history(value,**identity(path,value))
    assert changed['accepted_history_sha256']!=first_history['accepted_history_sha256']
    value=replan(path,reconcile(accept_proposal(propose(value,original_style))))
    reverted=journal.rebuild_journal_accepted_history(value,**identity(path,value))
    assert reverted['accepted_history_sha256']==first_history['accepted_history_sha256']
    assert reverted['journal_binding']['context_revision']==2
    assert reverted['journal_binding']['journal_sha256']!=source.journal_sha256
    with pytest.raises(ValueError):result.report()
    assert flow.run_from_accepted_archive(restore(path),current_chapter_id='ch-2',review=False).final_text


def test_owned_views_remain_owned_and_cannot_enter_v1_write_or_preflight(tmp_path):
    path,value=journal_ready(tmp_path);source=restore(path)
    for owned in [source.state,journal.owned_story(source.journal),state.validate_state(journal.project_journal(source.journal).story)]:
        assert owned.journal_owner
        with pytest.raises(ValueError,match='journal'):state.preflight_context(owned,[],120000)
        with pytest.raises(ValueError,match='journal'):state.transition(owned,{})
        with pytest.raises(ValueError,match='journal'):state.save_state(tmp_path/'forbidden-v1.json',owned)
    assert not (tmp_path/'forbidden-v1.json').exists()
    with pytest.raises(ValueError,match='journal'):
        writing.restore_source(path,expected_story_id='synthetic-story',expected_revision=1,expected_sha256=digest(path))


def test_journal_authority_budget_is_reserved_and_never_truncates_canon(tmp_path):
    path,value=journal_ready(tmp_path);source=restore(path)
    options=dict(current_chapter_id='ch-2',history_source_limit=0)
    full=writing.prepare_accepted_context(source,**options)
    size=full['preflight']['used_bytes']
    bounded=writing.prepare_accepted_context(source,**options,budget_bytes=size,recall_chapter_ids=['ch-1'])
    assert bounded['preflight']['used_bytes']==size and bounded['preflight']['dropped_sources']
    assert bounded['preflight']['journal_authority_bytes']>0
    assert 'keep_journal_style_marker' in bounded['preflight']['context_text']
    with pytest.raises(ValueError):writing.prepare_accepted_context(source,**options,budget_bytes=size-1)


def test_journal_runs_do_not_reset_existing_allowance(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path);source=restore(path)
    flow,calls=session(monkeypatch,limits=RequestBudgetLimits(max_requests=1))
    flow.run_from_accepted_archive(source,current_chapter_id='ch-2',review=False)
    with pytest.raises(RequestBudgetExceeded):flow.run_from_accepted_archive(source,current_chapter_id='ch-2',review=False)
    assert len(calls)==1 and flow.budget_snapshot()['requests_reserved']==1


def test_journal_descriptor_nested_views_are_detached_and_cannot_rebind(tmp_path,monkeypatch):
    path,value=journal_ready(tmp_path);source=restore(path);flow,calls=session(monkeypatch)
    source.state.style_profile['forged']='not canonical'
    source.journal.events.clear()
    assert 'forged' not in source.state.style_profile and source.journal.events
    with pytest.raises(ValueError):flow.run_from_accepted_archive(replace(source,state_sha256='0'*64),current_chapter_id='ch-2')
    with pytest.raises(ValueError):flow.run_from_accepted_archive(replace(source,context_revision=0),current_chapter_id='ch-2')
    assert calls==[]
