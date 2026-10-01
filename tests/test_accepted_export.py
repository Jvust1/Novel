"""Original synthetic accepted/rejected versions through the real review exporter."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from novel_ai import accepted_export as export
from novel_ai import author_workflow as workflow
from novel_ai import gpt_story_journal as journal
from novel_ai import gpt_story_state as state
from novel_ai.accepted_writing import restore_source, restore_journal_source
from novel_ai.market_eval import MARKET_RUBRIC, MarketScore
from novel_ai.release_pack import MarketProfile
from novel_ai.storage import ProjectStore
from test_accepted_archive_writing import art, confirm, digest, step
from test_gpt_story_journal import confirm as journal_confirm

REJECTED = 'REJECTED_A_PRIVATE_SENTINEL 这一版没有被接受。'
PENDING = 'CURRENT_PENDING_SENTINEL 这一版还在等待作者。'
CANON = 'PRIVATE_CANON_SECRET_SENTINEL'
STYLE = 'PRIVATE_STYLE_NOT_FOR_EXPORT'
PLAN = 'PRIVATE_PLAN_NOT_FOR_READERS'
CHAT = 'PRIVATE_AUTHOR_CHAT_REFERENCE'
RAW = '\ufeff\r\n  接受的 B 正文。灯还在门边。 \r\n'
COPY = dict(title='原创测试书', one_line_hook='一次明知代价的选择', short_blurb='从渡口开始寻找失物。')


def source_archive(tmp_path, *, count=3, kind='v1', pending=True, same_text=False,
                   story_id='synthetic-story', accepted_revision=2):
    value = state.create_state(story_id, template={
        'canon': {'characters': [], 'locked_facts': [CANON]},
        'style_profile': {'private_style': STYLE}})
    path = tmp_path / 'private-story.json'
    texts = {}
    def decision(scope):
        evidence = confirm(value, scope)
        evidence['confirmation_source'] = CHAT
        return evidence
    for index in range(1, count+1):
        chapter_id = f'ch-{index}'
        value = step(value, 'start_chapter', {'chapter_id': chapter_id})
        value = step(value, 'set_plan', {'artifact': art(PLAN + str(index), 'private-plan-' + chapter_id).model_dump(mode='json')})
        value = step(value, 'accept_plan', {'confirmation': decision('plan')})
        value = step(value, 'set_draft', {'artifact': art(REJECTED, 'rejected-A-' + chapter_id).model_dump(mode='json')})
        for version in range(2, accepted_revision+1):
            text = RAW if same_text else RAW + f'正文编号 {index}。\r\n'
            value = step(value, 'set_draft', {'artifact': art(text, f'accepted-B-{chapter_id}-r{version}').model_dump(mode='json')})
        texts[chapter_id] = text.encode('utf-8')
        value = step(value, 'review', {'draft_revision': value.progress.draft_revision, 'issues': [],
            'source': art('Synthetic explicit review of B', 'review-B-' + chapter_id).source.model_dump(mode='json')})
        value = step(value, 'accept_chapter', {'confirmation': decision('chapter')})
        value = step(value, 'propose_memory', {'changes': []})
        value = step(value, 'accept_memory', {'confirmation': decision('memory')})
        value = step(value, 'apply_memory', {'memory_update_id': value.progress.memory_update_id})
        saved = state.save_state(path, value, expected_disk_revision=index-1 if path.exists() else None,
                                  expected_disk_sha256=digest(path) if path.exists() else None)
        value = state.load_state(path, expected_story_id=story_id, expected_sha256=saved.sha256)
    if pending:
        value = step(value, 'start_chapter', {'chapter_id': f'ch-{count+1}'})
        value = step(value, 'set_plan', {'artifact': art(PLAN + ' pending', 'current-plan').model_dump(mode='json')})
        value = step(value, 'accept_plan', {'confirmation': decision('plan')})
        value = step(value, 'set_draft', {'artifact': art(PENDING, 'current-candidate').model_dump(mode='json')})
        state.save_state(path, value, expected_disk_revision=count, expected_disk_sha256=digest(path))
    if kind == 'v1':
        return restore_source(path, expected_story_id=story_id, expected_revision=count, expected_sha256=digest(path)), texts
    value = state.load_state(path, expected_story_id=story_id)
    origin = art(value.model_dump_json(), 'private-origin')
    owned = journal.migrate_state(origin, journal_confirm({'scope': 'migrate', 'story_id': story_id,
        'origin_source_fingerprint': state.source_fingerprint(origin)}))
    path = tmp_path / 'private-journal.json'
    journal.save_journal(path, owned)
    return restore_journal_source(path, expected_story_id=story_id, expected_revision=count,
        expected_context_revision=0, expected_journal_sha256=journal.journal_fingerprint(owned),
        expected_file_sha256=digest(path)), texts


def profile():
    return MarketProfile(genre='悬疑', audience='成人读者', tone='贴近人物')


def build(source, **options):
    args = {'chapter_ids':['ch-1','ch-2','ch-3'], 'stage':'opening_3', 'profile':profile(), **COPY}
    args.update(options)
    return export.build_accepted_review_bundle(source, **args)


def unpack(bundle):
    raw = bundle.bundle_bytes if type(bundle) is export.AcceptedReviewBundle else bundle
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.parametrize('kind',['v1','journal'])
@pytest.mark.parametrize('pending',[False,True])
def test_only_exact_accepted_B_is_exported_without_private_plans_or_candidate(kind,pending,tmp_path):
    source,texts=source_archive(tmp_path,kind=kind,pending=pending)
    before=Path(source.path).read_bytes();bundle=build(source);files=unpack(bundle)
    for index in range(1,4):assert files[f'chapters/{index:03d}.md']==texts[f'ch-{index}']
    entire=b''.join(files.values()).decode('utf-8-sig')
    for secret in [REJECTED,PENDING,CANON,STYLE,PLAN,CHAT,str(tmp_path),'unread.invalid']:
        assert secret not in entire
    proof=json.loads(files['accepted_source.json']);manifest=json.loads(files['manifest.json'])
    assert manifest['accepted_source_sha256']==hashlib.sha256(files['accepted_source.json']).hexdigest()
    assert proof['source_kind']==('author_journal' if kind=='journal' else 'v1_story')
    assert [row['draft_revision'] for row in proof['chapters']]==[2,2,2]
    assert [row['text_bytes'] for row in proof['chapters']]==[len(texts[f'ch-{i}']) for i in range(1,4)]
    assert manifest['human_review_status']=='awaiting_human_review' and manifest['publishability_verdict'] is None
    assert manifest['outline_status']=='not_included' and Path(source.path).read_bytes()==before


def test_explicit_subset_and_non_natural_order_keep_exact_membership(tmp_path):
    source,texts=source_archive(tmp_path,count=4)
    ids=['ch-4','ch-1','ch-3'];files=unpack(build(source,chapter_ids=ids))
    assert [files[f'chapters/{i:03d}.md'] for i in range(1,4)]==[texts[key] for key in ids]
    proof=json.loads(files['accepted_source.json'])
    assert [row['chapter_id'] for row in proof['chapters']]==ids
    assert [row['accepted_history_ordinal'] for row in proof['chapters']]==[4,1,3]
    assert texts['ch-2'] not in files.values()


def test_identical_text_chapters_still_bind_ordered_ids_independently(tmp_path):
    source,texts=source_archive(tmp_path,same_text=True)
    first=unpack(build(source));second=unpack(build(source,chapter_ids=['ch-3','ch-1','ch-2']))
    assert json.loads(first['manifest.json'])['corpus_sha256']!=json.loads(second['manifest.json'])['corpus_sha256']
    assert first['accepted_source.json']!=second['accepted_source.json']
    assert [row['chapter_id'] for row in json.loads(second['accepted_source.json'])['chapters']]==['ch-3','ch-1','ch-2']
    assert all(first[f'chapters/{i:03d}.md']==second[f'chapters/{i:03d}.md']==RAW.encode('utf-8') for i in range(1,4))


def test_identical_text_with_different_acceptance_versions_changes_proof(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    source_a,_=source_archive(a,same_text=True,accepted_revision=2)
    source_b,_=source_archive(b,same_text=True,accepted_revision=3)
    first=unpack(build(source_a));second=unpack(build(source_b))
    assert first['chapters/001.md']==second['chapters/001.md']
    x=json.loads(first['accepted_source.json'])['chapters'][0];y=json.loads(second['accepted_source.json'])['chapters'][0]
    assert x['text_sha256']==y['text_sha256'] and x['draft_revision']!=y['draft_revision']
    assert x['acceptance_records_sha256']!=y['acceptance_records_sha256']


@pytest.mark.parametrize('ids',[['ch-1','ch-1','ch-2'],['ch-1','ch-2'],['ch-1','ch-2','ch-4'],
    ['ch-1','ch-2','other-story'],['ch-1','ch-2','../escape']])
def test_invalid_selection_is_refused_not_filled_from_disk(tmp_path,ids):
    source,_=source_archive(tmp_path)
    with pytest.raises(ValueError):build(source,chapter_ids=ids)


def test_twenty_accepted_chapters_use_existing_retention_stage(tmp_path):
    source,texts=source_archive(tmp_path,count=20,pending=False)
    ids=[f'ch-{i}' for i in range(20,0,-1)]
    bundle=build(source,chapter_ids=ids,stage='retention_20')
    files=unpack(bundle)
    assert files['chapters/001.md']==texts['ch-20'] and files['chapters/020.md']==texts['ch-1']
    assert bundle.report()['stage']=='retention_20'


def test_repeated_build_and_identical_save_are_byte_deterministic(tmp_path):
    source,_=source_archive(tmp_path);store=ProjectStore(tmp_path/'out')
    first=build(source);second=build(source)
    assert first.bundle_bytes==second.bundle_bytes
    path=export.save_accepted_review_bundle(store,'synthetic-story',first)
    assert export.save_accepted_review_bundle(store,'synthetic-story',second)==path
    assert path.read_bytes()==first.bundle_bytes
    assert len(list(path.parent.glob('release-*.zip')))==1


def test_saved_legacy_rejected_manuscript_is_never_used_as_export_source(tmp_path):
    source,texts=source_archive(tmp_path);store=ProjectStore(tmp_path/'out')
    for i in range(1,4):store.write_chapter('synthetic-story',f'ch-{i}',REJECTED)
    bundle=build(source);path=export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    assert unpack(path.read_bytes())['chapters/001.md']==texts['ch-1']


def test_forged_handle_mutable_views_or_changed_spec_cannot_publish(tmp_path):
    source,_=source_archive(tmp_path);bundle=build(source);store=ProjectStore(tmp_path/'out')
    with pytest.raises(ValueError):export.save_accepted_review_bundle(store,'synthetic-story',replace(bundle))
    report=bundle.report();report['source']['chapters'].clear()
    assert len(bundle.report()['source']['chapters'])==3
    object.__setattr__(bundle,'_spec_json',b'{}')
    with pytest.raises(ValueError):export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    assert not (store.root/'projects').exists()


def test_source_change_after_build_blocks_bytes_report_and_save(tmp_path):
    source,_=source_archive(tmp_path);bundle=build(source);store=ProjectStore(tmp_path/'out')
    Path(source.path).write_bytes(Path(source.path).read_bytes()+b' ')
    for call in [lambda:bundle.bundle_bytes,bundle.report,lambda:export.save_accepted_review_bundle(store,'synthetic-story',bundle)]:
        with pytest.raises(ValueError):call()
    assert not (store.root/'projects').exists()


def test_source_change_during_packaging_does_not_return_observed_bundle(tmp_path,monkeypatch):
    source,_=source_archive(tmp_path);original=workflow.release_bundle_bytes
    def changed(*args,**kwargs):
        value=original(*args,**kwargs);Path(source.path).write_bytes(Path(source.path).read_bytes()+b' ');return value
    monkeypatch.setattr(workflow,'release_bundle_bytes',changed)
    with pytest.raises(ValueError):build(source)


def test_changed_source_during_existing_file_readback_refuses_success(tmp_path,monkeypatch):
    source,_=source_archive(tmp_path);bundle=build(source);store=ProjectStore(tmp_path/'out')
    target=export.save_accepted_review_bundle(store,'synthetic-story',bundle);expected=target.read_bytes()
    original=workflow._read_bytes
    def changed(path):
        result=original(path);Path(source.path).write_bytes(Path(source.path).read_bytes()+b' ');return result
    monkeypatch.setattr(workflow,'_read_bytes',changed)
    with pytest.raises(ValueError):export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    assert target.read_bytes()==expected


def test_failure_after_link_can_leave_complete_new_artifact_without_returning_success(tmp_path,monkeypatch):
    source,_=source_archive(tmp_path);bundle=build(source);raw=bundle.bundle_bytes;store=ProjectStore(tmp_path/'out')
    original=workflow.os.link
    def linked_then_failed(src,dst):
        original(src,dst);raise OSError('synthetic failure after completed publication')
    monkeypatch.setattr(workflow.os,'link',linked_then_failed)
    with pytest.raises(OSError):export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    paths=list((store.root/'projects'/'synthetic-story'/'exports').glob('release-*.zip'))
    assert len(paths)==1 and paths[0].read_bytes()==raw
    monkeypatch.setattr(workflow.os,'link',original)
    assert export.save_accepted_review_bundle(store,'synthetic-story',bundle)==paths[0]


@pytest.mark.parametrize('different',[False,True])
def test_racing_existing_target_is_read_back_without_clobber(tmp_path,monkeypatch,different):
    source,_=source_archive(tmp_path);bundle=build(source);raw=bundle.bundle_bytes;store=ProjectStore(tmp_path/'out')
    def race(src,dst):
        Path(dst).write_bytes(b'different existing bytes' if different else Path(src).read_bytes())
        raise FileExistsError('synthetic cooperating race')
    monkeypatch.setattr(workflow.os,'link',race)
    if different:
        with pytest.raises(ValueError):export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    else:
        assert export.save_accepted_review_bundle(store,'synthetic-story',bundle).read_bytes()==raw
    paths=list((store.root/'projects'/'synthetic-story'/'exports').glob('release-*.zip'))
    assert len(paths)==1 and paths[0].read_bytes()==(b'different existing bytes' if different else raw)


def test_source_changes_after_link_leave_only_complete_historical_package(tmp_path,monkeypatch):
    source,_=source_archive(tmp_path);bundle=build(source);raw=bundle.bundle_bytes;store=ProjectStore(tmp_path/'out')
    original=workflow.os.link
    def change_after_link(src,dst):
        original(src,dst);Path(source.path).write_bytes(Path(source.path).read_bytes()+b' ')
    monkeypatch.setattr(workflow.os,'link',change_after_link)
    with pytest.raises(ValueError):export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    paths=list((store.root/'projects'/'synthetic-story'/'exports').glob('release-*.zip'))
    assert len(paths)==1 and paths[0].read_bytes()==raw


def test_unrelated_recovery_and_canonical_files_are_not_touched(tmp_path,monkeypatch):
    source,_=source_archive(tmp_path);bundle=build(source);store=ProjectStore(tmp_path/'out')
    project=store.project_dir('synthetic-story');intent=project/'.memory-commit-transaction.json';intent.write_bytes(b'unrelated pending intent')
    def forbidden(*args,**kwargs):raise AssertionError('unrelated memory recovery invoked')
    monkeypatch.setattr(ProjectStore,'_guard',forbidden)
    export.save_accepted_review_bundle(store,'synthetic-story',bundle)
    assert intent.read_bytes()==b'unrelated pending intent'


@pytest.mark.parametrize('kind',['v1','journal'])
def test_real_offline_cli_packages_accepted_selection_without_printing_manuscript(tmp_path,kind):
    source,texts=source_archive(tmp_path,kind=kind)
    meta=tmp_path/'metadata.json';meta.write_text(json.dumps({'profile':profile().model_dump(),**COPY},ensure_ascii=False))
    args=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/export_accepted_review.py'),source.path,str(meta),
        '--source-kind',kind,'--story-id',source.story_id,'--revision',str(source.revision),'--sha256',source.file_sha256,
        '--stage','opening_3','--out-root',str(tmp_path/'cli-out')]
    for i in [3,1,2]:args.extend(['--chapter-id',f'ch-{i}'])
    if kind=='journal':args.extend(['--context-revision',str(source.context_revision),'--journal-sha256',source.journal_sha256])
    done=subprocess.run(args,capture_output=True,text=True)
    assert done.returncode==0,done.stderr
    result=json.loads(done.stdout);assert result['chapter_ids']==['ch-3','ch-1','ch-2']
    assert result['human_review_status']=='awaiting_human_review'
    assert RAW not in done.stdout and CHAT not in done.stdout
    assert unpack(Path(result['artifact_path']).read_bytes())['chapters/001.md']==texts['ch-3']


def test_explicit_scores_are_bound_to_the_exact_selected_review_corpus(tmp_path):
    source,_=source_archive(tmp_path)
    corpus=export.preview_accepted_corpus(source,chapter_ids=['ch-1','ch-2','ch-3'],stage='opening_3',profile=profile())
    scores=[MarketScore(project=corpus.project,stage=corpus.stage,corpus_sha256=corpus.fingerprint(),
        reviewer_id='synthetic-explicit-reviewer',dimension=dimension,score=3,note='Synthetic test opinion')
        for dimension,_,_ in MARKET_RUBRIC]
    bundle=build(source,scores=scores);files=unpack(bundle)
    assert bundle.report()['human_review_status']=='human_review_recorded'
    assert bundle.report()['publishability_verdict'] is None
    assert 'human_scores.json' in files and 'human_review_summary.json' in files
    with pytest.raises(ValueError):build(source,scores=scores,chapter_ids=['ch-3','ch-1','ch-2'])
    with pytest.raises(ValueError):build(source,scores=scores,profile=MarketProfile(genre='悬疑',audience='不同的测试读者'))
    scores[0].project='other-book'
    with pytest.raises(ValueError):build(source,scores=scores)


@pytest.mark.parametrize('tamper',['manuscript','duplicate','extra','approval'])
def test_final_packager_bytes_are_verified_not_just_its_declared_hashes(tmp_path,monkeypatch,tamper):
    source,_=source_archive(tmp_path);original=workflow.release_bundle_bytes
    def changed(*args,**kwargs):
        raw=original(*args,**kwargs);output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(output,'w') as dst:
            for info in src.infolist():
                data=src.read(info.filename)
                if tamper=='manuscript' and info.filename=='chapters/001.md':data=REJECTED.encode()
                if tamper=='approval' and info.filename=='manifest.json':
                    manifest=json.loads(data);manifest['publishability_verdict']='automatic-pass';data=json.dumps(manifest).encode()
                dst.writestr(info,data)
            if tamper=='extra':dst.writestr('private-plan.txt',PLAN)
            if tamper=='duplicate':
                with pytest.warns(UserWarning):dst.writestr('chapters/001.md',REJECTED)
        return output.getvalue()
    monkeypatch.setattr(workflow,'release_bundle_bytes',changed)
    with pytest.raises(ValueError):build(source)


@pytest.mark.parametrize('kind', ['v1', 'journal'])
def test_same_downloaded_snapshot_has_portable_package_identity(tmp_path, kind):
    source,_=source_archive(tmp_path, kind=kind)
    other=tmp_path/'another-download'/'same-private-snapshot.json';other.parent.mkdir()
    other.write_bytes(Path(source.path).read_bytes())
    if kind == 'journal':
        copied=restore_journal_source(other, expected_story_id=source.story_id,
            expected_revision=source.revision, expected_context_revision=source.context_revision,
            expected_journal_sha256=source.journal_sha256, expected_file_sha256=source.file_sha256)
    else:
        copied=restore_source(other,expected_story_id=source.story_id,expected_revision=source.revision,
                              expected_sha256=source.file_sha256)
    assert source.binding()!=copied.binding()  # Execution handles still bind their actual paths.
    assert build(source).bundle_bytes==build(copied).bundle_bytes
