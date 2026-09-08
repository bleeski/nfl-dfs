from __future__ import annotations

import ctypes
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True)
class DoctorReport:
    python: str
    processors: int
    available_memory_bytes: int
    workspace: str
    resolved_workspace: str
    sync_or_reparse_detected: bool
    sqlite_journal_mode: str
    sqlite_integrity: str
    sqlite_probe_error: str
    long_paths_enabled: bool | None
    excel_lock_probe: str
    workspace_probe_cleanup: str
    pass_status: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def available_memory_bytes() -> int:
    if os.name != "nt":
        try:
            pages = os.sysconf("SC_AVPHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except (AttributeError, ValueError):
            return 0
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0
    return int(status.ullAvailPhys)


def _long_paths_enabled() -> bool | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(value)
    except OSError:
        return False


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    reparse_flag = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def workbook_is_closed(path: str | Path) -> bool:
    workbook = Path(path)
    if not workbook.exists():
        return True
    try:
        with workbook.open("a+b"):
            return True
    except PermissionError:
        return False


def doctor(workspace: str | Path) -> DoctorReport:
    root = Path(workspace).resolve()
    sync_detected = _is_reparse(root) or "onedrive" in str(root).lower() or any(
        value and str(root).lower().startswith(str(value).lower())
        for key, value in os.environ.items()
        if key.upper().startswith("ONEDRIVE")
    )
    # The probe must run inside the workspace to observe that filesystem's real
    # journal behaviour, but a workspace can forbid deletion: a Cowork session
    # mounts the repository through a bridge that refuses unlink and rmdir. In
    # that case tempfile.TemporaryDirectory's own cleanup handler retries rmtree
    # on every PermissionError and recurses until RecursionError, taking doctor,
    # setup and the whole cowork-run path down with it. ignore_cleanup_errors
    # does not help, because the recursion happens below it. So own the
    # lifecycle: shutil.rmtree(ignore_errors=True) never recurses, and a probe
    # directory that survives is reported rather than raised.
    temporary = tempfile.mkdtemp(dir=root, prefix=".nfl-doctor-probe-")
    journal = ""
    integrity = ""
    probe_error = ""
    try:
        # WAL needs shared-memory mapping, which a bridge-mounted workspace does
        # not provide: on a Cowork mount the WAL probe raises "disk I/O error".
        # Reporting the mode the workspace actually supports is the point of this
        # probe, so fall back to DELETE and record why, instead of crashing.
        preferred = "DELETE" if sync_detected else "WAL"
        for mode in dict.fromkeys((preferred, "DELETE")):
            pragma = {"WAL": "PRAGMA journal_mode=WAL", "DELETE": "PRAGMA journal_mode=DELETE"}[mode]
            db_path = Path(temporary) / f"doctor-{mode.lower()}.sqlite"
            try:
                connection = sqlite3.connect(db_path)
                try:
                    journal = connection.execute(pragma).fetchone()[0]
                    connection.execute("CREATE TABLE probe(value INTEGER NOT NULL)")
                    connection.execute("INSERT INTO probe VALUES(1)")
                    connection.commit()
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    connection.close()
            except sqlite3.Error as exc:
                journal = ""
                integrity = ""
                probe_error = f"{mode}:{type(exc).__name__}:{exc}"
                continue
            probe_error = "" if mode == preferred else f"FELL_BACK_FROM_{preferred}:{probe_error}"
            break
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        probe_cleanup = (
            f"RETAINED:{Path(temporary).name}" if Path(temporary).exists() else "REMOVED"
        )
    staged_workbook = root / "operator_input.xlsx"
    lock_probe = "CLOSED_OR_ABSENT" if workbook_is_closed(staged_workbook) else "LOCKED_BY_EXCEL"
    long_paths = _long_paths_enabled()
    pinned_python = sys.version_info[:3] == (3, 13, 7)
    passed = (
        pinned_python
        and integrity == "ok"
        and lock_probe != "LOCKED_BY_EXCEL"
        and available_memory_bytes() > 0
    )
    return DoctorReport(
        python=sys.version.split()[0],
        processors=os.cpu_count() or 1,
        available_memory_bytes=available_memory_bytes(),
        workspace=str(workspace),
        resolved_workspace=str(root),
        sync_or_reparse_detected=sync_detected,
        sqlite_journal_mode=str(journal).upper(),
        sqlite_integrity=integrity,
        sqlite_probe_error=probe_error,
        long_paths_enabled=long_paths,
        excel_lock_probe=lock_probe,
        workspace_probe_cleanup=probe_cleanup,
        pass_status=passed,
    )


def live_memory_limit(workspace_limit: int = 4 * 1024**3) -> int:
    return min(workspace_limit, available_memory_bytes() // 2)
