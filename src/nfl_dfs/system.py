from __future__ import annotations

import ctypes
import json
import os
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
    long_paths_enabled: bool | None
    excel_lock_probe: str
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
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        db_path = Path(temporary) / "doctor.sqlite"
        connection = sqlite3.connect(db_path)
        journal = connection.execute(
            "PRAGMA journal_mode=DELETE" if sync_detected else "PRAGMA journal_mode=WAL"
        ).fetchone()[0]
        connection.execute("CREATE TABLE probe(value INTEGER NOT NULL)")
        connection.execute("INSERT INTO probe VALUES(1)")
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        connection.close()
    staged_workbook = root / "operator_input.xlsx"
    lock_probe = "CLOSED_OR_ABSENT" if workbook_is_closed(staged_workbook) else "LOCKED_BY_EXCEL"
    long_paths = _long_paths_enabled()
    passed = integrity == "ok" and lock_probe != "LOCKED_BY_EXCEL"
    return DoctorReport(
        python=sys.version.split()[0],
        processors=os.cpu_count() or 1,
        available_memory_bytes=available_memory_bytes(),
        workspace=str(workspace),
        resolved_workspace=str(root),
        sync_or_reparse_detected=sync_detected,
        sqlite_journal_mode=str(journal).upper(),
        sqlite_integrity=integrity,
        long_paths_enabled=long_paths,
        excel_lock_probe=lock_probe,
        pass_status=passed,
    )


def live_memory_limit(workspace_limit: int = 4 * 1024**3) -> int:
    return min(workspace_limit, available_memory_bytes() // 2)
