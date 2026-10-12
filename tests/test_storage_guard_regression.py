"""Synthetic filesystem guards; never touch author data."""
import errno
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_ai.storage_guard import reject_links


def test_one_metadata_query_per_ancestor(tmp_path, monkeypatch):
    path = tmp_path / "new" / "chapter.json"
    actual = os.lstat
    actual_stat = os.stat
    queried = []

    def track(path, *args, **kwargs):
        queried.append(Path(path))
        return actual(path, *args, **kwargs)

    def track_stat(path, *args, **kwargs):
        queried.append(Path(path))
        return actual_stat(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(os, "lstat", track)
        context.setattr(os, "stat", track_stat)
        reject_links(path)
    assert queried == [path, *path.parents]


@pytest.mark.parametrize("at_parent", [False, True])
def test_symlink_and_dangling_symlink_refused(tmp_path, at_parent):
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink or junction"):
        reject_links(link / "chapter.json" if at_parent else link)


@pytest.mark.parametrize("old_pathlib", [False, True])
@pytest.mark.parametrize("at_parent", [False, True])
@pytest.mark.skipif(os.name != "nt", reason="native Windows junction")
def test_native_junction_even_without_pathlib_helper(tmp_path, monkeypatch, old_pathlib, at_parent):
    import _winapi

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "alias"
    _winapi.CreateJunction(str(target), str(link))
    if old_pathlib:
        # Python 3.11 has no Path.is_junction; lstat still exposes the reparse tag.
        monkeypatch.delattr(Path, "is_junction", raising=False)
    with pytest.raises(ValueError, match="symlink or junction"):
        reject_links(link / "chapter.json" if at_parent else link)


@pytest.mark.parametrize("error", [PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "io")])
def test_unreadable_metadata_fails_closed(tmp_path, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    with monkeypatch.context() as context:
        context.setattr(os, "lstat", fail)
        context.setattr(os, "stat", fail)
        with pytest.raises(type(error)):
            reject_links(tmp_path)


def test_recheck_detects_new_link_not_a_cached_path(tmp_path):
    link = tmp_path / "alias"
    reject_links(link)
    link.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ValueError):
        reject_links(link)


def test_other_reparse_tags_are_not_mislabeled_as_junctions(tmp_path, monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(os, "lstat", lambda *a, **kw: SimpleNamespace(st_mode=0o040700, st_reparse_tag=0x8000001B))
        reject_links(tmp_path)


def test_ordinary_and_not_yet_created_paths_allowed(tmp_path):
    reject_links(tmp_path)
    reject_links(tmp_path / "new" / "chapter.json")
