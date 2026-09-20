"""Acceptance for `scripts/qa_classic_portfolio.py`.

The gate existed on 2026-09-20 and was simply never run: its Tier 2 already
measured bring-back rate, and the portfolio shipped at 12/18 against a suggested
floor of 70%. It also could not have caught the four lineups starting a backup
quarterback, because that check was dead code. These tests pin the checks that
were added, and the exit codes a caller depends on.

Nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "qa_classic_portfolio.py"


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
]


def salary_csv(tmp_path: Path) -> Path:
    body = "".join(
        f"{pos},{name} ({i}),{name},{i},{pos}/FLEX,{s},"
        f"{g} 09/20/2026 01:00PM ET,{t},0,\n"
        for i, name, pos, t, g, s in PEOPLE
    )
    p = tmp_path / "sal.csv"
    p.write_text(SALARY_HEADER + body, encoding="utf-8")
    return p


# A legal lineup: QB AAA, RB AAA, RB BBB, WR AAA, WR BBB, WR CCC, TE AAA,
# FLEX RB CCC, DST DDD.  DST DDD faces CCC, and CCC WR/RB are rostered, so this
# base intentionally has a DST-vs-own-skill clash unless DST is swapped.
LEGAL = ["1", "3", "6", "4", "7", "9", "5", "10", "8"]


def portfolio_json(tmp_path: Path, rosters, key="lineups") -> Path:
    p = tmp_path / "portfolio.json"
    if key == "lineups":
        doc = {"lineups": [{"index": n + 1, "roster": r} for n, r in enumerate(rosters)],
               "assignments_by_entry_id": {}}
    else:
        doc = {"lineups": [], "assignments_by_entry_id":
               {f"52632{n:05d}": r for n, r in enumerate(rosters)}}
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


def test_backup_pairs_catches_a_lineup_starting_the_backup(tmp_path):
    """The real 2026-09-20 defect: four lineups started somebody's backup and
    the old check could not see it, because legal Classic has exactly one QB."""

    backup_start = ["2", "3", "6", "4", "7", "9", "5", "10", "8"]
    assert run(tmp_path, [backup_start], ["--backup-pairs", "AAA QB>AAA QB2"]) == 1


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


def test_duplicate_lineups_are_detected(tmp_path):
    assert run(tmp_path, [LEGAL, list(LEGAL)], ["--max-overlap", "9"]) == 2


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


def _entries(tmp_path: Path, ids, filled=None) -> tuple[Path, Path]:
    tpl = tmp_path / "tpl.csv"
    tpl.write_text(ENTRY_HEADER + "".join(f"{i},C,1,$1,,,,,,,,,,,\n" for i in ids),
                   encoding="utf-8")
    exp = tmp_path / "exp.csv"
    rows = []
    for n, i in enumerate(ids):
        cells = ",".join(filled[n]) if filled else ",,,,,,,,"
        rows.append(f"{i},C,1,$1,{cells},,\n")
    exp.write_text(ENTRY_HEADER + "".join(rows), encoding="utf-8")
    return tpl, exp


def test_byte_fidelity_passes_on_an_untouched_template(tmp_path):
    tpl, exp = _entries(tmp_path, ["100"], [LEGAL])
    assert run(tmp_path, [LEGAL], ["--template", str(tpl), "--export", str(exp)]) == 0


def test_byte_fidelity_catches_a_mutated_identity_cell(tmp_path):
    tpl, exp = _entries(tmp_path, ["100"], [LEGAL])
    text = exp.read_text(encoding="utf-8").replace(",C,1,$1,", ",TAMPERED,1,$1,")
    exp.write_text(text, encoding="utf-8")
    assert run(tmp_path, [LEGAL], ["--template", str(tpl), "--export", str(exp)]) == 2


def test_entry_id_coverage_mismatch_is_a_defect(tmp_path):
    tpl, exp = _entries(tmp_path, ["100"], [LEGAL])
    tpl.write_text(ENTRY_HEADER + "999,C,1,$1,,,,,,,,,,,\n", encoding="utf-8")
    assert run(tmp_path, [LEGAL], ["--template", str(tpl), "--export", str(exp)]) == 2


def test_template_without_export_is_refused_rather_than_skipped_quietly(tmp_path):
    tpl, _ = _entries(tmp_path, ["100"], [LEGAL])
    assert run(tmp_path, [LEGAL], ["--template", str(tpl)]) == 2
