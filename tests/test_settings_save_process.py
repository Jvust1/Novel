"""Real process exits and contention at the fixed local settings boundary."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai.settings_commit import (
    INTENT_PATH,
    SETTINGS_PATHS,
    commit_settings_bundle,
    load_settings_bundle,
    prepare_settings_save,
)
from novel_ai.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[1]


def request(store, name, nonce, *, keep_bible=False):
    snapshot = load_settings_bundle(store, "SyntheticBook")
    bible = snapshot["bible"] if keep_bible else {"title": "原创测试书", "genre": name}
    return {"files": prepare_settings_save(snapshot, bible, "原创总纲：" + name),
            "expected_before": snapshot["sha256"], "request_id": nonce}


CHILD = '''
import json, os, sys, time
from pathlib import Path
from novel_ai.storage import ProjectStore
from novel_ai.settings_commit import commit_settings_bundle
store=ProjectStore(sys.argv[1]); request=json.loads(Path(sys.argv[2]).read_text())
marker=sys.argv[3]; start=Path(sys.argv[4]); original=store._write
def write(path, content, **kwargs):
    original(path, content, **kwargs)
    if marker and (path.name==marker or (marker=='receipt' and path.parent.name=='settings_commits')):
        os._exit(23)
store._write=write
deadline=time.monotonic()+20
while not start.exists():
    if time.monotonic()>deadline: raise RuntimeError('start timeout')
    time.sleep(.005)
try:
    commit_settings_bundle(store,'SyntheticBook',**request)
except ValueError:
    sys.exit(2)
'''


def spawn(root, path, marker, start):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.Popen([sys.executable, "-c", CHILD, str(root), str(path), marker, str(start)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def exact_files(store, req):
    for relative in SETTINGS_PATHS:
        assert (store.project_dir("SyntheticBook") / relative).read_text() == req["files"][relative]


@pytest.mark.parametrize("marker", [INTENT_PATH, "story_bible.json", "outline.json", "receipt"])
def test_exit_after_each_publication_recovers_exact_settings_pair(tmp_path, marker):
    store = ProjectStore(tmp_path / "data")
    req = request(store, "轨道科幻", "1" * 32)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(req))
    start = tmp_path / "start"
    start.touch()
    child = spawn(store.root, path, marker, start)
    output, error = child.communicate(timeout=40)
    assert child.returncode == 23, (output, error)
    fresh = ProjectStore(store.root)
    actual = load_settings_bundle(fresh, "SyntheticBook")
    assert actual["bible"]["genre"] == "轨道科幻"
    assert actual["outline"]["outline"] == "原创总纲：轨道科幻"
    exact_files(fresh, req)
    assert not (fresh.project_dir("SyntheticBook") / INTENT_PATH).exists()
    assert len(list((fresh.project_dir("SyntheticBook") / "memory/settings_commits").glob("*.json"))) == 1


def test_outline_only_save_recovers_when_bible_bytes_never_change(tmp_path):
    store = ProjectStore(tmp_path / "data")
    initial = request(store, "初始题材", "1" * 32)
    commit_settings_bundle(store, "SyntheticBook", **initial)
    req = request(store, "新的场景安排", "2" * 32, keep_bible=True)
    assert req["expected_before"][SETTINGS_PATHS[0]] == hashlib.sha256(req["files"][SETTINGS_PATHS[0]].encode()).hexdigest()
    path = tmp_path / "request.json"
    path.write_text(json.dumps(req))
    start = tmp_path / "start"
    start.touch()
    child = spawn(store.root, path, "outline.json", start)
    output, error = child.communicate(timeout=40)
    assert child.returncode == 23, (output, error)
    fresh = ProjectStore(store.root)
    actual = load_settings_bundle(fresh, "SyntheticBook")
    assert actual["bible"]["genre"] == "初始题材"
    assert actual["outline"]["outline"] == "原创总纲：新的场景安排"
    exact_files(fresh, req)


@pytest.mark.parametrize("identity", ["different-id", "same-id-same-request", "same-id-changed-request"])
def test_two_processes_never_mix_or_overwrite_competing_old_baselines(tmp_path, identity):
    store = ProjectStore(tmp_path / "data")
    first = request(store, "第一套设定", "1" * 32)
    second = (first if identity == "same-id-same-request"
              else request(store, "第二套设定", ("1" if identity == "same-id-changed-request" else "2") * 32))
    start = tmp_path / "start"
    requests = [first, second]
    children = []
    for i, req in enumerate(requests):
        path = tmp_path / f"request{i}.json"
        path.write_text(json.dumps(req))
        children.append(spawn(store.root, path, "", start))
    start.touch()
    for child in children:
        child.communicate(timeout=40)
    assert sorted(child.returncode for child in children) == ([0, 0] if identity == "same-id-same-request" else [0, 2])
    winner = next(i for i, child in enumerate(children) if child.returncode == 0)
    exact_files(store, requests[winner])
    assert len(list((store.project_dir("SyntheticBook") / "memory/settings_commits").glob("*.json"))) == 1

