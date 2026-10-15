"""Session 75: `first_place_coverage_v1`, the per-contest first-place reading (R38).

Acceptance (`docs/ROADMAP.md`, Session 75): a seven-entry contest with a repeated Captain names the repeat; a one-entry
contest prints its shape and the no-tail line; a run with no facts names `NO_CONTEST_FACTS` for each contest; the table
equals `contests_after` on the same file; the washout lines and every QA exit code are unchanged (a reading, not a gate);
on the committed MIN@NO and Week 5 Classic files the table prints for every Contest ID.

New fixtures are written with `write_bytes`. Both QA scripts run in-process, as their own tests run them, so no path and
no line ending reaches a hashed text. The pins below were captured from the scripts as they stood at `9432d53`, before
this session edited them (the Showdown ones are Session 66's `c997395` pins, unchanged since).
"""

from __future__ import annotations

import ast
import contextlib
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import contest_facts
from nfl_dfs import first_place_coverage as fpc
from nfl_dfs.dk import parse_salaries
from nfl_dfs.entry_record import _cell_id as record_cell_id

from . import test_qa_classic_portfolio as cl_base
from . import test_qa_showdown_portfolio as sd_base

REPO = Path(__file__).resolve().parent.parent
MINNO = REPO / "data" / "inbox" / "slates" / "min-no-sd-2026-10-11"
WK5 = REPO / "data" / "inbox" / "slates" / "wk5-classic-2026-10-11"
MODULE = REPO / "src" / "nfl_dfs" / "first_place_coverage.py"

# Exit code and SHA-256 of the stdout (`first_place_coverage` removed) per case, from the scripts at `9432d53`.
SHOWDOWN_PINS = {
    "clean": (0, "8c891b47e00ca31a96297eadd092a4ac4ef68d3a91e8c8ab7f6213a24b902afd"),
    "overlap_limit": (2, "a6a4785a99449d1d502c00c6add8506d819390c3040d943854a128cde34ef78e"),
    "unfilled": (3, "85c1626136bfe356f16cbf41039a81f817b6e45b35c8f35ef18f6f5d30d8bbeb"),
}
CLASSIC_PINS = {
    "pass": (0, "8343b0937fd9c2b6ddb6a4b9999c87debdefda82e5d314a84c21234bdfed32af"),
    "fail": (1, "6b6c841f589a8e138e7d180f46144e573e97f2ba2d491e177c307b47d3d855a3"),
    "limit": (2, "130d71f8fa6de75cf1283acfd6bfed57db3948cead7aff4f8cbd140d9655c793"),
    "partial": (3, "f55c672eccce19a8b0f48b9fc8179efb899ffa59e1f9afd0a0d1af37f2456636"),
    "json": (0, "39ac8935e85bad2e2529d70d5debad11d73e0cf00ce8b72456b92404925de109"),
}
REAL_PINS = {
    "min_no_v10": (2, "4f58d12e645a8346df41a07b7533c1218dcc2666be31eb41d83ee4606e10174f"),
    "wk5_v10": (1, "42efbddbd985e0a7334f89374952bbc2a847acf4aac00b976de922c9fcd7d985"),
}

SD_KEY_LINE = '  "first_place_coverage": {'
CL_TITLE = "FIRST PLACE, CONTEST BY CONTEST"


# ----------------------------------------------------------------------------------------------- helpers


def _stdout(call) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = call()
    return code, buffer.getvalue()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_showdown(text: str) -> str:
    """The Showdown stdout without the block: from its key line to the first later line that closes at its indent."""

    lines = text.split("\n")
    start = lines.index(SD_KEY_LINE)
    end = lines.index("  },", start)
    return "\n".join(lines[:start] + lines[end + 1:])


def strip_classic(text: str) -> str:
    """The Classic stdout without the section: from the blank line above its title rule to the blank line above VERDICT."""

    lines = text.split("\n")
    title = next(n for n, line in enumerate(lines) if line.startswith(CL_TITLE))
    verdict = next(n for n, line in enumerate(lines) if line.startswith("  VERDICT: "))
    return "\n".join(lines[:title - 2] + lines[verdict - 1:])


# Showdown: the 14 people of `test_qa_showdown_portfolio`, each with a CPT and a FLEX row.
SD_SEVEN = [
    ["kc_qb", "kc_wr1", "den_rb", "den_wr1", "kc_te", "den_te"],
    ["kc_qb", "kc_wr2", "den_rb", "den_wr2", "kc_rb", "den_k"],
    ["den_qb", "den_wr1", "kc_rb", "kc_wr1", "den_te", "kc_k"],
    ["kc_wr1", "kc_qb", "den_wr2", "den_rb", "kc_dst", "den_k"],
    ["den_wr1", "den_qb", "kc_wr2", "kc_te", "den_rb", "kc_k"],
    ["kc_rb", "kc_qb", "den_qb", "den_wr1", "kc_wr2", "den_dst"],
    ["den_rb", "den_qb", "kc_wr1", "kc_rb", "den_te", "kc_te"],
]
SD_ONE = ["den_wr2", "den_qb", "kc_qb", "kc_wr2", "den_te", "kc_dst"]   # Captain at 9000, 44000 in all
SD_PLAN = [("700", lineup) for lineup in SD_SEVEN] + [("100", SD_ONE)]
SD_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions\n"

