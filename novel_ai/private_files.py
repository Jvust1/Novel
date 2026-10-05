"""Private local temporary files; native Windows ACLs are not POSIX mode bits.

Windows creates an exclusive file with a protected, single-user DACL before any
content is written, then checks the actual descriptor on that same handle.
Unsupported ACL filesystems fail closed. Callers still need trusted directories:
this does not secure parents, old files, Drive, or privileged backup/owner access.
"""
from __future__ import annotations

from functools import lru_cache
import os
import tempfile


@lru_cache(maxsize=1)
def _native():
    import ctypes as c
    from ctypes import wintypes as w
    from types import SimpleNamespace

    k = c.WinDLL('kernel32', use_last_error=True)
    a = c.WinDLL('advapi32', use_last_error=True)
    pointer = c.c_void_p
    pp = c.POINTER(pointer)
    signatures = [
        (k.GetCurrentProcess, [], w.HANDLE), (k.GetCurrentThread, [], w.HANDLE),
        (k.CloseHandle, [w.HANDLE], w.BOOL), (k.LocalFree, [pointer], pointer),
        (a.OpenProcessToken, [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL),
        (a.OpenThreadToken, [w.HANDLE, w.DWORD, w.BOOL, c.POINTER(w.HANDLE)], w.BOOL),
        (a.GetTokenInformation, [w.HANDLE, c.c_int, pointer, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
        (a.ConvertSidToStringSidW, [pointer, c.POINTER(w.LPWSTR)], w.BOOL),
        (a.ConvertStringSecurityDescriptorToSecurityDescriptorW,
         [w.LPCWSTR, w.DWORD, pp, c.POINTER(w.DWORD)], w.BOOL),
        (a.GetSecurityDescriptorOwner, [pointer, pp, c.POINTER(w.BOOL)], w.BOOL),
        (a.GetSecurityInfo, [w.HANDLE, c.c_int, w.DWORD, pp, pp, pp, pp, pp], w.DWORD),
        (a.GetSecurityDescriptorControl, [pointer, c.POINTER(w.WORD), c.POINTER(w.DWORD)], w.BOOL),
        (a.GetAclInformation, [pointer, pointer, w.DWORD, c.c_int], w.BOOL),
        (a.GetAce, [pointer, w.DWORD, pp], w.BOOL),
        (a.EqualSid, [pointer, pointer], w.BOOL),
    ]
    for function, args, result in signatures:
        function.argtypes, function.restype = args, result

    class Attributes(c.Structure):
        _fields_ = [('length', w.DWORD), ('descriptor', pointer), ('inherit', w.BOOL)]

    class AclSize(c.Structure):
        _fields_ = [('count', w.DWORD), ('used', w.DWORD), ('free', w.DWORD)]

    class Ace(c.Structure):
        _fields_ = [('kind', w.BYTE), ('flags', w.BYTE), ('size', w.WORD), ('mask', w.DWORD)]

    k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(Attributes), w.DWORD, w.DWORD, w.HANDLE]
    k.CreateFileW.restype = w.HANDLE
    return SimpleNamespace(c=c, w=w, k=k, a=a, Attributes=Attributes, AclSize=AclSize, Ace=Ace)


def _check(value, api):
    if not value:
        raise api.c.WinError(api.c.get_last_error())


def _effective_user_sid(api):
    c, w, k, a = api.c, api.w, api.k, api.a
    token = w.HANDLE()
    # Honour thread impersonation rather than silently granting another account.
    if not a.OpenThreadToken(k.GetCurrentThread(), 0x0008, True, c.byref(token)):
        if c.get_last_error() != 1008:  # ERROR_NO_TOKEN is the only fallback.
            raise c.WinError(c.get_last_error())
        _check(a.OpenProcessToken(k.GetCurrentProcess(), 0x0008, c.byref(token)), api)
    try:
        size = w.DWORD()
        a.GetTokenInformation(token, 1, None, 0, c.byref(size))  # TokenUser
        if c.get_last_error() != 122 or not size.value:
            raise c.WinError(c.get_last_error())
        buffer = c.create_string_buffer(size.value)
        _check(a.GetTokenInformation(token, 1, buffer, size, c.byref(size)), api)
        sid = c.c_void_p.from_buffer(buffer)
        text = w.LPWSTR()
        _check(a.ConvertSidToStringSidW(sid, c.byref(text)), api)
        try:
            return text.value
        finally:
            k.LocalFree(c.cast(text, c.c_void_p))
    finally:
        k.CloseHandle(token)


def _verify_handle(api, handle, expected_descriptor):
    c, w, k, a = api.c, api.w, api.k, api.a
    expected = c.c_void_p()
    defaulted = w.BOOL()
    _check(a.GetSecurityDescriptorOwner(expected_descriptor, c.byref(expected), c.byref(defaulted)), api)
    owner, dacl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
    error = a.GetSecurityInfo(handle, 1, 0x00000005, c.byref(owner), None,
                              c.byref(dacl), None, c.byref(descriptor))
    if error:
        raise c.WinError(error)
    try:
        control, revision = w.WORD(), w.DWORD()
        _check(a.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)), api)
        if not dacl.value or not control.value & 0x1000 or not a.EqualSid(owner, expected):
            raise PermissionError('private file owner/protected DACL verification failed')
        size = api.AclSize()
        _check(a.GetAclInformation(dacl, c.byref(size), c.sizeof(size), 2), api)
        if size.count != 1:
            raise PermissionError('private file has unexpected access entries')
        entry = c.c_void_p()
        _check(a.GetAce(dacl, 0, c.byref(entry)), api)
        ace = api.Ace.from_address(entry.value)
        sid = c.c_void_p(entry.value + 8)
        if ace.kind != 0 or ace.flags != 0 or ace.mask != 0x001F01FF or not a.EqualSid(sid, expected):
            raise PermissionError('private file access entry differs from current user full control')
    finally:
        k.LocalFree(descriptor)


