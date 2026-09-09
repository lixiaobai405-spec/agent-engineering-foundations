from __future__ import annotations

import ctypes
import os
from pathlib import Path

_REPARSE_POINT = 0x400
_OWNER_SECURITY_INFORMATION = 0x00000001
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_FILE_ALL_ACCESS = 0x1F01FF
_GENERIC_ALL = 0x10000000
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_SE_FILE_OBJECT = 1
_SDDL_REVISION_1 = 1
_ACCESS_ALLOWED_ACE_TYPE = 0


class ArtifactPermissionError(RuntimeError):
    """Owner-only permission policy was violated."""


def apply_owner_only(path: Path) -> None:
    if os.name == "nt":
        _apply_windows_owner_only(path)
    else:
        mode = 0o700 if path.is_dir() else 0o600
        os.chmod(path, mode)
    verify_owner_only(path)


def verify_owner_only(path: Path) -> None:
    if os.name == "nt":
        _verify_windows_owner_only(path)
        return
    metadata = path.lstat()
    expected = 0o700 if path.is_dir() else 0o600
    getuid = getattr(os, "getuid", None)
    if getuid is None or metadata.st_uid != getuid():
        raise ArtifactPermissionError("artifact is not owned by the current user")
    if metadata.st_mode & 0o777 != expected:
        raise ArtifactPermissionError("artifact mode is not owner-only")


def is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if path.is_symlink():
        return True
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_ulong))


class _TokenUser(ctypes.Structure):
    _fields_ = (("User", _SidAndAttributes),)


def _apply_windows_owner_only(path: Path) -> None:
    sid = _current_user_sid_string()
    sddl = f"O:{sid}D:P(A;;FA;;;{sid})"
    descriptor = ctypes.c_void_p()
    descriptor_size = ctypes.c_ulong()
    if not _advapi32().ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl,
        _SDDL_REVISION_1,
        ctypes.byref(descriptor),
        ctypes.byref(descriptor_size),
    ):
        raise ArtifactPermissionError("failed to build owner-only security descriptor")
    try:
        owner = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        present = ctypes.c_int()
        defaulted = ctypes.c_int()
        if not _advapi32().GetSecurityDescriptorOwner(
            descriptor,
            ctypes.byref(owner),
            ctypes.byref(defaulted),
        ):
            raise ArtifactPermissionError("failed to read descriptor owner")
        if not _advapi32().GetSecurityDescriptorDacl(
            descriptor,
            ctypes.byref(present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        ):
            raise ArtifactPermissionError("failed to read descriptor DACL")
        status = _advapi32().SetNamedSecurityInfoW(
            str(path),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION
            | _DACL_SECURITY_INFORMATION
            | _PROTECTED_DACL_SECURITY_INFORMATION,
            owner,
            None,
            dacl,
            None,
        )
        if status != 0:
            raise ArtifactPermissionError("failed to apply owner-only DACL")
    finally:
        _kernel32().LocalFree(descriptor)


def _verify_windows_owner_only(path: Path) -> None:
    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    sacl = ctypes.c_void_p()
    security = ctypes.c_void_p()
    status = _advapi32().GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        ctypes.byref(group),
        ctypes.byref(dacl),
        ctypes.byref(sacl),
        ctypes.byref(security),
    )
    if status != 0:
        raise ArtifactPermissionError("failed to read artifact security descriptor")
    try:
        current = _sid_from_string(_current_user_sid_string())
        try:
            if not _advapi32().EqualSid(owner, current):
                raise ArtifactPermissionError("artifact owner is not the current user")
            if not _dacl_is_current_user_only(dacl, current):
                raise ArtifactPermissionError("artifact DACL is not current-user owner-only")
        finally:
            _kernel32().LocalFree(current)
    finally:
        _kernel32().LocalFree(security)


def _dacl_is_current_user_only(dacl: ctypes.c_void_p, current: ctypes.c_void_p) -> bool:
    dacl_address = dacl.value
    if dacl_address is None:
        return False
    count = ctypes.c_ushort.from_address(dacl_address + 4).value
    if count != 1:
        return False
    ace = ctypes.c_void_p()
    if not _advapi32().GetAce(dacl, 0, ctypes.byref(ace)):
        return False
    ace_address = ace.value
    if ace_address is None:
        return False
    ace_type = ctypes.c_ubyte.from_address(ace_address).value
    ace_flags = ctypes.c_ubyte.from_address(ace_address + 1).value
    mask = ctypes.c_ulong.from_address(ace_address + 4).value
    sid = ctypes.c_void_p(ace_address + 8)
    if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
        return False
    if ace_flags != 0:
        return False
    if mask & _FILE_ALL_ACCESS != _FILE_ALL_ACCESS and mask & _GENERIC_ALL != _GENERIC_ALL:
        return False
    return bool(_advapi32().EqualSid(sid, current))


def _current_user_sid_string() -> str:
    token = ctypes.c_void_p()
    process = _kernel32().GetCurrentProcess()
    if not _advapi32().OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
        raise ArtifactPermissionError("failed to open process token")
    try:
        size = ctypes.c_ulong(0)
        _advapi32().GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi32().GetTokenInformation(
            token,
            _TOKEN_USER,
            buffer,
            size,
            ctypes.byref(size),
        ):
            raise ArtifactPermissionError("failed to read token user")
        token_user = _TokenUser.from_buffer(buffer)
        return _sid_to_string(ctypes.c_void_p(token_user.User.Sid))
    finally:
        _kernel32().CloseHandle(token)


def _sid_to_string(sid: ctypes.c_void_p) -> str:
    text = ctypes.c_wchar_p()
    if not _advapi32().ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise ArtifactPermissionError("failed to convert SID")
    try:
        if text.value is None:
            raise ArtifactPermissionError("SID string was empty")
        return text.value
    finally:
        _kernel32().LocalFree(text)


def _sid_from_string(value: str) -> ctypes.c_void_p:
    sid = ctypes.c_void_p()
    if not _advapi32().ConvertStringSidToSidW(value, ctypes.byref(sid)):
        raise ArtifactPermissionError("failed to parse current-user SID")
    return sid


def _kernel32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.GetCurrentProcess.restype = ctypes.c_void_p
    library.GetCurrentProcess.argtypes = []
    library.CloseHandle.restype = ctypes.c_int
    library.CloseHandle.argtypes = [ctypes.c_void_p]
    library.LocalFree.restype = ctypes.c_void_p
    library.LocalFree.argtypes = [ctypes.c_void_p]
    return library


def _advapi32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    library.OpenProcessToken.restype = ctypes.c_int
    library.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.GetTokenInformation.restype = ctypes.c_int
    library.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    library.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    library.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = ctypes.c_int
    library.GetSecurityDescriptorOwner.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int),
    ]
    library.GetSecurityDescriptorOwner.restype = ctypes.c_int
    library.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int),
    ]
    library.GetSecurityDescriptorDacl.restype = ctypes.c_int
    library.SetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    library.SetNamedSecurityInfoW.restype = ctypes.c_ulong
    library.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.GetNamedSecurityInfoW.restype = ctypes.c_ulong
    library.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.EqualSid.restype = ctypes.c_int
    library.GetAce.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.GetAce.restype = ctypes.c_int
    library.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    library.ConvertSidToStringSidW.restype = ctypes.c_int
    library.ConvertStringSidToSidW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.ConvertStringSidToSidW.restype = ctypes.c_int
    return library
