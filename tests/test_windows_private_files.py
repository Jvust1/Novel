"""Native Windows security at creation, independent ACL checks, no author data."""
import os
from pathlib import Path

import pytest

from novel_ai import private_files as private
from novel_ai._vendor import boltons_atomic as atomic
from novel_ai.gpt_story_state import create_state, save_state
from private_file_assertions import assert_windows_private_file

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows DACL API')


@pytest.mark.parametrize('writer', ['state', 'atomic'])
def test_private_before_first_content_write_and_after_publication(tmp_path, monkeypatch, writer):
    target = tmp_path / 'private.json'
    original = os.fdopen
    before_write = []

    def fdopen(fd, *args, **kwargs):
        assert os.fstat(fd).st_size == 0
        temporary = next(p for p in tmp_path.iterdir() if p != target)
        assert_windows_private_file(temporary)
        before_write.append(temporary)
        return original(fd, *args, **kwargs)

    monkeypatch.setattr(os, 'fdopen', fdopen)
    if writer == 'state':
        save_state(target, create_state('synthetic-private'))
    else:
        with atomic.atomic_save(target, overwrite=False) as stream:
            stream.write(b'synthetic only')
    assert len(before_write) == 1
    assert_windows_private_file(target)
    assert list(tmp_path.iterdir()) == [target]


def test_private_replace_does_not_copy_destination_access(tmp_path):
    target = tmp_path / 'current.txt'
    target.write_bytes(b'old synthetic bytes')
    with atomic.atomic_save(target) as stream:
        stream.write(b'new synthetic bytes')
    assert target.read_bytes() == b'new synthetic bytes'
    assert_windows_private_file(target)


def test_existing_file_and_exclusive_temp_collision_are_untouched(tmp_path, monkeypatch):
    foreign = tmp_path / ('prefix-' + '00' * 16 + '.tmp')
    foreign.write_bytes(b'foreign synthetic bytes')
    with pytest.raises(FileExistsError):
        private.create_private_file(foreign)
    assert foreign.read_bytes() == b'foreign synthetic bytes'
    values = iter([bytes(16), b'1' * 16])
    monkeypatch.setattr(private.os, 'urandom', lambda count: next(values))
    fd, path = private.private_mkstemp(prefix='prefix-', suffix='.tmp', dir=tmp_path)
    try:
        assert Path(path) != foreign
        assert os.fstat(fd).st_size == 0
        assert_windows_private_file(path)
    finally:
        os.close(fd)
    assert foreign.read_bytes() == b'foreign synthetic bytes'


@pytest.mark.parametrize('writer', ['state', 'atomic'])
def test_acl_verification_failure_never_writes_or_publishes(tmp_path, monkeypatch, writer):
    target = tmp_path / 'current.txt'
    target.write_bytes(b'old synthetic bytes')
    handles = []

    def fail(api, handle, descriptor):
        handles.append(handle)
        raise PermissionError('synthetic ACL readback failure')

    monkeypatch.setattr(private, '_verify_handle', fail)
    with pytest.raises(PermissionError, match='ACL readback'):
        if writer == 'state':
            save_state(tmp_path / 'new-state.json', create_state('synthetic-private'))
        else:
            with atomic.atomic_save(target):
                pytest.fail('security verification must precede entering the body')
    assert target.read_bytes() == b'old synthetic bytes'
    assert list(tmp_path.iterdir()) == [target]
    assert len(handles) == 1
    api = private._native()
    import ctypes
    flags = ctypes.c_ulong()
    api.k.GetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    api.k.GetHandleInformation.restype = ctypes.c_int
    assert not api.k.GetHandleInformation(handles[0], ctypes.byref(flags))
    assert ctypes.get_last_error() == 6  # ERROR_INVALID_HANDLE


def test_fd_transfer_failure_closes_native_handle_and_cleans_empty_file(tmp_path, monkeypatch):
    import msvcrt
    target = tmp_path / 'never-published.txt'

    def fail(*args):
        raise OSError('synthetic CRT transfer failure')

    monkeypatch.setattr(msvcrt, 'open_osfhandle', fail)
    with pytest.raises(OSError, match='CRT transfer'):
        private.create_private_file(target)
    assert not target.exists()


def test_effective_token_failure_is_not_an_inherited_acl_fallback(tmp_path, monkeypatch):
    def fail(api):
        raise PermissionError('synthetic token lookup failure')

    monkeypatch.setattr(private, '_effective_user_sid', fail)
    with pytest.raises(PermissionError, match='token lookup'):
        private.create_private_file(tmp_path / 'private.txt')
    assert not list(tmp_path.iterdir())
