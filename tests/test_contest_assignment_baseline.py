"""Session 50c: the contest-assignment step on the baseline (`nfl_baseline_report_v4`).

The baseline still publishes first and is never blocked by the step: a failure leaves
the salary order and a `P` limitation. The step runs with no restarts under a 0.4 s
cap; these tests recompute every reading from the written bytes.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from nfl_dfs import baseline
from nfl_dfs import contest_assignment as ca
from nfl_dfs.contracts import DeliveryState
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.lineups import write_upload_bytes

from .test_baseline import (
    CLASSIC_ENTRIES_20,
    CLASSIC_SALARY,
    REPO,
    SHOWDOWN_SALARY,
    classic_template,
    codes,
    delivered_rosters,
    rows_of,
    run,
    showdown_template,
    write_rows,
)

CONTEST_COLUMN = 2


def with_contests(path: Path, per_contest: int, tmp_path: Path, name: str) -> Path:
    """`path` with its entries dealt into contests of `per_contest`, in template order."""

    rows = rows_of(path.read_bytes())
    numbered = 0
    for row in rows[1:]:
        if row[0].strip():
            row[CONTEST_COLUMN] = str(700 + numbered // per_contest)
            numbered += 1
    return write_rows(tmp_path / f"{name}.csv", rows)


def _stats(salary: Path, entries: Path, outcome, mode: str):
    slate = parse_salaries(salary)
    people = ca.people_from_slate(slate.players)
    contest_of = {e.entry_id: e.contest_id for e in parse_entries(entries).authorizations}
    return ca.statistics_from_rosters(
        [(eid, contest_of[eid], tuple(roster)) for eid, roster in delivered_rosters(outcome).items()],
        mode=mode, people=people)


def _total(stats) -> float:
    return sum(float(row["score"]) for row in stats.values())


def _salary_order_total(monkeypatch, tmp_path, salary: Path, entries: Path, mode: str) -> float:
    """The same run with the step failed: the lineups stay in the order the baseline built them."""

    def broken(*_args, **_kwargs):
        raise RuntimeError("injected")

    with monkeypatch.context() as patch:
        patch.setattr(ca, "diversify", broken)
        plain = run(tmp_path, salary, entries, out_dir=tmp_path / "salary-order")
    return _total(_stats(salary, entries, plain, mode)), plain


@pytest.mark.parametrize(
    ("mode", "salary", "make"),
    [("CLASSIC", CLASSIC_SALARY, lambda tmp: classic_template(tmp, 20)),
     ("SHOWDOWN", SHOWDOWN_SALARY, lambda tmp: showdown_template(tmp, 20))],
    ids=["classic", "showdown"])
def test_the_step_reaches_the_baseline_file_and_the_bytes_bear_it_out(tmp_path, monkeypatch, mode, salary, make):
    entries = with_contests(make(tmp_path), 2, tmp_path, "contests")
    outcome = run(tmp_path, salary, entries)
    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE, codes(outcome)
    assert (truths.model_status.value, truths.release_decision.value) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert outcome.output_path is not None and outcome.output_path.name.startswith("DK_BASELINE_ENTRY_V1_")

    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    step = report["contest_assignment"]
    assert step["contest_assignment_version"] == "within_contest_diversity_v1"
    assert step["status"] == "IMPROVED" and step["restarts_run"] == 0 and step["pools"] == {"all": 20}
    assert step["contest_count"] == 10 and step["moved_rows"] > 0

    after = _stats(salary, entries, outcome, mode)
    assert f"{_total(after):.6f}" == step["total_score_after"]
    salary_total, plain = _salary_order_total(monkeypatch, tmp_path, salary, entries, mode)
    assert _total(after) < salary_total
    assert step["contests_after"] == after
    audit = report["audit"]
    assert audit["status"] == "PASS" and audit["contest_assignment"]["status"] == "PASS"
    assert audit["contest_assignment"]["contests"] == after
    assert "CONTEST_ASSIGNMENT_MULTISET_FILLED_ROWS_AND_STATISTICS_FROM_THE_BYTES" in audit["checks_run"]

    # report["lineups"] follows the permutation: it lists the rows as the file holds them
    delivered = delivered_rosters(outcome)
    assert {row["entry_id"]: tuple(row["roster"]) for row in report["lineups"]} == delivered
    # the same lineups, only reassigned: distinct (R29) and the multiset of the salary-order build
    assert len({tuple(r) for r in delivered.values()}) == 20
    assert sorted(delivered.values()) == sorted(delivered_rosters(plain).values())
    assert baseline.summary(outcome)["contest_assignment"]["status"] == "IMPROVED"


def test_the_baseline_report_is_v4_and_v3_is_never_mutated(tmp_path):
    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    outcome = run(tmp_path, CLASSIC_SALARY, entries)
    assert outcome.report["schema_version"] == baseline.REPORT_VERSION == "nfl_baseline_report_v4"
    contracts = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    v3 = contracts[contracts.index("### `nfl_baseline_report_v3`"):contracts.index("### `nfl_baseline_report_v4`")]
    # v3 keeps its registered fields exactly; the step's block is v4's alone
    assert "contest_assignment" not in v3 and "Registered 2026-09-24 by Session 11" in v3
    v4 = contracts[contracts.index("### `nfl_baseline_report_v4`"):]
    assert "contest_assignment" in v4 and "0.4" in v4


def test_the_same_inputs_give_the_same_baseline_bytes(tmp_path):
    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    first = run(tmp_path, CLASSIC_SALARY, entries, out_dir=tmp_path / "a", run_id="det")
    second = run(tmp_path, CLASSIC_SALARY, entries, out_dir=tmp_path / "b", run_id="det")
    assert first.output_path.read_bytes() == second.output_path.read_bytes()
    def block(outcome):
        step = dict(outcome.report["contest_assignment"])
        step.pop("seconds")
        return step
    assert block(first) == block(second)


def test_a_single_contest_template_is_not_applicable_and_changes_nothing(tmp_path):
    entries = classic_template(tmp_path, 20)  # one Contest ID
    outcome = run(tmp_path, CLASSIC_SALARY, entries)
    step = outcome.report["contest_assignment"]
    assert step["status"] == "NOT_APPLICABLE" and step["moved_rows"] == 0
    salaries = [row["salary"] for row in outcome.report["lineups"]]
    assert salaries == sorted(salaries, reverse=True)  # still BASELINE_SALARY_RANK_V1 order, row for row


def test_the_cap_returns_the_best_found_and_the_baseline_still_ships(tmp_path):
    """A clock that runs past the 0.4 s cap: the climb stops, the file is valid and audited."""

    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    ticks = iter(range(10_000))
    outcome = run(tmp_path, CLASSIC_SALARY, entries, clock=lambda: next(ticks) * 0.2)
    step = outcome.report["contest_assignment"]
    assert step["timed_out"] is True and step["status"] in {"IMPROVED", "UNCHANGED"}
    assert float(step["total_score_after"]) <= float(step["total_score_before"])
    assert outcome.truths.delivery_state is DeliveryState.DELIVERABLE or outcome.truths.delivery_state is (
        DeliveryState.DELIVERABLE_PARTIAL)
    assert outcome.report["audit"]["status"] == "PASS"
    assert len({tuple(r) for r in delivered_rosters(outcome).values()}) == len(delivered_rosters(outcome))


def test_a_failed_step_leaves_the_salary_order_and_a_p_limitation_and_never_blocks(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(ca, "diversify", broken)
    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    outcome = run(tmp_path, CLASSIC_SALARY, entries)
    assert outcome.truths.delivery_state is DeliveryState.DELIVERABLE
    assert outcome.output_path is not None
    step = outcome.report["contest_assignment"]
    assert step["status"] == "FAILED" and step["error"] == "CONTEST_ASSIGNMENT_STEP_FAILED:RuntimeError:injected"
    salaries = [row["salary"] for row in outcome.report["lineups"]]
    assert salaries == sorted(salaries, reverse=True)
    limitation = {item.code: item for item in outcome.truths.delivery_limitations}["CONTEST_ASSIGNMENT_STEP_FAILED"]
    assert limitation.gate_class.value == "P"
    assert outcome.report["audit"]["status"] == "PASS"


def test_a_lying_step_report_is_p_and_the_file_still_ships(tmp_path, monkeypatch):
    real_step = ca.apply_step

    def lying(**kwargs):
        step = real_step(**kwargs)
        lie = json.loads(json.dumps(step.claim.reported_after))
        lie[sorted(lie)[0]]["worst_pair_shared_people"] += 5
        return ca.StepOutcome(step.assignments, step.report, replace(step.claim, reported_after=lie), step.failure)

    monkeypatch.setattr(ca, "apply_step", lying)
    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    outcome = run(tmp_path, CLASSIC_SALARY, entries)
    assert outcome.truths.delivery_state is DeliveryState.DELIVERABLE
    classes = {item.code: item.gate_class.value for item in outcome.truths.delivery_limitations}
    assert classes["CONTEST_ASSIGNMENT_STATS_MISMATCH"] == "P"
    assert outcome.report["audit"]["contest_assignment"]["status"] == "STATS_MISMATCH"


def test_a_changed_multiset_withholds_the_baseline_file_v(tmp_path, monkeypatch):
    """The audit holds the written rows to the lineups the build produced (`V`): nothing is kept."""

    real_step = ca.apply_step
    slate = parse_salaries(CLASSIC_SALARY)

    def swapping(**kwargs):
        step = real_step(**kwargs)
        held = set(step.assignments.values())
        built = baseline.build_distinct_lineups(
            slate, count=40, excluded_ids=(), per_solve_seconds=5.0, deadline=1e12, clock=lambda: 0.0)
        outsider = next(tuple(lineup.roster) for lineup in built.lineups if tuple(lineup.roster) not in held)
        first = next(iter(step.assignments))
        return ca.StepOutcome({**step.assignments, first: outsider}, step.report, step.claim, step.failure)

    monkeypatch.setattr(ca, "apply_step", swapping)
    entries = with_contests(classic_template(tmp_path, 20), 2, tmp_path, "contests")
    outcome = run(tmp_path, CLASSIC_SALARY, entries)
    assert outcome.output_path is None
    assert outcome.truths.delivery_state is not DeliveryState.DELIVERABLE
    assert any("CONTEST_ASSIGNMENT_MULTISET_CHANGED" in item.detail for item in outcome.truths.delivery_limitations)
    assert not list(outcome.run_dir.glob("DK_BASELINE_ENTRY_V1_*.csv"))


def test_the_audit_refuses_a_moved_filled_row_and_a_changed_multiset(tmp_path, monkeypatch):
    """A row the template filled is read from the template's bytes, never from the claim."""

    slate = parse_salaries(SHOWDOWN_SALARY)
    top = baseline.build_distinct_lineups(
        slate, count=1, excluded_ids=(), per_solve_seconds=5.0, deadline=1e12, clock=lambda: 0.0)
    prefilled = list(top.lineups[0].roster)  # legal and current, so the row resolves and is scored
    template = showdown_template(tmp_path, 6, SHOWDOWN_SALARY, prefilled={2: prefilled})
    entries = with_contests(template, 3, tmp_path, "contests")
    seen: dict[str, object] = {}
    real_step = ca.apply_step

    def keep(**kwargs):
        step = real_step(**kwargs)
        seen["claim"] = step.claim
        return step

    monkeypatch.setattr(ca, "apply_step", keep)
    outcome = run(tmp_path, SHOWDOWN_SALARY, entries)
    assert outcome.output_path is not None, codes(outcome)
    claim = seen["claim"]
    assert claim.selected_by_pool and [row.entry_id for row in claim.rows if row.pool is None]  # a filled row
    raw = outcome.output_path.read_bytes()
    template_ids = [e.entry_id for e in parse_entries(entries).authorizations]
    unfilled = tuple(eid for eid in template_ids if eid not in outcome.assignments and eid != template_ids[1])
    kwargs = dict(salary_path=SHOWDOWN_SALARY, entries_path=entries, assignments=outcome.assignments,
                  unfilled=unfilled)

    reading: dict[str, object] = {}
    assert baseline.audit_baseline_bytes(raw, contest_assignment_claim=claim, contest_reading=reading, **kwargs) == []
    assert reading["status"] == "PASS"

    fixed = next(row for row in claim.rows if row.pool is None)
    moved = replace(claim, rows=tuple(replace(row, roster=tuple(reversed(row.roster))) if row is fixed else row
                                      for row in claim.rows))
    problems = baseline.audit_baseline_bytes(raw, contest_assignment_claim=moved, **kwargs)
    assert f"CONTEST_ASSIGNMENT_FIXED_ROW_MOVED:{fixed.entry_id}" in problems

    lines = raw.decode("utf-8").splitlines(keepends=True)
    changed = dict(outcome.assignments)
    first, second = list(changed)[:2]
    changed[first] = changed[second]  # a repeated lineup: R29 and the multiset both refuse it
    problems = baseline.audit_baseline_bytes(
        write_upload_bytes(parse_entries(entries), changed, unfilled=unfilled), contest_assignment_claim=claim,
        **{**kwargs, "assignments": changed})
    assert any(item.startswith("CONTEST_ASSIGNMENT_MULTISET_CHANGED") for item in problems), problems
    assert any(item.startswith("BASELINE_AUDIT_DUPLICATE_LINEUP") for item in problems)
