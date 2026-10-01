"""Synthetic project files only; no public deployment or hostile-OS claims."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from novel_ai.storage import ProjectStore, StorageIntegrityError
from novel_ai import eval as evaluation


@pytest.mark.parametrize('relative', ['../outside.json','../../escape.json','/tmp/outside.json','memory/../../outside.json','C:/outside.json','memory\\outside.json','memory//x.json','memory/./x.json','memory/../x.json','', '.', 'memory/' + '界' * 86 + '.json','.store.lock','.extraction-transaction.json'])
def test_confined_paths_for_read_write_append(tmp_path, relative):
    store=ProjectStore(tmp_path/'data')
    for action in (lambda: store.write_json('P',relative,{}),lambda: store.read_json('P',relative),lambda: store.append_jsonl('P',relative,{})):
        with pytest.raises(ValueError): action()
    assert not (tmp_path/'outside.json').exists()


def test_symlink_same_project_and_cross_project_refused(tmp_path):
    store=ProjectStore(tmp_path/'data')
    root=store.project_dir('P')
    store.write_json('Q','memory/secret.json',{'private':'synthetic'})
    (root/'alias').symlink_to(store.project_dir('Q'),target_is_directory=True)
    (root/'memory'/'same.json').symlink_to(root/'memory'/'genuine.json')
    for path in ('alias/memory/secret.json','memory/same.json'):
        with pytest.raises(ValueError):store.read_json('P',path)
        with pytest.raises(ValueError):store.write_json('P',path,{})
    symlink_root=tmp_path/'alias-root';symlink_root.symlink_to(store.root,target_is_directory=True)
    with pytest.raises(ValueError):ProjectStore(symlink_root)


def test_jsonl_and_chapter_atomic_failure(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path)
    chapter=store.write_chapter('P','ch','旧稿')
    line=store.append_jsonl('P','memory/log.jsonl',{'n':1})
    before=(chapter.read_bytes(),line.read_bytes())
    def fail(*args):raise OSError('synthetic replacement failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):store.write_chapter('P','ch','新稿')
    with pytest.raises(OSError):store.append_jsonl('P','memory/log.jsonl',{'n':2})
    assert (chapter.read_bytes(),line.read_bytes())==before


def test_invalid_serialization_does_not_publish_intent(tmp_path):
    store=ProjectStore(tmp_path)
    store.save_extraction('P',{'chapter_id':'c','summary':'old'})
    before=store.all_chapter_summaries('P')
    for invalid in (object(),float('nan'),float('inf')):
        with pytest.raises((TypeError,ValueError)):
            store.save_extraction('P',{'chapter_id':'c','summary':invalid})
    assert store.all_chapter_summaries('P')==before
    assert not (store.project_dir('P')/'.extraction-transaction.json').exists()


@pytest.mark.parametrize('fail_target',['memory/extractions/c.json','memory/chapter_summaries.jsonl'])
def test_extraction_pair_rolls_forward_after_interrupted_write(tmp_path,monkeypatch,fail_target):
    store=ProjectStore(tmp_path)
    store.save_extraction('P',{'chapter_id':'c','summary':'old'})
    actual=store._write
    def fail(path,content,**kwargs):
        if path.as_posix().endswith(fail_target):raise OSError('synthetic crash')
        return actual(path,content,**kwargs)
    monkeypatch.setattr(store,'_write',fail)
    with pytest.raises(OSError):store.save_extraction('P',{'chapter_id':'c','summary':'new'})
    root=store.project_dir('P')
    assert (root/'.extraction-transaction.json').exists()
    # Fresh process/object recovers only through the guarded read API.
    fresh=ProjectStore(tmp_path)
    assert fresh.read_json('P','memory/extractions/c.json')['summary']=='new'
    assert fresh.all_chapter_summaries('P')[0]['summary']=='new'
    assert not (root/'.extraction-transaction.json').exists()
    before=(root/'memory/chapter_summaries.jsonl').read_bytes()
    fresh.save_extraction('P',{'chapter_id':'c','summary':'new'})
    assert (root/'memory/chapter_summaries.jsonl').read_bytes()==before


def pending_pair(tmp_path,monkeypatch):
    store=ProjectStore(tmp_path)
    store.save_extraction('P',{'chapter_id':'c','summary':'old'})
    actual=store._write
    def fail(path,content,**kwargs):
        if path.name=='chapter_summaries.jsonl':raise OSError('synthetic crash')
        return actual(path,content,**kwargs)
    monkeypatch.setattr(store,'_write',fail)
    with pytest.raises(OSError):store.save_extraction('P',{'chapter_id':'c','summary':'new'})
    return store.project_dir('P')


def test_recovery_conflict_fails_before_overwriting_other_file(tmp_path,monkeypatch):
    root=pending_pair(tmp_path,monkeypatch)
    summary=root/'memory/chapter_summaries.jsonl'
    summary.write_text('{"chapter_id":"c","summary":"external"}\n')
    extraction=(root/'memory/extractions/c.json').read_bytes()
    with pytest.raises(StorageIntegrityError):ProjectStore(tmp_path).all_chapter_summaries('P')
    assert 'external' in summary.read_text()
    assert (root/'memory/extractions/c.json').read_bytes()==extraction
    assert (root/'.extraction-transaction.json').exists()


@pytest.mark.parametrize('corruption',['truncated','outside','mismatch'])
def test_corrupt_intent_fails_closed(tmp_path,monkeypatch,corruption):
    root=pending_pair(tmp_path,monkeypatch)
    target=root/'.extraction-transaction.json'
    data=json.loads(target.read_text())
    if corruption=='truncated':target.write_text('{')
    else:
        if corruption=='outside':data['files'][0]['path']='../../escape.json'
        else:data['files'][0]['content']='{}'
        target.write_text(json.dumps(data))
    with pytest.raises(StorageIntegrityError):ProjectStore(tmp_path).read_json('P','memory/extractions/c.json')
    assert not (tmp_path/'escape.json').exists()
    assert target.exists()


def test_stable_summary_order_after_edit_and_duplicates(tmp_path):
    store=ProjectStore(tmp_path)
    for name in ['a','b','c']:
        store.save_extraction('P',{'chapter_id':name,'summary':'old'})
    store.append_jsonl('P','memory/chapter_summaries.jsonl',{'chapter_id':'a','summary':'duplicate'})
    store.save_extraction('P',{'chapter_id':'a','summary':'revised'})
    rows=store.all_chapter_summaries('P')
    assert [r['chapter_id'] for r in rows]==['a','b','c']
    assert rows[0]['summary']=='revised'


def test_cooperating_processes_do_not_lose_summaries(tmp_path):
    root=Path(__file__).resolve().parents[1]
    script='''from novel_ai.storage import ProjectStore
import sys
s=ProjectStore(sys.argv[1])
for i in range(8):s.save_extraction("P",{"chapter_id":sys.argv[2]+str(i),"summary":"synthetic"})
'''
    workers=[subprocess.Popen([sys.executable,'-c',script,str(tmp_path),prefix],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for prefix in ['a','b','c']]
    for worker in workers:
        _,error=worker.communicate(timeout=30)
        assert worker.returncode==0,error
    store=ProjectStore(tmp_path)
    rows=store.all_chapter_summaries('P')
    assert len(rows)==24 and len({r['chapter_id'] for r in rows})==24
    lock=store.project_dir('P')/'.store.lock'
    inode=lock.stat().st_ino
    store.save_extraction('P',{'chapter_id':'z','summary':'new'})
    assert lock.stat().st_ino==inode


def test_same_second_benchmarks_and_existing_scores_are_preserved(tmp_path):
    fixed=datetime(2026,10,1,8,0,0,tzinfo=timezone.utc)
    class Clock:
        @staticmethod
        def now(tz):return fixed
    def record(text):return {'case_id':'urban_dispute','variant':'A_baseline','text':text}
    with patch.object(evaluation,'datetime',Clock),patch.object(evaluation,'run_case',side_effect=[record('first'),record('second')]):
        first=evaluation.run_benchmark(None,'benchmarks',tmp_path,variants=['A_baseline'],cases=['urban_dispute'])
        scores=first/'scoring_sheet.csv';scores.write_text('human score sentinel')
        second=evaluation.run_benchmark(None,'benchmarks',tmp_path,variants=['A_baseline'],cases=['urban_dispute'])
    assert first!=second
    assert (first/'urban_dispute__A_baseline.txt').read_text()=='first'
    assert scores.read_text()=='human score sentinel'
    with pytest.raises(FileExistsError):evaluation.make_scoring_sheet({'run_id':'x','cases':[]},scores)
    assert scores.read_text()=='human score sentinel'


@pytest.mark.parametrize('relative',['.STORE.LOCK','.EXTRACTION-TRANSACTION.JSON','memory/NUL.json','memory/COM1','memory/name.','memory/name '])
def test_platform_aliases_cannot_replace_reserved_files(tmp_path,relative):
    with pytest.raises(ValueError):ProjectStore(tmp_path).write_json('P',relative,{})


def test_oversize_intent_rejected_before_it_can_block_project(tmp_path,monkeypatch):
    import novel_ai.storage as module
    store=ProjectStore(tmp_path)
    store.save_extraction('P',{'chapter_id':'c','summary':'old'})
    monkeypatch.setattr(module,'_MAX_INTENT_BYTES',32)
    with pytest.raises(ValueError,match='上限'):
        store.save_extraction('P',{'chapter_id':'c','summary':'new'})
    assert not (store.project_dir('P')/'.extraction-transaction.json').exists()
    assert store.all_chapter_summaries('P')[0]['summary']=='old'


def test_forked_lock_lineage_refuses_reentrant_bypass(tmp_path,monkeypatch):
    from novel_ai import storage_guard
    monkeypatch.setattr(storage_guard,'_PROCESS_ID',-1)
    with pytest.raises(RuntimeError,match='spawned'):
        with storage_guard.project_lock(tmp_path/'.lock'):pass
    assert not (tmp_path/'.lock').exists()


def test_unlock_failure_still_closes_descriptor(tmp_path,monkeypatch):
    if os.name!='posix':pytest.skip('POSIX native lock fault test')
    import fcntl
    from novel_ai import storage_guard
    actual=fcntl.flock
    captured=[]
    def fail(fd,operation):
        captured.append(fd)
        if operation==fcntl.LOCK_UN:raise OSError('synthetic unlock failure')
        return actual(fd,operation)
    monkeypatch.setattr(fcntl,'flock',fail)
    with pytest.raises(OSError):
        with storage_guard.project_lock(tmp_path/'.lock'):pass
    with pytest.raises(OSError):os.fstat(captured[-1])


def test_different_chapter_ids_cannot_alias_extraction_file(tmp_path):
    store=ProjectStore(tmp_path)
    store.save_extraction('P',{'chapter_id':'a/b','summary':'original'})
    with pytest.raises(StorageIntegrityError,match='同一文件名'):
        store.save_extraction('P',{'chapter_id':'a b','summary':'other'})
    assert store.all_chapter_summaries('P')==[{'chapter_id':'a/b','chapter_title':'','summary':'original'}]


def test_invalid_benchmark_selection_has_no_output_side_effect(tmp_path):
    target=tmp_path/'out'
    with pytest.raises(ValueError):evaluation.run_benchmark(None,'benchmarks',target,cases=['not-a-case'])
    assert not target.exists()
    with pytest.raises(ValueError):evaluation.run_benchmark(None,'benchmarks',target,variants=['A_baseline','A_baseline'])
    assert not target.exists()


def test_benchmark_case_id_cannot_escape_run_directory(tmp_path):
    from types import SimpleNamespace
    with patch.object(evaluation,'load_benchmark',return_value=[SimpleNamespace(case_id='../escape')]):
        with pytest.raises(ValueError):evaluation.run_benchmark(None,'benchmarks',tmp_path/'out')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('constant',['NaN','Infinity','-Infinity','1e999'])
def test_nonfinite_stored_json_is_reported_without_rewriting(tmp_path,constant):
    store=ProjectStore(tmp_path)
    path=store.project_dir('P')/'memory'/'bad.json'
    raw='{"value":'+constant+'}'
    path.write_text(raw)
    with pytest.raises(StorageIntegrityError):store.read_json('P','memory/bad.json')
    assert path.read_text()==raw
