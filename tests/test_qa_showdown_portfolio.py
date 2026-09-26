"""Acceptance for `scripts/qa_showdown_portfolio.py`.

The Showdown twin of Classic QA, written 2026-09-14 and untested until Session
02b (2026-09-23). The audit (issue #40, §4 standalone-QA rows) found it failed
its exit code on four construction choices DraftKings allows: no quarterback,
two kickers, two defences, and a defence with its own offense. Those are now
strategy observations, reported and never counted as defects. What DraftKings
itself would reject, or what breaks the file, still exits 2.

Session 37 (2026-09-26, code review V2 and V11) moved the script onto Classic
QA's exit codes and byte audit. Every expectation below that read exit 2 for a
validity failure now reads exit 1, with verdict `FAIL`; exit 2 is left to the
operator's limits, and exit 3 is a sanctioned unfilled blank row. That is an
edited expectation, named in `changelog.md`, not a loosened one: each case
still fails.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "qa_showdown_portfolio.py"


def _load():
    spec = importlib.util.spec_from_file_location("qa_showdown_portfolio", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa_showdown_portfolio"] = module
    spec.loader.exec_module(module)
    return module


qa = _load()

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions\n"
GAME = "DEN@KC 09/14/2026 08:20PM ET"

# (key, name, position, team, FLEX salary). Each person has a FLEX row and a CPT
# row at 1.5 times the salary, with different DraftKings IDs, as DraftKings
# prices Showdown.
PEOPLE = [
    ("kc_qb", "KC QB", "QB", "KC", 11000), ("kc_rb", "KC RB", "RB", "KC", 5000),
    ("kc_wr1", "KC WR1", "WR", "KC", 10000), ("kc_wr2", "KC WR2", "WR", "KC", 6000),
    ("kc_te", "KC TE", "TE", "KC", 4000), ("kc_k", "KC K", "K", "KC", 3000),
    ("kc_dst", "Chiefs", "DST", "KC", 3000),
    ("den_qb", "DEN QB", "QB", "DEN", 11000), ("den_rb", "DEN RB", "RB", "DEN", 5000),
    ("den_wr1", "DEN WR1", "WR", "DEN", 10000), ("den_wr2", "DEN WR2", "WR", "DEN", 6000),
    ("den_te", "DEN TE", "TE", "DEN", 4000), ("den_k", "DEN K", "K", "DEN", 3000),
    ("den_dst", "Broncos", "DST", "DEN", 3000),
]
FLEX = {key: str(3000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}
CPT = {key: str(4000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}

# Captain first, then five FLEX, by person key.
LEGAL = ["kc_qb", "kc_wr2", "den_rb", "den_wr2", "kc_te", "kc_rb"]
OTHER = ["den_qb", "den_wr2", "kc_rb", "kc_wr2", "den_te", "den_rb"]
ZERO_QB = ["kc_wr1", "kc_wr2", "den_wr2", "kc_te", "den_rb", "kc_rb"]
TWO_KICKERS = ["kc_qb", "kc_k", "den_k", "den_rb", "kc_wr2", "den_te"]
TWO_DST = ["kc_qb", "kc_dst", "den_dst", "den_rb", "kc_wr2", "den_te"]
DST_OWN_OFFENSE = ["kc_qb", "kc_dst", "kc_wr2", "den_rb", "den_wr2", "kc_te"]


def entry_id(n: int) -> str:
    return f"48800{n:05d}"


def ids(lineup: list[str]) -> list[str]:
    return [CPT[lineup[0]], *(FLEX[k] for k in lineup[1:])]


def salary_csv(tmp_path: Path) -> Path:
    rows = []
    for key, name, pos, team, salary in PEOPLE:
        for role, table, price in (("CPT", CPT, salary * 3 // 2), ("FLEX", FLEX, salary)):
            ident = table[key]
            rows.append(f"{pos},{name} ({ident}),{name},{ident},{role},{price},{GAME},{team},0,\n")
    p = tmp_path / "sal.csv"
    p.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    return p


def entry_line(n: int, cells=("",) * 6) -> str:
    return f"{entry_id(n)},Showdown,9001,$5,{','.join(cells)},,\n"


def files(tmp_path: Path, lineups: list[list[str]]):
    """A template with one blank row per lineup, and the export filling each."""

    tpl = tmp_path / "tpl.csv"
    tpl.write_text(ENTRY_HEADER + "".join(entry_line(n) for n in range(len(lineups))),
                   encoding="utf-8")
    exp = tmp_path / "exp.csv"
    exp.write_text(ENTRY_HEADER + "".join(entry_line(n, ids(l)) for n, l in enumerate(lineups)),
                   encoding="utf-8")
    return tpl, exp


def check(tmp_path, capsys, tpl, exp, extra=()):
    code = qa.main(["--salaries", str(salary_csv(tmp_path)), "--template", str(tpl),
                    "--export", str(exp), *extra])
    return code, json.loads(capsys.readouterr().out)


def run(tmp_path, capsys, lineups, extra=()):
    return check(tmp_path, capsys, *files(tmp_path, lineups), extra)


def codes(findings: list[str]) -> set[str]:
    """`52632... ZERO_QB` and `OVERLAP_5_EXCEEDS_4 a/b` both reduce to their code."""

    out = set()
    for f in findings:
        parts = f.split()
        code = parts[1] if parts[0].isdigit() and len(parts) > 1 else parts[0]
        out.add(code.rstrip(":"))
    return out


def test_a_legal_portfolio_passes_with_no_observation(tmp_path, capsys):
    code, rep = run(tmp_path, capsys, [LEGAL, OTHER])
    assert code == 0
    assert (rep["VERDICT"], rep["defects"], rep["observations"]) == ("PASS", 0, 0)
    assert rep["lineups"] == 2


@pytest.mark.parametrize("lineup, expected", [
    (ZERO_QB, {"ZERO_QB"}),
    (TWO_KICKERS, {"MULTIPLE_KICKERS"}),
    # Two defences always share the roster with one of their offenses: every
    # Showdown player is on one of the two teams.
    (TWO_DST, {"MULTIPLE_DST", "DST_WITH_OWN_OFFENSE"}),
    (DST_OWN_OFFENSE, {"DST_WITH_OWN_OFFENSE"}),
])
def test_a_strategy_choice_is_an_observation_not_a_defect(tmp_path, capsys, lineup, expected):
    """DraftKings accepts each of these. The old script exited 2 on all four."""

    code, rep = run(tmp_path, capsys, [lineup, LEGAL], extra=["--max-overlap", "6"])
    assert code == 0
    assert rep["VERDICT"] == "PASS"
    assert rep["DEFECTS"] == []
    assert codes(rep["OBSERVATIONS"]) == expected
    assert all(o.startswith(entry_id(0)) for o in rep["OBSERVATIONS"])


def test_all_four_observations_together_still_pass(tmp_path, capsys):
    code, rep = run(tmp_path, capsys, [ZERO_QB, TWO_KICKERS, TWO_DST, LEGAL],
                    extra=["--max-overlap", "6"])
    assert code == 0
    assert codes(rep["OBSERVATIONS"]) == {"ZERO_QB", "MULTIPLE_KICKERS", "MULTIPLE_DST",
                                          "DST_WITH_OWN_OFFENSE"}
    assert rep["qb_count_histogram"] == {"0": 1, "1": 3}


def test_an_observation_never_masks_a_defect(tmp_path, capsys):
    tpl, exp = files(tmp_path, [ZERO_QB, ZERO_QB])
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert code == 1
    assert rep["VERDICT"] == "FAIL"
    assert codes(rep["DEFECTS"]) == {"DUPLICATE_LINEUPS"}
    assert codes(rep["OBSERVATIONS"]) == {"ZERO_QB"}


def test_a_different_captain_is_a_different_lineup(tmp_path, capsys):
    """R29: identity is the exact roster, so the same six with a new captain differ."""

    swapped = [LEGAL[1], LEGAL[0], *LEGAL[2:]]
    code, rep = run(tmp_path, capsys, [LEGAL, swapped], extra=["--max-overlap", "6"])
    assert code == 0, rep["DEFECTS"]


# ------------------------------------------------------------------ true defects
# Each is something DraftKings would reject, or a file that is not the template
# it claims to fill. Every one exits 1 since Session 37 (exit 2 before).

def _blank_cell(rows):
    rows[1][6] = ""


def _unknown_id(rows):
    rows[1][6] = "999999"


def _flex_row_as_captain(rows):
    rows[1][4] = FLEX[LEGAL[0]]


def _captain_row_in_flex(rows):
    rows[1][6] = CPT[LEGAL[2]]


def _same_person_twice(rows):
    rows[1][5] = FLEX[LEGAL[0]]


def _over_the_cap(rows):
    rows[1][4:10] = ids(["kc_qb", "den_qb", "kc_wr1", "den_wr1", "kc_wr2", "den_wr2"])


def _one_team(rows):
    rows[1][4:10] = ids(["kc_qb", "kc_rb", "kc_wr1", "kc_wr2", "kc_te", "kc_k"])


def _repeated_lineup(rows):
    rows[2][4:10] = rows[1][4:10]


def _contest_cell_changed(rows):
    rows[1][1] = "Another contest"


def _row_dropped(rows):
    del rows[2]


def _rows_swapped(rows):
    rows[1], rows[2] = rows[2], rows[1]


@pytest.mark.parametrize("mutate, expected", [
    (_blank_cell, "PARTIALLY_FILLED_ROW"),
    (_unknown_id, "UNKNOWN_DK_ID"),
    (_flex_row_as_captain, "SLOT1_NOT_CPT_ROW"),
    (_captain_row_in_flex, "FLEX_SLOT_HAS_CPT_ROW"),
    (_same_person_twice, "DUPLICATE_PERSON"),
    (_over_the_cap, "SALARY_CAP_EXCEEDED"),
    (_one_team, "SINGLE_TEAM_LINEUP"),
    (_repeated_lineup, "DUPLICATE_LINEUPS"),
    (_contest_cell_changed, "LINE_2_BYTES_CHANGED_OUTSIDE_ROSTER"),
    (_row_dropped, "LINE_COUNT_CHANGED"),
    (_rows_swapped, "ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH"),
])
def test_a_true_roster_or_file_defect_exits_one(tmp_path, capsys, mutate, expected):
    tpl, exp = files(tmp_path, [LEGAL, OTHER])
    rows = [line.split(",") for line in exp.read_text(encoding="utf-8").splitlines()]
    mutate(rows)
    exp.write_text("".join(",".join(r) + "\n" for r in rows), encoding="utf-8")
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert code == 1
    assert rep["VERDICT"] == "FAIL"
    assert expected in codes(rep["DEFECTS"])


def test_an_officially_inactive_player_exits_one(tmp_path, capsys):
    code, rep = run(tmp_path, capsys, [LEGAL, OTHER],
                    extra=["--inactive-dk-ids", FLEX["kc_wr2"]])
    assert code == 1
    assert "OFFICIALLY_INACTIVE_ROSTERED" in codes(rep["DEFECTS"])


def test_overlap_and_backup_pairs_are_operator_limits_at_exit_two(tmp_path, capsys):
    """Session 37 closed the Session 02b open item: the operator's limits exit 2,
    apart from the validity failures, which exit 1."""

    code, rep = run(tmp_path, capsys, [LEGAL, OTHER], extra=["--max-overlap", "2"])
    assert (code, rep["VERDICT"], rep["DEFECTS"]) == (2, "DEFECT", [])
    assert any(d.startswith("OVERLAP_") for d in rep["LIMIT_BREACHES"])
    code, rep = run(tmp_path, capsys, [LEGAL, OTHER], extra=["--backup-pairs", "KC QB>KC WR2"])
    assert (code, rep["DEFECTS"]) == (2, [])
    assert "STARTER_WITH_OWN_BACKUP" in codes(rep["LIMIT_BREACHES"])


def test_a_backup_pair_may_name_draftkings_ids(tmp_path, capsys):
    """Either role's ID names the person: LEGAL has KC QB at Captain."""

    code, rep = run(tmp_path, capsys, [LEGAL, OTHER],
                    extra=["--backup-pairs", f"{FLEX['kc_qb']}>{FLEX['kc_wr2']}"])
    assert code == 2 and "STARTER_WITH_OWN_BACKUP" in codes(rep["LIMIT_BREACHES"])