def create_private_file(path):
    """Windows-only exclusive binary read/write fd with verified private ACL.

    The returned CRT fd owns the handle. No post-write chmod or ACL fallback.
    Existing files (including symlinks) are never opened or modified.
    """
    if os.name != 'nt':
        raise RuntimeError('native Windows private creation requires Windows')
    import msvcrt

    api = _native()
    c, k, a = api.c, api.k, api.a
    path = os.path.abspath(os.fspath(path))
    if not isinstance(path, str):
        raise TypeError('private file requires a text path')
    sid = _effective_user_sid(api)
    descriptor = c.c_void_p()
    _check(a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        'O:' + sid + 'D:P(A;;FA;;;' + sid + ')', 1, c.byref(descriptor), None), api)
    try:
        attributes = api.Attributes(c.sizeof(api.Attributes), descriptor, False)
        native_path = path if path.startswith('\\\\?\\') else (
            '\\\\?\\UNC\\' + path[2:] if path.startswith('\\\\') else '\\\\?\\' + path)
        handle = k.CreateFileW(native_path, 0xC0000000, 7, c.byref(attributes), 1, 0x00200080, None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            _verify_handle(api, handle, descriptor)
            fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY | os.O_NOINHERIT)
        except BaseException:
            k.CloseHandle(handle)
            try:
                os.unlink(path)
            except OSError:
                pass  # Keep the primary error; no content was ever written.
            raise
        return fd
    finally:
        k.LocalFree(descriptor)


def private_mkstemp(*, prefix, suffix, dir):
    """Same private temp contract: POSIX mkstemp, Windows security at creation."""
    if os.name != 'nt':
        return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=dir)
    for _ in range(128):
        path = os.path.join(os.fspath(dir), prefix + os.urandom(16).hex() + suffix)
        try:
            return create_private_file(path), path
        except FileExistsError:
            continue
    raise FileExistsError('no unused private temporary name')