# Classic: the people of `test_qa_classic_portfolio`. Contest 300 holds three lineups of one QB; contest 100 one lineup
# of the other (AAA QB2 with three AAA teammates, two BBB players, 41000 in all).
CL_BACKUP_START = ["2", "3", "6", "4", "7", "9", "5", "10", "8"]
CL_PLAN = [("300", cl_base.legal_for(k)) for k in range(3)] + [("100", CL_BACKUP_START)]
CL_HEADER = cl_base.ENTRY_HEADER


def sd_entry_id(n: int) -> str:
    return f"77700{n:05d}"


def cl_entry_id(n: int) -> str:
    return f"88800{n:05d}"


def sd_salary(folder: Path) -> Path:
    rows = []
    for key, name, pos, team, salary in sd_base.PEOPLE:
        for role, table, price in (("CPT", sd_base.CPT, salary * 3 // 2), ("FLEX", sd_base.FLEX, salary)):
            rows.append(f"{pos},{name} ({table[key]}),{name},{table[key]},{role},{price},{sd_base.GAME},{team},0,\n")
    path = folder / "sd_salary.csv"
    path.write_bytes((sd_base.SALARY_HEADER + "".join(rows)).encode("utf-8"))
    return path


def cl_salary(folder: Path) -> Path:
    body = "".join(
        f"{pos},{name} ({i}),{name},{i},{cl_base.roster_position(pos)},{s},{g} 09/20/2026 01:00PM ET,{t},0,\n"
        for i, name, pos, t, g, s in cl_base.PEOPLE + cl_base.FLEX_POOL)
    path = folder / "cl_salary.csv"
    path.write_bytes((cl_base.SALARY_HEADER + body).encode("utf-8"))
    return path


def sd_line(n: int, contest: str, cells=("",) * 6) -> str:
    return f"{sd_entry_id(n)},Showdown,{contest},$5,{','.join(cells)},,\n"


def cl_line(n: int, contest: str, cells=None) -> str:
    return f"{cl_entry_id(n)},Classic,{contest},$5,{','.join(cells) if cells else ',' * 8},,\n"


def sd_files(folder: Path, plan=SD_PLAN) -> tuple[Path, Path, Path]:
    template = folder / "sd_template.csv"
    template.write_bytes((SD_HEADER + "".join(sd_line(n, c) for n, (c, _l) in enumerate(plan))).encode("utf-8"))
    export = folder / "sd_export.csv"
    export.write_bytes(
        (SD_HEADER + "".join(sd_line(n, c, sd_base.ids(l)) for n, (c, l) in enumerate(plan))).encode("utf-8"))
    return sd_salary(folder), template, export


def cl_files(folder: Path, plan=CL_PLAN) -> tuple[Path, Path, Path, Path]:
    template = folder / "cl_template.csv"
    template.write_bytes((CL_HEADER + "".join(cl_line(n, c) for n, (c, _l) in enumerate(plan))).encode("utf-8"))
    export = folder / "cl_export.csv"
    export.write_bytes((CL_HEADER + "".join(cl_line(n, c, l) for n, (c, l) in enumerate(plan))).encode("utf-8"))
    portfolio = folder / "cl_portfolio.json"
    portfolio.write_bytes(json.dumps(
        {"lineups": [], "assignments_by_entry_id": {cl_entry_id(n): l for n, (_c, l) in enumerate(plan)}}).encode("utf-8"))
    return cl_salary(folder), template, export, portfolio


def sd_qa(folder: Path, *extra: str, plan=SD_PLAN) -> tuple[int, dict, str]:
    salary, template, export = sd_files(folder, plan)
    code, text = _stdout(lambda: sd_base.qa.main(
        ["--salaries", str(salary), "--template", str(template), "--export", str(export), *extra]))
    return code, json.loads(text), text


def cl_qa(folder: Path, *extra: str, plan=CL_PLAN, export_file=True) -> tuple[int, dict, str]:
    salary, template, export, portfolio = cl_files(folder, plan)
    record = folder / "qa.json"
    files = ["--template", str(template), "--export", str(export)] if export_file else []
    code, text = _stdout(lambda: cl_base.qa.main(
        ["--portfolio", str(portfolio), "--salaries", str(salary), *files, "--json", str(record), *extra]))
    return code, json.loads(record.read_text(encoding="utf-8")), text


def facts_json(folder: Path, body: str, entries_file: Path, mode: str, name: str = "facts.json") -> Path:
    """The run's `selection/contest_facts.json` for these entries, built by `contest_facts.build_block` itself."""

    facts_csv = folder / "facts.csv"
    facts_csv.write_bytes(body.encode("utf-8"))
    rows, _state = fpc.read_entries_file(entries_file, mode=mode)
    block = contest_facts.build_block(facts_csv, [(entry_id, contest, 5.0) for entry_id, contest, _r in rows])
    path = folder / name
    path.write_bytes(contest_facts.canonical_bytes(block))
    return path


def by_contest(reading: dict) -> dict[str, dict]:
    return {row["contest_id"]: row for row in reading["contests"]}


SD_CAPTAIN = "KC|QB|KC QB"
CL_QB = "AAA|QB|AAA QB"
FACTS_HEADER = "contest_id,field_size,places_paid,entry_fee\n"


# ---------------------------------------------------------------------- acceptance 1: a repeat is named


def test_a_repeated_captain_in_a_seven_entry_contest_is_named(tmp_path):
    salary, _template, export = sd_files(tmp_path)
    rows, state = fpc.read_entries_file(export, mode=ca.MODE_SHOWDOWN)
    assert state == fpc.READ
    reading = fpc.reading(rows, mode=ca.MODE_SHOWDOWN, players=fpc.players_from_salary_csv(salary))
    seven = by_contest(reading)["700"]
    assert seven["entries"] == 7
    assert seven["repeated_key_people"] == [{"person": SD_CAPTAIN, "entries": 2}]
    assert seven["statistics"]["distinct_key_people"] == 6
    assert reading["key_person"] == "CAPTAIN"


def test_the_showdown_qa_names_the_repeated_captain(tmp_path):
    _code, report, _text = sd_qa(tmp_path)
    seven = by_contest(report["first_place_coverage"])["700"]
    assert seven["repeated_key_people"] == [{"person": SD_CAPTAIN, "entries": 2}]


def test_the_classic_qa_names_the_repeated_quarterback(tmp_path):
    code, record, text = cl_qa(tmp_path)
    three = by_contest(record["first_place_coverage"])["300"]
    assert three["repeated_key_people"] == [{"person": CL_QB, "entries": 3}]
    assert f"repeated QBs: {CL_QB} x3" in text
    assert code == 0


# ---------------------------------------------------------------- acceptance 2: one entry reads its shape


def test_a_one_entry_showdown_contest_prints_its_captain_salary_and_the_no_tail_line(tmp_path):
    _code, report, _text = sd_qa(tmp_path)
    one = by_contest(report["first_place_coverage"])["100"]
    assert one["entries"] == 1 and "statistics" not in one
    assert one["shape"] == {"captain": "DEN|WR|DEN WR2", "captain_salary": 9000, "salary_left": 6000}
    assert one["no_tail_statistic"] == fpc.NO_TAIL_LINE
    assert report["first_place_coverage"]["one_entry_contest_count"] == 1


def test_a_one_entry_classic_contest_prints_its_stack_bring_back_and_the_no_tail_line(tmp_path):
    _code, record, text = cl_qa(tmp_path)
    one = by_contest(record["first_place_coverage"])["100"]
    assert one["shape"] == {"quarterback": "AAA|QB|AAA QB2", "stack_team": "AAA", "stack_depth": 4,
                            "bring_back": 2, "salary_left": 9000}
    assert one["no_tail_statistic"] == fpc.NO_TAIL_LINE
    section = text[text.index(CL_TITLE):]
    assert "contest 100: 1 entry" in section and fpc.NO_TAIL_LINE in section
    assert "QB AAA|QB|AAA QB2, stack AAA x4, bring-back 2, salary left 9000" in section


def test_repeated_quarterbacks_are_listed_most_held_first(tmp_path):
    second_qb = ["2", "3", "6", "4", "7", "9", "5", cl_base.FLEX_POOL[0][0], "8"]
    rosters = [cl_base.legal_for(k) for k in range(3)] + [CL_BACKUP_START, second_qb]
    reading = fpc.reading([(cl_entry_id(n), "600", tuple(r)) for n, r in enumerate(rosters)], mode=ca.MODE_CLASSIC,
                          players=fpc.players_from_salary_csv(cl_salary(tmp_path)))
    assert by_contest(reading)["600"]["repeated_key_people"] == [
        {"person": CL_QB, "entries": 3}, {"person": "AAA|QB|AAA QB2", "entries": 2}]


def test_the_bring_back_is_read_from_the_stack_teams_opponent(tmp_path):
    """The QB's team (AAA, two players) is not the primary stack (CCC, three), so the bring-back is DDD's two, not BBB's one."""

    roster = ("1", "10", "6", "9", "13", "20", "12", "3", "11")
    reading = fpc.reading([(cl_entry_id(0), "500", roster)], mode=ca.MODE_CLASSIC,
                          players=fpc.players_from_salary_csv(cl_salary(tmp_path)))
    assert by_contest(reading)["500"]["shape"] == {"quarterback": CL_QB, "stack_team": "CCC", "stack_depth": 3,
                                                  "bring_back": 2, "salary_left": 9000}


# ------------------------------------------------------------------- acceptance 3: no facts, named per contest


def test_with_no_facts_every_contest_reads_no_contest_facts(tmp_path):
    (tmp_path / "sd").mkdir()
    (tmp_path / "cl").mkdir()
    _code, report, _text = sd_qa(tmp_path / "sd")
    _code, record, text = cl_qa(tmp_path / "cl")
    for reading in (report["first_place_coverage"], record["first_place_coverage"]):
        assert reading["facts"] == {"binding": "NOT_SUPPLIED", "detail": None, "facts_status": None}
        assert reading["contests"] and all(row["facts_state"] == "NO_CONTEST_FACTS" for row in reading["contests"])
        assert all(row["field_size"] is None and row["label"] is None for row in reading["contests"])
    section = text[text.index(CL_TITLE):]
    assert section.count("facts NO_CONTEST_FACTS") == 2
    assert "every contest is read as a tournament (R38)" in section


# ----------------------------------------------------------------------- the facts states pass through


def test_the_facts_states_pass_through_on_both_scripts(tmp_path):
    (tmp_path / "sd").mkdir()
    (tmp_path / "cl").mkdir()
    _salary, _template, sd_export = sd_files(tmp_path / "sd")
    sd_facts = facts_json(tmp_path / "sd", FACTS_HEADER + "700,1000,49,5\n", sd_export, ca.MODE_SHOWDOWN)
    _code, report, _text = sd_qa(tmp_path / "sd", "--contest-facts", str(sd_facts))
    _salary, _template, cl_export, _portfolio = cl_files(tmp_path / "cl")
    cl_facts = facts_json(tmp_path / "cl", FACTS_HEADER + "300,1000,49,5\n100,200,40,6\n", cl_export, ca.MODE_CLASSIC)
    _code, record, text = cl_qa(tmp_path / "cl", "--contest-facts", str(cl_facts))

    showdown = by_contest(report["first_place_coverage"])
    assert report["first_place_coverage"]["facts"] == {"binding": "BOUND", "detail": None, "facts_status": "PARTIAL"}
    assert {c: row["facts_state"] for c, row in showdown.items()} == {"100": "NO_FACTS_ROW", "700": "SUPPLIED"}
    assert (showdown["700"]["field_size"], showdown["700"]["places_paid"]) == (1000, 49)
    assert (showdown["700"]["paid_fraction"], showdown["700"]["label"]) == ("49/1000", "FIRST_PLACE_OBJECTIVE")
    assert showdown["100"]["label"] is None and showdown["100"]["field_size"] is None

    classic = by_contest(record["first_place_coverage"])
    assert {c: row["facts_state"] for c, row in classic.items()} == {"100": "FEE_DISAGREES", "300": "SUPPLIED"}
    assert classic["100"]["paid_fraction"] is None and classic["100"]["field_size"] == 200
    assert "contest 300: 3 entries; facts SUPPLIED (field 1000, paid 49, 49/1000, FIRST_PLACE_OBJECTIVE)" in text


def _no_object(path: Path, _good: Path) -> None:
    path.write_bytes(b"[]")


def _not_json(path: Path, _good: Path) -> None:
    path.write_bytes(b"{not json")


def _other_schema(path: Path, good: Path) -> None:
    block = json.loads(good.read_bytes())
    block["schema_version"] = "nfl_contest_facts_labels_v9"
    path.write_bytes(json.dumps(block).encode("utf-8"))


def _other_contests(path: Path, good: Path) -> None:
    block = json.loads(good.read_bytes())
    block["contests"] = [dict(row, contest_id="999") if row["contest_id"] == "100" else row for row in block["contests"]]
    path.write_bytes(json.dumps(block).encode("utf-8"))


def _too_deep(path: Path, _good: Path) -> None:
    path.write_bytes(b"[" * 200_000)   # json raises RecursionError, not ValueError


NOT_BOUND_CASES = {
    "not_object": (_no_object, "NOT_AN_OBJECT"),
    "not_json": (_not_json, "UNREADABLE"),
    "too_deep": (_too_deep, "UNREADABLE"),
    "schema": (_other_schema, "SCHEMA_VERSION"),
    "contests": (_other_contests, "CONTEST_SET"),
}


@pytest.mark.parametrize("case", sorted(NOT_BOUND_CASES))
def test_a_showdown_facts_file_that_does_not_bind_is_named_for_the_table_alone(tmp_path, case):
    make, detail = NOT_BOUND_CASES[case]
    (tmp_path / "none").mkdir()
    plain_code, plain, _text = sd_qa(tmp_path / "none")
    _salary, _template, export = sd_files(tmp_path)
    good = facts_json(tmp_path, FACTS_HEADER + "700,1000,49,5\n100,200,40,5\n", export, ca.MODE_SHOWDOWN)
    bad = tmp_path / "bad.json"
    make(bad, good)
    code, report, _text = sd_qa(tmp_path, "--contest-facts", str(bad))
    reading = report.pop("first_place_coverage")
    assert reading["facts"] == {"binding": "NOT_BOUND", "detail": detail, "facts_status": None}
    assert all(row["facts_state"] == "NO_CONTEST_FACTS" for row in reading["contests"])
    plain.pop("first_place_coverage")
    assert (code, report) == (plain_code, plain)


def test_a_classic_facts_file_that_does_not_bind_changes_no_other_line(tmp_path):
    (tmp_path / "none").mkdir()
    plain_code, _record, plain_text = cl_qa(tmp_path / "none")
    _salary, _template, export, _portfolio = cl_files(tmp_path)
    good = facts_json(tmp_path, FACTS_HEADER + "300,1000,49,5\n100,200,40,5\n", export, ca.MODE_CLASSIC)
    bad = tmp_path / "bad.json"
    _other_contests(bad, good)
    code, record, text = cl_qa(tmp_path, "--contest-facts", str(bad))
    assert record["first_place_coverage"]["facts"]["binding"] == "NOT_BOUND"
    assert "facts NOT_BOUND (CONTEST_SET)" in text
    assert code == plain_code
    assert strip_classic(text).replace(str(tmp_path), "") == strip_classic(plain_text).replace(str(tmp_path / "none"), "")


def test_a_refused_facts_block_binds_with_no_rows(tmp_path):
    _salary, _template, export = sd_files(tmp_path)
    refused = facts_json(tmp_path, FACTS_HEADER + "700,1000,0,5\n", export, ca.MODE_SHOWDOWN)
    assert json.loads(refused.read_bytes())["status"] == "REFUSED"
    _code, report, _text = sd_qa(tmp_path, "--contest-facts", str(refused))
    reading = report["first_place_coverage"]
    assert reading["facts"] == {"binding": "NO_ROWS", "detail": None, "facts_status": "REFUSED"}
    assert all(row["facts_state"] == "NO_CONTEST_FACTS" for row in reading["contests"])


# ------------------------------------------------------- acceptance 4: the table equals `contests_after`


def _diversified(mode, plan, entry_id, players, labelled):
    people = fpc.people(players)
    rosters = {entry_id(n): tuple(lineup) for n, (_c, lineup) in enumerate(plan)}
    labels = {roster: ("A" if n % 2 else "B") for n, roster in enumerate(rosters.values())} if labelled else None
    rows = [ca.EntryRow(entry_id(n), contest, rosters[entry_id(n)], ca.POOL_ALL) for n, (contest, _l) in enumerate(plan)]
    outcome = ca.diversify(rows, mode=mode, people=people, thesis_by_roster=labels, time_limit_seconds=None)
    final = [(row.entry_id, row.contest_id, tuple(outcome.assignments[row.entry_id])) for row in rows]
    thesis_by_entry = {entry: labels[roster] for entry, _c, roster in final} if labels else None
    return final, thesis_by_entry, outcome.report["contests_after"]


# Two contests of four and one of one, so the assignment has rows to move between contests.
SD_EXTRA = ["den_te", "kc_qb", "den_qb", "kc_wr1", "den_rb", "kc_k"]
SD_EQUALITY_PLAN = ([("700", sd_base.ids(l)) for l in SD_SEVEN[:4]] + [("800", sd_base.ids(l)) for l in SD_SEVEN[4:]]
                    + [("800", sd_base.ids(SD_EXTRA)), ("100", sd_base.ids(SD_ONE))])
CL_EQUALITY_PLAN = ([("300", cl_base.legal_for(k)) for k in range(3)] + [("400", cl_base.legal_for(k)) for k in range(3, 6)]
                    + [("400", CL_BACKUP_START), ("100", cl_base.legal_for(7))])


@pytest.mark.parametrize("labelled", [False, True], ids=["plain", "labels"])
@pytest.mark.parametrize("mode", [ca.MODE_SHOWDOWN, ca.MODE_CLASSIC], ids=["sd", "cl"])
def test_the_statistics_equal_contests_after_on_the_same_file(tmp_path, mode, labelled):
    if mode == ca.MODE_SHOWDOWN:
        plan, players, entry_id = SD_EQUALITY_PLAN, fpc.players_from_salary_csv(sd_salary(tmp_path)), sd_entry_id
    else:
        plan, players, entry_id = CL_EQUALITY_PLAN, fpc.players_from_salary_csv(cl_salary(tmp_path)), cl_entry_id
    final, thesis_by_entry, after = _diversified(mode, plan, entry_id, players, labelled)
    reading = fpc.reading(final, mode=mode, players=players, thesis_by_entry=thesis_by_entry)
    table = {row["contest_id"]: row["statistics"] for row in reading["contests"] if row["entries"] >= 2}
    assert table == after and set(after) == {c for c, _l in plan} - {"100"}
    assert reading["thesis_labels"] == ("SUPPLIED" if labelled else "NONE")


def test_a_one_entry_contest_is_a_shape_row_and_absent_from_contests_after(tmp_path):
    players = fpc.players_from_salary_csv(cl_salary(tmp_path))
    final, _labels, after = _diversified(ca.MODE_CLASSIC, CL_PLAN, cl_entry_id, players, False)
    reading = fpc.reading(final, mode=ca.MODE_CLASSIC, players=players)
    assert "100" not in after and "shape" in by_contest(reading)["100"]
    assert set(after) == {"300"}


def test_the_salary_people_are_the_runs_people():
    for path in (MINNO / "input" / "DKSalaries_169.csv", WK5 / "input" / "DKSalaries.csv"):
        players = fpc.players_from_salary_csv(path)
        slate = parse_salaries(path)
        assert fpc.people(players) == ca.people_from_slate(slate.players)
        assert players == fpc.players_from_slate(slate.players)


def test_the_synthetic_salary_people_are_keyed_team_position_name(tmp_path):
    players = fpc.players_from_salary_csv(sd_salary(tmp_path))
    assert players[sd_base.CPT["kc_qb"]].key == players[sd_base.FLEX["kc_qb"]].key == SD_CAPTAIN
    assert players[sd_base.CPT["kc_qb"]].salary == 16500 and players[sd_base.FLEX["kc_qb"]].opponent == "DEN"
    classic = fpc.players_from_salary_csv(cl_salary(tmp_path))
    assert (classic["1"].key, classic["1"].team, classic["1"].opponent) == (CL_QB, "AAA", "BBB")


CELL_FORMS = ["123", " 123 ", "Name (123)", "Name (123) (LOCKED)", "Name (123)(LOCKED)", "Name", "", "(LOCKED)",
              "Name (123) (LOCKED) (LOCKED)", "12a", "Name (12a)", "Name (123) x"]


def test_the_cell_reader_matches_the_build_records(tmp_path):
    assert [fpc.cell_dk_id(cell) for cell in CELL_FORMS] == [record_cell_id(cell) for cell in CELL_FORMS]


# ---------------------------------------------------------- acceptance 5: a reading, never a gate (pins)


def showdown_pin_runs(tmp_path: Path) -> dict[str, tuple[int, str]]:
    """Session 66's three unflagged runs (`tests/test_qa_showdown_thesis.py::no_flag_runs`), with the raw stdout."""

    base = tmp_path / "clean"
    base.mkdir()
    salary = sd_base.salary_csv(base)
    template, export = sd_base.files(base, [sd_base.LEGAL, sd_base.OTHER])
    argv = ["--salaries", str(salary), "--template", str(template), "--export", str(export)]
    unfilled = tmp_path / "unfilled"
    unfilled.mkdir()
    salary_u = sd_base.salary_csv(unfilled)
    template_u = unfilled / "tpl.csv"
    template_u.write_text(sd_base.ENTRY_HEADER + sd_base.entry_line(0) + sd_base.entry_line(1), encoding="utf-8")
    export_u = unfilled / "exp.csv"
    export_u.write_text(sd_base.ENTRY_HEADER + sd_base.entry_line(0, sd_base.ids(sd_base.LEGAL)) + sd_base.entry_line(1),
                        encoding="utf-8")
    return {
        "clean": _stdout(lambda: sd_base.qa.main(argv)),
        "overlap_limit": _stdout(lambda: sd_base.qa.main([*argv, "--max-overlap", "1"])),
        "unfilled": _stdout(lambda: sd_base.qa.main(
            ["--salaries", str(salary_u), "--template", str(template_u), "--export", str(export_u)])),
    }


def test_the_showdown_output_outside_the_block_is_the_pinned_output(tmp_path):
    for name, (code, text) in showdown_pin_runs(tmp_path).items():
        assert SD_KEY_LINE in text
        assert (code, _sha(strip_showdown(text))) == SHOWDOWN_PINS[name], name
        whole = json.loads(text)
        assert list(whole)[-2:] == ["first_place_coverage", "VERDICT"]
        whole.pop("first_place_coverage")
        assert json.loads(strip_showdown(text)) == whole


def classic_pin_runs(tmp_path: Path) -> dict[str, tuple[int, str]]:
    """The Classic cases, as captured from the script at `9432d53` (no `--export` except `partial`, its path masked)."""

    runs = {}
    for name, rosters, extra in (("pass", [cl_base.LEGAL], []),
                                 ("fail", [cl_base.LEGAL], ["--cap", "10000"]),
                                 ("limit", [CL_BACKUP_START], ["--backup-pairs", "AAA QB>AAA QB2"])):
        folder = tmp_path / name
        folder.mkdir()
        runs[name] = _stdout(lambda: cl_base.run(folder, rosters, extra))
    folder = tmp_path / "partial"
    folder.mkdir()
    assigned, template, export, _code, _named = cl_base._missing_id(folder)
    code, out = _stdout(lambda: cl_base.check(folder, assigned, template, export))
    runs["partial"] = (code, out.replace(str(export), "<EXPORT>"))
    return runs


def test_the_classic_output_outside_the_section_is_the_pinned_output(tmp_path):
    for name, (code, text) in classic_pin_runs(tmp_path).items():
        assert CL_TITLE in text, name
        assert (code, _sha(strip_classic(text))) == CLASSIC_PINS[name], name


def test_the_classic_json_record_is_the_pinned_record_plus_one_key(tmp_path):
    record = tmp_path / "qa.json"
    code, _text = _stdout(lambda: cl_base.run(tmp_path, [cl_base.LEGAL, cl_base.legal_for(0)], ["--json", str(record)]))
    doc = json.loads(record.read_text(encoding="utf-8"))
    keys = list(doc)
    assert keys.index("first_place_coverage") == keys.index("anti_correlation") - 1
    assert doc.pop("first_place_coverage")["status"] == "NO_CONTEST_IDS"
    assert (code, _sha(json.dumps(doc, sort_keys=True))) == CLASSIC_PINS["json"]


def test_the_showdown_stdout_is_exactly_one_json_object(tmp_path):
    _code, report, text = sd_qa(tmp_path)
    assert isinstance(json.loads(text), dict)
    assert list(report)[-2:] == ["first_place_coverage", "VERDICT"]


@pytest.mark.parametrize("extra", [(), ("--max-overlap", "1")], ids=["plain", "limit"])
def test_the_showdown_exit_code_does_not_move_with_the_reading(tmp_path, extra, monkeypatch):
    code, report, _text = sd_qa(tmp_path, *extra)
    monkeypatch.setattr(fpc, "reading", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    (tmp_path / "again").mkdir()
    again, broken, _text = sd_qa(tmp_path / "again", *extra)
    assert broken["first_place_coverage"]["status"] == "NOT_COMPUTED"
    assert broken["first_place_coverage"]["detail"] == "RuntimeError"
    assert again == code and broken["VERDICT"] == report["VERDICT"]


def test_the_classic_exit_code_does_not_move_with_the_reading(tmp_path, monkeypatch):
    code, _record, _text = cl_qa(tmp_path)
    monkeypatch.setattr(fpc, "reading", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    (tmp_path / "again").mkdir()
    again, record, text = cl_qa(tmp_path / "again")
    assert record["first_place_coverage"]["status"] == "NOT_COMPUTED"
    assert "NOT_COMPUTED: RuntimeError" in text
    assert again == code


# ------------------------------------------------------------------- the entries file, read and named


def test_a_locked_cell_is_read(tmp_path):
    lines = [cl_line(n, c, [f"P ({i}) (LOCKED)" for i in l] if n == 0 else l) for n, (c, l) in enumerate(CL_PLAN)]
    path = tmp_path / "locked.csv"
    path.write_bytes((CL_HEADER + "".join(lines)).replace("\n", "\r\n").encode("utf-8"))
    rows, state = fpc.read_entries_file(path, mode=ca.MODE_CLASSIC)
    assert state == fpc.READ
    assert [roster for _e, _c, roster in rows] == [tuple(l) for _c, l in CL_PLAN]


def test_a_file_with_no_contest_id_column_is_named_never_failed(tmp_path):
    _salary, _template, export, _portfolio = cl_files(tmp_path)
    renamed = tmp_path / "renamed.csv"
    renamed.write_bytes(export.read_bytes().replace(b"Contest ID", b"Contest", 1))
    rows, state = fpc.read_entries_file(renamed, mode=ca.MODE_CLASSIC)
    assert (rows, state) == ([], fpc.NO_CONTEST_ID_COLUMN)
    (tmp_path / "plain").mkdir()
    plain, _record, _text = cl_qa(tmp_path / "plain", export_file=False)
    code, record, text = cl_qa(tmp_path, "--entries", str(renamed), export_file=False)
    assert record["first_place_coverage"]["status"] == "NO_CONTEST_ID_COLUMN"
    assert "NO_CONTEST_ID_COLUMN" in text and code == plain == 0


def test_a_classic_run_with_no_entries_file_is_named_never_failed(tmp_path):
    code, record, text = cl_qa(tmp_path, export_file=False)
    assert code == 0 and "VERDICT: PASS" in text
    assert record["first_place_coverage"]["status"] == "NO_CONTEST_IDS"
    assert "NO_CONTEST_IDS: no DraftKings entries file was given (--export or --entries)" in text


def test_the_classic_entries_flag_reads_the_template_with_the_portfolios_rosters(tmp_path):
    _salary, template, _export, _portfolio = cl_files(tmp_path)
    code, record, _text = cl_qa(tmp_path, "--entries", str(template), export_file=False)
    reading = record["first_place_coverage"]
    assert code == 0 and reading["source"] == "ENTRIES"
    assert {c: row["entries"] for c, row in by_contest(reading).items()} == {"100": 1, "300": 3}
    assert by_contest(reading)["300"]["repeated_key_people"] == [{"person": CL_QB, "entries": 3}]


def test_an_unknown_id_and_a_blank_row_are_counted_never_scored(tmp_path):
    players = fpc.players_from_salary_csv(cl_salary(tmp_path))
    rows = [(cl_entry_id(n), c, tuple(l)) for n, (c, l) in enumerate(CL_PLAN)]
    rows[1] = (rows[1][0], "300", ("999999",) + rows[1][2][1:])
    rows.append((cl_entry_id(9), "300", None))
    rows.append((cl_entry_id(0), "300", rows[0][2]))
    reading = fpc.reading(rows, mode=ca.MODE_CLASSIC, players=players)
    three = by_contest(reading)["300"]
    assert three["rows_unscored"] == [cl_entry_id(1)] and three["rows_without_roster"] == [cl_entry_id(9)]
    assert three["entries"] == 3 and three["entry_ids"] == [cl_entry_id(0), cl_entry_id(2), cl_entry_id(0)]
    assert reading["duplicate_entry_ids"] == [cl_entry_id(0)]


def test_an_illegal_complete_roster_is_scored_as_the_contract_says(tmp_path):
    """The reading runs no validator: a row naming its QB twice is scored (QA Tier 1 names it), where the run's prefilled
    reader would leave it unscored, so equality is claimed only for legal, unlocked prefilled rows."""

    repeated = ("1", "3", "6", "4", "7", "9", "5", "1", "8")
    rows = [(cl_entry_id(0), "C", tuple(cl_base.LEGAL)), (cl_entry_id(1), "C", repeated)]
    reading = fpc.reading(rows, mode=ca.MODE_CLASSIC, players=fpc.players_from_salary_csv(cl_salary(tmp_path)))
    row = by_contest(reading)["C"]
    assert row["entries"] == 2 and row["rows_unscored"] == [] and "statistics" in row


# ---------------------------------------------------------------- acceptance 6: the committed files


def test_min_no_v10_prints_every_contest_id_with_the_output_otherwise_pinned():
    code, text = _stdout(lambda: sd_base.qa.main([
        "--salaries", str(MINNO / "input" / "DKSalaries_169.csv"),
        "--template", str(MINNO / "input" / "DKEntries_141.csv"),
        "--export", str(MINNO / "construction" / "DK_REVIEW_ENTRY_min-no-sd_final_v10.csv")]))
    assert (code, _sha(strip_showdown(text))) == REAL_PINS["min_no_v10"]
    reading = json.loads(text)["first_place_coverage"]
    contests = by_contest(reading)
    assert sorted(row["entries"] for row in contests.values()) == [1, 1, 2, 2, 7, 20]
    assert {c for c, row in contests.items() if row["entries"] == 1} == {"196458830", "196458834"}
    assert all(row["no_tail_statistic"] == fpc.NO_TAIL_LINE for row in contests.values() if row["entries"] == 1)
    assert all(row["facts_state"] == "NO_CONTEST_FACTS" for row in contests.values())
    assert reading["thesis_labels"] == "NONE" and reading["status"] == fpc.READ


def test_week5_v10_prints_all_ten_contest_ids_inside_its_fail_verdict(tmp_path):
    export = WK5 / "DK_LATESWAP_wk5_classic_v10.csv"
    record = tmp_path / "qa.json"
    argv = ["--portfolio", str(WK5 / "construction" / "portfolio_v10_lateswap.json"),
            "--salaries", str(WK5 / "input" / "DKSalaries.csv"), "--template", str(WK5 / "input" / "DKEntries.csv"),
            "--export", str(export)]
    code, text = _stdout(lambda: cl_base.qa.main([*argv, "--json", str(record)]))
    assert (code, "VERDICT: FAIL" in text) == (1, True)
    plain_code, plain_text = _stdout(lambda: cl_base.qa.main(argv))
    assert (plain_code, _sha(strip_classic(plain_text).replace(str(export), "<EXPORT>"))) == REAL_PINS["wk5_v10"]
    contest_column = [row[2].strip() for row in csv.reader(export.read_text(encoding="utf-8-sig").splitlines()[1:])
                      if row and row[0].strip().isdigit()]
    reading = json.loads(record.read_text(encoding="utf-8"))["first_place_coverage"]
    assert [row["contest_id"] for row in reading["contests"]] == sorted(set(contest_column))
    assert len(reading["contests"]) == 10 and sum(row["entries"] for row in reading["contests"]) == 33
    section = text[text.index(CL_TITLE):]
    assert all(f"contest {contest}:" in section for contest in set(contest_column))


# ------------------------------------------------------------------------ vocabulary and determinism


BANNED_WORDS = {"ev", "roi", "edge", "equity", "probability", "likely"}


def _words(value) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_words(key) | _words(item) for key, item in value.items())) if value else set()
    if isinstance(value, list):
        return set().union(*(_words(item) for item in value)) if value else set()
    if isinstance(value, str):
        return {word.lower() for word in re.findall(r"[A-Za-z]+", value.replace("_", " "))}
    return set()


def test_no_key_label_or_printed_line_says_equity_ev_probability_or_edge(tmp_path):
    (tmp_path / "sd").mkdir()
    _salary, _template, export = sd_files(tmp_path / "sd")
    facts = facts_json(tmp_path / "sd", FACTS_HEADER + "700,1000,49,5\n", export, ca.MODE_SHOWDOWN)
    _code, report, _text = sd_qa(tmp_path / "sd", "--contest-facts", str(facts))
    (tmp_path / "cl").mkdir()
    _code, record, text = cl_qa(tmp_path / "cl")
    constants = {node.value for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8")))
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    found = (_words(report["first_place_coverage"]) | _words(record["first_place_coverage"])
             | _words(text[text.index(CL_TITLE):]) | _words(sorted(constants)))
    assert not found & BANNED_WORDS, found & BANNED_WORDS


def test_the_same_bytes_give_the_same_reading(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = cl_qa(tmp_path / "a")
    second = cl_qa(tmp_path / "b")
    assert first[1] == second[1]
    assert first[2].replace(str(tmp_path / "a"), "") == second[2].replace(str(tmp_path / "b"), "")
    assert sd_qa(tmp_path / "a")[1] == sd_qa(tmp_path / "b")[1]
