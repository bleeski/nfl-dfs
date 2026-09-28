"""Acceptance for `scripts/filter_pool_scores.py`.

Promoted from a 2026-09-27 slate-day inline step: the fallback Classic build
keeps anyone scored above zero, and the engine's own dump used to carry
role-gated people scored above zero on purpose (their score stays as scored;
only their selectability changes). This removes them before the build sees
the file, from whichever source names them: the dump's own `excluded_dk_ids`
(since 2026-09-27) or, for an older dump, the run's selection report.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "filter_pool_scores.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


filt = _load("filter_pool_scores", SCRIPT)

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)

# Four people: one clean, one role-gated (scored above zero on purpose), one
# kicker-zero-share (also scored above zero here, to keep the fixture simple),
# and one whose score already floored to zero.
PEOPLE = [
    ("AAA", "QB", "Clean Guy", "1001", 12.0),
    ("AAA", "RB", "Gated Guy", "1002", 9.5),
    ("BBB", "K", "Backup Kicker", "1003", 3.0),
    ("BBB", "WR", "Zero Guy", "1004", 0.0),
]


def _salaries(tmp_path: Path) -> Path:
    rows = "".join(
        f"{pos},{name} ({dk_id}),{name},{dk_id},{pos},4000,AAA@BBB 09/20/2026 01:00PM ET,{team},0,\n"
        for team, pos, name, dk_id, _score in PEOPLE
    )
    path = tmp_path / "sal.csv"
    path.write_text(SALARY_HEADER + rows, encoding="utf-8")
    return path


def _scores(tmp_path: Path, *, excluded_dk_ids=None, name="scores.json") -> Path:
    doc = {
        "schema_version": "nfl_prior_pool_scores_v1",
        "score_version": "v1",
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "by_dk_id": {dk_id: score for _t, _p, _n, dk_id, score in PEOPLE},
        "by_person": {f"{t}|{p}|{n}": score for t, p, n, _d, score in PEOPLE},
        "threshold_sensitive": [],
        "omissions": [],
    }
    if excluded_dk_ids is not None:
        doc["excluded_dk_ids"] = sorted(excluded_dk_ids)
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _report(tmp_path: Path, *, excluded_rows: int, nesting: str = "flat") -> Path:
    """`nesting`: flat (unwrapped report), selection (`.selection`), or
    cowork (`.prior_review_reports.selection.selection`), matching the three
    shapes the running order can hand this script."""

    raw = {
        "excluded_rows": excluded_rows,
        "offensive_roles": {
            "excluded_by_finding": {"OFFENSIVE_MISSING_HISTORY": ["BBB|K|Backup Kicker"]},
            "material_role_change_exclusions": [
                "OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE:AAA|RB|Gated Guy:salary=4000:"
                "prior_points=1.0:places=14:old_teams=SEA:the market prices him above his prior."
            ],
        },
    }
    if nesting == "flat":
        doc = raw
    elif nesting == "selection":
        doc = {"status": "DO_NOT_UPLOAD", "selection": raw}
    else:
        doc = {"prior_review_reports": {"selection": {"selection": raw, "status": "DO_NOT_UPLOAD"}}}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_uses_the_dumps_own_excluded_dk_ids_when_present(tmp_path):
    """The 2026-09-27 fix: the dump names its own exclusions; no report needed."""

    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path, excluded_dk_ids=["1002", "1003"])
    out = tmp_path / "filtered.json"
    code = filt.main(["--scores", str(scores), "--salaries", str(salaries), "--out", str(out)])
    assert code == filt.EXIT_OK
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["by_dk_id"]) == {"1001", "1004"}
    assert set(doc["by_person"]) == {"AAA|QB|Clean Guy", "BBB|WR|Zero Guy"}
    assert doc["filter_report"]["removed_dk_ids"] == ["1002", "1003"]
    assert doc["filter_report"]["source"] == "the dump's own excluded_dk_ids"


def test_falls_back_to_the_selection_report_for_an_older_dump(tmp_path):
    """No `excluded_dk_ids` on the dump: derive it from the report instead,
    exactly as the 2026-09-27 slate session did by hand."""

    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path)  # no excluded_dk_ids: an older dump
    report = _report(tmp_path, excluded_rows=2)  # Gated Guy + Backup Kicker
    out = tmp_path / "filtered.json"
    code = filt.main([
        "--scores", str(scores), "--salaries", str(salaries),
        "--report", str(report), "--out", str(out),
    ])
    assert code == filt.EXIT_OK
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["by_dk_id"]) == {"1001", "1004"}
    assert doc["filter_report"]["removed_persons"] == ["AAA|RB|Gated Guy", "BBB|K|Backup Kicker"]


@pytest.mark.parametrize("nesting", ["flat", "selection", "cowork"])
def test_the_report_is_found_at_any_of_the_three_running_order_shapes(tmp_path, nesting):
    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path)
    report = _report(tmp_path, excluded_rows=2, nesting=nesting)
    out = tmp_path / "filtered.json"
    code = filt.main([
        "--scores", str(scores), "--salaries", str(salaries),
        "--report", str(report), "--out", str(out),
    ])
    assert code == filt.EXIT_OK


def test_refuses_when_the_removed_count_does_not_equal_excluded_rows(tmp_path):
    """Never silently remove an incomplete or overlapping set."""

    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path)
    report = _report(tmp_path, excluded_rows=5)  # the fixture only names 2
    out = tmp_path / "filtered.json"
    code = filt.main([
        "--scores", str(scores), "--salaries", str(salaries),
        "--report", str(report), "--out", str(out),
    ])
    assert code == filt.EXIT_REFUSED
    assert not out.exists()


def test_refuses_a_dump_excluded_dk_ids_count_mismatch_against_the_report(tmp_path):
    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path, excluded_dk_ids=["1002"])
    report = _report(tmp_path, excluded_rows=2)
    out = tmp_path / "filtered.json"
    code = filt.main([
        "--scores", str(scores), "--salaries", str(salaries),
        "--report", str(report), "--out", str(out),
    ])
    assert code == filt.EXIT_REFUSED
    assert not out.exists()


def test_refuses_an_older_dump_with_no_report(tmp_path):
    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path)
    out = tmp_path / "filtered.json"
    code = filt.main(["--scores", str(scores), "--salaries", str(salaries), "--out", str(out)])
    assert code == filt.EXIT_REFUSED
    assert not out.exists()


def test_refuses_an_excluded_person_not_on_the_salary_file(tmp_path):
    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "excluded_rows": 1,
        "offensive_roles": {"excluded_by_finding": {"OFFENSIVE_MISSING_HISTORY": ["ZZZ|QB|Nobody"]}},
    }), encoding="utf-8")
    out = tmp_path / "filtered.json"
    code = filt.main([
        "--scores", str(scores), "--salaries", str(salaries),
        "--report", str(report_path), "--out", str(out),
    ])
    assert code == filt.EXIT_REFUSED
    assert not out.exists()


def test_refuses_to_overwrite_an_existing_out_path(tmp_path):
    salaries = _salaries(tmp_path)
    scores = _scores(tmp_path, excluded_dk_ids=["1002"])
    out = tmp_path / "filtered.json"
    out.write_text("stale", encoding="utf-8")
    code = filt.main(["--scores", str(scores), "--salaries", str(salaries), "--out", str(out)])
    assert code == filt.EXIT_REFUSED
    assert out.read_text(encoding="utf-8") == "stale"


def test_refuses_a_schema_mismatch(tmp_path):
    salaries = _salaries(tmp_path)
    bad = tmp_path / "scores.json"
    bad.write_text(json.dumps({"schema_version": "not_it", "by_dk_id": {}}), encoding="utf-8")
    out = tmp_path / "filtered.json"
    code = filt.main(["--scores", str(bad), "--salaries", str(salaries), "--out", str(out)])
    assert code == filt.EXIT_REFUSED
    assert not out.exists()
