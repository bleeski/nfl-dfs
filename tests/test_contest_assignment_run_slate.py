"""Session 50: the contest-assignment step through `run-slate`, Showdown exits.

One test per `prior_review` Showdown exit (policy, sequential, subset policy with a
fill), each showing the diversified assignment reaching `assignments.csv`, the
independent audit and the review, with every release truth unchanged. Classic
exits (C1, C2, C3) are Session 50c's.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries

from .test_deadline_controller import FakeClock, _clocked
from .test_entry_groups import SD3_CONTROLS, _cells, _cowork_args, _edit, _raw_lines, _readable

CONTEST_COLUMN = 2
SIX = tuple(f"90000000{index}" for index in range(1, 7))
# Solver order puts lineups 1 to 3 in contest A and 4 to 6 in B; a good assignment
# splits the strongest, most alike lineups across the two.
TWO_CONTESTS = {entry_id: ("111" if index < 3 else "222") for index, entry_id in enumerate(SIX)}


def _run(tmp_path, monkeypatch, *, run_id, contests, cells=None, policy_controls=None, bound=None,
         entry_ids=SIX, wrap_step=None, cowork=None):
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module
    from nfl_dfs.portfolio_policy import portfolio_policy_template

    from .test_entry_groups import _attachments
    from .test_prior_review_profile import _prepared_run
    from .test_prior_selection import _entries_bytes

    _clocked(monkeypatch, FakeClock())
    tmp_path.mkdir(parents=True, exist_ok=True)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    entry_path.write_bytes(_entries_bytes(entry_ids))
    _edit(entry_path, cells=cells, columns={eid: {CONTEST_COLUMN: cid} for eid, cid in contests.items()})
    attachments = _attachments(tmp_path, salary_path, entry_path)
    values = dict(run_id=run_id, prior_package_dir=str(package_dir), **(cowork or {}))
    if policy_controls is not None:
        slate = parse_salaries(salary_path)
        plan = plan_entries(parse_entries(entry_path), slate)
        policy_path = tmp_path / "policy" / "portfolio.json"
        policy_path.parent.mkdir()
        policy_path.write_text(json.dumps(portfolio_policy_template(
            slate, list(plan.fillable if bound is None else bound), controls=policy_controls)),
            encoding="utf-8")
        values["portfolio_policy_json"] = str(policy_path)
    if wrap_step is not None:
        real_step = ca.apply_step
        monkeypatch.setattr(
            ca, "apply_step", lambda **kwargs: wrap_step(real_step(**kwargs), parse_salaries(salary_path)))
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project))
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, **values))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, attachments / "entries.csv", parse_salaries(salary_path)


def _assignment_rosters(report) -> dict[str, tuple[str, ...]]:
    lines = Path(report["prior_review_artifacts"]["assignments"]).read_text(encoding="utf-8").splitlines()
    return {line.split(",")[0]: tuple(line.split(",")[1:7]) for line in lines[1:] if line}


def _selection_rosters(report) -> list[tuple[str, ...]]:
    return [tuple(row["roster"]) for row in report["prior_review_reports"]["selection"]["lineups"]]


def _recompute(slate, entries_path, delivered_path):
    """Per-contest statistics from the delivered bytes and from the solver's order."""

    people = ca.people_from_slate(slate.players)
    contest_of = {e.entry_id: e.contest_id for e in parse_entries(entries_path).authorizations}
    delivered = _cells(delivered_path)
    return ca.statistics_from_rosters(
        [(eid, contest_of[eid], tuple(roster)) for eid, roster in delivered.items() if any(roster)],
        mode=ca.MODE_SHOWDOWN, people=people)


def _total(stats) -> float:
    return sum(float(row["score"]) for row in stats.values())


def _solver_order_total(slate, entries_path, report, order_entries) -> float:
    people = ca.people_from_slate(slate.players)
    contest_of = {e.entry_id: e.contest_id for e in parse_entries(entries_path).authorizations}
    rosters = _selection_rosters(report)
    return _total(ca.statistics_from_rosters(
        [(eid, contest_of[eid], roster) for eid, roster in zip(order_entries, rosters)],
        mode=ca.MODE_SHOWDOWN, people=people))