def test_a_validity_failure_outranks_an_operator_limit(tmp_path, capsys):
    code, rep = run(tmp_path, capsys, [LEGAL, OTHER],
                    extra=["--max-overlap", "2", "--inactive-dk-ids", FLEX["kc_wr2"]])
    assert (code, rep["VERDICT"]) == (1, "FAIL")
    assert rep["LIMIT_BREACHES"]


# ------------------------------------------------ Session 37: prefilled and blank rows

def mixed(tmp_path, template_rows, export_rows):
    """Template and export from per-row roster lists; None is a blank row."""

    def body(rows):
        return ENTRY_HEADER + "".join(
            entry_line(n, ids(r) if r else ("",) * 6) for n, r in enumerate(rows))

    tpl, exp = tmp_path / "tpl.csv", tmp_path / "exp.csv"
    tpl.write_text(body(template_rows), encoding="utf-8")
    exp.write_text(body(export_rows), encoding="utf-8")
    return tpl, exp


def test_an_export_that_overwrote_a_prefilled_row_fails(tmp_path, capsys):
    """V2: the old loop exempted the roster cells of every row and printed PASS."""

    tpl, exp = mixed(tmp_path, [LEGAL, None], [OTHER, LEGAL])
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert (code, rep["VERDICT"]) == (1, "FAIL")
    assert any(d.startswith("LINE_2_BYTES_CHANGED on prefilled entry") for d in rep["DEFECTS"])


