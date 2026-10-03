"""Acceptance for `scripts/showdown_value_add.py` (Session 55, 2026-10-02 review F-01).

`keenum_swap.py` (2026-09-28) built its new roster without checking the person was not already in it, so a
re-run on the tracked v4 published two LINEUP_PERSON_REPEATED rows and exited 0. The tool under test works
one named person into a filled Showdown review file by one swap per row and refuses to publish anything
`validate_lineup` or R29 distinctness would reject. The independent oracle for the bytes is the test's own
row writer (`entry_line`), and for the verdict `qa_showdown_portfolio.py`; neither shares code with the tool.

Synthetic DraftKings fixtures only; the real parsers, no solver, no network.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.lineups import roster_canonical_key, validate_lineup

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _load("showdown_value_add")
qa = _load("qa_showdown_portfolio")

SALARY_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions\r\n"
GAME = "DEN@KC 09/14/2026 08:20PM ET"

# (key, name, position, team, FLEX salary); the CPT row costs 1.5 times the FLEX row, with its own DraftKings ID.
PEOPLE = [
    ("kc_qb", "KC QB", "QB", "KC", 11000), ("kc_rb", "KC RB", "RB", "KC", 5000),
    ("kc_wr1", "KC WR1", "WR", "KC", 10000), ("kc_wr2", "KC WR2", "WR", "KC", 6000),
    ("kc_te", "KC TE", "TE", "KC", 4000), ("kc_k", "KC K", "K", "KC", 3000),
    ("kc_dst", "Chiefs", "DST", "KC", 3000), ("kc_qb2", "KC QB2", "QB", "KC", 2000),
    ("den_qb", "DEN QB", "QB", "DEN", 11000), ("den_rb", "DEN RB", "RB", "DEN", 5000),
    ("den_wr1", "DEN WR1", "WR", "DEN", 10000), ("den_wr2", "DEN WR2", "WR", "DEN", 6000),
    ("den_te", "DEN TE", "TE", "DEN", 4000), ("den_k", "DEN K", "K", "DEN", 3000),
    ("den_dst", "Broncos", "DST", "DEN", 3000),
]
FLEX = {key: str(3000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}
CPT = {key: str(4000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}
NAME = {key: name for key, name, *_rest in PEOPLE}
T = "kc_qb2"  # the person being worked in

L0 = ["kc_qb", "kc_wr2", "den_rb", "den_wr2", "kc_te", "kc_rb"]
L1 = ["den_qb", "den_wr2", "kc_rb", "kc_wr2", "den_te", "den_rb"]
L2 = ["kc_wr1", "kc_te", "den_qb", "den_rb", "den_wr1", "kc_rb"]
L3 = ["den_wr1", "den_te", "kc_qb", "kc_wr1", "kc_k", "den_dst"]
BASE = [L0, L1, L2, L3]


def ids(lineup: list[str]) -> list[str]:
    return [CPT[lineup[0]], *(FLEX[k] for k in lineup[1:])]


def entry_id(n: int) -> str:
    return f"48800{n:05d}"


def entry_line(n: int, cells=("",) * 6) -> bytes:
    """One DraftKings entry row. Row 0 is wide, with an embedded pool table cell; the rest carry a quoted note."""
    tail = ",,,Position,Name + ID" if n == 0 else ',,"note, with a comma"'
    return f'{entry_id(n)},"Showdown, Sun",9001,$5,{",".join(cells)}{tail}\r\n'.encode()


def salary_csv(tmp_path: Path, status: str = "") -> Path:
    rows = []
    for key, name, pos, team, salary in PEOPLE:
        for role, table, price in (("CPT", CPT, salary * 3 // 2), ("FLEX", FLEX, salary)):
            ident = table[key]
            rows.append(f"{pos},{name} ({ident}),{name},{ident},{role},{price},{GAME},{team},0,"
                        f"{status if key == T else ''}\n")
    path = tmp_path / "sal.csv"
    path.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    return path


def build(tmp_path: Path, rows, prefilled=(), status: str = ""):
    """Salary file, template (blank rows, except `prefilled`) and review. `rows[n]` is cells, or None for a blank row."""
    cells = [None if r is None else (list(ids(r)) if isinstance(r[0], str) and r[0] in CPT else list(r)) for r in rows]
    tpl = ENTRY_HEADER.encode() + b"".join(
        entry_line(n, c if (n in prefilled and c) else ("",) * 6) for n, c in enumerate(cells))
    rev = ENTRY_HEADER.encode() + b"".join(entry_line(n, c or ("",) * 6) for n, c in enumerate(cells))
    paths = {"sal": salary_csv(tmp_path, status), "tpl": tmp_path / "tpl.csv", "rev": tmp_path / "rev.csv"}
    paths["tpl"].write_bytes(tpl)
    paths["rev"].write_bytes(rev)
    return paths


def go(tmp_path, capsys, w, *args, out="out.csv"):
    target = tmp_path / out
    code = tool.main(["--salaries", str(w["sal"]), "--template", str(w["tpl"]), "--review", str(w["rev"]),
                      "--out", str(target), *args])
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out.strip() else None), captured.err, target


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roster(line: bytes) -> list[str]:
    return next(csv.reader([line.decode()]))[4:10]


def qa_defects(tmp_path, capsys, w, export: Path) -> int:
    qa.main(["--salaries", str(w["sal"]), "--template", str(w["tpl"]), "--export", str(export)])
    return json.loads(capsys.readouterr().out)["defects"]


def scores(tmp_path: Path, mapping: dict[str, float]) -> Path:
    path = tmp_path / "scores.json"
    path.write_text(json.dumps({"by_dk_id": mapping}), encoding="utf-8")
    return path


def refused(code, err, out, name):
    assert code == tool.EXIT_REFUSED, err
    assert f"REFUSED {name}" in err and "nothing was written" in err
    assert not out.exists()


# ----- acceptance 4: a valid substitution ------------------------------------------------------------------

def test_a_valid_substitution_is_byte_exact_legal_and_distinct(tmp_path, capsys):
    w = build(tmp_path, BASE)
    cheap = {FLEX[k]: s / 1000 for k, _n, _p, _t, s in PEOPLE}  # a score per FLEX row, except the two tight ones
    cheap[FLEX["den_te"]], cheap[FLEX["kc_te"]] = 0.1, 0.2
    before = {k: digest(p) for k, p in w.items()}
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2",
                                "--scores", str(scores(tmp_path, cheap)))
    assert code == tool.EXIT_OK, err
    assert [(s["entry_id"], s["slot"], s["removed"]) for s in report["swaps"]] == [
        (entry_id(1), "FLEX 4", "DEN TE"), (entry_id(3), "FLEX 1", "DEN TE")]
    expected = [list(r) for r in BASE]
    expected[1][4], expected[3][1] = T, T
    want = ENTRY_HEADER.encode() + b"".join(entry_line(n, ids(r)) for n, r in enumerate(expected))
    assert out.read_bytes() == want  # entry metadata, quoted notes, the wide row and CRLF endings all intact
    assert {k: digest(p) for k, p in w.items()} == before  # no input was touched
    slate = parse_salaries(w["sal"])
    rows = [ids(r) for r in expected]
    assert all(validate_lineup(slate, r).valid for r in rows)
    assert len({roster_canonical_key(slate, r) for r in rows}) == len(rows)
    assert qa_defects(tmp_path, capsys, w, out) == 0
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert "0 prior points" in report["LIMITATION"] and "KC QB2" in report["LIMITATION"]
    assert (report["salary_sha256"], report["template_sha256"], report["review_sha256"], report["out_sha256"]) == (
        before["sal"], before["tpl"], before["rev"], digest(out))  # every byte that shaped the output is bound
    assert report["scores_sha256"] == hashlib.sha256((tmp_path / "scores.json").read_bytes()).hexdigest()
    assert report["theses_sha256"] is None
    assert not any("projection" in k.lower() or "prior_points" in k for k in report)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.csv", "rev.csv", "sal.csv", "scores.json", "tpl.csv"]


def test_either_role_id_names_the_same_person(tmp_path, capsys):
    w = build(tmp_path, BASE)
    flex_run = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", out="a.csv")
    cpt_run = go(tmp_path, capsys, w, "--dk-id", CPT[T], "--count", "2", out="b.csv")
    assert flex_run[0] == cpt_run[0] == tool.EXIT_OK
    assert flex_run[3].read_bytes() == cpt_run[3].read_bytes()
    assert flex_run[1]["person"]["name"] == cpt_run[1]["person"]["name"] == NAME[T]


# ----- acceptance 1 and 2: a row that already holds him -------------------------------------------------------

@pytest.mark.parametrize("holder", [
    ["kc_qb", "kc_wr2", "den_rb", "den_wr2", T, "kc_rb"],   # in a FLEX cell
    [T, "kc_wr2", "den_rb", "den_wr2", "kc_te", "kc_rb"],   # Captain
])
def test_a_named_row_that_already_holds_him_refuses_the_run(tmp_path, capsys, holder):
    w = build(tmp_path, [holder, L1])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", entry_id(0))
    refused(code, err, out, "PERSON_ALREADY_ROSTERED")


@pytest.mark.parametrize("captain", [False, True])
def test_when_every_row_already_holds_him_nothing_is_written(tmp_path, capsys, captain):
    holders = [["kc_qb", "kc_wr2", "den_rb", "den_wr2", T, "kc_rb"], [T, "kc_wr2", "den_rb", "den_wr2", "kc_te", "kc_rb"]]
    w = build(tmp_path, holders)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], *(["--captain"] if captain else []))
    refused(code, err, out, "NO_ROW_CHANGED")
    assert "2 already hold him" in err


# ----- acceptance 3: R29, a FLEX permutation is the same lineup ---------------------------------------------------

def permuted_holders(x):
    """One row per FLEX cell of `x`, each with that cell replaced by T and the FLEX order reversed."""
    return [[x[0], *reversed([T if i == k else c for i, c in enumerate(x) if i])] for k in range(1, 6)]


def test_a_swap_that_would_repeat_a_flex_permuted_lineup_is_refused(tmp_path, capsys):
    rows = [L0, *permuted_holders(L0)]  # every possible swap into row 0 equals one of the five rows below it
    w = build(tmp_path, rows)
    slate = parse_salaries(w["sal"])
    assert len({roster_canonical_key(slate, ids(r)) for r in rows}) == 6  # the fixture itself is distinct
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", entry_id(0))
    refused(code, err, out, "NO_VALID_SWAP")
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "NO_ROW_CHANGED")


def test_a_swap_avoids_the_permuted_twin_and_takes_another_cell(tmp_path, capsys):
    twin = [L0[0], *reversed([T if c == "kc_te" else c for c in L0[1:]])]  # row 0 with kc_te -> T, order reversed
    w = build(tmp_path, [L0, twin])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", entry_id(0))
    assert code == tool.EXIT_OK, err
    assert report["swaps"][0]["removed"] != "KC TE"
    slate = parse_salaries(w["sal"])
    keys = [roster_canonical_key(slate, _roster(line)) for line in out.read_bytes().splitlines()[1:]]
    assert len(set(keys)) == len(keys) == 2


def test_a_prefilled_row_counts_for_distinctness(tmp_path, capsys):
    prefilled = [L0[0], *[T if c == "kc_te" else c for c in L0[1:]]]  # what swapping kc_te out of row 0 would make
    w = build(tmp_path, [L0, prefilled], prefilled={1})
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", entry_id(0))
    assert code == tool.EXIT_OK, err
    assert report["swaps"][0]["removed"] != "KC TE"


def test_an_input_file_that_already_repeats_a_lineup_is_not_published_from(tmp_path, capsys):
    permuted = [L0[0], *reversed(L0[1:])]
    w = build(tmp_path, [L0, permuted, L1])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "INPUT_FILE_NOT_VALID")
    assert "DUPLICATE_LINEUP" in err


def test_the_same_six_people_under_another_captain_is_legal_input_but_is_never_created(tmp_path, capsys):
    other_captain = ["kc_wr2", "kc_qb", "den_rb", "den_wr2", "kc_te", "kc_rb"]
    slate = parse_salaries(salary_csv(tmp_path))
    assert tool.file_defects(slate, {"a": ids(L0), "b": ids(other_captain)}) == []  # R29: a different lineup
    w = build(tmp_path, [L0, other_captain])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2")
    assert code == tool.EXIT_OK, err
    # Both rows would lose KC TE for the same six people under two Captains; the second takes its next cell.
    assert [s["removed"] for s in report["swaps"]] == ["KC TE", "DEN RB"]
    by_id = {p.dk_id: p.underlying_id for p in slate.players}
    sets = [frozenset(by_id[c] for c in _roster(line)) for line in out.read_bytes().splitlines()[1:]]
    assert len(set(sets)) == len(sets) and qa_defects(tmp_path, capsys, w, out) == 0


def test_the_file_check_reads_a_flex_permutation_as_one_lineup_and_a_new_captain_as_two(tmp_path):
    slate = parse_salaries(salary_csv(tmp_path))
    permuted = [ids(L0)[0], *reversed(ids(L0)[1:])]
    assert any("DUPLICATE_LINEUP" in d for d in tool.file_defects(slate, {"a": ids(L0), "b": permuted}))
    other_captain = ids(["kc_wr2", "kc_qb", *L0[2:]])
    assert tool.file_defects(slate, {"a": ids(L0), "b": other_captain}) == []


# ----- one invalid row refuses the whole publication --------------------------------------------------------------

@pytest.mark.parametrize("bad_row, needle", [
    (["kc_qb", "den_qb", "kc_wr1", "den_wr1", "kc_wr2", "den_wr2"], "LINEUP_SALARY_CAP_EXCEEDED"),
    (["kc_qb", "kc_qb", "den_rb", "den_wr2", "kc_te", "kc_rb"], "LINEUP_PERSON_REPEATED"),
    (["kc_qb", "kc_wr2", "kc_rb", "kc_te", "kc_k", "kc_dst"], "LINEUP_TEAM_COUNT_INVALID"),
])
def test_one_invalid_row_anywhere_refuses_the_whole_file(tmp_path, capsys, bad_row, needle):
    w = build(tmp_path, [L0, L1, bad_row, L3])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "3")
    refused(code, err, out, "INPUT_FILE_NOT_VALID")
    assert needle in err and entry_id(2) in err


def test_a_roster_id_outside_the_pool_refuses_the_whole_file(tmp_path, capsys):
    w = build(tmp_path, [L0, [CPT["kc_qb"], "999", *ids(L0)[2:]]])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "INPUT_FILE_NOT_VALID")


def test_a_partly_filled_row_refuses(tmp_path, capsys):
    w = build(tmp_path, [L0, [*ids(L1)[:3], "", "", ""]])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "PARTIAL_ROW")


# ----- exclusive create, and nothing else ---------------------------------------------------------------------------

def test_an_existing_output_is_refused_and_never_touched(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, BASE)
    existing = tmp_path / "out.csv"
    existing.write_bytes(b"an earlier file\r\n")
    code, _report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    assert code == tool.EXIT_REFUSED and "REFUSED OUTPUT_EXISTS" in err
    assert existing.read_bytes() == b"an earlier file\r\n"
    # The early look is not the only guard: the create itself is exclusive, so a file that appears after it is safe too.
    monkeypatch.setattr(Path, "exists", lambda self: False)
    code, _report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    assert code == tool.EXIT_REFUSED and "appeared while writing" in err
    assert existing.read_bytes() == b"an earlier file\r\n"


def test_an_output_in_a_missing_directory_is_refused_and_leaves_nothing(tmp_path, capsys):
    w = build(tmp_path, BASE)
    code, _report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], out="no_such_dir/out.csv")
    assert code == tool.EXIT_REFUSED and "REFUSED OUTPUT_UNWRITABLE" in err
    assert not (tmp_path / "no_such_dir").exists()


def test_output_is_deterministic_and_a_changed_input_byte_withholds_it(tmp_path, capsys):
    w = build(tmp_path, BASE)
    first = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "3", out="a.csv")
    second = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "3", out="b.csv")
    assert first[0] == second[0] == tool.EXIT_OK
    assert first[3].read_bytes() == second[3].read_bytes()
    assert first[1]["out_sha256"] == second[1]["out_sha256"]
    # One byte of the review outside the roster (the Contest ID) no longer matches the template.
    w["rev"].write_bytes(w["rev"].read_bytes().replace(b",9001,", b",9002,", 1))
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], out="c.csv")
    refused(code, err, out, "REVIEW_NOT_DERIVED_FROM_TEMPLATE")


@pytest.mark.parametrize("gate", ["file_defects", "bytes_defects"])
def test_the_output_is_audited_on_its_own_and_one_defect_there_publishes_nothing(tmp_path, capsys, monkeypatch, gate):
    """The search cannot be trusted to be the only guard: a defect found only in the rebuilt bytes withholds the file."""
    real, calls = getattr(tool, gate), []

    def second_call_finds_a_defect(*args, **kwargs):
        calls.append(1)
        found = real(*args, **kwargs)
        return found if len(calls) == 1 else [*found, f"{gate}: forced defect"]

    monkeypatch.setattr(tool, gate, second_call_finds_a_defect)
    w = build(tmp_path, BASE)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "OUTPUT_FAILED_VALIDATION")
    assert "forced defect" in err and len(calls) == 2


def test_a_write_failure_after_the_file_exists_removes_it_and_is_a_refusal(tmp_path, capsys, monkeypatch):
    def disk_full(_fd):
        raise OSError("disk full")

    monkeypatch.setattr(tool.os, "fsync", disk_full)
    code, _report, err, out = go(tmp_path, capsys, build(tmp_path, BASE), "--dk-id", FLEX[T])
    refused(code, err, out, "OUTPUT_UNWRITABLE")
    assert "disk full" in err


def test_a_file_that_does_not_read_back_as_validated_is_removed(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(tool.os, "fsync", lambda fd: os.ftruncate(fd, 7))  # the bytes on disk are not the bytes checked
    code, _report, err, out = go(tmp_path, capsys, build(tmp_path, BASE), "--dk-id", FLEX[T])
    refused(code, err, out, "OUTPUT_READBACK_MISMATCH")


def test_a_file_that_cannot_be_removed_is_named_as_unusable(tmp_path, capsys, monkeypatch):
    def disk_full(_fd):
        raise OSError("disk full")

    def locked(self, *args, **kwargs):
        raise PermissionError("locked by another process")

    monkeypatch.setattr(tool.os, "fsync", disk_full)
    monkeypatch.setattr(Path, "unlink", locked)
    code, _report, err, out = go(tmp_path, capsys, build(tmp_path, BASE), "--dk-id", FLEX[T])
    assert code == tool.EXIT_REFUSED and "REFUSED OUTPUT_LEFT_BEHIND" in err and "do not use it" in err
    assert out.exists()  # the one case where a file stays, and the refusal says so


# Every variant is applied to the template and the review alike; the expected output gets the same transform.
VARIANTS = {
    "bom": lambda b: b"\xef\xbb\xbf" + b,
    "lf_only": lambda b: b.replace(b"\r\n", b"\n"),
    "no_final_newline": lambda b: b[:-2],
    "cp1252_note": lambda b: b.replace(b"note, with", b"n\xf3te, with"),
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_every_byte_outside_the_swapped_cell_survives_a_file_shape_variant(tmp_path, capsys, variant):
    w = build(tmp_path, BASE)
    for key in ("tpl", "rev"):
        w[key].write_bytes(VARIANTS[variant](w[key].read_bytes()))
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1")
    assert code == tool.EXIT_OK, err
    row, slot = int(report["swaps"][0]["entry_id"][-5:]), int(report["swaps"][0]["slot"].split()[1])
    expected = [list(r) for r in BASE]
    expected[row][slot] = T
    plain = ENTRY_HEADER.encode() + b"".join(entry_line(n, ids(r)) for n, r in enumerate(expected))
    assert out.read_bytes() == VARIANTS[variant](plain)


@pytest.mark.parametrize("bad", ["null", '"abc"', "NaN", "true"])
def test_a_score_that_is_not_a_finite_number_is_a_named_refusal(tmp_path, capsys, bad):
    path = tmp_path / "scores.json"
    path.write_text('{"by_dk_id": {"%s": %s}}' % (FLEX["kc_te"], bad), encoding="utf-8")
    code, _report, err, out = go(tmp_path, capsys, build(tmp_path, BASE), "--dk-id", FLEX[T], "--scores", str(path))
    refused(code, err, out, "SCORES_UNREADABLE")


def test_a_cell_is_scored_by_its_own_id_and_not_by_the_other_role_row(tmp_path, capsys):
    w = build(tmp_path, [L0])
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1",
                                 "--scores", str(scores(tmp_path, {CPT["kc_te"]: -9.0})))
    assert code == tool.EXIT_OK, err
    assert report["swaps"][0]["removed"] == "KC TE" and report["swaps"][0]["removed_score"] == 0.0


# ----- the template decides which rows may change ---------------------------------------------------------------

def test_a_row_draftkings_prefilled_is_never_edited_and_still_counts_for_distinctness(tmp_path, capsys):
    named = [f"{NAME[L1[0]]} ({CPT[L1[0]]})", *(f"{NAME[k]} ({FLEX[k]})" for k in L1[1:])]  # `Name (ID)` cells
    rows = [L0, named, L2, L3]
    w = build(tmp_path, rows, prefilled={1})
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "10")
    assert code == tool.EXIT_PARTIAL, err  # asked for ten, only the three template-blank rows can change
    assert report["swapped"] == 3 and entry_id(1) not in {s["entry_id"] for s in report["swaps"]}
    assert out.read_bytes().splitlines()[2] == w["rev"].read_bytes().splitlines()[2]
    assert qa_defects(tmp_path, capsys, w, out) == 0
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", entry_id(1), out="d.csv")
    refused(code, err, out, "ENTRY_NOT_SWAPPABLE")


def test_a_review_that_changed_a_prefilled_row_is_refused(tmp_path, capsys):
    w = build(tmp_path, [L0, L1], prefilled={1})
    w["rev"].write_bytes(w["rev"].read_bytes().replace(CPT["den_qb"].encode(), CPT["kc_qb"].encode(), 1))
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "REVIEW_NOT_DERIVED_FROM_TEMPLATE")


def test_the_byte_audit_lets_only_a_blank_rows_roster_cells_change(tmp_path):
    w = build(tmp_path, [L0, L1], prefilled={1})
    tpl = w["tpl"].read_bytes()

    def audit(other: bytes):
        return tool.bytes_defects(tpl, other, 4, "x")

    assert audit(tpl) == []
    assert audit(tpl.replace(entry_line(0), entry_line(0, ids(L0)))) == []           # a blank row, filled
    assert audit(tpl.replace(entry_line(1, ids(L1)), entry_line(1, ids(L0))))         # a prefilled row, edited
    assert audit(tpl.replace(b",9001,", b",9002,", 1))                                # outside the roster cells
    assert audit(tpl.replace(b"\r\n", b"\n", 1))                                      # a line ending
    assert audit(tpl + b"one more line\r\n")                                          # the line count


def test_blank_rows_pass_through_and_do_not_count(tmp_path, capsys):
    w = build(tmp_path, [L0, None, L2])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "5")
    assert code == tool.EXIT_PARTIAL, err
    assert report["swapped"] == 2 and report["after"]["filled_rows"] == 2
    assert out.read_bytes().splitlines()[2] == entry_line(1).rstrip(b"\r\n")


# ----- the shape of the review's reproduction (acceptance 5) ---------------------------------------------------------

def test_a_rerun_on_a_file_that_already_holds_him_publishes_no_invalid_row(tmp_path, capsys):
    holders = [[L1[0], *[T if c == "den_te" else c for c in L1[1:]]],
               [L3[0], *[T if c == "kc_k" else c for c in L3[1:]]],
               [L2[0], *[T if c == "kc_te" else c for c in L2[1:]]]]
    w = build(tmp_path, [L0, *holders, ["kc_wr2", "kc_qb", "den_rb", "den_wr2", "kc_te", "kc_rb"]])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "36")
    assert code == tool.EXIT_PARTIAL, err
    assert report["already_holds"] == [entry_id(1), entry_id(2), entry_id(3)]
    assert report["swapped"] == 2 and qa_defects(tmp_path, capsys, w, out) == 0
    slate = parse_salaries(w["sal"])
    new_rows = [_roster(line) for line in out.read_bytes().splitlines()[1:]]
    assert all(validate_lineup(slate, r).valid for r in new_rows)
    assert len({roster_canonical_key(slate, r) for r in new_rows}) == len(new_rows)
    assert new_rows[1:4] == [_roster(line) for line in w["rev"].read_bytes().splitlines()[2:5]]


# ----- selection ---------------------------------------------------------------------------------------------------------

def test_the_lowest_scored_cell_goes_first_and_the_last_team_player_never_does(tmp_path, capsys):
    only_den = ["kc_qb", "kc_wr2", "kc_rb", "kc_te", "kc_wr1", "den_rb"]  # den_rb is the only Denver player
    w = build(tmp_path, [only_den])
    mapping = {FLEX["den_rb"]: -5.0, FLEX["kc_te"]: 1.0, FLEX["kc_wr2"]: 2.0, FLEX["kc_rb"]: 3.0, FLEX["kc_wr1"]: 4.0}
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1", "--scores",
                                 str(scores(tmp_path, mapping)))
    assert code == tool.EXIT_OK, err
    assert report["swaps"][0]["removed"] == "KC TE" and report["swaps"][0]["removed_score"] == 1.0
    assert report["order"] == "scores"


def test_without_scores_the_cheapest_cell_goes_first_and_the_report_says_so(tmp_path, capsys):
    w = build(tmp_path, [L0])
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1")
    assert code == tool.EXIT_OK, err
    assert report["swaps"][0]["removed"] == "KC TE" and report["order"] == "UNSCORED_BY_SALARY_THEN_DK_ID"


def test_the_captain_is_touched_only_with_the_captain_flag_and_the_cap_binds(tmp_path, capsys):
    over = ["kc_te", "kc_qb", "kc_wr1", "den_wr1", "den_rb", "kc_rb"]   # 47,000: a 16,500 Captain does not fit
    room = ["den_dst", "kc_wr2", "kc_te", "kc_rb", "den_te", "kc_k"]    # 26,500: it does
    w = build(tmp_path, [over, room])
    target = "den_qb"
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[target], "--captain", "--count", "5")
    assert code == tool.EXIT_PARTIAL, err
    assert [(s["entry_id"], s["slot"]) for s in report["swaps"]] == [(entry_id(1), "CPT")]
    assert report["skipped"] == {entry_id(0): "NO_VALID_SWAP"}
    want = ENTRY_HEADER.encode() + entry_line(0, ids(over)) + entry_line(
        1, [CPT[target], *ids(room)[1:]])
    assert out.read_bytes() == want  # only cell 5, the Captain, changed
    flex_only = go(tmp_path, capsys, w, "--dk-id", FLEX[target], "--count", "5", out="flex.csv")
    assert all(s["slot"].startswith("FLEX") for s in flex_only[1]["swaps"])


def test_the_thesis_filter_restricts_automatic_selection(tmp_path, capsys):
    w = build(tmp_path, BASE)
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id(0): "S1", entry_id(1): "S2", entry_id(3): "S2"}), encoding="utf-8")
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "9", "--theses", str(theses),
                                 "--thesis", "S2")
    assert code == tool.EXIT_PARTIAL, err
    assert [s["entry_id"] for s in report["swaps"]] == [entry_id(1), entry_id(3)]
    assert go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--thesis", "S2", out="x.csv")[0] == tool.EXIT_REFUSED


def test_a_shortfall_writes_the_file_and_exits_3(tmp_path, capsys):
    w = build(tmp_path, [L0, L1])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "5")
    assert code == tool.EXIT_PARTIAL, err
    assert (report["requested"], report["swapped"], report["shortfall"]) == (5, 2, 3) and out.exists()


# ----- refusals by name -------------------------------------------------------------------------------------------------------

def test_an_unknown_dk_id_is_refused(tmp_path, capsys):
    w = build(tmp_path, BASE)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", "999999")
    refused(code, err, out, "DK_ID_NOT_IN_POOL")


@pytest.mark.parametrize("status", ["Out", "IR"])
def test_a_person_draftkings_marks_unavailable_is_refused(tmp_path, capsys, status):
    w = build(tmp_path, BASE, status=status)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T])
    refused(code, err, out, "PERSON_UNAVAILABLE_PER_DK_STATUS")


def test_a_classic_slate_is_a_hard_stop(tmp_path, capsys):
    games = ["AAA@BBB 09/14/2026 01:00PM ET", "CCC@DDD 09/14/2026 04:25PM ET"]
    sal, n = [], 100
    for game in games:
        for team in game.split()[0].split("@"):
            for pos, roster, count in (("QB", "QB", 1), ("RB", "RB/FLEX", 2), ("WR", "WR/FLEX", 3),
                                       ("TE", "TE/FLEX", 1), ("DST", "DST", 1)):
                for k in range(count):
                    n += 1
                    sal.append(f"{pos},{team} {pos}{k} ({n}),{team} {pos}{k},{n},{roster},5000,{game},{team},0,\n")
    sal_path = tmp_path / "classic.csv"
    sal_path.write_text(SALARY_HEADER + "".join(sal), encoding="utf-8")
    header = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\r\n"
    body = "1,Classic,9001,$5,,,,,,,,,,,\r\n"
    for name in ("ctpl", "crev"):
        (tmp_path / f"{name}.csv").write_text(header + body, encoding="utf-8", newline="")
    w = {"sal": sal_path, "tpl": tmp_path / "ctpl.csv", "rev": tmp_path / "crev.csv"}
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", "101")
    refused(code, err, out, "DK_MODE_NOT_SHOWDOWN")
    showdown = {**build(tmp_path, BASE), "tpl": w["tpl"], "rev": w["rev"]}  # a Showdown salary file, Classic entries
    code, _report, err, out = go(tmp_path, capsys, showdown, "--dk-id", FLEX[T], out="y.csv")
    refused(code, err, out, "INPUT_REFUSED")


def test_flag_combinations_that_cannot_mean_anything_are_refused(tmp_path, capsys):
    w = build(tmp_path, BASE)
    for args, name in ((("--count", "2", "--entry-id", entry_id(0)), "ENTRY_ID_CONFLICT"),
                       (("--thesis", "S1", "--theses", "x.json", "--entry-id", entry_id(0)), "ENTRY_ID_CONFLICT"),
                       (("--count", "0"), "COUNT_INVALID"), (("--thesis", "S1"), "THESIS_FILTER_INCOMPLETE"),
                       (("--entry-id", "123"), "ENTRY_NOT_SWAPPABLE"), (("--scores", str(tmp_path / "nope.json")),
                                                                         "SCORES_UNREADABLE")):
        code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], *args)
        refused(code, err, out, name)
