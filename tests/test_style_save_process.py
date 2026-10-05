"""Process death and concurrent processes through the real fixed save protocol."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai.storage import ProjectStore
from novel_ai.style_commit import STYLE_PATHS, load_style_bundle, prepare_style_addition
from novel_ai.style_engine import analyze_style, build_reference_signature

ROOT = Path(__file__).resolve().parents[1]
TEXT = '原创样本。院里的石凳还湿着，周宁把外套放到门边，等晚归的人先开口。' * 20


def request(store, name, nonce):
    snapshot = load_style_bundle(store, 'P')
    files = prepare_style_addition(snapshot, {'name': name, 'weight': 1.0,
                                  'fingerprint': analyze_style(TEXT).model_dump()}, build_reference_signature(TEXT))
    return {'files': files, 'expected_before': snapshot['sha256'], 'request_id': nonce}


CHILD = '''
import json, os, sys, time
from pathlib import Path
from novel_ai.storage import ProjectStore
from novel_ai.style_commit import commit_style_bundle
store=ProjectStore(sys.argv[1]); request=json.loads(Path(sys.argv[2]).read_text())
marker=sys.argv[3]; start=Path(sys.argv[4])
original=store._write
def write(path, content, **kwargs):
    original(path, content, **kwargs)
    if marker and (path.name == marker or (marker == 'receipt' and path.parent.name == 'commits')):
        os._exit(23)
store._write=write
deadline=time.monotonic()+20
while not start.exists():
    if time.monotonic()>deadline: raise RuntimeError('start timeout')
    time.sleep(.005)
try:
    commit_style_bundle(store,'P',**request)
except ValueError:
    sys.exit(2)
'''


def spawn(root, path, marker, start):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.Popen([sys.executable, '-c', CHILD, str(root), str(path), marker, str(start)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.mark.parametrize('marker', ['.style-commit-transaction.json', 'style_profiles.json',
                                   'style_dna.json', 'reference_signature.json', 'receipt'])
def test_process_exit_at_every_publication_checkpoint_recovers(tmp_path, marker):
    store = ProjectStore(tmp_path / 'data')
    req = request(store, 'Process fixture', '1' * 32)
    path = tmp_path / 'request.json'; path.write_text(json.dumps(req))
    start = tmp_path / 'start'; start.touch()
    process = spawn(store.root, path, marker, start)
    out, err = process.communicate(timeout=40)
    assert process.returncode == 23, (out, err)
    restored = load_style_bundle(ProjectStore(store.root), 'P')
    assert len(restored['profiles']) == 1
    for relative in STYLE_PATHS:
        assert (store.project_dir('P') / relative).read_text() == req['files'][relative]
    assert not (store.project_dir('P') / '.style-commit-transaction.json').exists()


def test_two_processes_with_same_before_version_do_not_lose_updates(tmp_path):
    store = ProjectStore(tmp_path / 'data')
    requests = [request(store, name, str(i) * 32) for i, name in [(1, 'First'), (2, 'Second')]]
    start = tmp_path / 'start'
    children = []
    for i, req in enumerate(requests):
        path = tmp_path / f'request{i}.json'; path.write_text(json.dumps(req))
        children.append(spawn(store.root, path, '', start))
    start.touch()
    for child in children:
        child.communicate(timeout=40)
    assert sorted(child.returncode for child in children) == [0, 2]
    restored = load_style_bundle(ProjectStore(store.root), 'P')
    winner = next(i for i, child in enumerate(children) if child.returncode == 0)
    assert len(restored['profiles']) == 1
    assert restored['profiles'][0]['name'] == ('First' if winner == 0 else 'Second')
    for relative in STYLE_PATHS:
        assert (store.project_dir('P') / relative).read_text() == requests[winner]['files'][relative]
