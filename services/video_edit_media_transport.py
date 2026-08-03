"""Pure transport-lane policy for Video Edit media."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

from services import telegram_transport


SHORT_MEDIA_MAX_SECONDS = 60.0
SHORT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
STREAM_CHUNK_BYTES = 512 * 1024
DELIVERY_BOUNDARY_ATTEMPTS = 4
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_DELIVERY_BOUNDARY_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{31,69}$")


def _effective_origin(url: str) -> tuple[str, str, int]:
    validated = telegram_transport.validate_api_url(url)
    if not validated:
        raise ValueError("invalid Telegram media request URL")
    parsed = urlsplit(validated)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("invalid Telegram media request URL")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), hostname, port


@dataclass(frozen=True)
class TelegramMediaConfig:
    """Validated, I/O-free configuration for credential-bearing media calls."""

    token: str = field(repr=False)
    api_root: str
    proxy_secret_header: str
    proxy_secret: str = field(repr=False)
    local_file_root: str
    local_media_path: str
    follow_redirects: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        telegram_transport.bot_method_url(
            api_root=self.api_root,
            token=self.token,
            method="getFile",
        )
        telegram_transport.validate_local_file_root(self.local_file_root)
        telegram_transport.validate_local_media_path(self.local_media_path)
        if (
            not isinstance(self.proxy_secret_header, str)
            or not _HEADER_NAME.fullmatch(self.proxy_secret_header)
        ):
            raise ValueError("invalid Telegram proxy secret header")
        if not isinstance(self.proxy_secret, str):
            raise ValueError("invalid Telegram proxy secret")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.proxy_secret):
            raise ValueError("invalid Telegram proxy secret")
        if self.proxy_secret != self.proxy_secret.strip():
            raise ValueError("invalid Telegram proxy secret")

    @property
    def is_local(self) -> bool:
        root = telegram_transport.normalize_api_root(self.api_root)
        return bool(root and not telegram_transport.is_cloud_api_url(root))

    def request_headers(self, *, request_url: str) -> dict[str, str]:
        request_origin = _effective_origin(request_url)
        if not self.is_local or not self.proxy_secret:
            return {}
        configured_root = telegram_transport.normalize_api_root(self.api_root)
        if request_origin != _effective_origin(configured_root):
            return {}
        return {self.proxy_secret_header: self.proxy_secret}


def select_media_lane(*, duration_seconds: float, size_bytes: int) -> str:
    duration = max(0.0, float(duration_seconds or 0.0))
    size = max(0, int(size_bytes or 0))
    if duration and size and duration <= SHORT_MEDIA_MAX_SECONDS and size <= SHORT_MEDIA_MAX_BYTES:
        return "short_media"
    return "large_media"


class MediaTransferError(RuntimeError):
    """A classified transfer failure whose message is always safe to expose."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "transfer_failed")
        super().__init__(f"media transfer failed: {self.reason}")


@dataclass(frozen=True)
class DownloadReceipt:
    """Evidence recorded only after a streamed artifact is atomically published."""

    path: str
    bytes_written: int
    sha256: str
    lane: str
    transport: str
    declared_bytes: int | None = None

    @property
    def actual_bytes(self) -> int:
        """Compatibility alias that makes actual-versus-declared evidence explicit."""

        return self.bytes_written


@dataclass(frozen=True)
class DeliveryReceipt:
    """Immutable evidence from one accepted Telegram artifact delivery."""

    message_id: str
    file_id: str
    delivery_method: str
    bytes_sent: int
    sha256: str


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


