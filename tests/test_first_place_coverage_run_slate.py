"""Session 75: both QA scripts, run on a `run-slate` run's own delivered file, equal that run's `contests_after`.

The card's equality clause on real runs (`tests/test_first_place_coverage.py` holds the synthetic one):

- Showdown on the engine's default policy, which carries no thesis labels;
- Showdown on a v4 portfolio of theses, read with `--policy` and `--claim`, whose labels the contest step scored with;
- Classic C3, against `selection/contest_assignment.json`, the artifact the card names.

Session 75b adds the run's own block and the readable review's section to this file.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from nfl_dfs import first_place_coverage as fpc
from nfl_dfs.dk import parse_entries

from . import test_qa_classic_portfolio as cl_base
from . import test_qa_showdown_portfolio as sd_base
from .test_contest_facts_run_slate import _classic, _showdown
from .test_entry_groups import _policy
from .test_readable_review_theses import _controls, _finished
from .test_showdown_thesis_check import claim_path, policy_path


def _stdout(call) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = call()
    return code, buffer.getvalue()


def _delivered(report) -> Path:
    return Path(report["latest_deliverable"]["path"])


def _statistics(reading) -> dict[str, dict]:
    return {row["contest_id"]: row["statistics"] for row in reading["contests"] if row["entries"] >= 2}


def _showdown_reading(salary: Path, entries: Path, delivered: Path, *extra: str) -> dict:
    _code, text = _stdout(lambda: sd_base.qa.main(
        ["--salaries", str(salary), "--template", str(entries), "--export", str(delivered), *extra]))
    return json.loads(text)["first_place_coverage"]


@pytest.fixture(scope="module")
def sd_default(tmp_path_factory):
    return _showdown(tmp_path_factory.mktemp("fp_sd"), "fp-sd", None)


@pytest.fixture(scope="module")
def sd_theses(tmp_path_factory):
    return _finished(tmp_path_factory, "fp-th", policy_controls=_controls(4))


@pytest.fixture(scope="module")
def c3_run(tmp_path_factory):
    return _classic(tmp_path_factory.mktemp("fp_c3"), "fp-c3", None, policy=_policy)


def test_the_showdown_qa_on_a_runs_file_equals_its_contests_after(sd_default):
    assert sd_default.code == 0, sd_default.report["blockers"]
    report = sd_default.report
    reading = _showdown_reading(sd_default.entries.parent / "salary.csv", sd_default.entries, _delivered(report))
    after = report["prior_review_reports"]["contest_assignment"]["contests_after"]
    assert after and _statistics(reading) == after
    assert reading["thesis_labels"] == "NONE" and reading["status"] == fpc.READ


def test_the_showdown_qa_with_the_claim_equals_a_portfolio_of_theses_contests_after(sd_theses):
    run = sd_theses
    after = run.report["prior_review_reports"]["contest_assignment"]["contests_after"]
    assert any(stats["distinct_theses"] for stats in after.values()), "the run's step scored with thesis labels"
    labelled = _showdown_reading(run.salary, run.entries, _delivered(run.report),
                                 "--policy", str(policy_path(run)), "--claim", str(claim_path(run)))
    assert labelled["thesis_labels"] == "SUPPLIED"
    assert _statistics(labelled) == after
    plain = _showdown_reading(run.salary, run.entries, _delivered(run.report))
    assert plain["thesis_labels"] == "NONE"
    assert all(stats["distinct_theses"] == 0 for stats in _statistics(plain).values())


def test_the_classic_qa_on_a_c3_file_equals_contest_assignment_json(c3_run, tmp_path):
    report = c3_run.report
    assert report["latest_deliverable"]["producer"] != "run-slate:baseline", report["blockers"]
    artifact = json.loads(Path(report["prior_review_artifacts"]["contest_assignment"]).read_text(encoding="utf-8"))
    delivered = _delivered(report)
    rosters = {entry.entry_id: [fpc.cell_dk_id(cell) for cell in entry.existing_cells]
               for entry in parse_entries(delivered).authorizations if all(entry.existing_cells)}
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_bytes(json.dumps({"lineups": [], "assignments_by_entry_id": rosters}).encode("utf-8"))
    record = tmp_path / "qa.json"
    _code, _text = _stdout(lambda: cl_base.qa.main([
        "--portfolio", str(portfolio), "--salaries", str(c3_run.entries.parent / "salary.csv"),
        "--template", str(c3_run.entries), "--export", str(delivered), "--json", str(record)]))
    reading = json.loads(record.read_text(encoding="utf-8"))["first_place_coverage"]
    assert artifact["contests_after"] and _statistics(reading) == artifact["contests_after"]
    assert reading["source"] == "EXPORT" and reading["thesis_labels"] == "NONE"
