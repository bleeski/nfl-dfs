from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .contracts import WorkflowState
from .lifecycle import transition


SCHEMA_VERSION = 1


class RegistryError(RuntimeError):
    pass


class RunRegistry:
    def __init__(self, path: str | Path, *, sync_safe: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sync_safe = sync_safe
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "PRAGMA journal_mode=DELETE" if self.sync_safe else "PRAGMA journal_mode=WAL"
            )
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    state TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS models (
                    model_id TEXT PRIMARY KEY,
                    family TEXT NOT NULL,
                    version TEXT NOT NULL,
                    artifact_hash TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    deployed INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            existing = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if existing and int(existing[0]) != SCHEMA_VERSION:
                raise RegistryError("unsupported registry schema version")
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),),
            )

    def create_run(self, run_id: str, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, sort_keys=True, default=str)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runs(run_id,state,created_at,updated_at,payload_json) VALUES(?,?,?,?,?)",
                (run_id, WorkflowState.NEW.value, now, now, encoded),
            )
            connection.execute(
                "INSERT INTO events(run_id,state,occurred_at,payload_json) VALUES(?,?,?,?)",
                (run_id, WorkflowState.NEW.value, now, encoded),
            )

    def set_state(self, run_id: str, state: WorkflowState, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, sort_keys=True, default=str)
        with self.connect() as connection:
            current = connection.execute(
                "SELECT state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if current is None:
                raise RegistryError(f"unknown run: {run_id}")
            transition(WorkflowState(current[0]), state)
            connection.execute(
                "UPDATE runs SET state=?,updated_at=?,payload_json=? WHERE run_id=?",
                (state.value, now, encoded, run_id),
            )
            connection.execute(
                "INSERT INTO events(run_id,state,occurred_at,payload_json) VALUES(?,?,?,?)",
                (run_id, state.value, now, encoded),
            )

    def get_run(self, run_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT run_id,state,created_at,updated_at,payload_json FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RegistryError(f"unknown run: {run_id}")
        return {
            "run_id": row[0],
            "state": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "payload": json.loads(row[4]),
        }
