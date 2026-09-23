"""Acceptance for `scripts/qa_classic_portfolio.py`.

The gate existed on 2026-09-20 and was simply never run: its Tier 2 already
measured bring-back rate, and the portfolio shipped at 12/18 against a suggested
floor of 70%. It also could not have caught the four lineups starting a backup
quarterback, because that check was dead code. These tests pin the checks that
were added, and the exit codes a caller depends on.

Session 02 (2026-09-23) made the final CSV the object of the check. The audit
(issue #40, D6) found that QA validated the JSON rosters and never compared an
exported roster to its assignment, skipped its count check when nothing was
filled, called a cell-value comparison "byte fidelity", and returned the same
exit code for a mutated file as for an exceeded exposure cap. Exit codes now:
1 validity, 3 partial coverage with the unfilled Entry IDs named, 2 an
operator-requested limit, 0 pass. Tier 2 never changes the code.

Nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "qa_classic_portfolio.py"
WRITER = REPO_ROOT / "scripts" / "write_dk_entries.py"


def _load():
    spec = importlib.util.spec_from_file_location("qa_classic_portfolio", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa_classic_portfolio"] = module
    spec.loader.exec_module(module)
    return module


qa = _load()

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"

# Two games, four teams. Salaries chosen so a nine-man lineup lands near 45000.
PEOPLE = [
    # (dk_id, name, pos, team, game, salary)
    ("1", "AAA QB", "QB", "AAA", "AAA@BBB", 6000),
    ("2", "AAA QB2", "QB", "AAA", "AAA@BBB", 4000),
    ("3", "AAA RB", "RB", "AAA", "AAA@BBB", 5000),
    ("4", "AAA WR", "WR", "AAA", "AAA@BBB", 5000),
    ("5", "AAA TE", "TE", "AAA", "AAA@BBB", 4000),
    ("6", "BBB RB", "RB", "BBB", "AAA@BBB", 5000),
    ("7", "BBB WR", "WR", "BBB", "AAA@BBB", 5000),
    ("8", "BBB DST", "DST", "BBB", "AAA@BBB", 3000),
    ("9", "CCC WR", "WR", "CCC", "CCC@DDD", 5000),
    ("10", "CCC RB", "RB", "CCC", "CCC@DDD", 5000),
    ("11", "DDD DST", "DST", "DDD", "CCC@DDD", 3000),
    ("12", "CCC TE", "TE", "CCC", "CCC@DDD", 4000),
    ("13", "DDD WR", "WR", "DDD", "CCC@DDD", 5000),
    ("14", "CCC PRICEY WR", "WR", "CCC", "CCC@DDD", 20000),
]
# Cheap pass catchers, so a 20-entry file can carry 20 distinct lineups.
FLEX_POOL = [(str(20 + k), f"DDD WR{k}", "WR", "DDD", "CCC@DDD", 3000) for k in range(20)]


def roster_position(pos: str) -> str:
    return pos if pos in {"QB", "DST"} else f"{pos}/FLEX"


def salary_csv(tmp_path: Path) -> Path:
    body = "".join(
        f"{pos},{name} ({i}),{name},{i},{roster_position(pos)},{s},"
        f"{g} 09/20/2026 01:00PM ET,{t},0,\n"
        for i, name, pos, t, g, s in PEOPLE + FLEX_POOL
    )
    p = tmp_path / "sal.csv"
    p.write_text(SALARY_HEADER + body, encoding="utf-8")
    return p


# A legal lineup in DraftKings slot order: QB AAA, RB AAA, RB BBB, WR AAA,
# WR BBB, WR CCC, TE AAA, FLEX RB CCC, DST BBB.
LEGAL = ["1", "3", "6", "4", "7", "9", "5", "10", "8"]


def legal_for(k: int) -> list[str]:
    """LEGAL with the FLEX swapped for the k-th cheap WR: distinct for every k."""

    return ["1", "3", "6", "4", "7", "9", "5", FLEX_POOL[k][0], "8"]


def entry_id(n: int) -> str:
    return f"52632{n:05d}"


def portfolio_json(tmp_path: Path, rosters, key="lineups") -> Path:
    p = tmp_path / "portfolio.json"
    if key == "lineups":
        doc = {"lineups": [{"index": n + 1, "roster": r} for n, r in enumerate(rosters)],
               "assignments_by_entry_id": {}}
    elif key == "assignments":
        doc = {"lineups": [], "assignments_by_entry_id":
               {entry_id(n): r for n, r in enumerate(rosters)}}
    else:                                          # an explicit {entry_id: roster} map
        doc = {"lineups": [], "assignments_by_entry_id": key}
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def run(tmp_path, rosters, extra=(), key="lineups"):
    return qa.main([
        "--portfolio", str(portfolio_json(tmp_path, rosters, key)),
        "--salaries", str(salary_csv(tmp_path)),
        *extra,
    ])


def test_a_legal_portfolio_passes_with_exit_zero(tmp_path):
    assert run(tmp_path, [LEGAL]) == 0


def test_assignments_by_entry_id_is_read_when_populated(tmp_path):
    """The builder now emits this; the gate must read it, not just 'lineups'."""

    assert run(tmp_path, [LEGAL], key="assignments") == 0


# Session 02 changed this from exit 1 to exit 2. A backup pair is the operator's
# assertion about who starts, with no evidence bound to it (audit #40 §4, "S/P"),
# not a DraftKings roster rule; it stays blocking, as an enforcement defect.
def test_backup_pairs_catches_a_lineup_starting_the_backup(tmp_path):
    """The real 2026-09-20 defect: four lineups started somebody's backup and
    the old check could not see it, because legal Classic has exactly one QB."""

    backup_start = ["2", "3", "6", "4", "7", "9", "5", "10", "8"]
    assert run(tmp_path, [backup_start], ["--backup-pairs", "AAA QB>AAA QB2"]) == 2


def test_backup_pairs_is_silent_when_the_starter_is_rostered(tmp_path):
    assert run(tmp_path, [LEGAL], ["--backup-pairs", "AAA QB>AAA QB2"]) == 0


def test_min_salary_floor_is_an_enforcement_defect_exit_two(tmp_path):
    assert run(tmp_path, [LEGAL], ["--min-salary", "49000"]) == 2


def test_salary_over_the_cap_is_a_legality_failure_exit_one(tmp_path):
    assert run(tmp_path, [LEGAL], ["--cap", "10000"]) == 1


# Differs from LEGAL only in the DST, so the pair overlaps on 8 of 9.
NEAR_DUPLICATE = ["1", "3", "6", "4", "7", "9", "5", "10", "11"]


def test_overlap_is_enforced_when_given(tmp_path):
    """Reported but never enforced until 2026-09-20; its Showdown twin has
    enforced it as a defect with exit 2 since 2026-09-14."""

    assert run(tmp_path, [LEGAL, NEAR_DUPLICATE], ["--max-overlap", "4"]) == 2


def test_overlap_is_only_reported_when_no_limit_is_given(tmp_path):
    """Backwards compatible: without --max-overlap the pair is legal."""

    assert run(tmp_path, [LEGAL, NEAR_DUPLICATE]) == 0


def test_exposure_is_enforced_when_given(tmp_path):
    assert run(tmp_path, [LEGAL, NEAR_DUPLICATE], ["--max-exposure", "1"]) == 2


# Session 02 changed this from exit 2 to exit 1. R29 makes a repeated lineup a
# validity failure, not a construction preference.
def test_duplicate_lineups_are_detected(tmp_path):
    assert run(tmp_path, [LEGAL, list(LEGAL)], ["--max-overlap", "9"]) == 1


def test_dst_against_its_own_skill_players_is_reported(tmp_path, capsys):
    clash = ["1", "3", "6", "4", "7", "9", "5", "10", "11"]  # DST DDD vs CCC skill
    run(tmp_path, [clash])
    out = capsys.readouterr().out
    assert "dst_vs_own_skill    : 1" in out


def test_the_always_zero_duplicate_metric_is_gone(tmp_path, capsys):
    """`qb_vs_opposing_dst` was declared, never appended to, and is the same
    relation as dst_vs_own_qb in a nine-man lineup. It was removed, not faked."""

    run(tmp_path, [LEGAL])
    out = capsys.readouterr().out
    assert "qb_vs_opposing_dst" not in out
    assert "dst_vs_own_qb" in out


def test_bringback_rate_is_reported_with_its_floor(tmp_path, capsys):
    run(tmp_path, [LEGAL])
    out = capsys.readouterr().out
    assert "bring-back" in out
    assert "suggested floor 70%" in out


def test_missing_ownership_is_stated_not_silently_skipped(tmp_path, capsys):
    run(tmp_path, [LEGAL])
    out = capsys.readouterr().out
    assert "NO leverage model" in out


def test_inactive_rostered_is_a_legality_failure(tmp_path):
    status = tmp_path / "status.csv"
    status.write_text(
        "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\nAAA,1,INACTIVE,,\n",
        encoding="utf-8",
    )
    assert run(tmp_path, [LEGAL], ["--status", str(status)]) == 1


def test_an_empty_portfolio_fails_by_name(tmp_path, capsys):
    """A builder shortfall can write zero lineups; Tier 2 used to crash on it."""

    assert run(tmp_path, []) == 1
    assert "NO_LINEUPS" in capsys.readouterr().out


def test_a_json_only_run_says_the_export_was_not_checked(tmp_path, capsys):
    assert run(tmp_path, [LEGAL]) == 0
    assert "export not checked" in capsys.readouterr().out


# ---------------------------------------------------------------- the export

def template_line(eid: str) -> str:
    return f"{eid},C,1,$1,,,,,,,,,,,\n"


def export_line(eid: str, cells) -> str:
    return f"{eid},C,1,$1,{','.join(cells)},,\n" if cells else template_line(eid)


def files(tmp_path: Path, ids, filled) -> tuple[Path, Path]:
    """A template with `ids` blank, and an export filling `filled[eid]` in slot order."""

    tpl = tmp_path / "tpl.csv"
    tpl.write_bytes((ENTRY_HEADER + "".join(template_line(i) for i in ids)).encode())
    exp = tmp_path / "exp.csv"
    exp.write_bytes((ENTRY_HEADER + "".join(export_line(i, filled.get(i)) for i in ids)).encode())
    return tpl, exp


def check(tmp_path, assignments, tpl, exp, extra=()):
    return qa.main([
        "--portfolio", str(portfolio_json(tmp_path, [], key=assignments)),
        "--salaries", str(salary_csv(tmp_path)),
        "--template", str(tpl), "--export", str(exp), *extra,
    ])


def test_export_audit_passes_on_a_correct_fill(tmp_path):
    """Replaces `test_byte_fidelity_passes_on_an_untouched_template`, which ran
    with a `lineups`-only portfolio. An export is now compared to its Entry ID
    map, so a portfolio without one cannot pass an export check."""

    ids = [entry_id(0), entry_id(1)]
    assigned = {ids[0]: LEGAL, ids[1]: legal_for(0)}
    tpl, exp = files(tmp_path, ids, assigned)
    assert check(tmp_path, assigned, tpl, exp) == 0


# Session 02 changed these two from exit 2 to exit 1: a mutated file is invalid.
def test_byte_fidelity_catches_a_mutated_identity_cell(tmp_path):
    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {ids[0]: LEGAL})
    exp.write_bytes(exp.read_bytes().replace(b",C,1,$1,", b",TAMPERED,1,$1,"))
    assert check(tmp_path, {ids[0]: LEGAL}, tpl, exp) == 1


def test_entry_id_coverage_mismatch_is_a_failure(tmp_path):
    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {ids[0]: LEGAL})
    tpl.write_bytes((ENTRY_HEADER + template_line("999")).encode())
    assert check(tmp_path, {ids[0]: LEGAL}, tpl, exp) == 1


# Session 02 changed this from exit 2 to exit 1: a claimed check that did not run
# is a failure, not an enforcement defect.
def test_template_without_export_is_refused_rather_than_skipped_quietly(tmp_path):
    tpl, _ = files(tmp_path, [entry_id(0)], {})
    assert run(tmp_path, [LEGAL], ["--template", str(tpl)]) == 1


# The card's adversarial fixtures (docs/ROADMAP.md, Session 02). QA must fail
# every one: 1 where the file is wrong, 3 where it is valid but rows are unfilled.
def _extra_id(tmp_path):
    ids = [entry_id(0)]
    assigned = {ids[0]: LEGAL, "9999999999": legal_for(0)}
    return (assigned, *files(tmp_path, ids, {ids[0]: LEGAL}), 1, "ASSIGNMENT_ENTRY_ID_NOT_IN_TEMPLATE")


def _missing_id(tmp_path):
    ids = [entry_id(0), entry_id(1)]
    assigned = {ids[0]: LEGAL}
    return (assigned, *files(tmp_path, ids, assigned), 3, ids[1])


def _qb_in_flex(tmp_path):
    ids = [entry_id(0)]
    roster = ["1", "3", "6", "4", "7", "9", "5", "2", "8"]      # AAA QB2 in FLEX
    return ({ids[0]: roster}, *files(tmp_path, ids, {ids[0]: roster}), 1, "SLOT_INELIGIBLE")


def _over_the_cap(tmp_path):
    ids = [entry_id(0)]
    roster = ["1", "3", "6", "4", "7", "9", "5", "14", "8"]     # 58000
    return ({ids[0]: roster}, *files(tmp_path, ids, {ids[0]: roster}), 1, "over 50000")


def _duplicate_person(tmp_path):
    ids = [entry_id(0)]
    roster = ["1", "3", "6", "4", "7", "9", "5", "3", "8"]
    return ({ids[0]: roster}, *files(tmp_path, ids, {ids[0]: roster}), 1, "duplicate player")


def _output_equal_to_template(tmp_path):
    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {})
    return ({ids[0]: LEGAL}, tpl, tpl, 1, "EXPORT_IDENTICAL_TO_TEMPLATE")


def _pre_existing_output(tmp_path):
    """An export left from an earlier portfolio, checked against the new one."""

    ids = [entry_id(0), entry_id(1)]
    tpl, exp = files(tmp_path, ids, {ids[0]: legal_for(5), ids[1]: legal_for(6)})
    return ({ids[0]: LEGAL, ids[1]: legal_for(0)}, tpl, exp, 1, "EXPORT_ROSTER_DIFFERS_FROM_ASSIGNMENT")


def _eighteen_of_twenty(tmp_path):
    ids = [entry_id(n) for n in range(20)]
    assigned = {eid: legal_for(n) for n, eid in enumerate(ids[:18])}
    return (assigned, *files(tmp_path, ids, assigned), 3, ids[19])


ADVERSARIAL = {
    "extra_id": _extra_id,
    "missing_id": _missing_id,
    "qb_in_flex": _qb_in_flex,
    "over_the_cap": _over_the_cap,
    "duplicate_person": _duplicate_person,
    "output_equal_to_template": _output_equal_to_template,
    "pre_existing_output": _pre_existing_output,
    "eighteen_of_twenty": _eighteen_of_twenty,
}


@pytest.mark.parametrize("case", sorted(ADVERSARIAL))
def test_qa_fails_every_adversarial_export(tmp_path, capsys, case):
    assigned, tpl, exp, code, named = ADVERSARIAL[case](tmp_path)
    got = check(tmp_path, assigned, tpl, exp)
    out = capsys.readouterr().out
    assert got == code, out
    assert named in out
    assert "VERDICT: PASS" not in out


def test_unfilled_entry_ids_are_listed_exactly(tmp_path, capsys):
    assigned, tpl, exp, _code, _named = _eighteen_of_twenty(tmp_path)
    report = tmp_path / "qa.json"
    assert check(tmp_path, assigned, tpl, exp, ["--json", str(report)]) == 3
    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["verdict"] == "PARTIAL"
    assert doc["unfilled_entry_ids"] == [entry_id(18), entry_id(19)]
    assert doc["export_checked"] is True


def test_an_exported_roster_must_match_its_own_entry_id(tmp_path, capsys):
    """Two legal rosters, swapped between rows: every old check passed this."""

    ids = [entry_id(0), entry_id(1)]
    assigned = {ids[0]: LEGAL, ids[1]: legal_for(0)}
    tpl, exp = files(tmp_path, ids, {ids[0]: legal_for(0), ids[1]: LEGAL})
    assert check(tmp_path, assigned, tpl, exp) == 1
    assert "EXPORT_ROSTER_DIFFERS_FROM_ASSIGNMENT" in capsys.readouterr().out


def test_an_assigned_row_left_blank_fails_even_when_nothing_was_filled(tmp_path, capsys):
    """The old count check ran only `if rosters`, so an all-blank export passed."""

    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {})
    assert check(tmp_path, {ids[0]: LEGAL}, tpl, exp) == 1
    assert "ASSIGNED_ROW_NOT_FILLED" in capsys.readouterr().out


def test_a_slot_the_player_cannot_fill_is_caught_in_the_export(tmp_path, capsys):
    """Right nine people, wrong cells: the JSON roster is legal, the file is not."""

    ids = [entry_id(0)]
    swapped = ["3", "1", "6", "4", "7", "9", "5", "10", "8"]   # RB in QB, QB in RB
    tpl, exp = files(tmp_path, ids, {ids[0]: swapped})
    assert check(tmp_path, {ids[0]: LEGAL}, tpl, exp) == 1
    assert "SLOT_INELIGIBLE" in capsys.readouterr().out


@pytest.mark.parametrize("mutation", [
    (b",C,1,$1,1,", b',C,1,"$1",1,'),   # same cell value once parsed, different bytes
    (b"\n", b"\r\n"),                    # a line-ending rewrite
])
def test_a_byte_change_a_cell_comparison_cannot_see_is_caught(tmp_path, capsys, mutation):
    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {ids[0]: LEGAL})
    exp.write_bytes(exp.read_bytes().replace(*mutation))
    assert check(tmp_path, {ids[0]: LEGAL}, tpl, exp) == 1
    assert "BYTES_CHANGED" in capsys.readouterr().out


def test_an_export_with_a_lineups_only_portfolio_fails(tmp_path, capsys):
    ids = [entry_id(0)]
    tpl, exp = files(tmp_path, ids, {ids[0]: LEGAL})
    assert run(tmp_path, [LEGAL], ["--template", str(tpl), "--export", str(exp)]) == 1
    assert "EXPORT_HAS_NO_ASSIGNMENT_MAP" in capsys.readouterr().out


@pytest.mark.parametrize("assigned_count, expected", [(20, 0), (18, 3)])
def test_the_writer_and_qa_agree(tmp_path, assigned_count, expected):
    """End to end on the fallback's last two stages: write, then check the bytes."""

    ids = [entry_id(n) for n in range(20)]
    tpl = tmp_path / "tpl.csv"
    tpl.write_bytes((ENTRY_HEADER + "".join(template_line(i) for i in ids))
                    .encode().replace(b"\n", b"\r\n"))
    assigned = {eid: legal_for(n) for n, eid in enumerate(ids[:assigned_count])}
    sel = portfolio_json(tmp_path, [], key=assigned)
    sal = salary_csv(tmp_path)
    out = tmp_path / "entries_filled.csv"
    proc = subprocess.run([sys.executable, str(WRITER), str(sel), str(tpl), str(sal), str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == expected, proc.stderr
    assert qa.main(["--portfolio", str(sel), "--salaries", str(sal),
                    "--template", str(tpl), "--export", str(out)]) == expected