def _assert_truths_unchanged(report):
    truths = report["release_truths"]
    assert (truths["MODEL_STATUS"], truths["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert report["DELIVERY_STATE"] == "DELIVERABLE"


@pytest.mark.parametrize("policy_controls", [None, SD3_CONTROLS], ids=["sequential", "policy"])
def test_the_diversified_assignment_reaches_the_file_the_audit_and_the_review(
    tmp_path, monkeypatch, policy_controls
):
    code, report, entries, slate = _run(
        tmp_path, monkeypatch, run_id="cd-run", contests=TWO_CONTESTS, policy_controls=policy_controls)
    assert code == 0, report["blockers"]
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    _assert_truths_unchanged(report)
    delivered = Path(report["latest_deliverable"]["path"])

    step = report["prior_review_reports"]["contest_assignment"]
    assert step["contest_assignment_version"] == "within_contest_diversity_v1"
    assert step["status"] == "IMPROVED" and step["moved_rows"] > 0
    assert "PAYOUT_OR_CONTEST_WORTH" in step["does_not_establish"]

    # assignments.csv, the delivered CSV and the selection hold the same lineups, entry for entry
    assignment = _assignment_rosters(report)
    cells = _cells(delivered)
    assert {eid: tuple(cells[eid]) for eid in SIX} == assignment
    assert sorted(assignment.values()) == sorted(_selection_rosters(report))

    # the file's own bytes bear the improvement out, recomputed here and not read from the step
    after = _recompute(slate, entries, delivered)
    assert _total(after) < _solver_order_total(slate, entries, report, SIX)
    assert f"{_total(after):.6f}" == step["total_score_after"]

    readable = _readable(report)
    block = readable["contest_assignment"]
    assert block["reported_statistics_match"] is True
    assert block["basis"] == ca.REVIEW_BASIS and block["status"] == "IMPROVED"
    assert {row["contest_id"] for row in block["contests"]} == {"111", "222"}
    assert all(row["score_after"] <= row["score_before"] for row in block["contests"])
    assert readable["reconciliation"]["status"] == "PASS"
    assert "Within each contest" in Path(report["prior_review_artifacts"]["readable_review_html"]).read_text("utf-8")

    if policy_controls is not None:
        audit = report["prior_review_reports"]["portfolio_policy_audit"]
        assert audit["status"] == "PASS"
        reading = audit["contest_assignment"]
        assert reading["status"] == "PASS" and reading["findings"] == []
        assert {k: {kk: vv for kk, vv in v.items()} for k, v in reading["contests"].items()} == after


def test_a_prefilled_row_stays_put_and_counts_in_its_contest(tmp_path, monkeypatch):
    code, plain, _entries, _slate = _run(
        tmp_path / "plain", monkeypatch, run_id="cd-plain", entry_ids=SIX[:2],
        contests={SIX[0]: "111", SIX[1]: "111"})
    assert code == 0
    first = _cells(Path(plain["latest_deliverable"]["path"]))[SIX[0]]

    code, report, entries, slate = _run(
        tmp_path / "prefilled", monkeypatch, run_id="cd-prefilled", contests=TWO_CONTESTS,
        cells={SIX[1]: list(first)})
    assert code == 0, report["blockers"]
    delivered = Path(report["latest_deliverable"]["path"])
    assert _raw_lines(delivered)[SIX[1]] == _raw_lines(entries)[SIX[1]]
    step = report["prior_review_reports"]["contest_assignment"]
    assert step["fixed_entry_ids"] == [SIX[1]]
    assert tuple(_cells(delivered)[SIX[1]]) == tuple(first)
    # its contest (111) still scores the pair the prefilled lineup forms
    stats = _recompute(slate, entries, delivered)
    assert stats["111"]["entries"] == 3 and stats["222"]["entries"] == 3


def test_a_subset_policy_keeps_each_lineup_in_its_own_pool(tmp_path, monkeypatch):
    bound = (SIX[0], SIX[2], SIX[4])
    code, report, entries, slate = _run(
        tmp_path, monkeypatch, run_id="cd-subset", contests=TWO_CONTESTS,
        policy_controls=SD3_CONTROLS, bound=bound)
    assert code == 0, report["blockers"]
    _assert_truths_unchanged(report)
    step = report["prior_review_reports"]["contest_assignment"]
    assert step["pools"] == {"bound": 3, "fill": 3}
    selected = _selection_rosters(report)
    policy_lineups, fill_lineups = selected[:3], selected[3:]
    assignment = _assignment_rosters(report)
    assert sorted(assignment[eid] for eid in bound) == sorted(policy_lineups)
    assert sorted(assignment[eid] for eid in SIX if eid not in bound) == sorted(fill_lineups)
    readable = _readable(report)
    assert readable["contest_assignment"]["reported_statistics_match"] is True
    assert readable["reconciliation"]["status"] == "PASS"
    assert report["portfolio_policy"]["independent_audit"]["contest_assignment"]["status"] == "PASS"


def test_the_same_inputs_give_the_same_delivered_bytes(tmp_path, monkeypatch):
    first = _run(tmp_path / "a", monkeypatch, run_id="cd-a", contests=TWO_CONTESTS)[1]
    second = _run(tmp_path / "b", monkeypatch, run_id="cd-a", contests=TWO_CONTESTS)[1]
    assert Path(first["latest_deliverable"]["path"]).read_bytes() == Path(
        second["latest_deliverable"]["path"]).read_bytes()


def test_a_failed_step_leaves_the_solver_order_and_ships_with_the_gap_named(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(ca, "diversify", broken)
    code, report, _entries, _slate = _run(tmp_path, monkeypatch, run_id="cd-failed", contests=TWO_CONTESTS)
    assert code == 0, report["blockers"]
    _assert_truths_unchanged(report)
    step = report["prior_review_reports"]["contest_assignment"]
    assert step["status"] == "FAILED" and "CONTEST_ASSIGNMENT_STEP_FAILED:RuntimeError:injected" == step["error"]
    # the file is the solver's order, entry for entry
    assert list(_assignment_rosters(report).values()) == _selection_rosters(report)
    limitations = {item["code"]: item for item in report["release_truths"]["delivery_limitations"]}
    assert limitations["CONTEST_ASSIGNMENT_STEP_FAILED"]["class"] == "P"
    assert _readable(report)["contest_assignment"]["status"] == "FAILED"


def test_the_policy_audit_refuses_a_lineup_from_outside_the_selection(tmp_path, monkeypatch):
    """`audit_policy_assignments` recomputes from the exact assignment bytes, never the step's numbers."""

    import hashlib

    from nfl_dfs import portfolio_enforcement as pe

    seen = {}
    real_audit = pe.audit_policy_assignments

    def capture(**kwargs):
        seen["kwargs"] = kwargs
        return real_audit(**kwargs)

    monkeypatch.setattr("nfl_dfs.prior_review.audit_policy_assignments", capture)
    code, report, _entries, slate = _run(
        tmp_path, monkeypatch, run_id="cd-audit", contests=TWO_CONTESTS, policy_controls=SD3_CONTROLS)
    assert code == 0, report["blockers"]
    kwargs = seen["kwargs"]
    assert real_audit(**kwargs).passed

    # row one now holds a lineup the selection never held: its Captain is another person's
    lines = kwargs["assignment_artifact_bytes"].decode("utf-8").splitlines(keepends=True)
    cells = lines[1].rstrip("\r\n").split(",")
    other_captain = next(
        player.dk_id for player in slate.players if player.role == "CPT" and player.dk_id not in cells[1:7])
    cells[1] = other_captain
    tampered_line = ",".join(cells) + ("\r\n" if lines[1].endswith("\r\n") else "\n")
    tampered_bytes = (lines[0] + tampered_line + "".join(lines[2:])).encode("utf-8")
    pairs = list(kwargs["assignments"])
    pairs[0] = (pairs[0][0], tuple(cells[1:7]))
    audit = real_audit(**{
        **kwargs,
        "assignment_artifact_bytes": tampered_bytes,
        "expected_assignment_artifact_sha256": hashlib.sha256(tampered_bytes).hexdigest(),
        "assignments": pairs,
    })
    assert not audit.passed
    assert any(item.startswith("CONTEST_ASSIGNMENT_MULTISET_CHANGED:") for item in audit.problems), audit.problems


def test_the_runs_claim_refuses_a_moved_filled_row(tmp_path, monkeypatch):
    captured = {}
    code, plain, _entries, _slate = _run(
        tmp_path / "plain", monkeypatch, run_id="cd-plain2", entry_ids=SIX[:2],
        contests={SIX[0]: "111", SIX[1]: "111"})
    first = _cells(Path(plain["latest_deliverable"]["path"]))[SIX[0]]

    def keep(step, _slate):
        captured["claim"] = step.claim
        return step

    code, report, _entries, _slate = _run(
        tmp_path / "prefilled", monkeypatch, run_id="cd-fixed", contests=TWO_CONTESTS,
        cells={SIX[1]: list(first)}, wrap_step=keep)
    assert code == 0, report["blockers"]
    claim = captured["claim"]
    final = {**_assignment_rosters(report), SIX[1]: tuple(first)}
    assert claim.audit(final)[0] == []
    moved = {**final, SIX[1]: final[SIX[0]]}
    problems, _ = claim.audit(moved)
    assert f"CONTEST_ASSIGNMENT_FIXED_ROW_MOVED:{SIX[1]}" in problems


def _falsify_stats(step, _slate):
    report = json.loads(json.dumps(step.report))
    first = sorted(report["contests_after"])[0]
    report["contests_after"][first]["worst_pair_shared_people"] += 5
    return ca.StepOutcome(step.assignments, report, step.claim, step.failure)


def test_the_readable_review_reconciles_the_block_and_a_lie_is_a_presentation_limitation(tmp_path, monkeypatch):
    """DISPLAY_RECONCILIATION covers the block: reported numbers the bytes do not bear out are named `P`."""

    code, report, _entries, _slate = _run(
        tmp_path, monkeypatch, run_id="cd-lie", contests=TWO_CONTESTS, wrap_step=_falsify_stats)
    assert code == 2 or report["blockers"], "the review reconciles or names the discrepancy"
    joined = ";".join(report["blockers"])
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" in joined
    limitations = {item["code"]: item for item in report["release_truths"]["delivery_limitations"]}
    assert limitations["CONTEST_ASSIGNMENT_STATS_MISMATCH"]["class"] == "P"
    # a `P` discrepancy never withholds the file: the lineups and their rows are intact
    assert report["latest_deliverable"] is not None
    _assert_truths_unchanged(report)


def test_the_readable_review_withholds_a_file_whose_lineups_are_not_the_selections(tmp_path, monkeypatch):
    """A tampered assignment on the sequential exit, where no policy audit stands guard."""

    from nfl_dfs import baseline

    def swap_in_an_outsider(step, slate):
        held = set(step.assignments.values())
        built = baseline.build_distinct_lineups(
            slate, count=8, excluded_ids=(), per_solve_seconds=5.0, deadline=1e12, clock=lambda: 0.0)
        outsider = next(lineup.roster for lineup in built.lineups if tuple(lineup.roster) not in held)
        assignments = dict(step.assignments)
        assignments[SIX[0]] = tuple(outsider)  # legal, distinct, and never in the selection
        return ca.StepOutcome(assignments, step.report, step.claim, step.failure)

    code, report, _entries, _slate = _run(
        tmp_path, monkeypatch, run_id="cd-swap", contests=TWO_CONTESTS, wrap_step=swap_in_an_outsider)
    joined = ";".join(report["blockers"])
    assert "READABLE_REVIEW" in joined
    assert report["latest_deliverable"] is None or report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert report["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_the_review_block_refuses_a_changed_multiset_and_names_a_lying_report():
    people = {f"c{i}": ca.Person(f"p{i}") for i in range(12)} | {f"f{i}": ca.Person(f"p{i}") for i in range(12)}

    def roster(cpt, *flex):
        return (f"c{cpt}",) + tuple(f"f{i}" for i in flex)

    rows = [("1", "A", roster(1, 2, 3, 4, 5, 6), "all"), ("2", "A", roster(7, 8, 9, 10, 11, 0), "all"),
            ("3", "B", roster(2, 3, 4, 5, 6, 7), "all"), ("4", "B", roster(8, 9, 10, 11, 0, 1), "all")]
    selected = [r[2] for r in rows]
    step = ca.diversify([ca.EntryRow(*r) for r in rows], mode="SHOWDOWN", people=people,
                        restarts=5, time_limit_seconds=None)
    block, problems = ca.review_block(mode="SHOWDOWN", people=people, rows=rows,
                                      selected_in_solver_order=selected, reported=step.report)
    assert problems == [] and block["reported_statistics_match"] is True

    changed = [rows[0][:2] + (roster(1, 2, 3, 4, 5, 11),) + rows[0][3:]] + rows[1:]
    _, problems = ca.review_block(mode="SHOWDOWN", people=people, rows=changed,
                                  selected_in_solver_order=selected, reported=step.report)
    assert "CONTEST_ASSIGNMENT_MULTISET_CHANGED:delivered_rosters" in problems

    lying = dict(step.report, contests_after={k: dict(v, entries=99) for k, v in step.report["contests_after"].items()})
    block, problems = ca.review_block(mode="SHOWDOWN", people=people, rows=rows,
                                      selected_in_solver_order=selected, reported=lying)
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" in problems and block["reported_statistics_match"] is False
    assert ca.review_block(mode="SHOWDOWN", people=people, rows=rows,
                           selected_in_solver_order=selected, reported=None) == (None, [])


def test_a_sequential_run_that_selects_more_lineups_than_entries_still_ships(tmp_path, monkeypatch):
    """`lineup_count` above the entry count keeps the extra lineups in the selection only."""

    code, report, entries, slate = _run(
        tmp_path, monkeypatch, run_id="cd-extra", contests=TWO_CONTESTS, cowork={"lineup_count": 8})
    assert code == 0, report["blockers"]
    assert len(_selection_rosters(report)) == 8
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    block = _readable(report)["contest_assignment"]
    assert block["reported_statistics_match"] is True
    held = {tuple(r) for r in _assignment_rosters(report).values()}
    assert held <= set(_selection_rosters(report)[:8]) and len(held) == 6


def test_the_contest_block_is_on_the_workbooks_exposure_sheet(tmp_path, monkeypatch):
    from openpyxl import load_workbook

    code, report, _entries, _slate = _run(tmp_path, monkeypatch, run_id="cd-book", contests=TWO_CONTESTS)
    assert code == 0, report["blockers"]
    sheet = load_workbook(report["review_workbook"])["Exposure"]
    cells = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None]
    assert any("within_contest_diversity_v1" in value for value in cells)
    assert "Reported statistics match the recomputation" in cells
    assert {"111", "222"} <= set(cells)


def test_the_policy_audit_reads_a_filled_row_from_the_template_bytes(tmp_path, monkeypatch):
    """Tamper the claim's copy of a filled roster: the template's bytes say otherwise."""

    from dataclasses import replace

    from nfl_dfs import portfolio_enforcement as pe

    code, plain, _e, _s = _run(
        tmp_path / "plain", monkeypatch, run_id="cd-plain3", entry_ids=SIX[:2],
        contests={SIX[0]: "111", SIX[1]: "111"})
    first = _cells(Path(plain["latest_deliverable"]["path"]))[SIX[0]]
    seen = {}
    real_audit = pe.audit_policy_assignments

    def capture(**kwargs):
        seen["kwargs"] = kwargs
        return real_audit(**kwargs)

    monkeypatch.setattr("nfl_dfs.prior_review.audit_policy_assignments", capture)
    code, report, _e, _s = _run(
        tmp_path / "prefilled", monkeypatch, run_id="cd-fixed2", contests=TWO_CONTESTS,
        cells={SIX[1]: list(first)}, policy_controls=SD3_CONTROLS, bound=tuple(s for s in SIX if s != SIX[1]))
    assert code == 0, report["blockers"]
    kwargs = seen["kwargs"]
    claim = kwargs["contest_assignment"]
    assert real_audit(**kwargs).contest_assignment["status"] == "PASS"
    rows = tuple(replace(r, roster=tuple(reversed(r.roster))) if r.entry_id == SIX[1] else r for r in claim.rows)
    audit = real_audit(**{**kwargs, "contest_assignment": replace(claim, rows=rows)})
    assert not audit.passed
    assert any(item.startswith(f"CONTEST_ASSIGNMENT_FIXED_ROW_MOVED:{SIX[1]}") for item in audit.problems)
