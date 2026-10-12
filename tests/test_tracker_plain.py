"""Ben's plain-English tracker must cover the whole roadmap.

Ben asked (2026-10-12) for a page that shows every chunk of work in plain
English: what it is, why we are doing it, why it matters. The page reads the
board's status through `scripts/repo_state.py` and the words from
`docs/tracker/plain.json`. These tests keep the two from drifting: a new board
row or operator item without a card fails here with the exact ID and file, and
"ready" on the page is exactly what the session-start digest calls startable.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tracker():
    return _load("tracker_payload_under_test", "scripts/tracker_payload.py")


@pytest.fixture(scope="module")
def queue():
    return _load("repo_state_for_tracker_test", "scripts/repo_state.py").session_queue()


@pytest.fixture(scope="module")
def plain(tracker):
    return tracker.load_plain()


@pytest.fixture(scope="module")
def documents(tracker, plain, queue):
    dates = tracker.completion_dates(tracker.ROADMAP.read_text(encoding="utf-8"))
    return tracker.build(plain, queue, dates, now=datetime(2026, 10, 12, tzinfo=timezone.utc), commit="test")


def test_every_board_row_and_operator_item_has_a_plain_card(tracker, plain, queue):
    gaps = tracker.coverage_gaps(plain, queue)
    assert not gaps, "Ben's tracker is missing cards:\n" + "\n".join(gaps)


def test_ready_cards_are_exactly_the_startable_sessions(documents, queue):
    ready = {
        chunk["id"]
        for (collection, _), body in documents.items()
        if collection == "goals"
        for chunk in body["chunks"].values()
        if chunk["state"] == "ready"
    }
    assert ready == {row["short"] for row in queue["rows"] if row["startable"]}


def test_every_row_lands_in_exactly_one_goal(documents, queue):
    seen = [
        chunk_id
        for (collection, _), body in documents.items()
        if collection == "goals"
        for chunk_id in body["chunks"]
    ]
    assert sorted(seen) == sorted(row["short"] for row in queue["rows"])


def test_the_payload_fits_one_database_batch(tracker, documents):
    assert len(documents) <= tracker.MAX_DOCUMENTS
    for key, body in documents.items():
        assert len(json.dumps(body, ensure_ascii=False).encode("utf-8")) < tracker.MAX_DOCUMENT_BYTES, key


def test_a_missing_card_is_named_with_its_file(tracker, plain, queue):
    trimmed = copy.deepcopy(plain)
    first = queue["rows"][0]["short"]
    del trimmed["chunks"][first]
    gaps = tracker.coverage_gaps(trimmed, queue)
    assert any(first in gap and "docs/tracker/plain.json" in gap for gap in gaps), gaps


def test_forbidden_claims_are_refused(tracker, plain, queue):
    doctored = copy.deepcopy(plain)
    first = queue["rows"][0]["short"]
    doctored["chunks"][first]["matters"] = "Raises our ROI."
    assert any("ROI" in gap for gap in tracker.coverage_gaps(doctored, queue))


@pytest.mark.parametrize(
    ("status", "startable", "depends", "expected"),
    [
        ("Complete", False, ["none"], "done"),
        ("Deferred", False, ["Session 01"], "parked"),
        ("In Progress", False, ["none"], "active"),
        ("Pending", True, ["none"], "ready"),
        ("Pending", False, ["Session 02", "O1"], "blocked"),
        ("Pending", False, ["Session 01", "BEN ruling"], "decision"),
        ("Pending", False, ["Session 01", "O1"], "you"),
    ],
)
def test_state_of(tracker, status, startable, depends, expected):
    row = {"status": status, "startable": startable, "depends_on": depends}
    sessions = {"Session 01": "Complete", "Session 02": "Pending"}
    assert tracker.state_of(row, sessions, {"O1": "Open"}) == expected