def test_an_untouched_prefilled_row_passes_and_still_counts_for_r29(tmp_path, capsys):
    tpl, exp = mixed(tmp_path, [LEGAL, None], [LEGAL, OTHER])
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert (code, rep["VERDICT"], rep["lineups"]) == (0, "PASS", 1)
    assert rep["prefilled_entry_ids"] == [entry_id(0)]

    tpl, exp = mixed(tmp_path, [LEGAL, None], [LEGAL, LEGAL])
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert code == 1 and "DUPLICATE_LINEUPS" in codes(rep["DEFECTS"])


def test_a_sanctioned_blank_row_left_blank_exits_three_and_is_named(tmp_path, capsys):
    """V11: R29 exhaustion leaves a row blank on purpose; that is PARTIAL, not a defect."""

    tpl, exp = mixed(tmp_path, [None, None, None], [LEGAL, OTHER, None])
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert (code, rep["VERDICT"], rep["DEFECTS"]) == (3, "PARTIAL", [])
    assert rep["unfilled_entry_ids"] == [entry_id(2)]


def test_an_export_identical_to_the_template_fails(tmp_path, capsys):
    tpl, exp = mixed(tmp_path, [None, None], [None, None])
    code, rep = check(tmp_path, capsys, tpl, exp)
    assert code == 1 and "EXPORT_IDENTICAL_TO_TEMPLATE" in codes(rep["DEFECTS"])


