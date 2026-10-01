"""Original synthetic fixed memory-batch commits. No model/network calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading

import pytest

from novel_ai import memory_commit as commit
from novel_ai.models import MemoryExtraction
from novel_ai.storage import ProjectStore


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def bundle(tmp_path, *, missing=False):
    store = ProjectStore(tmp_path / 'data')
    project, chapter = 'Synthetic', 'c'
    root = store.project_dir(project)
    inputs = {'chapters/c.md': '守灯人把灯留在门边。\n',
        'memory/chapter_plans/' + hashlib.sha256(b'c').hexdigest() + '.json': '{"source":"saved synthetic plan"}\n',
        'memory/story_bible.json': '{"title":"Synthetic source"}\n'}
    for relative, text in inputs.items():
        path = store._path(project, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    def outputs(new):
        word = 'new' if new else 'old'
        voice = {'守灯人': {'line_count': 2 if new else 1}}
        extraction = MemoryExtraction(chapter_id=chapter, chapter_title=word, summary=word + ' summary')
        data = {
            'memory/characters.json': [{'name': '守灯人', 'current_goal': word, 'custom_author_note': {'preserve': True}}],
            'memory/story_state.json': {'facts': [word + ' fact'], 'timeline': [], 'foreshadowing': [],
                                       'open_threads': [], 'unapplied_updates': [], 'custom_note': {'preserve': True}},
            'memory/extractions/c.json': extraction.model_dump(),
            'memory/chapter_summaries.jsonl': {'chapter_id': chapter, 'chapter_title': word, 'summary': word + ' summary'},
            'memory/story_graph.json': {'nodes': [{'id': word}], 'edges': []},
            'memory/voice_dna/c.json': {'chapter_id': chapter, 'voice_dna': voice},
            'memory/longform_health.json': {'voice_dna': voice, 'custom_diagnostic': word},
            'memory/story_dna/c.json': {'chapter_id': chapter, 'story_dna': {'chapter_title': word}},
            'memory/chapter_analytics/c.json': {'chapter_id': chapter, 'analytics': {'chapter_id': chapter, 'scene_count': int(new)}},
        }
        return {key: json.dumps(value, ensure_ascii=False) + '\n' if key.endswith('.jsonl') else encoded(value)
                for key, value in data.items()}
    old, files = outputs(False), outputs(True)
    if not missing:
        for relative, text in old.items():
            path = store._path(project, relative)
            store._write(path, text)
    before = {relative: digest(store._path(project, relative)) for relative in files}
    identities = {relative: digest(store._path(project, relative)) for relative in inputs}
    proposal = 'memory-' + hashlib.sha256(b'synthetic complete proposal').hexdigest()
    confirmation = {'project': project, 'chapter_id': chapter, 'proposal_id': proposal,
        'source_text_sha256': identities['chapters/c.md'], 'chapter_accepted': True, 'memory_accepted': True,
        'confirmation_source': 'synthetic-test://explicit-two-author-controls'}
    arguments = dict(proposal_id=proposal, chapter_id=chapter, files=files, expected_before=before,
                     inputs=identities, confirmation=confirmation)
    return store, project, root, arguments


def snap(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*')
            if path.is_file() and path.name != '.store.lock'}


def run(store, project, args):
    return commit.commit_confirmed_memory(store, project, **args)


def assert_after(root, args):
    for relative, text in args['files'].items():
        assert (root / relative).read_bytes() == text.encode('utf-8')


@pytest.mark.parametrize('missing', [False, True])
def test_complete_batch_receipt_and_exact_retry_do_not_rewrite_newer_state(tmp_path, monkeypatch, missing):
    store, project, root, args = bundle(tmp_path, missing=missing)
    sources = {key: (root / key).read_bytes() for key in args['inputs']}
    receipt = run(store, project, args)
    assert receipt['status'] == 'committed'
    assert_after(root, args)
    assert all((root / key).read_bytes() == value for key, value in sources.items())
    assert commit.inspect_memory_commit(store, project) is None
    assert commit.recover_memory_commit(store, project) is None
    receipt_path = root / 'memory/memory_commits' / (args['proposal_id'] + '.json')
    original_receipt = receipt_path.read_bytes()
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    receipt['confirmation']['memory_accepted'] = False
    assert receipt_path.read_bytes() == original_receipt
    (root / 'memory/characters.json').write_text('[{"name":"Newer author"}]')
    (root / 'chapters/c.md').write_text('A newer source after the historical commit')
    before = snap(root)
    monkeypatch.setattr(store, '_write', lambda *a, **kw: pytest.fail('idempotent receipt retry wrote a file'))
    assert run(store, project, args) == json.loads(original_receipt)
    assert snap(root) == before


def test_existing_receipt_does_not_accept_rebound_after_images_or_sources(tmp_path):
    store, project, root, args = bundle(tmp_path)
    run(store, project, args)
    before = snap(root)
    altered = deepcopy(args)
    value = json.loads(altered['files']['memory/story_state.json'])
    value['facts'].append('unreviewed fact')
    altered['files']['memory/story_state.json'] = encoded(value)
    with pytest.raises(commit.MemoryCommitError, match='receipt differs'):
        run(store, project, altered)
    altered = deepcopy(args)
    altered['inputs']['memory/story_bible.json'] = '0' * 64
    with pytest.raises(commit.MemoryCommitError, match='receipt differs'):
        run(store, project, altered)
    assert snap(root) == before


@pytest.mark.parametrize('relative', ['memory/story_state.json', 'chapters/c.md',
    'memory/story_bible.json', 'memory/chapter_plans/' + hashlib.sha256(b'c').hexdigest() + '.json'])
def test_changed_baseline_or_source_refused_before_intent_or_canonical_write(tmp_path, relative):
    store, project, root, args = bundle(tmp_path)
    (root / relative).write_bytes((root / relative).read_bytes() + b' ')
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError):
        run(store, project, args)
    assert snap(root) == before


@pytest.mark.parametrize('field,value', [('project', 'Other'), ('chapter_id', 'other'), ('proposal_id', 'memory-' + '0'*64),
    ('source_text_sha256', '0'*64), ('chapter_accepted', False), ('chapter_accepted', 1),
    ('memory_accepted', False), ('memory_accepted', 'true'), ('confirmation_source', ' ')])
def test_explicit_confirmation_must_bind_entire_source_identity(tmp_path, field, value):
    store, project, root, args = bundle(tmp_path)
    args['confirmation'][field] = value
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='confirmation'):
        run(store, project, args)
    assert snap(root) == before


@pytest.mark.parametrize('change', ['missing_target', 'extra_target', 'foreign_target', 'missing_chapter', 'missing_plan', 'extra_input',
    'summary_mismatch', 'duplicate_summary', 'foreign_extraction', 'foreign_nested_chapter', 'foreign_voice',
    'foreign_analytics', 'health_mismatch', 'duplicate_characters', 'gpt_state', 'duplicate_json_key', 'nan', 'bad_hash'])
def test_fixed_shapes_paths_and_related_records_validate_before_publication(tmp_path, change):
    store, project, root, args = bundle(tmp_path)
    files = args['files']
    if change == 'missing_target': files.pop('memory/story_graph.json')
    elif change == 'extra_target': files['chapters/c.md'] = 'overwrite manuscript'
    elif change == 'foreign_target': files['memory/extractions/other.json'] = files.pop('memory/extractions/c.json')
    elif change == 'missing_chapter': args['inputs'].pop('chapters/c.md')
    elif change == 'missing_plan': args['inputs'].pop('memory/chapter_plans/' + hashlib.sha256(b'c').hexdigest() + '.json')
    elif change == 'extra_input': args['inputs']['../outside'] = None
    elif change == 'summary_mismatch': files['memory/chapter_summaries.jsonl'] = '{"chapter_id":"c","summary":"wrong","chapter_title":"new"}\n'
    elif change == 'duplicate_summary': files['memory/chapter_summaries.jsonl'] *= 2
    elif change in {'foreign_extraction', 'foreign_nested_chapter'}:
        value = json.loads(files['memory/extractions/c.json'])
        if change == 'foreign_extraction': value['chapter_id'] = 'other'
        else: value['timeline_events'] = [{'chapter_id': 'other', 'description': 'foreign source'}]
        files['memory/extractions/c.json'] = encoded(value)
    elif change == 'foreign_voice': files['memory/voice_dna/c.json'] = '{"chapter_id":"other","voice_dna":{}}'
    elif change == 'foreign_analytics': files['memory/chapter_analytics/c.json'] = '{"chapter_id":"c","analytics":{"chapter_id":"other"}}'
    elif change == 'health_mismatch': files['memory/longform_health.json'] = '{"voice_dna":{}}'
    elif change == 'duplicate_characters': files['memory/characters.json'] = '[{"name":"Same"},{"name":"Same"}]'
    elif change == 'gpt_state': files['memory/story_state.json'] = '{"engine_version":"gpt-state-checks-v1"}'
    elif change == 'duplicate_json_key': files['memory/story_graph.json'] = '{"nodes":[],"nodes":[],"edges":[]}'
    elif change == 'nan': files['memory/story_graph.json'] = '{"nodes":[],"edges":[],"x":NaN}'
    else: args['expected_before']['memory/story_state.json'] = 'not-a-hash'
    before = snap(root)
    with pytest.raises(ValueError):
        run(store, project, args)
    assert snap(root) == before


@pytest.mark.parametrize('which', ['target', 'input', 'hardlink'])
def test_aliases_and_links_do_not_allow_target_or_source_collision(tmp_path, which):
    store, project, root, args = bundle(tmp_path)
    target = root / ('memory/characters.json' if which != 'input' else 'chapters/c.md')
    original = target.read_bytes()
    alias = tmp_path / 'outside.txt'
    alias.write_bytes(original)
    target.unlink()
    if which == 'hardlink':
        import os
        os.link(root / 'memory/story_state.json', target)
        args['expected_before']['memory/characters.json'] = digest(target)
    else:
        target.symlink_to(alias)
    before = snap(root)
    with pytest.raises(ValueError):
        run(store, project, args)
    assert snap(root) == before and alias.read_bytes() == original


def test_legacy_recovery_is_neither_triggered_nor_overwritten(tmp_path):
    store, project, root, args = bundle(tmp_path)
    legacy = root / '.extraction-transaction.json'
    legacy.write_text('{"synthetic":"pending legacy evidence"}')
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='legacy'):
        run(store, project, args)
    assert snap(root) == before


TARGETS = sorted(commit._paths('c'))
@pytest.mark.parametrize('failure_target', [*TARGETS, 'receipt'])
def test_failure_at_every_publication_retains_intent_and_recovers_complete_after_images(tmp_path, monkeypatch, failure_target):
    store, project, root, args = bundle(tmp_path)
    actual = store._write
    def fail(path, text, **kwargs):
        relative = path.relative_to(root).as_posix()
        if relative == failure_target or failure_target == 'receipt' and relative.startswith('memory/memory_commits/'):
            raise OSError('synthetic interrupted batch')
        return actual(path, text, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(store, '_write', fail)
        with pytest.raises(OSError, match='interrupted batch'):
            run(store, project, args)
    before_inspect = snap(root)
    assert commit.inspect_memory_commit(store, project)['status'] == 'pending'
    assert snap(root) == before_inspect
    receipt = commit.recover_memory_commit(ProjectStore(store.root), project)
    assert receipt['proposal_id'] == args['proposal_id']
    assert_after(root, args)
    assert not (root / commit.INTENT_PATH).exists()
    assert commit.recover_memory_commit(store, project) is None


def pending(tmp_path, monkeypatch):
    store, project, root, args = bundle(tmp_path)
    actual = store._write
    def fail(path, text, **kwargs):
        if path.relative_to(root).as_posix() == 'memory/story_state.json':
            raise OSError('synthetic pending state')
        return actual(path, text, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(store, '_write', fail)
        with pytest.raises(OSError):
            run(store, project, args)
    return store, project, root, args


@pytest.mark.parametrize('conflict', ['target', 'input', 'legacy'])
def test_recovery_conflict_preserves_entire_remaining_batch_and_evidence(tmp_path, monkeypatch, conflict):
    store, project, root, args = pending(tmp_path, monkeypatch)
    path = root / ({'target': 'memory/story_graph.json', 'input': 'chapters/c.md', 'legacy': '.extraction-transaction.json'}[conflict])
    path.write_text('independent conflicting content')
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError):
        commit.recover_memory_commit(store, project)
    assert snap(root) == before


@pytest.mark.parametrize('tamper', ['old_image', 'new_image', 'project_root', 'proposal', 'receipt', 'duplicate_target'])
def test_tampered_intent_never_performs_more_writes(tmp_path, monkeypatch, tamper):
    store, project, root, args = pending(tmp_path, monkeypatch)
    path = root / commit.INTENT_PATH
    value = json.loads(path.read_text())
    if tamper == 'old_image': value['files'][0]['before_content'] += ' '
    elif tamper == 'new_image': value['files'][0]['after_content'] += ' '
    elif tamper == 'project_root': value['project_root'] = str(tmp_path / 'Other')
    elif tamper == 'proposal': value['proposal_id'] = 'memory-' + '0' * 64
    elif tamper == 'receipt': value['receipt']['confirmation']['memory_accepted'] = False
    else: value['files'].append(value['files'][0])
    path.write_text(encoded(value))
    before = snap(root)
    with pytest.raises(ValueError):
        commit.recover_memory_commit(store, project)
    assert snap(root) == before


@pytest.mark.parametrize('failure', ['intent_write', 'oversize'])
def test_pre_intent_failure_leaves_all_canonical_files_unchanged(tmp_path, monkeypatch, failure):
    store, project, root, args = bundle(tmp_path)
    before = snap(root)
    if failure == 'oversize': monkeypatch.setattr(commit, 'MAX_INTENT_BYTES', 128)
    else:
        actual = store._write
        def fail(path, text, **kwargs):
            if path.name == commit.INTENT_PATH: raise OSError('synthetic before intent')
            return actual(path, text, **kwargs)
        monkeypatch.setattr(store, '_write', fail)
    with pytest.raises((ValueError, OSError)):
        run(store, project, args)
    assert snap(root) == before


@pytest.mark.parametrize('when', ['target_published', 'receipt_published', 'cleanup_sync', 'post_cleanup_sync'])
def test_late_publication_errors_are_retryable_without_claiming_rollback(tmp_path, monkeypatch, when):
    store, project, root, args = bundle(tmp_path)
    actual_write, actual_sync = store._write, commit.sync_directory
    def fail_write(path, text, **kwargs):
        result = actual_write(path, text, **kwargs)
        relative = path.relative_to(root).as_posix()
        if when == 'target_published' and relative == 'memory/characters.json': raise OSError('synthetic post-publication')
        if when == 'receipt_published' and relative.startswith('memory/memory_commits/'): raise OSError('synthetic post-publication')
        return result
    def fail_sync(path):
        receipt = root / 'memory/memory_commits' / (args['proposal_id'] + '.json')
        exists = (root / commit.INTENT_PATH).exists()
        if Path(path) == root and receipt.exists() and ((when == 'cleanup_sync' and exists) or (when == 'post_cleanup_sync' and not exists)):
            raise OSError('synthetic directory sync')
        return actual_sync(path)
    with monkeypatch.context() as scoped:
        scoped.setattr(store, '_write', fail_write)
        scoped.setattr(commit, 'sync_directory', fail_sync)
        with pytest.raises(OSError): run(store, project, args)
    receipt = run(store, project, args)
    assert receipt['status'] == 'committed'
    assert_after(root, args)
    assert not (root / commit.INTENT_PATH).exists()


def test_published_receipt_cleanup_does_not_replay_over_newer_author_state(tmp_path, monkeypatch):
    store, project, root, args = bundle(tmp_path)
    actual = store._write
    def fail(path, text, **kwargs):
        result = actual(path, text, **kwargs)
        if path.parent.name == 'memory_commits': raise OSError('synthetic receipt already visible')
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(store, '_write', fail)
        with pytest.raises(OSError): run(store, project, args)
    (root / 'memory/characters.json').write_text('[{"name":"A later accepted character"}]')
    (root / 'chapters/c.md').write_text('A later draft')
    before = snap(root)
    monkeypatch.setattr(store, '_write', lambda *a, **kw: pytest.fail('cleanup rewrote newer canonical files'))
    receipt = commit.recover_memory_commit(store, project)
    assert receipt['status'] == 'committed'
    after = snap(root)
    before.pop(commit.INTENT_PATH)
    assert after == before


def test_source_change_during_commit_stops_and_preserves_pending_intent(tmp_path, monkeypatch):
    store, project, root, args = bundle(tmp_path)
    actual = store._write
    def change(path, text, **kwargs):
        result = actual(path, text, **kwargs)
        if path.relative_to(root).as_posix() == TARGETS[0]:
            (root / 'chapters/c.md').write_text('New author draft during commit')
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(store, '_write', change)
        with pytest.raises(commit.MemoryCommitError, match='input changed'):
            run(store, project, args)
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='input changed'):
        commit.recover_memory_commit(store, project)
    assert snap(root) == before and (root / commit.INTENT_PATH).exists()


@pytest.mark.parametrize('same_proposal', [False, True])
def test_cooperating_commits_share_exact_retries_or_reject_another_old_baseline(tmp_path, same_proposal):
    store, project, root, args = bundle(tmp_path)
    barrier = threading.Barrier(2)
    def perform(index):
        own = deepcopy(args)
        if index and not same_proposal:
            own['proposal_id'] = 'memory-' + hashlib.sha256(b'another proposal').hexdigest()
            own['confirmation']['proposal_id'] = own['proposal_id']
        barrier.wait(timeout=10)
        try:
            return run(ProjectStore(store.root), project, own)
        except commit.MemoryCommitError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(perform, [0, 1]))
    assert sum(value is not None for value in results) == (2 if same_proposal else 1)
    if same_proposal:
        assert results[0] == results[1]
    assert len(list((root / 'memory/memory_commits').glob('*.json'))) == 1
    assert_after(root, args)


def test_public_receipt_read_is_detached_historical_and_read_only(tmp_path):
    store, project, root, args = bundle(tmp_path)
    assert commit.read_memory_commit_receipt(store, project, args['proposal_id']) is None
    original = run(store, project, args)
    (root / 'chapters/c.md').write_text('Newer manuscript after successful memory commit')
    before = snap(root)
    receipt = commit.read_memory_commit_receipt(store, project, args['proposal_id'])
    assert receipt == original
    receipt['confirmation']['memory_accepted'] = False
    assert commit.read_memory_commit_receipt(store, project, args['proposal_id']) == original
    assert snap(root) == before


def test_public_receipt_read_refuses_tampered_metadata_without_writes(tmp_path):
    store, project, root, args = bundle(tmp_path)
    receipt = run(store, project, args)
    receipt['after_sha256']['memory/story_state.json'] = '0' * 64
    path = root / 'memory/memory_commits' / (args['proposal_id'] + '.json')
    path.write_text(encoded(receipt))
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='identity'):
        commit.read_memory_commit_receipt(store, project, args['proposal_id'])
    assert snap(root) == before


@pytest.mark.parametrize('existing', [{"engine_version": "gpt-state-checks-v1"}, {"journal_owner": {}}])
def test_legacy_committer_cannot_replace_an_existing_gpt_authority(tmp_path, existing):
    store, project, root, args = bundle(tmp_path)
    path = root / 'memory/story_state.json'
    path.write_text(encoded(existing))
    args['expected_before']['memory/story_state.json'] = digest(path)
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='GPT state'):
        run(store, project, args)
    assert snap(root) == before


@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_intent_write_return_is_not_assumed_to_be_verified_publication(tmp_path, monkeypatch, fault):
    store, project, root, args = bundle(tmp_path)
    before = snap(root)
    actual = store._write
    def fake_success(path, text, **kwargs):
        if path.name == commit.INTENT_PATH:
            if fault == 'changed':
                return actual(path, text + '\n', **kwargs)
            return None
        return actual(path, text, **kwargs)
    monkeypatch.setattr(store, '_write', fake_success)
    with pytest.raises(commit.MemoryCommitError, match='intent did not read back'):
        run(store, project, args)
    after = snap(root)
    after.pop(commit.INTENT_PATH, None)
    assert after == before


@pytest.mark.parametrize('bad_project,bad_chapter', [('Not Canonical', 'c'), ('Synthetic', 'c/name'), ('Synthetic', 'c name')])
def test_new_commits_refuse_lossy_project_or_chapter_normalization(tmp_path, bad_project, bad_chapter):
    store, project, root, args = bundle(tmp_path)
    args['chapter_id'] = bad_chapter
    before = snap(root)
    with pytest.raises(commit.MemoryCommitError, match='canonical'):
        run(store, bad_project, args)
    assert snap(root) == before
