"""Synthetic-only failure and source-provenance checks for the narrow port."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from novel_ai._vendor import boltons_atomic as atomic


def parts(directory):
    return list(directory.glob(".novel-*.tmp"))


def test_upstream_pathlike_roundtrip_and_explicit_utf8(tmp_path):
    # The upstream tests/test_fileutils.py AtomicSaver PathLike contract.
    target = tmp_path / "output.bin"
    with atomic.atomic_save(target) as stream:
        stream.write(b"synthetic bytes")
    assert target.read_bytes() == b"synthetic bytes"
    with atomic.AtomicSaver(target, text_mode=True) as stream:
        stream.write("合成正文\n")
    assert target.read_bytes() == "合成正文\n".encode("utf-8")
    assert not parts(tmp_path)


def test_body_failure_never_publishes_and_cleans_part(tmp_path):
    target = tmp_path / "old.txt"
    target.write_bytes(b"old complete document")
    with pytest.raises(ValueError, match="synthetic body"):
        with atomic.atomic_save(target) as stream:
            stream.write(b"partial new")
            raise ValueError("synthetic body")
    assert target.read_bytes() == b"old complete document"
    assert not parts(tmp_path)


@pytest.mark.parametrize("step", ["flush", "fsync", "close", "replace"])
def test_prepublication_failure_keeps_old_complete_bytes(tmp_path, monkeypatch, step):
    target = tmp_path / "old.txt"
    target.write_bytes(b"old complete document")
    saver = atomic.atomic_save(target)

    def fail(*args, **kwargs):
        raise OSError("synthetic " + step)

    with pytest.raises(OSError, match="synthetic " + step):
        with saver as stream:
            stream.write(b"new complete document")
            if step in {"flush", "close"}:
                original = saver.part_file

                class FaultyStream:
                    def __init__(self):
                        self.failed = False

                    def flush(self):
                        if step == "flush":
                            fail()
                        return original.flush()

                    def fileno(self):
                        return original.fileno()

                    def close(self):
                        if step == "close" and not self.failed:
                            self.failed = True
                            fail()
                        return original.close()

                saver.part_file = FaultyStream()
            else:
                monkeypatch.setattr(atomic.os, step, fail)
    assert target.read_bytes() == b"old complete document"
    assert not parts(tmp_path)


def test_fdopen_failure_closes_owned_descriptor_and_removes_part(tmp_path, monkeypatch):
    descriptors = []

    def fail(descriptor, *args, **kwargs):
        descriptors.append(descriptor)
        raise LookupError("synthetic encoding setup")

    monkeypatch.setattr(atomic.os, "fdopen", fail)
    with pytest.raises(LookupError, match="synthetic encoding"):
        with atomic.atomic_save(tmp_path / "new.txt"):
            pytest.fail("must not enter")
    assert descriptors
    with pytest.raises(OSError) as error:
        os.fstat(descriptors[0])
    assert error.value.errno == errno.EBADF
    assert not parts(tmp_path)


def test_error_after_replace_leaves_complete_new_file(tmp_path, monkeypatch):
    target = tmp_path / "current.txt"
    target.write_bytes(b"old")
    original = atomic.os.replace

    def replace_then_fail(source, destination):
        original(source, destination)
        raise OSError("synthetic after publication")

    monkeypatch.setattr(atomic.os, "replace", replace_then_fail)
    with pytest.raises(OSError, match="after publication"):
        with atomic.atomic_save(target) as stream:
            stream.write(b"new complete document")
    assert target.read_bytes() == b"new complete document"
    assert not parts(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory fsync")
@pytest.mark.parametrize("error_number", [errno.EIO, errno.EACCES])
def test_directory_sync_error_is_postcommit_not_rollback(tmp_path, monkeypatch, error_number):
    target = tmp_path / "current.txt"
    target.write_bytes(b"old")
    original = atomic.os.fsync

    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(error_number, "synthetic directory sync")
        return original(descriptor)

    monkeypatch.setattr(atomic.os, "fsync", fail_directory)
    with pytest.raises(OSError, match="synthetic directory sync"):
        with atomic.atomic_save(target) as stream:
            stream.write(b"new complete document")
    assert target.read_bytes() == b"new complete document"
    assert not parts(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory fsync")
def test_unsupported_directory_sync_is_explicit(tmp_path, monkeypatch):
    original = atomic.os.fsync

    def unsupported_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EINVAL, "synthetic unsupported directory sync")
        return original(descriptor)

    monkeypatch.setattr(atomic.os, "fsync", unsupported_directory)
    saver = atomic.atomic_save(tmp_path / "current.txt")
    with saver as stream:
        stream.write(b"complete")
    assert saver.directory_synced is False
    assert (tmp_path / "current.txt").read_bytes() == b"complete"


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory fsync")
def test_sync_order_is_file_then_publish_then_directory(tmp_path, monkeypatch):
    events = []
    original_sync = atomic.os.fsync
    original_replace = atomic.os.replace

    def sync(descriptor):
        events.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        return original_sync(descriptor)

    def replace(source, destination):
        events.append("publish")
        return original_replace(source, destination)

    monkeypatch.setattr(atomic.os, "fsync", sync)
    monkeypatch.setattr(atomic.os, "replace", replace)
    saver = atomic.atomic_save(tmp_path / "current.txt")
    with saver as stream:
        stream.write(b"complete")
    assert events == ["file", "publish", "directory"]
    assert saver.directory_synced is True


def test_no_clobber_existing_file_and_concurrent_creator(tmp_path, monkeypatch):
    target = tmp_path / "current.txt"
    target.write_bytes(b"other writer")
    with pytest.raises(FileExistsError):
        with atomic.atomic_save(target, overwrite=False):
            pytest.fail("must not enter")
    assert target.read_bytes() == b"other writer"
    target.unlink()

    def racing_link(source, destination):
        Path(destination).write_bytes(b"concurrent winner")
        raise FileExistsError(errno.EEXIST, "synthetic winner", destination)

    monkeypatch.setattr(atomic.os, "link", racing_link)
    with pytest.raises(FileExistsError):
        with atomic.atomic_save(target, overwrite=False) as stream:
            stream.write(b"losing candidate")
    assert target.read_bytes() == b"concurrent winner"
    assert not parts(tmp_path)


def test_no_clobber_success_and_unsupported_link_fails_closed(tmp_path, monkeypatch):
    target = tmp_path / "current.txt"
    with atomic.atomic_save(target, overwrite=False) as stream:
        stream.write(b"new complete")
    assert target.read_bytes() == b"new complete"
    assert not parts(tmp_path)
    target.unlink()

    def unsupported(*args, **kwargs):
        raise OSError(errno.EPERM, "synthetic unsupported hard link")

    monkeypatch.setattr(atomic.os, "link", unsupported)
    with pytest.raises(OSError, match="unsupported hard link"):
        with atomic.atomic_save(target, overwrite=False) as stream:
            stream.write(b"new candidate")
    assert not target.exists()
    assert not parts(tmp_path)


def test_no_clobber_cleanup_failure_can_be_postcommit(tmp_path, monkeypatch):
    target = tmp_path / "current.txt"
    original = atomic.os.unlink
    failed = False

    def fail_once(path, *args, **kwargs):
        nonlocal failed
        if str(path).endswith(".tmp") and not failed:
            failed = True
            raise OSError(errno.EIO, "synthetic post-link cleanup")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(atomic.os, "unlink", fail_once)
    with pytest.raises(OSError, match="post-link cleanup"):
        with atomic.atomic_save(target, overwrite=False) as stream:
            stream.write(b"new complete document")
    assert target.read_bytes() == b"new complete document"
    assert not parts(tmp_path)


@pytest.mark.parametrize("supported", [True, False])
def test_public_directory_sync_accepts_pathlike_and_reports_support(tmp_path, monkeypatch, supported):
    received = []

    def sync(path):
        received.append(path)
        return supported

    monkeypatch.setattr(atomic, "_sync_directory", sync)
    assert atomic.sync_directory(tmp_path) is supported
    assert received == [str(tmp_path)]


def test_existing_random_part_is_not_deleted_or_followed(tmp_path, monkeypatch):
    external = tmp_path / "untouched.txt"
    external.write_bytes(b"synthetic external bytes")
    collision = tmp_path / (".novel-" + "00" * 16 + ".tmp")
    collision.symlink_to(external)
    values = iter([bytes(16), b"1" * 16])
    monkeypatch.setattr(atomic.os, "urandom", lambda size: next(values))
    with atomic.atomic_save(tmp_path / "current.txt") as stream:
        stream.write(b"new document")
    assert external.read_bytes() == b"synthetic external bytes"
    assert collision.is_symlink()
    assert parts(tmp_path) == [collision]


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_private_default_permissions_and_context_single_use(tmp_path):
    saver = atomic.atomic_save(tmp_path / "current.txt")
    with saver as stream:
        assert stat.S_IMODE(os.fstat(stream.fileno()).st_mode) & 0o077 == 0
        stream.write(b"private synthetic text")
    assert stat.S_IMODE((tmp_path / "current.txt").stat().st_mode) & 0o077 == 0
    with pytest.raises(RuntimeError, match="reused"):
        with saver:
            pytest.fail("must not enter")


def test_parent_creation_and_confinement_are_callers_responsibility(tmp_path):
    with pytest.raises(FileNotFoundError):
        with atomic.atomic_save(tmp_path / "absent" / "current.txt"):
            pytest.fail("must not enter")
    assert not (tmp_path / "absent").exists()


def test_complete_license_pinned_source_and_runtime_port_provenance():
    root = Path(__file__).resolve().parents[1]
    metadata = json.loads((root / "third_party/boltons/provenance.json").read_text())
    assert metadata["source_commit"] == "4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d"
    assert metadata["observed_stars"] >= 1000
    assert metadata["github_license_spdx_id"] == "NOASSERTION"
    assert metadata["license_assessment"] == "BSD-style three-clause permissive license; preserve exact supplied text"
    for item in [metadata["license_file"], *metadata["files"], metadata["adaptation"]]:
        assert hashlib.sha256((root / item["local_path"]).read_bytes()).hexdigest() == item["sha256"]
    license_text = (root / metadata["license_file"]["local_path"]).read_text()
    assert "Copyright (c) 2013, Mahmoud Hashemi" in license_text
    assert "THIS SOFTWARE IS PROVIDED" in license_text
    assert "EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE" in license_text
