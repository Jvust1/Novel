"""Native locks for cooperating local ProjectStore users, not a filesystem sandbox."""
from __future__ import annotations

import os
import stat
import threading
from contextlib import contextmanager
from pathlib import Path

_LOCKS: dict[str, threading.RLock] = {}
_REGISTRY = threading.Lock()
_HELD = threading.local()
_PROCESS_ID = os.getpid()


def reject_links(path: Path) -> None:
    """Reject existing symlink/junction ancestry before touching project data.

    Rechecking ordinary paths does not defend against a hostile directory swap
    racing between checks. Project directories must be trusted and writers cooperate.
    """
    for item in (path, *path.parents):
        if item.is_symlink() or (getattr(item, "is_junction", lambda: False)()):
            raise ValueError("project storage refuses symlink or junction ancestry")


@contextmanager
def project_lock(path: Path):
    """Hold one stable advisory-lock inode per project, reentrant in this thread."""
    if os.getpid() != _PROCESS_ID:
        raise RuntimeError("forked processes must use a fresh spawned interpreter for project locks")
    reject_links(path)
    key = os.path.normcase(str(path.resolve()))
    with _REGISTRY:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        held = getattr(_HELD, "paths", {})
        _HELD.paths = held
        if key in held:
            held[key] += 1
            try:
                yield
            finally:
                held[key] -= 1
            return
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        acquired = False
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("project lock must be a regular file")
            if os.name == "posix":
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            elif os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                raise RuntimeError("native project locks are unsupported on this platform")
            acquired = True
            held[key] = 1
            yield
        finally:
            held.pop(key, None)
            try:
                if acquired:
                    if os.name == "posix":
                        import fcntl
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    elif os.name == "nt":
                        import msvcrt
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(descriptor)
            # Do not unlink: replacing lock-file inodes would split cooperating locks.
