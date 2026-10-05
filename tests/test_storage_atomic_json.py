import json
import pytest
from novel_ai.storage import ProjectStore


def test_json_replacement_failure_keeps_prior_document_and_cleans_temp(monkeypatch, tmp_path):
    import novel_ai.storage as storage
    store = ProjectStore(tmp_path)
    path = store.write_json("P", "memory/workspace.json", {"old": "保留"})
    before = path.read_bytes()
    def fail(*args):
        raise OSError("synthetic interrupted rename")
    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError):
        store.write_json("P", "memory/workspace.json", {"new": "未完成"})
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["workspace.json"]


def test_unserializable_json_leaves_original_untouched(tmp_path):
    store = ProjectStore(tmp_path)
    path = store.write_json("P", "memory/workspace.json", {"old": 1})
    with pytest.raises(TypeError):
        store.write_json("P", "memory/workspace.json", {"bad": object()})
    assert json.loads(path.read_text()) == {"old": 1}
