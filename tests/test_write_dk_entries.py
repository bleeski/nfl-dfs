"""Acceptance for `scripts/write_dk_entries.py`.

This is the byte-level verification the Classic handoff depends on: it fills the
nine blank roster cells of each reserved Entry ID and proves nothing else moved.
It ran on every version shipped on 2026-09-13 and 2026-09-20 and had no test.

Driven as a subprocess on purpose. The script parses `sys.argv` at module level,
so importing it would execute it; running it is also what actually exercises the
entry point an operator uses. Nothing here touches the network.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "write_dk_entries.py"

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"

PEOPLE = [
    ("1", "Alpha QB", "QB", "AAA", "AAA@BBB"),
    ("2", "Alpha RB", "RB", "AAA", "AAA@BBB"),
    ("3", "Bravo RB", "RB", "BBB", "AAA@BBB"),
    ("4", "Alpha WR", "WR", "AAA", "AAA@BBB"),
    ("5", "Bravo WR", "WR", "BBB", "AAA@BBB"),
    ("6", "Charlie WR", "WR", "CCC", "CCC@DDD"),
    ("7", "Alpha TE", "TE", "AAA", "AAA@BBB"),
    ("8", "Charlie RB", "RB", "CCC", "CCC@DDD"),
    ("9", "Delta DST", "DST", "DDD", "CCC@DDD"),
]
ROSTER = [p[0] for p in PEOPLE]


def fixtures(tmp_path: Path, entry_ids=("5263216931", "5263223608")):
    sal = tmp_path / "sal.csv"
    sal.write_text(
        SALARY_HEADER + "".join(
            f"{pos},{name} ({i}),{name},{i},{pos}/FLEX,5000,"
            f"{g} 09/20/2026 01:00PM ET,{t},0,\n"
            for i, name, pos, t, g in PEOPLE
        ),
        encoding="utf-8",
    )
    tpl = tmp_path / "tpl.csv"
    tpl.write_text(
        ENTRY_HEADER + "".join(f"{e},Contest {n},99{n},$1,,,,,,,,,,,\n"
                               for n, e in enumerate(entry_ids)),
        encoding="utf-8",
    )
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "lineups": [], "assignments_by_entry_id": {e: ROSTER for e in entry_ids}
    }), encoding="utf-8")
    return sel, tpl, sal


def run(tmp_path, sel, tpl, sal, out=None):
    out = out or (tmp_path / "out.csv")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(sel), str(tpl), str(sal), str(out)],
        capture_output=True, text=True,
    )
    return proc, out


def test_fills_every_reserved_entry_and_moves_nothing_else(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    assert "entries filled: 2" in proc.stdout
    assert "cells changed outside the nine roster slots: 0" in proc.stdout


def test_identity_columns_survive_byte_for_byte(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _proc, out = run(tmp_path, sel, tpl, sal)
    src = list(csv.reader(tpl.open(encoding="utf-8-sig")))
    got = list(csv.reader(out.open(encoding="utf-8-sig")))
    assert len(src) == len(got)
    assert src[0] == got[0]
    for a, b in zip(src[1:], got[1:]):
        assert a[0:4] == b[0:4]          # Entry ID, Contest Name, Contest ID, Fee


def test_roster_lands_in_dk_slot_order(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _proc, out = run(tmp_path, sel, tpl, sal)
    rows = list(csv.reader(out.open(encoding="utf-8-sig")))
    pos = {p[0]: p[2] for p in PEOPLE}
    for row in rows[1:]:
        cells = row[4:13]
        assert [pos[c] for c in cells[:1]] == ["QB"]
        assert [pos[c] for c in cells[1:3]] == ["RB", "RB"]
        assert [pos[c] for c in cells[3:6]] == ["WR", "WR", "WR"]
        assert pos[cells[6]] == "TE"
        assert pos[cells[7]] in {"RB", "WR", "TE"}   # FLEX
        assert pos[cells[8]] == "DST"


def test_output_is_crlf_like_a_draftkings_export(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _proc, out = run(tmp_path, sel, tpl, sal)
    assert b"\r\n" in out.read_bytes()


def test_same_inputs_same_bytes(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _p1, o1 = run(tmp_path, sel, tpl, sal, tmp_path / "a.csv")
    _p2, o2 = run(tmp_path, sel, tpl, sal, tmp_path / "b.csv")
    assert hashlib.sha256(o1.read_bytes()).hexdigest() == hashlib.sha256(o2.read_bytes()).hexdigest()


def test_it_refuses_to_overwrite_a_cell_that_was_not_blank(tmp_path):
    """The guardrail that stops a filled entry being silently replaced."""

    sel, tpl, sal = fixtures(tmp_path)
    tpl.write_text(
        ENTRY_HEADER + "5263216931,Contest 0,990,$1,1,2,3,4,5,6,7,8,9,,\n",
        encoding="utf-8",
    )
    sel.write_text(json.dumps({
        "lineups": [], "assignments_by_entry_id": {"5263216931": ROSTER}
    }), encoding="utf-8")
    proc, _out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode != 0
    assert "was not blank" in proc.stderr


def test_an_entry_id_not_in_the_template_is_simply_not_written(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, entry_ids=("5263216931",))
    sel.write_text(json.dumps({
        "lineups": [],
        "assignments_by_entry_id": {"5263216931": ROSTER, "9999999999": ROSTER},
    }), encoding="utf-8")
    proc, _out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    assert "entries filled: 1" in proc.stdout


def test_reports_a_sha256_of_what_it_wrote(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    proc, out = run(tmp_path, sel, tpl, sal)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    assert digest in proc.stdout