def test_a_changed_line_ending_on_a_filled_row_fails(tmp_path, capsys):
    """Bytes, not parsed cells: CRLF for LF on one filled row is a changed line."""

    tpl, exp = files(tmp_path, [LEGAL, OTHER])
    raw = exp.read_bytes().split(b"\n")
    raw[1] += b"\r"
    exp.write_bytes(b"\n".join(raw))
    code, rep = check(tmp_path, capsys, tpl, exp, ["--max-overlap", "6"])
    assert code == 1 and "LINE_2_BYTES_CHANGED_OUTSIDE_ROSTER" in codes(rep["DEFECTS"])


def test_people_are_identified_by_draftkings_id_not_name(tmp_path, capsys):
    """V11: two players who share a name on different teams are two people."""

    tpl, exp = files(tmp_path, [LEGAL, OTHER])
    sal = salary_csv(tmp_path)
    sal.write_text(sal.read_text(encoding="utf-8").replace("DEN RB", "KC RB"), encoding="utf-8")
    code = qa.main(["--salaries", str(sal), "--template", str(tpl), "--export", str(exp),
                    "--max-overlap", "6"])
    rep = json.loads(capsys.readouterr().out)
    assert (code, rep["DEFECTS"]) == (0, [])


def test_the_observation_rule_is_stated_in_the_report(tmp_path, capsys):
    _code, rep = run(tmp_path, capsys, [ZERO_QB, LEGAL], extra=["--max-overlap", "6"])
    assert "never change the exit code" in rep["observation_note"]
