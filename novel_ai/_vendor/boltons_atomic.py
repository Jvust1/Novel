# Copyright (c) 2013, Mahmoud Hashemi
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * The names of the contributors may not be used to endorse or
#      promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Narrow, modified boltons AtomicSaver port for Novel's single-file writes.

Source: mahmoud/boltons at 4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d,
boltons/fileutils.py lines 214-489. Full license and pinned source are in
third_party/boltons. The context-manager lifecycle, exclusive part creation,
and overwrite/no-clobber publication derive from that implementation.

Novel modifications: private randomized part names; explicit UTF-8 text mode;
0600 default permissions; modern os.replace; cleanup covering setup, flush,
fsync and close failures; and parent-directory fsync where supported. Removed
legacy Python/Windows ctypes branches, permission copying, caller-selected part
paths, and overwrite_part. This is deliberately not the full boltons API.

Callers must create and confine the parent directory and coordinate read-modify-
write operations. This module neither locks writers nor provides transactions.
A failure after publication may leave the complete NEW file visible; an error
does not promise rollback. SIGKILL may leave an unreferenced private part file.
POSIX directory sync is attempted; unsupported filesystems and non-POSIX hosts
do not receive a power-loss durability guarantee.
"""

from __future__ import annotations

import errno
import os

__all__ = ["AtomicSaver", "atomic_save", "sync_directory"]

# Adapted from upstream _TEXT_OPENFLAGS/_BIN_OPENFLAGS. O_EXCL also refuses
# existing symlinks; O_NOFOLLOW explicitly narrows the supported native path.
_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_EXCL
_OPEN_FLAGS |= getattr(os, "O_NOINHERIT", 0)
_OPEN_FLAGS |= getattr(os, "O_CLOEXEC", 0)
_OPEN_FLAGS |= getattr(os, "O_NOFOLLOW", 0)
_OPEN_FLAGS |= getattr(os, "O_BINARY", 0)
_UNSUPPORTED_DIRECTORY_SYNC = {
    errno.EINVAL, errno.ENOSYS,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


def _sync_directory(directory: str) -> bool:
    """Sync published directory entries, returning False only if unsupported.

    Other errors propagate, including when the new complete file is already
    visible. Successful fsync is still subject to the filesystem/device's
    durability contract.
    """
    if os.name != "posix":
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_SYNC:
            return False
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno in _UNSUPPORTED_DIRECTORY_SYNC:
                return False
            raise
    finally:
        os.close(descriptor)
    return True


def sync_directory(directory):
    """Sync an existing directory for a caller's bounded recovery protocol.

    Returns False when unsupported; other errors propagate. This does not sync
    parent-directory creation or establish a multi-file transaction.
    """
    return _sync_directory(os.fspath(directory))


def atomic_save(
    dest_path, *, overwrite=True, text_mode=False, encoding="utf-8",
    file_perms=0o600, sync_directory=True,
):
    """Return an AtomicSaver; write bytes unless text_mode=True is requested."""
    return AtomicSaver(
        dest_path, overwrite=overwrite, text_mode=text_mode, encoding=encoding,
        file_perms=file_perms, sync_directory=sync_directory,
    )


def atomic_rename(src, dst, overwrite=False):
    """Publish one complete file; never clobber a target when overwrite=False."""
    if overwrite:
        os.replace(src, dst)
    else:
        # The final hard link, rather than a preflight exists check, arbitrates
        # concurrent creators. No unsafe rename fallback on unsupported hosts.
        os.link(src, dst)
        os.unlink(src)


class AtomicSaver:
    """Single-use context manager derived from boltons.fileutils.AtomicSaver.

    Parent directories must already exist. Temporary files are created in the
    destination directory with exclusive/no-follow flags and random names.
    file_perms is filtered by the process umask; default files remain private.
    The directory_synced attribute is True only after a successful directory
    fsync, False when unsupported/disabled, and None before that step finishes.
    """

    def __init__(
        self, dest_path, *, overwrite=True, text_mode=False, encoding="utf-8",
        file_perms=0o600, sync_directory=True,
    ):
        self.dest_path = os.path.abspath(os.fspath(dest_path))
        if not isinstance(self.dest_path, str):
            raise TypeError("AtomicSaver requires a text path")
        self.dest_dir = os.path.dirname(self.dest_path)
        self.overwrite = overwrite
        self.file_perms = file_perms
        self.text_mode = text_mode
        self.encoding = encoding
        self.sync_directory = sync_directory
        self.mode = "w+" if self.text_mode else "w+b"
        self.part_path = None
        self.part_file = None
        self.directory_synced = None
        self._owns_part = False
        self._used = False

    def _remove_part(self):
        if self._owns_part:
            try:
                os.unlink(self.part_path)
            except FileNotFoundError:
                pass
            self._owns_part = False

    def _close_and_clean(self):
        # On an earlier failure, cleanup must not replace its useful exception.
        try:
            if self.part_file is not None:
                self.part_file.close()
        except BaseException:
            pass
        try:
            self._remove_part()
        except BaseException:
            pass

    def _open_part_file(self):
        # The fixed-size name also supports destination names near NAME_MAX.
        for _ in range(128):
            self.part_path = os.path.join(
                self.dest_dir, ".novel-" + os.urandom(16).hex() + ".tmp"
            )
            try:
                descriptor = os.open(self.part_path, _OPEN_FLAGS, self.file_perms)
            except FileExistsError:
                continue
            self._owns_part = True
            break
        else:
            raise FileExistsError(errno.EEXIST, "No unused atomic part name", self.dest_dir)

        try:
            if self.text_mode:
                self.part_file = os.fdopen(
                    descriptor, self.mode, encoding=self.encoding, newline="\n"
                )
            else:
                self.part_file = os.fdopen(descriptor, self.mode)
        except BaseException:
            try:
                os.close(descriptor)
            except BaseException:
                pass
            self._close_and_clean()
            raise

    def setup(self):
        if self._used:
            raise RuntimeError("AtomicSaver contexts cannot be reused")
        self._used = True
        if not self.overwrite and os.path.lexists(self.dest_path):
            raise FileExistsError(errno.EEXIST, "Overwrite disabled", self.dest_path)
        self._open_part_file()

    def __enter__(self):
        self.setup()
        return self.part_file

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._close_and_clean()
            return False
        try:
            # Same ordering as upstream: flush, file fsync, close, publication.
            # The enclosing guard additionally cleans failures in all steps.
            self.part_file.flush()
            os.fsync(self.part_file.fileno())
            self.part_file.close()
            atomic_rename(self.part_path, self.dest_path, overwrite=self.overwrite)
            self._owns_part = False
            self.directory_synced = (
                _sync_directory(self.dest_dir) if self.sync_directory else False
            )
        except BaseException:
            self._close_and_clean()
            raise
        return False
