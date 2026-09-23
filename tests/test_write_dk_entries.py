"""Acceptance for `scripts/write_dk_entries.py`.

This is the byte-level writer the Classic fallback hands off through: it fills
the nine blank roster cells of each reserved Entry ID and proves nothing else
moved. It ran on every version shipped on 2026-09-13 and 2026-09-20 and had no
test until 2026-09-20.

Session 02 (2026-09-23) made it refuse what it used to let through. The 2026-09-22
audit (issue #40, D6) showed that it exited 0 on an assignment Entry ID the
template does not have, left rows blank without saying so, never checked a
roster's salary or people, rewrote every line as CRLF, and overwrote whatever
sat at the output path. The tests below pin the refusals by name, the exit 3
that names every unfilled Entry ID (R29: a shortfall is reported, never padded
with a repeated lineup), and raw-byte preservation of every untouched line.

Driven as a subprocess on purpose: running it is what exercises the entry point
an operator uses. Nothing here touches the network.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "write_dk_entries.py"
SUPPLIED = REPO_ROOT / "tests" / "fixtures" / "supplied"

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"
SHOWDOWN_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions\n"

# (dk_id, name, position, team, game, salary)
PEOPLE = [
    ("1", "Alpha QB", "QB", "AAA", "AAA@BBB", 5000),
    ("2", "Alpha RB", "RB", "AAA", "AAA@BBB", 5000),
    ("3", "Bravo RB", "RB", "BBB", "AAA@BBB", 5000),
    ("4", "Alpha WR", "WR", "AAA", "AAA@BBB", 5000),
    ("5", "Bravo WR", "WR", "BBB", "AAA@BBB", 5000),
    ("6", "Charlie WR", "WR", "CCC", "CCC@DDD", 5000),
    ("7", "Alpha TE", "TE", "AAA", "AAA@BBB", 5000),
    ("8", "Charlie RB", "RB", "CCC", "CCC@DDD", 5000),
    ("9", "Delta DST", "DST", "DDD", "CCC@DDD", 5000),
]
EXTRAS = [
    ("10", "Bravo QB", "QB", "BBB", "AAA@BBB", 5000),
    ("11", "Pricey WR", "WR", "CCC", "CCC@DDD", 20000),
    ("12", "Bravo WR2", "WR", "BBB", "AAA@BBB", 5000),
    ("13", "Bravo RB2", "RB", "BBB", "AAA@BBB", 5000),
    ("14", "Bravo DST", "DST", "BBB", "AAA@BBB", 5000),
]
# One cheap pass catcher per lineup, so every entry can carry a distinct roster.
FLEX_POOL = [
    (str(100 + k), f"Flex WR{k}", "WR", "CCC" if k % 2 else "DDD", "CCC@DDD", 3000)
    for k in range(24)
]
EVERYONE = PEOPLE + EXTRAS + FLEX_POOL
POSITION = {p[0]: p[2] for p in EVERYONE}

ROSTER = [p[0] for p in PEOPLE]            # QB RB RB WR WR WR TE RB(FLEX) DST


def roster_for(k: int) -> list[str]:
    """A legal lineup that differs from every other k only in its FLEX."""

    return ["1", "2", "3", "4", "5", "6", "7", FLEX_POOL[k][0], "9"]


def roster_position(pos: str) -> str:
    return pos if pos in {"QB", "DST"} else f"{pos}/FLEX"


def entry_ids(n: int) -> list[str]:
    return [f"52632{k:05d}" for k in range(n)]


def write_salaries(path: Path) -> Path:
    path.write_text(
        SALARY_HEADER + "".join(
            f"{pos},{name} ({i}),{name},{i},{roster_position(pos)},{s},"
            f"{g} 09/20/2026 01:00PM ET,{t},0,\n"
            for i, name, pos, t, g, s in EVERYONE
        ),
        encoding="utf-8",
    )
    return path


def template_text(ids, header=ENTRY_HEADER) -> str:
    return header + "".join(f"{e},Contest {n},99{n},$1,,,,,,,,,,,\n" for n, e in enumerate(ids))


def fixtures(tmp_path: Path, ids=("5263216931", "5263223608"), assignments=None):
    sal = write_salaries(tmp_path / "sal.csv")
    tpl = tmp_path / "tpl.csv"
    tpl.write_text(template_text(ids), encoding="utf-8")
    if assignments is None:
        assignments = {e: roster_for(n) for n, e in enumerate(ids)}
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({"lineups": [], "assignments_by_entry_id": assignments}),
                   encoding="utf-8")
    return sel, tpl, sal


def run(tmp_path, sel, tpl, sal, out=None):
    out = out or (tmp_path / "out.csv")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(sel), str(tpl), str(sal), str(out)],
        capture_output=True, text=True,
    )
    return proc, out


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines_of(path: Path) -> list[bytes]:
    return path.read_bytes().split(b"\n")


# ---------------------------------------------------------------- happy path

def test_fills_every_reserved_entry_and_moves_nothing_else(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    assert "entries filled: 2" in proc.stdout
    assert "unfilled authorized Entry IDs: 0" in proc.stdout
    # Session 02: the claim is about bytes now, because the check is.
    assert "bytes changed outside the nine roster cells: 0" in proc.stdout


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
    for row in rows[1:]:
        cells = row[4:13]
        assert [POSITION[c] for c in cells[:1]] == ["QB"]
        assert [POSITION[c] for c in cells[1:3]] == ["RB", "RB"]
        assert [POSITION[c] for c in cells[3:6]] == ["WR", "WR", "WR"]
        assert POSITION[cells[6]] == "TE"
        assert POSITION[cells[7]] in {"RB", "WR", "TE"}   # FLEX
        assert POSITION[cells[8]] == "DST"


def test_each_row_gets_its_own_assignment(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _proc, out = run(tmp_path, sel, tpl, sal)
    rows = {r[0]: r for r in csv.reader(out.open(encoding="utf-8-sig")) if r and r[0].isdigit()}
    assert rows["5263216931"][11] == FLEX_POOL[0][0]
    assert rows["5263223608"][11] == FLEX_POOL[1][0]


def test_a_roster_given_as_an_object_is_read(tmp_path):
    ids = ("5263216931",)
    sel, tpl, sal = fixtures(tmp_path, ids, {ids[0]: {"roster": ROSTER}})
    proc, _out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr


# Session 02 replaced `test_output_is_crlf_like_a_draftkings_export`. The old
# writer rewrote every line with csv.writer and a CRLF terminator, so an LF
# template came back CRLF: every line in the file changed. Raw-line
# preservation keeps each line's own ending, and DraftKings' own exports are
# CRLF, which the real-template test below pins.
@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_line_endings_follow_the_template(tmp_path, ending):
    sel, tpl, sal = fixtures(tmp_path)
    tpl.write_bytes(template_text(("5263216931", "5263223608")).encode("utf-8").replace(b"\n", ending))
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    raw = out.read_bytes()
    if ending == b"\n":
        assert b"\r" not in raw
    else:
        assert raw.count(b"\r\n") == raw.count(b"\n") == 3


def test_same_inputs_same_bytes(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    _p1, o1 = run(tmp_path, sel, tpl, sal, tmp_path / "a.csv")
    _p2, o2 = run(tmp_path, sel, tpl, sal, tmp_path / "b.csv")
    assert sha(o1) == sha(o2)


def test_reports_a_sha256_of_what_it_wrote(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    proc, out = run(tmp_path, sel, tpl, sal)
    assert sha(out) in proc.stdout


def test_a_quoted_contest_name_with_a_comma_survives(tmp_path):
    """Field positions come from a quote-aware byte scan, not a comma split."""

    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_bytes((ENTRY_HEADER + '5263216931,"NFL $5K, Week 3",990,$1,,,,,,,,,,,\n').encode())
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    line = lines_of(out)[1]
    assert line.startswith(b'5263216931,"NFL $5K, Week 3",990,$1,1,')
    assert line.endswith(b",9,,")


def test_a_prefilled_row_without_an_assignment_is_preserved_not_counted(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_text(
        ENTRY_HEADER
        + "5263216931,Contest 0,990,$1,,,,,,,,,,,\n"
        + "5263299999,Contest 1,991,$1,1,2,3,4,5,6,7,100,9,,\n",
        encoding="utf-8",
    )
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    assert "prefilled rows preserved: 1" in proc.stdout
    assert lines_of(out)[2] == lines_of(tpl)[2]


def test_real_draftkings_template_moves_only_roster_cells(tmp_path):
    """The supplied 20-entry DKEntries export: 727 CRLF lines, with the player
    list on the right of every entry row. Copied first; the fixture is immutable."""

    tpl = tmp_path / "DKEntries.csv"
    shutil.copyfile(SUPPLIED / "DKEntries CSV 20 entries.csv", tpl)
    sal = tmp_path / "DKSalaries.csv"
    shutil.copyfile(SUPPLIED / "DKSalaries Salary CSV Classic.csv", sal)
    before = sha(tpl)

    by_pos: dict[str, list[tuple[int, str, str]]] = {}
    with sal.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            by_pos.setdefault(r["Position"], []).append(
                (int(r["Salary"]), r["ID"], r["Game Info"].split()[0]))
    for pos in by_pos:
        by_pos[pos].sort()
    base = ([by_pos["QB"][0], *by_pos["RB"][:2], *by_pos["WR"][:3], by_pos["TE"][0]])
    flex = by_pos["WR"][3:23]
    dst = by_pos["DST"][0]
    ids = [r[0].strip() for r in csv.reader(tpl.open(encoding="utf-8-sig"))
           if r and r[0].strip().isdigit()]
    assert len(ids) == 20
    assignments = {}
    for eid, f in zip(ids, flex):
        lineup = [*base, f, dst]
        assert sum(p[0] for p in lineup) <= 50000
        assert len({p[2] for p in lineup}) >= 2
        assignments[eid] = [p[1] for p in lineup]
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({"assignments_by_entry_id": assignments}), encoding="utf-8")

    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 0, proc.stderr
    assert "entries filled: 20" in proc.stdout
    assert sha(tpl) == before

    src, got = lines_of(tpl), lines_of(out)
    assert len(src) == len(got) == 728          # 727 lines plus the final empty split
    entry_lines = 0
    for a, b in zip(src, got):
        if a.split(b",", 1)[0].decode("utf-8", "replace") in assignments:
            entry_lines += 1
            fa, fb = a.split(b","), b.split(b",")
            assert fa[:4] == fb[:4] and fa[13:] == fb[13:]
            assert all(not c for c in fa[4:13]) and all(fb[4:13])
            assert b.endswith(b"\r")            # CRLF kept on the rewritten line
        else:
            assert a == b
    assert entry_lines == 20


# ---------------------------------------------------------------- coverage

def test_a_missing_id_leaves_its_row_blank_and_is_named(tmp_path):
    ids = ("5263216931", "5263223608")
    sel, tpl, sal = fixtures(tmp_path, ids, {ids[0]: roster_for(0)})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 3, proc.stderr
    assert out.exists()
    assert "UNFILLED_AUTHORIZED_ROWS" in proc.stderr and ids[1] in proc.stderr
    assert f"unfilled authorized Entry IDs: 1 ['{ids[1]}']" in proc.stdout
    assert lines_of(out)[2] == lines_of(tpl)[2]


def test_eighteen_of_twenty_filled_exits_non_zero_naming_both(tmp_path):
    ids = entry_ids(20)
    sel, tpl, sal = fixtures(tmp_path, ids, {e: roster_for(n) for n, e in enumerate(ids[:18])})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert proc.returncode == 3, proc.stderr
    assert "entries filled: 18" in proc.stdout
    assert f"unfilled authorized Entry IDs: 2 {ids[18:]}" in proc.stdout
    for missing in ids[18:]:
        assert missing in proc.stderr


# ---------------------------------------------------------------- refusals

def assert_refused(proc, out: Path, code: str):
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert f"REFUSED {code}" in proc.stderr, proc.stderr
    assert not out.exists()
    strays = [p.name for p in out.parent.iterdir() if p.name.startswith(f".{out.name}.")]
    assert strays == [], strays


# Session 02 replaced `test_an_entry_id_not_in_the_template_is_simply_not_written`,
# which asserted exit 0 here. An assignment for an Entry ID the operator's file
# does not hold is a lineup that silently goes nowhere.
def test_an_entry_id_not_in_the_template_is_refused_by_name(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",),
                             {"5263216931": roster_for(0), "9999999999": roster_for(1)})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "UNKNOWN_ENTRY_ID")
    assert "9999999999" in proc.stderr


def test_it_refuses_to_overwrite_a_cell_that_was_not_blank(tmp_path):
    """The guardrail that stops a filled entry being silently replaced."""

    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_text(ENTRY_HEADER + "5263216931,Contest 0,990,$1,1,2,3,4,5,6,7,8,9,,\n",
                   encoding="utf-8")
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "PREFILLED_ROW_ASSIGNED")
    assert "was not blank" in proc.stderr


BAD_ROSTERS = {
    "QB_IN_FLEX": (["1", "2", "3", "4", "5", "6", "7", "10", "9"], "ROSTER_SHAPE"),
    "OVER_THE_CAP": (["1", "2", "3", "4", "5", "6", "7", "11", "9"], "OVER_SALARY_CAP"),
    "DUPLICATE_PERSON": (["1", "2", "3", "4", "5", "6", "7", "2", "9"], "DUPLICATE_PLAYER"),
    "NOT_IN_POOL": (["1", "2", "3", "4", "5", "6", "7", "999", "9"], "DK_ID_NOT_IN_POOL"),
    "ONE_GAME": (["1", "2", "3", "4", "5", "12", "7", "13", "14"], "TWO_GAME_RULE"),
    "EIGHT_PLAYERS": (["1", "2", "3", "4", "5", "6", "7", "9"], "ROSTER_SIZE"),
}


@pytest.mark.parametrize("case", sorted(BAD_ROSTERS))
def test_an_invalid_roster_refuses_the_whole_file_by_name(tmp_path, case):
    roster, code = BAD_ROSTERS[case]
    ids = ("5263216931", "5263223608")
    sel, tpl, sal = fixtures(tmp_path, ids, {ids[0]: roster_for(0), ids[1]: roster})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, code)
    assert ids[1] in proc.stderr


def test_a_repeated_lineup_is_refused_never_written_twice(tmp_path):
    """R29: within a portfolio every submitted lineup is distinct."""

    ids = ("5263216931", "5263223608")
    sel, tpl, sal = fixtures(tmp_path, ids, {ids[0]: ROSTER, ids[1]: list(reversed(ROSTER))})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "DUPLICATE_LINEUP")


def test_a_showdown_template_is_refused(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_text(SHOWDOWN_HEADER + "5263216931,Contest 0,990,$1,,,,,,,,\n", encoding="utf-8")
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "NOT_A_CLASSIC_TEMPLATE")


def test_a_row_narrower_than_the_roster_is_refused(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_text(ENTRY_HEADER + "5263216931,Contest 0,990,$1\n", encoding="utf-8")
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "ROW_NARROWER_THAN_ROSTER")


def test_no_assignments_is_refused(tmp_path):
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {})
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "NO_ASSIGNMENTS")


def test_output_equal_to_the_template_is_refused(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    before = sha(tpl)
    proc, _out = run(tmp_path, sel, tpl, sal, out=tpl)
    assert proc.returncode == 2
    assert "REFUSED OUTPUT_IS_TEMPLATE" in proc.stderr
    assert sha(tpl) == before


def test_output_equal_to_another_input_is_refused(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    before = sha(sal)
    proc, _out = run(tmp_path, sel, tpl, sal, out=sal)
    assert proc.returncode == 2
    assert "REFUSED OUTPUT_IS_AN_INPUT" in proc.stderr
    assert sha(sal) == before


def test_a_pre_existing_output_is_never_overwritten(tmp_path):
    sel, tpl, sal = fixtures(tmp_path)
    out = tmp_path / "out.csv"
    out.write_bytes(b"an earlier portfolio\r\n")
    proc, _ = run(tmp_path, sel, tpl, sal, out=out)
    assert proc.returncode == 2
    assert "REFUSED OUTPUT_EXISTS" in proc.stderr
    assert out.read_bytes() == b"an earlier portfolio\r\n"


@pytest.mark.parametrize("style", ["ids", "name_and_id"])
def test_a_lineup_repeating_a_prefilled_row_is_refused(tmp_path, style):
    """R29 covers rows filled before this run, in either cell format."""

    names = {p[0]: p[1] for p in EVERYONE}
    cells = ROSTER if style == "ids" else [f"{names[i]} ({i})" for i in ROSTER]
    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": list(reversed(ROSTER))})
    tpl.write_text(
        ENTRY_HEADER
        + "5263216931,Contest 0,990,$1,,,,,,,,,,,\n"
        + f"5263299999,Contest 1,991,$1,{','.join(cells)},,\n",
        encoding="utf-8",
    )
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, "DUPLICATE_LINEUP")
    assert "5263299999" in proc.stderr


@pytest.mark.parametrize("mutation, code", [
    ((b"Contest 0", b"Contest \xff"), "TEMPLATE_NOT_UTF8"),
    ((b"Contest 0", b'"Contest 0'), "UNREADABLE_TEMPLATE_ROW"),     # unterminated quote
])
def test_a_damaged_template_byte_withholds_the_file(tmp_path, mutation, code):
    """`.claude/rules/tests.md`: a changed input byte withholds the artifact."""

    sel, tpl, sal = fixtures(tmp_path, ("5263216931",), {"5263216931": ROSTER})
    tpl.write_bytes(tpl.read_bytes().replace(*mutation))
    proc, out = run(tmp_path, sel, tpl, sal)
    assert_refused(proc, out, code)