if os.name == "nt":
    _FILE_ATTRIBUTE_DIRECTORY = 0x10
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_READ_ATTRIBUTES = 0x0080
    _DELETE = 0x00010000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _CREATE_NEW = 1
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _DUPLICATE_SAME_ACCESS = 0x00000002
    _FILE_RENAME_INFO_CLASS = 3
    _FILE_DISPOSITION_INFO_CLASS = 4
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _WinFileInformation(ctypes.Structure):
        _fields_ = (
            ("file_attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("last_access_time", wintypes.FILETIME),
            ("last_write_time", wintypes.FILETIME),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        )

    class _WinFileRenameInformation(ctypes.Structure):
        _fields_ = (
            ("replace_if_exists", wintypes.BOOLEAN),
            ("root_directory", wintypes.HANDLE),
            ("file_name_length", wintypes.DWORD),
            ("file_name", ctypes.c_wchar * 1),
        )

    class _WinFileDispositionInformation(ctypes.Structure):
        _fields_ = (("delete_file", wintypes.BOOLEAN),)

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _CreateFileW.restype = wintypes.HANDLE
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    _CloseHandle.restype = wintypes.BOOL
    _GetFileInformationByHandle = _kernel32.GetFileInformationByHandle
    _GetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_WinFileInformation),
    )
    _GetFileInformationByHandle.restype = wintypes.BOOL
    _GetFinalPathNameByHandleW = _kernel32.GetFinalPathNameByHandleW
    _GetFinalPathNameByHandleW.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    _GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _GetCurrentProcess = _kernel32.GetCurrentProcess
    _GetCurrentProcess.argtypes = ()
    _GetCurrentProcess.restype = wintypes.HANDLE
    _DuplicateHandle = _kernel32.DuplicateHandle
    _DuplicateHandle.argtypes = (
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    _DuplicateHandle.restype = wintypes.BOOL
    _SetFileInformationByHandle = _kernel32.SetFileInformationByHandle
    _SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _SetFileInformationByHandle.restype = wintypes.BOOL


def _win_error() -> OSError:
    return OSError(ctypes.get_last_error(), "Win32 filesystem operation failed")


def _win_close_handle(handle: int | None) -> None:
    if handle is not None and not _CloseHandle(handle):
        raise _win_error()


def _win_open_directory(path: Path) -> int:
    handle = _CreateFileW(
        str(path),
        _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise _win_error()
    return int(handle)


def _win_create_partial(path: Path) -> int:
    handle = _CreateFileW(
        str(path),
        _GENERIC_WRITE | _DELETE | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _CREATE_NEW,
        _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise _win_error()
    return int(handle)


def _win_duplicate_handle(handle: int) -> int:
    duplicate = wintypes.HANDLE()
    process = _GetCurrentProcess()
    if not _DuplicateHandle(
        process,
        handle,
        process,
        ctypes.byref(duplicate),
        0,
        False,
        _DUPLICATE_SAME_ACCESS,
    ):
        raise _win_error()
    return int(duplicate.value)


def _win_file_information(handle: int) -> _WinFileInformation:
    information = _WinFileInformation()
    if not _GetFileInformationByHandle(handle, ctypes.byref(information)):
        raise _win_error()
    return information


def _win_identity(information: _WinFileInformation) -> tuple[int, int]:
    file_index = (int(information.file_index_high) << 32) | int(
        information.file_index_low
    )
    return int(information.volume_serial_number), file_index


def _win_is_plain_directory(information: _WinFileInformation) -> bool:
    return bool(information.file_attributes & _FILE_ATTRIBUTE_DIRECTORY) and not bool(
        information.file_attributes & _REPARSE_POINT
    )


def _win_is_plain_regular_file(information: _WinFileInformation) -> bool:
    return not bool(
        information.file_attributes
        & (_FILE_ATTRIBUTE_DIRECTORY | _REPARSE_POINT)
    )


def _win_final_path(handle: int) -> str:
    size = 32768
    buffer = ctypes.create_unicode_buffer(size)
    length = _GetFinalPathNameByHandleW(handle, buffer, size, 0)
    if not length or length >= size:
        raise _win_error()
    path = buffer.value
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return os.path.normcase(os.path.abspath(path))


def _win_rename_handle(handle: int, destination: Path) -> None:
    encoded_name = str(destination).encode("utf-16-le")
    name_offset = _WinFileRenameInformation.file_name.offset
    size = ctypes.sizeof(_WinFileRenameInformation) + len(encoded_name)
    buffer = ctypes.create_string_buffer(size)
    information = _WinFileRenameInformation.from_buffer(buffer)
    information.replace_if_exists = True
    information.root_directory = None
    information.file_name_length = len(encoded_name)
    ctypes.memmove(ctypes.addressof(buffer) + name_offset, encoded_name, len(encoded_name))
    if not _SetFileInformationByHandle(
        handle,
        _FILE_RENAME_INFO_CLASS,
        buffer,
        size,
    ):
        raise _win_error()


def _win_delete_handle(handle: int) -> None:
    information = _WinFileDispositionInformation(True)
    if not _SetFileInformationByHandle(
        handle,
        _FILE_DISPOSITION_INFO_CLASS,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise _win_error()


def _file_identity(result: os.stat_result) -> tuple[int, int]:
    return int(result.st_dev), int(result.st_ino)


def _is_reparse_point(result: os.stat_result) -> bool:
    return bool(getattr(result, "st_file_attributes", 0) & _REPARSE_POINT)


def _is_plain_directory(result: os.stat_result) -> bool:
    return stat.S_ISDIR(result.st_mode) and not _is_reparse_point(result)


def _is_plain_regular_file(result: os.stat_result) -> bool:
    return stat.S_ISREG(result.st_mode) and not _is_reparse_point(result)


class _DestinationGuard:
    """Keep destination operations bound to one validated parent directory.

    POSIX operations use a retained directory descriptor and relative basenames.
    Windows retains no-delete-share handles for the captured directory and exact
    partial, then renames/deletes that partial by handle.  No platform falls
    back to an unanchored path-only publish operation.
    """

    def __init__(self, destination: str | os.PathLike[str]) -> None:
        self.directory_fd: int | None = None
        self.windows_parent_handle: int | None = None
        self.windows_parent_identity: tuple[int, int] | None = None
        self.windows_partial_handle: int | None = None
        self.windows_partial_identity: tuple[int, int] | None = None
        self.partial_identity: tuple[int, int] | None = None
        try:
            raw_path = os.fspath(destination)
            self.final_path = Path(os.path.abspath(raw_path))
            self.parent = self.final_path.parent
            self.final_name = self.final_path.name
            self.partial_name = self.final_name + ".partial"
            self.partial_path = self.parent / self.partial_name
            if not self.final_name:
                raise OSError

            parent_realpath = os.path.realpath(self.parent)
            parent_abspath = os.path.abspath(self.parent)
            if os.path.normcase(parent_realpath) != os.path.normcase(parent_abspath):
                raise OSError
            parent_result = os.lstat(self.parent)
            if not _is_plain_directory(parent_result):
                raise OSError
            self.parent_identity = _file_identity(parent_result)
            self.parent_realpath = parent_realpath

            if os.name == "posix" and all(
                hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")
            ):
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                self.directory_fd = os.open(str(self.parent), flags)
                opened_parent = os.fstat(self.directory_fd)
                if (
                    not _is_plain_directory(opened_parent)
                    or _file_identity(opened_parent) != self.parent_identity
                    or opened_parent.st_uid != os.getuid()
                ):
                    raise OSError
            elif os.name == "nt":
                self.windows_parent_handle = _win_open_directory(self.parent)
                opened_parent = _win_file_information(self.windows_parent_handle)
                self.windows_parent_identity = _win_identity(opened_parent)
                if (
                    not _win_is_plain_directory(opened_parent)
                    or self.windows_parent_identity[1] != self.parent_identity[1]
                    or _win_final_path(self.windows_parent_handle)
                    != os.path.normcase(os.path.abspath(self.parent_realpath))
                ):
                    raise OSError
            else:
                raise OSError
            self._verify_parent()
            self._validate_final()
            if self._stat_name(self.partial_name) is not None:
                raise FileExistsError
        except MediaTransferError:
            self.close()
            raise
        except (OSError, TypeError, ValueError):
            self.close()
            raise MediaTransferError("invalid_destination") from None

    def close(self) -> None:
        self._close_windows_partial()
        if self.directory_fd is not None:
            try:
                os.close(self.directory_fd)
            except OSError:
                pass
            self.directory_fd = None
        if self.windows_parent_handle is not None:
            handle = self.windows_parent_handle
            self.windows_parent_handle = None
            try:
                _win_close_handle(handle)
            except OSError:
                pass

    def _close_windows_partial(self) -> None:
        if self.windows_partial_handle is not None:
            handle = self.windows_partial_handle
            self.windows_partial_handle = None
            try:
                _win_close_handle(handle)
            except OSError:
                pass
        self.windows_partial_identity = None

    def _verify_parent(self) -> None:
        try:
            path_result = os.lstat(self.parent)
            if (
                not _is_plain_directory(path_result)
                or _file_identity(path_result) != self.parent_identity
                or os.path.normcase(os.path.realpath(self.parent))
                != os.path.normcase(self.parent_realpath)
            ):
                raise OSError
            if self.directory_fd is not None:
                opened_parent = os.fstat(self.directory_fd)
                if (
                    not _is_plain_directory(opened_parent)
                    or _file_identity(opened_parent) != self.parent_identity
                    or opened_parent.st_uid != os.getuid()
                ):
                    raise OSError
            elif os.name == "nt":
                if (
                    self.windows_parent_handle is None
                    or self.windows_parent_identity is None
                ):
                    raise OSError
                opened_parent = _win_file_information(self.windows_parent_handle)
                if (
                    not _win_is_plain_directory(opened_parent)
                    or _win_identity(opened_parent) != self.windows_parent_identity
                    or self.windows_parent_identity[1] != self.parent_identity[1]
                    or _win_final_path(self.windows_parent_handle)
                    != os.path.normcase(os.path.abspath(self.parent_realpath))
                ):
                    raise OSError
            else:
                raise OSError
        except (OSError, ValueError):
            raise MediaTransferError("invalid_destination") from None

    def _stat_name(self, name: str) -> os.stat_result | None:
        self._verify_parent()
        try:
            if self.directory_fd is not None:
                result = os.stat(
                    name, dir_fd=self.directory_fd, follow_symlinks=False
                )
            else:
                result = os.lstat(self.parent / name)
        except FileNotFoundError:
            result = None
        except OSError:
            raise MediaTransferError("invalid_destination") from None
        self._verify_parent()
        return result

    def _validate_final(self) -> None:
        result = self._stat_name(self.final_name)
        if result is not None and not _is_plain_regular_file(result):
            raise MediaTransferError("invalid_destination")

    def open_partial(self) -> int:
        self._verify_parent()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd: int | None = None
        io_handle: int | None = None
        try:
            if self.directory_fd is not None:
                fd = os.open(
                    self.partial_name, flags, 0o600, dir_fd=self.directory_fd
                )
            elif os.name == "nt":
                self.windows_partial_handle = _win_create_partial(self.partial_path)
                partial_information = _win_file_information(
                    self.windows_partial_handle
                )
                if not _win_is_plain_regular_file(partial_information):
                    raise OSError
                self.windows_partial_identity = _win_identity(partial_information)
                io_handle = _win_duplicate_handle(self.windows_partial_handle)
                fd = msvcrt.open_osfhandle(
                    io_handle,
                    os.O_WRONLY | getattr(os, "O_BINARY", 0),
                )
                io_handle = None
            else:
                raise OSError
            opened = os.fstat(fd)
            if not _is_plain_regular_file(opened):
                raise OSError
            if self.directory_fd is not None and opened.st_uid != os.getuid():
                raise OSError
            identity = _file_identity(opened)
            self.partial_identity = identity
            if (
                os.name == "nt"
                and (
                    self.windows_partial_identity is None
                    or self.windows_partial_identity[1] != identity[1]
                )
            ):
                raise OSError
            self._verify_parent()
            named = self._stat_name(self.partial_name)
            if (
                named is None
                or not _is_plain_regular_file(named)
                or _file_identity(named) != identity
            ):
                raise OSError
            return fd
        except Exception as error:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            elif io_handle is not None:
                try:
                    _win_close_handle(io_handle)
                except OSError:
                    pass
            self._cleanup_exact_partial()
            if isinstance(error, MediaTransferError):
                raise
            raise MediaTransferError("invalid_destination") from None

    def verify_partial(self, fd: int | None = None) -> None:
        try:
            if self.partial_identity is None:
                raise OSError
            if fd is not None:
                opened = os.fstat(fd)
                if (
                    not _is_plain_regular_file(opened)
                    or _file_identity(opened) != self.partial_identity
                ):
                    raise OSError
            if os.name == "nt":
                if (
                    self.windows_partial_handle is None
                    or self.windows_partial_identity is None
                ):
                    raise OSError
                opened = _win_file_information(self.windows_partial_handle)
                if (
                    not _win_is_plain_regular_file(opened)
                    or _win_identity(opened) != self.windows_partial_identity
                    or self.windows_partial_identity[1] != self.partial_identity[1]
                ):
                    raise OSError
            named = self._stat_name(self.partial_name)
            if (
                named is None
                or not _is_plain_regular_file(named)
                or _file_identity(named) != self.partial_identity
            ):
                raise OSError
        except (OSError, ValueError):
            raise MediaTransferError("invalid_destination") from None

    def _cleanup_exact_partial(self) -> None:
        if self.partial_identity is None:
            return
        try:
            if self.directory_fd is not None:
                opened_parent = os.fstat(self.directory_fd)
                if (
                    not _is_plain_directory(opened_parent)
                    or _file_identity(opened_parent) != self.parent_identity
                    or opened_parent.st_uid != os.getuid()
                ):
                    return
                try:
                    named = os.stat(
                        self.partial_name,
                        dir_fd=self.directory_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    named = None
            elif os.name == "nt":
                self._verify_parent()
                if (
                    self.windows_partial_handle is None
                    or self.windows_partial_identity is None
                ):
                    return
                opened = _win_file_information(self.windows_partial_handle)
                if (
                    not _win_is_plain_regular_file(opened)
                    or _win_identity(opened) != self.windows_partial_identity
                    or self.windows_partial_identity[1] != self.partial_identity[1]
                ):
                    return
                named = self._stat_name(self.partial_name)
            else:
                return
            if (
                named is None
                or not _is_plain_regular_file(named)
                or _file_identity(named) != self.partial_identity
            ):
                return
            if self.directory_fd is not None:
                os.unlink(self.partial_name, dir_fd=self.directory_fd)
            elif os.name == "nt":
                _win_delete_handle(self.windows_partial_handle)
        except (OSError, MediaTransferError):
            pass
        finally:
            self._close_windows_partial()
            self.partial_identity = None

    def cleanup_partial(self) -> None:
        self._cleanup_exact_partial()

    def publish(self) -> None:
        self._verify_parent()
        self._validate_final()
        self.verify_partial()
        try:
            if self.directory_fd is not None:
                os.replace(
                    self.partial_name,
                    self.final_name,
                    src_dir_fd=self.directory_fd,
                    dst_dir_fd=self.directory_fd,
                )
            elif os.name == "nt":
                if (
                    self.windows_parent_handle is None
                    or self.windows_partial_handle is None
                ):
                    raise OSError
                _win_rename_handle(
                    self.windows_partial_handle,
                    self.final_path,
                )
            else:
                raise OSError
        except OSError:
            raise MediaTransferError("publish_failed") from None
        self._verify_parent()
        published = self._stat_name(self.final_name)
        if (
            published is None
            or not _is_plain_regular_file(published)
            or _file_identity(published) != self.partial_identity
        ):
            raise MediaTransferError("publish_failed")
        self._close_windows_partial()
        self.partial_identity = None


def _get_file_result(payload: object) -> tuple[str, int | None]:
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise MediaTransferError("get_file_invalid")
    result = payload.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("file_path"), str):
        raise MediaTransferError("get_file_invalid")
    file_path = result["file_path"]
    declared = result.get("file_size")
    if declared is not None and (isinstance(declared, bool) or not isinstance(declared, int) or declared < 0):
        raise MediaTransferError("get_file_invalid")
    return file_path, declared


def _transfer_url(config: TelegramMediaConfig, file_path: str) -> tuple[str, str]:
    try:
        if config.is_local:
            return (
                telegram_transport.local_media_url(
                    api_root=config.api_root,
                    token=config.token,
                    absolute_file_path=file_path,
                    file_root=config.local_file_root,
                    media_path=config.local_media_path,
                ),
                "localfile",
            )
        return (
            telegram_transport.bot_file_url(
                api_root=config.api_root,
                token=config.token,
                file_path=file_path,
            ),
            "file",
        )
    except (TypeError, ValueError):
        raise MediaTransferError("get_file_invalid") from None


def _guard_before_chunk(
    *,
    destination_guard: _DestinationGuard,
    cancel_requested: Callable[[], bool] | None,
    deadline_monotonic: float | None,
    monotonic: Callable[[], float],
    partial_parent: Path,
    workspace_reserve_bytes: int,
    disk_usage: Callable[[str | os.PathLike[str]], Any],
    free_bytes: Callable[[str | os.PathLike[str]], int] | None,
    required_bytes: int = 0,
) -> None:
    destination_guard._verify_parent()
    if cancel_requested is not None and cancel_requested():
        raise MediaTransferError("cancelled")
    if deadline_monotonic is not None and monotonic() >= deadline_monotonic:
        raise MediaTransferError("deadline_exceeded")
    try:
        if workspace_reserve_bytes > 0 or required_bytes > 0:
            available = (
                int(free_bytes(partial_parent))
                if free_bytes is not None
                else int(disk_usage(partial_parent).free)
            )
            if available < workspace_reserve_bytes + required_bytes:
                raise MediaTransferError("insufficient_disk")
    except MediaTransferError:
        raise
    except Exception:
        raise MediaTransferError("disk_check_failed") from None


def _default_retry_backoff(attempt: int) -> float:
    return 0.1 * (2 ** (attempt - 1))


def _close_streams(*resources: object) -> None:
    seen: set[int] = set()
    first_error: Exception | None = None
    for resource in resources:
        identity = id(resource)
        if resource is None or identity in seen:
            continue
        seen.add(identity)
        close = getattr(resource, "close", None)
        if callable(close):
            try:
                close()
            except Exception as error:
                if first_error is None:
                    first_error = error
    if first_error is not None:
        raise first_error


def download_file_to_path(
    *,
    config: TelegramMediaConfig,
    file_id: str,
    destination: str | os.PathLike[str],
    get_file_json: Callable[..., object] | None = None,
    stream_bytes: Callable[..., Iterable[bytes]] | None = None,
    expected_bytes: int | None = None,
    expected_size: int | None = None,
    open_json: Callable[..., object] | None = None,
    open_stream: Callable[..., Iterable[bytes]] | None = None,
    progress_callback: Callable[[int, int | None], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    deadline_monotonic: float | None = None,
    workspace_reserve_bytes: int = 0,
    hard_max_bytes: int | None = None,
    disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
    free_bytes: Callable[[str | os.PathLike[str]], int] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    max_attempts: int = 2,
    retry_backoff: Callable[[int], float] = _default_retry_backoff,
    max_retry_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadReceipt:
    """Stream a Telegram file into a sibling partial, then publish it atomically.

    The injected functions keep network clients out of this policy layer.  They
    receive explicit headers and ``follow_redirects=False`` so callers cannot
    accidentally forward a local proxy credential to a redirect origin.
    """

    if not isinstance(config, TelegramMediaConfig):
        raise MediaTransferError("invalid_config")
    if not isinstance(file_id, str) or not file_id or len(file_id) > 512 or any(ord(c) < 32 for c in file_id):
        raise MediaTransferError("invalid_file_id")
    if expected_size is not None:
        if expected_bytes is not None and expected_bytes != expected_size:
            raise MediaTransferError("invalid_expected_size")
        expected_bytes = expected_size
    if expected_bytes is not None and (isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0):
        raise MediaTransferError("invalid_expected_size")
    if hard_max_bytes is not None and (isinstance(hard_max_bytes, bool) or not isinstance(hard_max_bytes, int) or hard_max_bytes < 1):
        raise MediaTransferError("invalid_size_limit")
    if isinstance(workspace_reserve_bytes, bool) or not isinstance(workspace_reserve_bytes, int) or workspace_reserve_bytes < 0:
        raise MediaTransferError("invalid_disk_reserve")
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or not 1 <= max_attempts <= 3
    ):
        raise MediaTransferError("invalid_max_attempts")
    if (
        not callable(retry_backoff)
        or not callable(sleep)
        or isinstance(max_retry_delay_seconds, bool)
        or not isinstance(max_retry_delay_seconds, (int, float))
        or not math.isfinite(float(max_retry_delay_seconds))
        or max_retry_delay_seconds <= 0
    ):
        raise MediaTransferError("invalid_retry_policy")
    attempts = max_attempts
    get_file_json = get_file_json or open_json
    stream_bytes = stream_bytes or open_stream
    if not callable(get_file_json) or not callable(stream_bytes):
        raise MediaTransferError("invalid_transport")
    if free_bytes is not None and not callable(free_bytes):
        raise MediaTransferError("invalid_disk_guard")
    destination_guard = _DestinationGuard(destination)
    try:
        for attempt in range(attempts):
            created_partial = False
            stream_complete = False
            try:
                method_url = telegram_transport.bot_method_url(
                    api_root=config.api_root, token=config.token, method="getFile"
                )
                method_headers = config.request_headers(request_url=method_url)
                payload = get_file_json(
                    url=method_url,
                    headers=method_headers,
                    follow_redirects=False,
                    json={"file_id": file_id},
                )
                file_path, declared_bytes = _get_file_result(payload)
                if (
                    expected_bytes is not None
                    and declared_bytes is not None
                    and declared_bytes != expected_bytes
                ):
                    raise MediaTransferError("size_mismatch")
                transfer_url, transport = _transfer_url(config, file_path)
                headers = config.request_headers(request_url=transfer_url)

                fd = destination_guard.open_partial()
                created_partial = True
                actual_bytes = 0
                digest = hashlib.sha256()
                with os.fdopen(fd, "wb", closefd=True) as output:
                    stream_resource: object | None = None
                    chunks: object | None = None
                    active_error = False
                    try:
                        stream_resource = stream_bytes(
                            url=transfer_url,
                            headers=headers,
                            follow_redirects=False,
                            chunk_size=STREAM_CHUNK_BYTES,
                        )
                        chunks = iter(stream_resource)
                        while True:
                            _guard_before_chunk(
                                destination_guard=destination_guard,
                                cancel_requested=cancel_requested,
                                deadline_monotonic=deadline_monotonic,
                                monotonic=monotonic,
                                partial_parent=destination_guard.parent,
                                workspace_reserve_bytes=workspace_reserve_bytes,
                                required_bytes=0,
                                disk_usage=disk_usage,
                                free_bytes=free_bytes,
                            )
                            try:
                                chunk = next(chunks)
                            except StopIteration:
                                stream_complete = True
                                break
                            if not isinstance(chunk, bytes) or len(chunk) > STREAM_CHUNK_BYTES:
                                raise MediaTransferError("stream_chunk_invalid")
                            if not chunk:
                                continue
                            next_size = actual_bytes + len(chunk)
                            if hard_max_bytes is not None and next_size > hard_max_bytes:
                                raise MediaTransferError("size_limit_exceeded")
                            if declared_bytes is not None and next_size > declared_bytes:
                                raise MediaTransferError("size_mismatch")
                            if expected_bytes is not None and next_size > expected_bytes:
                                raise MediaTransferError("size_mismatch")
                            _guard_before_chunk(
                                destination_guard=destination_guard,
                                cancel_requested=cancel_requested,
                                deadline_monotonic=deadline_monotonic,
                                monotonic=monotonic,
                                partial_parent=destination_guard.parent,
                                workspace_reserve_bytes=workspace_reserve_bytes,
                                required_bytes=len(chunk),
                                disk_usage=disk_usage,
                                free_bytes=free_bytes,
                            )
                            destination_guard.verify_partial(output.fileno())
                            output.write(chunk)
                            digest.update(chunk)
                            actual_bytes = next_size
                            if progress_callback is not None:
                                progress_callback(
                                    actual_bytes,
                                    declared_bytes
                                    if declared_bytes is not None
                                    else expected_bytes,
                                )
                        output.flush()
                        os.fsync(output.fileno())
                        destination_guard.verify_partial(output.fileno())
                    except Exception:
                        active_error = True
                        raise
                    finally:
                        try:
                            _close_streams(chunks, stream_resource)
                        except Exception:
                            if not active_error:
                                raise
                if actual_bytes < 1:
                    raise MediaTransferError("empty_file")
                final_expected = (
                    expected_bytes if expected_bytes is not None else declared_bytes
                )
                if final_expected is not None and actual_bytes != final_expected:
                    raise MediaTransferError("size_mismatch")
                destination_guard.publish()
                return DownloadReceipt(
                    path=str(destination_guard.final_path),
                    bytes_written=actual_bytes,
                    sha256=digest.hexdigest(),
                    lane="large_media",
                    transport=transport,
                    declared_bytes=(
                        declared_bytes
                        if declared_bytes is not None
                        else expected_bytes
                    ),
                )
            except MediaTransferError:
                if created_partial:
                    destination_guard.cleanup_partial()
                raise
            except Exception:
                if created_partial:
                    destination_guard.cleanup_partial()
                if stream_complete or attempt + 1 >= attempts:
                    raise MediaTransferError("stream_failed") from None
                try:
                    delay = retry_backoff(attempt + 1)
                    if (
                        isinstance(delay, bool)
                        or not isinstance(delay, (int, float))
                        or not math.isfinite(float(delay))
                        or delay <= 0
                    ):
                        raise ValueError
                    sleep(min(float(delay), float(max_retry_delay_seconds)))
                except Exception:
                    raise MediaTransferError("invalid_retry_policy") from None
        raise MediaTransferError("stream_failed")
    finally:
        destination_guard.close()


def _stat_fingerprint(result: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(result.st_dev),
        int(result.st_ino),
        int(result.st_size),
        int(result.st_mtime_ns),
        int(result.st_ctime_ns),
    )


class _ArtifactSnapshot:
    """Bind one delivery to a plain file and its captured plain parent."""

    def __init__(self, artifact: str | os.PathLike[str]) -> None:
        try:
            raw_path = os.fspath(artifact)
            self.path = Path(os.path.abspath(raw_path))
            self.parent = self.path.parent
            self.filename = self.path.name
            if (
                not self.filename
                or len(self.filename.encode("utf-8")) > 255
                or any(ord(char) < 32 or ord(char) == 127 for char in self.filename)
                or any(char in self.filename for char in ('"', "\\"))
            ):
                raise OSError
            parent_abspath = os.path.abspath(self.parent)
            self.parent_realpath = os.path.realpath(self.parent)
            if os.path.normcase(self.parent_realpath) != os.path.normcase(
                parent_abspath
            ):
                raise OSError
            parent_result = os.lstat(self.parent)
            if not _is_plain_directory(parent_result):
                raise OSError
            self.parent_identity = _file_identity(parent_result)
            file_result = os.lstat(self.path)
            if not _is_plain_regular_file(file_result) or file_result.st_size < 1:
                raise OSError
            self.file_fingerprint = _stat_fingerprint(file_result)
            self.size = int(file_result.st_size)
            self.verify()
        except (OSError, TypeError, ValueError, UnicodeError):
            raise MediaTransferError("invalid_artifact") from None

    def verify(self, opened: object | None = None) -> None:
        try:
            parent_result = os.lstat(self.parent)
            if (
                not _is_plain_directory(parent_result)
                or _file_identity(parent_result) != self.parent_identity
                or os.path.normcase(os.path.realpath(self.parent))
                != os.path.normcase(self.parent_realpath)
            ):
                raise OSError
            path_result = os.lstat(self.path)
            if (
                not _is_plain_regular_file(path_result)
                or _stat_fingerprint(path_result) != self.file_fingerprint
            ):
                raise OSError
            if opened is not None:
                fileno = getattr(opened, "fileno", None)
                if not callable(fileno):
                    raise OSError
                opened_result = os.fstat(fileno())
                if (
                    not _is_plain_regular_file(opened_result)
                    or _stat_fingerprint(opened_result) != self.file_fingerprint
                ):
                    raise OSError
        except (OSError, TypeError, ValueError):
            raise MediaTransferError("invalid_artifact") from None


class _MultipartArtifactBody:
    """Single-use multipart iterable with bounded artifact reads."""

    def __init__(
        self,
        *,
        snapshot: _ArtifactSnapshot,
        header: bytes,
        footer: bytes,
    ) -> None:
        snapshot.verify()
        self._snapshot = snapshot
        self._header = header
        self._footer = footer
        self._file: object | None = None
        self._started = False
        self.closed = False
        self.complete = False
        self.bytes_sent = 0
        self._digest = hashlib.sha256()

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()

    def __iter__(self) -> Iterable[bytes]:
        if self._started or self.closed:
            raise MediaTransferError("invalid_artifact")
        self._started = True
        return self._iterate()

    def _iterate(self) -> Iterable[bytes]:
        try:
            self._snapshot.verify()
            self._file = open(self._snapshot.path, "rb", buffering=0)
            self._snapshot.verify(self._file)
            yield self._header
            while True:
                self._snapshot.verify(self._file)
                chunk = self._file.read(STREAM_CHUNK_BYTES)
                self._snapshot.verify(self._file)
                if not isinstance(chunk, bytes) or len(chunk) > STREAM_CHUNK_BYTES:
                    raise MediaTransferError("invalid_artifact")
                if not chunk:
                    break
                next_size = self.bytes_sent + len(chunk)
                if next_size > self._snapshot.size:
                    raise MediaTransferError("invalid_artifact")
                self._digest.update(chunk)
                self.bytes_sent = next_size
                yield chunk
            if self.bytes_sent != self._snapshot.size:
                raise MediaTransferError("invalid_artifact")
            self.complete = True
            yield self._footer
        finally:
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        opened = self._file
        self._file = None
        if opened is not None:
            close = getattr(opened, "close", None)
            if callable(close):
                close()


def _multipart_text(value: object, *, reason: str, maximum: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MediaTransferError(reason)
    text = str(value)
    if (
        not text
        or len(text) > maximum
        or text != text.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in text)
    ):
        raise MediaTransferError(reason)
    return text


def _delivery_header(
    *,
    boundary: str,
    method_name: str,
    chat_id: str,
    caption: str,
    snapshot: _ArtifactSnapshot,
) -> bytes:
    media_field = "video" if method_name == "sendVideo" else "document"
    content_type = (
        "video/mp4" if snapshot.path.suffix.lower() == ".mp4" else "application/octet-stream"
    )
    parts = [
        f"--{boundary}\r\n",
        'Content-Disposition: form-data; name="chat_id"\r\n\r\n',
        f"{chat_id}\r\n",
    ]
    if caption:
        parts.extend(
            (
                f"--{boundary}\r\n",
                'Content-Disposition: form-data; name="caption"\r\n\r\n',
                f"{caption}\r\n",
            )
        )
    parts.extend(
        (
            f"--{boundary}\r\n",
            f'Content-Disposition: form-data; name="{media_field}"; filename="{snapshot.filename}"\r\n',
            f"Content-Type: {content_type}\r\n\r\n",
        )
    )
    return "".join(parts).encode("utf-8")


def _default_delivery_boundary() -> str:
    return f"ToanAasBoundary{secrets.token_hex(24)}"


def _artifact_contains_boundary(
    *,
    snapshot: _ArtifactSnapshot,
    boundary: str,
) -> bool:
    needle = boundary.encode("ascii")
    overlap = b""
    opened: object | None = None
    try:
        snapshot.verify()
        opened = open(snapshot.path, "rb", buffering=0)
        snapshot.verify(opened)
        while True:
            snapshot.verify(opened)
            chunk = opened.read(STREAM_CHUNK_BYTES)
            snapshot.verify(opened)
            if not isinstance(chunk, bytes) or len(chunk) > STREAM_CHUNK_BYTES:
                raise MediaTransferError("invalid_artifact")
            if not chunk:
                snapshot.verify(opened)
                snapshot.verify()
                return False
            window = overlap + chunk
            if needle in window:
                snapshot.verify(opened)
                snapshot.verify()
                return True
            overlap = window[-(len(needle) - 1) :]
    except MediaTransferError:
        raise
    except Exception:
        raise MediaTransferError("invalid_artifact") from None
    finally:
        if opened is not None:
            try:
                opened.close()
            except Exception:
                pass


def _select_delivery_boundary(
    *,
    snapshot: _ArtifactSnapshot,
    boundary_factory: Callable[[], object],
    used_boundaries: set[str],
) -> str:
    for _attempt in range(DELIVERY_BOUNDARY_ATTEMPTS):
        try:
            boundary = boundary_factory()
        except Exception:
            raise MediaTransferError("invalid_boundary") from None
        if not isinstance(boundary, str) or not _DELIVERY_BOUNDARY_TOKEN.fullmatch(
            boundary
        ):
            raise MediaTransferError("invalid_boundary")
        if boundary in used_boundaries:
            continue
        if _artifact_contains_boundary(snapshot=snapshot, boundary=boundary):
            continue
        return boundary
    raise MediaTransferError("invalid_boundary")


def _parse_delivery_receipt(
    payload: object,
    *,
    method_name: str,
    body: _MultipartArtifactBody,
) -> DeliveryReceipt:
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise MediaTransferError("delivery_unknown")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise MediaTransferError("delivery_unknown")
    message_id = result.get("message_id")
    if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
        raise MediaTransferError("delivery_unknown")
    media_field = "video" if method_name == "sendVideo" else "document"
    media = result.get(media_field)
    if not isinstance(media, Mapping):
        raise MediaTransferError("delivery_unknown")
    file_id = media.get("file_id")
    if (
        not isinstance(file_id, str)
        or not file_id.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in file_id)
    ):
        raise MediaTransferError("delivery_unknown")
    if not body.complete or body.bytes_sent < 1:
        raise MediaTransferError("delivery_unknown")
    return DeliveryReceipt(
        message_id=str(message_id).strip(),
        file_id=file_id,
        delivery_method=method_name,
        bytes_sent=body.bytes_sent,
        sha256=body.sha256,
    )


_PREACCEPTANCE_REJECTION_STATUS_CODES = frozenset(
    (400, 401, 403, 404, 405, 411, 413, 414, 415, 422)
)


def _deterministic_rejection(payload: object) -> bool:
    if not isinstance(payload, Mapping) or payload.get("ok") is not False:
        return False
    error_code = payload.get("error_code")
    status_code = payload.get("status_code") if "status_code" in payload else error_code
    description = payload.get("description")
    return (
        isinstance(error_code, int)
        and not isinstance(error_code, bool)
        and isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and error_code in _PREACCEPTANCE_REJECTION_STATUS_CODES
        and status_code == error_code
        and error_code not in (409, 429)
        and isinstance(description, str)
        and bool(description.strip())
    )


def _eligible_video_fallback(payload: object) -> bool:
    return bool(
        isinstance(payload, Mapping)
        and payload.get("ok") is False
        and payload.get("error_code") == 400
        and payload.get("description")
        == "Bad Request: VIDEO_CONTENT_TYPE_INVALID"
    )


def send_artifact_from_path(
    *,
    config: TelegramMediaConfig,
    chat_id: str | int,
    artifact: str | os.PathLike[str],
    request: Callable[..., object],
    caption: str = "",
    preview_threshold_bytes: int = SHORT_MEDIA_MAX_BYTES,
    _boundary_factory: Callable[[], object] | None = None,
) -> DeliveryReceipt:
    """Deliver one artifact with bounded multipart streaming and no blind retry."""

    if not isinstance(config, TelegramMediaConfig):
        raise MediaTransferError("invalid_config")
    if not callable(request):
        raise MediaTransferError("invalid_transport")
    if _boundary_factory is not None and not callable(_boundary_factory):
        raise MediaTransferError("invalid_boundary")
    boundary_factory = _boundary_factory or _default_delivery_boundary
    if (
        isinstance(preview_threshold_bytes, bool)
        or not isinstance(preview_threshold_bytes, int)
        or preview_threshold_bytes < 1
    ):
        raise MediaTransferError("invalid_preview_threshold")
    normalized_chat_id = _multipart_text(
        chat_id, reason="invalid_chat_id", maximum=128
    )
    if not isinstance(caption, str):
        raise MediaTransferError("invalid_caption")
    if caption:
        normalized_caption = _multipart_text(
            caption, reason="invalid_caption", maximum=1024
        )
    else:
        normalized_caption = ""
    snapshot = _ArtifactSnapshot(artifact)

    first_method = (
        "sendVideo"
        if snapshot.path.suffix.lower() == ".mp4"
        and snapshot.size <= preview_threshold_bytes
        else "sendDocument"
    )
    methods = (
        ("sendVideo", "sendDocument")
        if first_method == "sendVideo"
        else ("sendDocument",)
    )
    used_boundaries: set[str] = set()

    for attempt, method_name in enumerate(methods):
        snapshot.verify()
        boundary = _select_delivery_boundary(
            snapshot=snapshot,
            boundary_factory=boundary_factory,
            used_boundaries=used_boundaries,
        )
        used_boundaries.add(boundary)
        method_url = telegram_transport.bot_method_url(
            api_root=config.api_root,
            token=config.token,
            method=method_name,
        )
        header = _delivery_header(
            boundary=boundary,
            method_name=method_name,
            chat_id=normalized_chat_id,
            caption=normalized_caption,
            snapshot=snapshot,
        )
        footer = f"\r\n--{boundary}--\r\n".encode("ascii")
        content_length = len(header) + snapshot.size + len(footer)
        body = _MultipartArtifactBody(
            snapshot=snapshot,
            header=header,
            footer=footer,
        )
        headers = config.request_headers(request_url=method_url)
        headers.update(
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(content_length),
            }
        )
        try:
            try:
                payload = request(
                    method_name=method_name,
                    url=method_url,
                    headers=headers,
                    content_length=content_length,
                    body=body,
                    follow_redirects=False,
                )
            except Exception:
                raise MediaTransferError("delivery_unknown") from None
            if payload is not None and isinstance(payload, Mapping) and payload.get("ok") is True:
                return _parse_delivery_receipt(
                    payload,
                    method_name=method_name,
                    body=body,
                )
            if _deterministic_rejection(payload):
                if (
                    attempt == 0
                    and method_name == "sendVideo"
                    and _eligible_video_fallback(payload)
                ):
                    continue
                raise MediaTransferError("delivery_rejected")
            raise MediaTransferError("delivery_unknown")
        finally:
            try:
                body.close()
            except Exception:
                pass

    raise MediaTransferError("delivery_rejected")
