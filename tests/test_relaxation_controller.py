"""Session 10: the relaxation controller walks the rung ladder inside one run-slate run.

The acceptance, each a real `run-slate` run on the synthetic Classic fixture
(4 teams, 20 people) or the Showdown fixture, on a fake monotonic clock:

- an impossible exposure cap relaxes to feasible and exports;
- a bank timeout shrinks the bank first and relaxes no structure;
- a pool too small for distinct lineups never repeats a lineup and reports the
  unfilled Entry IDs;
- budget exhaustion mid-ladder stops with the baseline delivered and the stop
  named;
- a Showdown Captain-cap infeasibility relaxes and exports.

The rest pins the ladder itself: a generator's rung-k policy becomes rung k+1
exactly, a relaxation never tightens, and neither uniqueness nor an exclusion is
ever on it.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
)
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.portfolio_policy import (
    canonical_decimal_json_bytes,
    portfolio_policy_template,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.relaxation import (
    classic_limits,
    classic_relaxed_controls,
    classic_rung_controls,
    own_exclusion_dk_ids,
    showdown_relaxed_controls,
)

from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_deadline_controller import FakeClock, _baseline_is_the_file, _clocked, _truth_codes
from .test_prior_review_profile import _attachments, _cowork_args, _prepared_run

SUPPLIED = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "supplied"


# ----------------------------------------------------------------- helpers


def _classic(tmp_path, monkeypatch, *, run_id, policy, entries=3, window=60.0, review=None, clock=None):
    """`run-slate` on the Classic fixture with `window` seconds before the improvement stops."""

    from nfl_dfs import cli

    _clocked(monkeypatch, clock or FakeClock())
    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=entries)
    attachments = _attachments(tmp_path, salary, entry)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    if review is not None:
        monkeypatch.setattr(cli, "run_prior_review", review)
    deadline = AS_OF + timedelta(minutes=5, seconds=window)  # the improvement stops 5 minutes before it
    values = dict(
        label=run_id, run_id=run_id, prior_package_dir=str(package), official_status_csv=str(status),
        offensive_role_evidence_json=str(role), as_of=AS_OF.isoformat(),
        delivery_deadline_utc=deadline.isoformat(), portfolio_policy_json=str(policy(attachments)))
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, **values))
    root = tmp_path / "outputs" / run_id
    return code, json.loads((root / "cowork_run.json").read_text(encoding="utf-8")), root


def _policy_file(attachments: Path, *, controls=None, limits=None) -> Path:
    slate = parse_salaries(attachments / "salary.csv")
    entries = parse_entries(attachments / "entries.csv")
    path = attachments.parent / "classic_policy.json"
    path.write_text(json.dumps(classic_portfolio_policy_template(
        slate, tuple(item.entry_id for item in entries.authorizations), entry_sha256=entries.raw_hash,
        controls=controls, limits=limits)), encoding="utf-8")
    return path


def _exported_rosters(report) -> list[tuple[str, ...]]:
    path = Path(report["latest_deliverable"]["path"])
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    header = rows[0]
    slots = range(header.index("Entry Fee") + 1, header.index("Entry Fee") + 10)
    return [tuple(sorted(row[index] for index in slots)) for row in rows[1:]
            if row and row[0].strip().isdigit() and all(row[index].strip() for index in slots)]


def _timed_out_bank(monkeypatch, *, every_time=False, kept=20):
    """The C2 bank reports `CANDIDATE_BANK_TIMEOUT` with `kept` of its candidates.

    The bank is real, built to a small size so the test stays quick; its status
    and count are what a bank stopped by its total budget reports. Only the first
    call times out unless `every_time`.
    """

    from nfl_dfs import selection

    real = selection.build_classic_candidate_bank
    calls: list[int] = []

    def bank(slate, objective, policy, **kwargs):
        calls.append(policy.search_limits.candidate_limit)
        if calls[1:] and not every_time:
            return real(slate, objective, policy, **kwargs)
        small = replace(policy, search_limits=replace(policy.search_limits, candidate_limit=kept))
        built = real(slate, objective, small, **kwargs)
        return replace(built, status="CANDIDATE_BANK_TIMEOUT", candidates=built.candidates[:kept],
                       requested_candidates=policy.search_limits.candidate_limit, exhaustive=False)

    monkeypatch.setattr(selection, "build_classic_candidate_bank", bank)
    return calls


# ----------------------------------------------------------------- the acceptance


def test_an_impossible_exposure_cap_relaxes_to_feasible_and_exports(tmp_path, monkeypatch):
    """Every person capped at one of three entries cannot fill 27 roster slots from 20 people.

    The policy's only problems are construction preferences, so the ladder takes
    it at intake: rungs 0 to 2 still cap each person at two, which four wide
    receivers cannot stretch over nine WR slots, and the validator refuses them;
    rung 3 carries no exposure cap, validates, and C2 and C3 export it.
    """

    def policy(attachments):
        slate = parse_salaries(attachments / "salary.csv")
        bounds = [{"underlying_id": row.underlying_id, "dk_id": row.dk_id, "minimum_entries": 0,
                   "maximum_entries": 1, "hard": True} for row in slate.players]
        return _policy_file(attachments, controls={"player_exposure_bounds": bounds})

    code, report, root = _classic(tmp_path, monkeypatch, run_id="impossible-cap", policy=policy)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    assert report["improvement"]["status"] == "DELIVERED"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    relaxation = report["relaxation"]
    assert relaxation["schema_version"] == "nfl_relaxation_record_v1"
    assert relaxation["final_rung"] == "3" and relaxation["stop"] is None
    refused = [item for item in relaxation["attempts"] if item["outcome"] == "REFUSED_AT_VALIDATION"]
    assert [item["rung"] for item in refused] == ["0", "1", "2"]
    assert all("CLASSIC_POLICY_POSITION_CAPACITY_INSUFFICIENT" in item["codes"] for item in refused)
    (bounds,) = [item for item in relaxation["relaxations"] if item["constraint"] == "player_exposure_bounds"]
    assert bounds["original"]["maximum_entries"] == [1] and bounds["final"]["bounded"] == 0
    assert bounds["trigger_origin"] == "INTAKE" and bounds["class"] == "S"
    assert bounds["limitation_code"] == "RELAXATION_STRUCTURE_RELAXED"
    assert bounds["entry_ids"] == list(report["release_truths"]["delivered_entry_ids"])
    # The rung's policy is a real artifact: written, hashed, validated, normalized,
    # bound in its record, and the one the review consumed.
    from nfl_dfs.hashing import sha256_file

    binding = bounds["policy"]
    source = Path(binding["source_path"])
    assert source.parent.parent == tmp_path / "runs" / "impossible-cap" / "relaxation"
    assert sha256_file(source) == binding["source_sha256"]
    assert json.loads((source.parent / "portfolio_policy_validation.json").read_text())["valid"] is True
    assert report["prior_review_hashes"]["portfolio_policy_source"] == binding["source_sha256"]
    assert report["prior_review_hashes"]["portfolio_policy_normalized"] == binding["normalized_sha256"]
    assert relaxation["final_policy"] == binding
    assert _truth_codes(report)["RELAXATION_STRUCTURE_RELAXED"] == "S"
    rosters = _exported_rosters(report)
    assert len(rosters) == 3 and len(set(rosters)) == 3
    assert (tmp_path / "runs" / "impossible-cap" / "relaxation" / "relaxation.json").is_file()


def test_a_bank_timeout_shrinks_the_bank_first_and_relaxes_no_structure(tmp_path, monkeypatch):
    calls = _timed_out_bank(monkeypatch)
    limits = {"candidate_limit": 200, "candidate_total_milliseconds": 60_000,
              "candidate_per_solve_milliseconds": 1_500, "selection_milliseconds": 10_000}
    code, report, root = _classic(tmp_path, monkeypatch, run_id="bank-timeout", window=1_800.0,
                                  policy=lambda attachments: _policy_file(attachments, limits=limits))
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    relaxation = report["relaxation"]
    (resized,) = relaxation["relaxations"]
    assert (resized["step"], resized["constraint"], resized["trigger"]) == (
        "BANK", "search_limits", "CANDIDATE_BANK_TIMEOUT")
    assert resized["limitation_code"] == "RELAXATION_BANK_RESIZED" and resized["family"] == "search_budget"
    # 1 candidate in the declared 60 s is 60 s a candidate: the bank shrinks to the
    # floor and its budget rises to fit it, and nothing structural moves.
    assert resized["original"]["candidate_limit"] == 200
    assert resized["final"]["candidate_limit"] < 200
    assert resized["final"]["candidate_total_milliseconds"] > 60_000
    assert calls == [200, resized["final"]["candidate_limit"]]
    assert relaxation["final_rung"] == "SUPPLIED"  # the same rung: only the bank changed
    before = json.loads(Path(relaxation["started_from"]["policy"]["normalized_path"]).read_text())
    after = json.loads(Path(relaxation["final_policy"]["normalized_path"]).read_text())
    assert before["controls"] == after["controls"]
    assert before["selection"]["limits"] != after["selection"]["limits"]
    assert _truth_codes(report)["RELAXATION_BANK_RESIZED"] == "S"
    assert "RELAXATION_STRUCTURE_RELAXED" not in _truth_codes(report)


def _one_lineup_salaries(monkeypatch) -> None:
    """Nine people fit under the cap together, and any substitution breaks it.

    The nine cost 5,500 each (49,500); everyone else costs 6,100, so swapping one
    in costs 50,100. Exactly one distinct lineup exists on the slate, for the
    baseline and the review alike, and no person has to leave the pool, so no
    evidence gate is involved.
    """

    from . import test_classic_prior_review as fixture

    keep = {("NE", "QB"), ("NE", "RB"), ("DAL", "RB"), ("NE", "WR"), ("SEA", "WR"), ("DAL", "WR"),
            ("NE", "TE"), ("PHI", "TE"), ("SEA", "DST")}
    original = fixture._salary_bytes

    def salaries(**kwargs) -> bytes:
        rows = list(csv.reader(io.StringIO(original(**kwargs).decode("utf-8"))))
        header = rows[0]
        position, team, salary = header.index("Position"), header.index("TeamAbbrev"), header.index("Salary")
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(header)
        for row in rows[1:]:
            row[salary] = "5500" if (row[team], row[position]) in keep else "6100"
            writer.writerow(row)
        return output.getvalue().encode("utf-8")

    monkeypatch.setattr(fixture, "_salary_bytes", salaries)


def test_a_pool_too_small_for_distinct_lineups_never_repeats_one_and_names_the_unfilled_entries(
        tmp_path, monkeypatch):
    """One distinct lineup; three entries want three. R29 is never on the ladder.

    The C2 bank is exhaustive with one candidate, `MODELED_BANK_INFEASIBILITY`;
    the template policy has no structure a rung can loosen, so the ladder takes
    rung 4, and C1 runs out of distinct lineups after the first. The baseline,
    with its one lineup and two unfilled Entry IDs, is the file.
    """

    _one_lineup_salaries(monkeypatch)
    code, report, root = _classic(tmp_path, monkeypatch, run_id="too-few",
                                  policy=lambda attachments: _policy_file(attachments))
    assert code == 2  # the run's own review did not complete; the baseline is the file
    assert report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert report["DELIVERY_STATE"] == "DELIVERABLE_PARTIAL" and report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    entry_ids = [item.entry_id for item in parse_entries(tmp_path / "attachments" / "entries.csv").authorizations]
    assert report["release_truths"]["unfilled_entry_ids"] == entry_ids[1:]
    rosters = _exported_rosters(report)
    assert len(rosters) == 1 and len(set(rosters)) == len(rosters)  # never a repeat
    relaxation = report["relaxation"]
    assert [(item["rung"], item["failure"]) for item in relaxation["attempts"]] == [
        ("SUPPLIED", "MODELED_BANK_INFEASIBILITY"), ("4", None)]
    assert relaxation["final_rung"] == "4" and relaxation["stop"] is None
    (dropped,) = relaxation["relaxations"]
    assert (dropped["step"], dropped["trigger"]) == ("NO_POLICY", "MODELED_BANK_INFEASIBILITY")
    assert dropped["why"] == "no structural rung is left"
    assert any(text.startswith("SELECTION_FAILED:SelectionError:SOLVER_RETURNED_NO_LINEUP:index=2")
               for text in report["blockers"])
    assert report["prior_review_reports"]["selection_failure"]["status"] == "SOLVER_RETURNED_NO_LINEUP"
    assert all("unique" not in item["constraint"] for item in relaxation["relaxations"])


def test_budget_exhaustion_mid_ladder_stops_with_the_baseline_delivered_and_the_stop_named(
        tmp_path, monkeypatch):
    from nfl_dfs import prior_review as prior_review_module

    clock = FakeClock()
    _timed_out_bank(monkeypatch, every_time=True)
    real = prior_review_module.run_prior_review

    def review(**kwargs):
        outcome = real(**kwargs)
        if str(kwargs["run_root"]).endswith("prior_review_attempt_1"):
            clock.advance(1_799.0)  # the retry ran long: one second of the window is left
        return outcome

    limits = {"candidate_limit": 200, "candidate_total_milliseconds": 60_000,
              "candidate_per_solve_milliseconds": 1_500, "selection_milliseconds": 10_000}
    code, report, root = _classic(tmp_path, monkeypatch, run_id="spent", window=1_800.0, clock=clock,
                                  review=review, policy=lambda attachments: _policy_file(attachments, limits=limits))
    assert code == 2
    _baseline_is_the_file(report, root)
    relaxation = report["relaxation"]
    assert [item["step"] for item in relaxation["relaxations"]] == ["BANK"]
    assert relaxation["stop"].startswith("RELAXATION_LADDER_STOPPED:after CANDIDATE_BANK_TIMEOUT at rung SUPPLIED")
    assert "rung 4 needs 2 s for 3 sequential solves" in relaxation["stop"]
    assert _truth_codes(report)["RELAXATION_LADDER_STOPPED"] == "S"
    assert report["blockers"][0].startswith("RELAXATION_BANK_RESIZED:")
    assert any(text.startswith("RELAXATION_LADDER_STOPPED:") for text in report["blockers"])
    assert [item["attempt"] for item in relaxation["attempts"]] == [0, 1]


def test_a_showdown_captain_cap_infeasibility_relaxes_and_exports(tmp_path, monkeypatch):
    """A 10% Captain cap over two entries floors to zero Captains for everyone.

    Rung 1 widens it to 25%, still zero of two, and is refused; rung 2 widens it
    to 50%, one each, and SD3 builds and exports the portfolio.
    """

    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    _clocked(monkeypatch, FakeClock())
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    attachments = _attachments(tmp_path, salary_path, entry_path)
    slate = parse_salaries(salary_path)
    entries = parse_entries(entry_path)
    policy_path = tmp_path / "policy" / "portfolio.json"
    policy_path.parent.mkdir()
    policy_path.write_text(json.dumps(portfolio_policy_template(
        slate, [entry.entry_id for entry in entries.authorizations],
        controls={"max_captain_exposure": {"default_fraction": 0.1, "overrides": []},
                  "max_pairwise_person_overlap": 4})), encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project))
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id="sd-captain", portfolio_policy_json=str(policy_path),
        prior_package_dir=str(package_dir)))
    report = json.loads((tmp_path / "outputs" / "sd-captain" / "cowork_run.json").read_text(encoding="utf-8"))
    assert code == 0 and report["stage"] == "PRIOR_ONLY_REVIEW_EXPORT"
    assert report["improvement"]["status"] == "DELIVERED" and report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    relaxation = report["relaxation"]
    assert relaxation["mode"] == "SHOWDOWN" and relaxation["final_rung"] == "2"
    refused = [item for item in relaxation["attempts"] if item["outcome"] == "REFUSED_AT_VALIDATION"]
    assert [item["rung"] for item in refused] == ["1"]
    assert "PORTFOLIO_POLICY_CAPTAIN_CAPACITY_INSUFFICIENT" in refused[0]["codes"]
    (captain,) = [item for item in relaxation["relaxations"] if item["constraint"] == "max_captain_exposure"]
    assert captain["original"]["default_fraction"] == "0.1" and captain["final"]["default_fraction"] == "0.5"
    assert captain["trigger"] == "PORTFOLIO_POLICY_CAPTAIN_CAPACITY_INSUFFICIENT"
    assert _truth_codes(report)["RELAXATION_STRUCTURE_RELAXED"] == "S"
    assert report["prior_review_hashes"]["portfolio_policy_normalized"] == (
        relaxation["final_policy"]["normalized_sha256"])
    rosters = _exported_rosters_showdown(report)
    assert len(rosters) == 2 and len(set(rosters)) == 2


def test_a_structural_failure_at_selection_takes_the_next_rung_exactly(tmp_path, monkeypatch):
    """A generator's rung-0 policy whose joint solve is infeasible runs next at rung 1.

    The first joint solve reports `MODELED_BANK_INFEASIBILITY`; the ladder loosens
    only what rung 1 loosens (the bring-back floor), re-sizes the bank to the
    window, and the second attempt exports through C3.
    """

    from nfl_dfs import selection

    real = selection.solve_classic_portfolio
    calls: list[str] = []

    def solve(policy, bank, **kwargs):
        result = real(policy, bank, **kwargs)
        calls.append(result.status)
        if len(calls) == 1:
            return replace(result, status="MODELED_BANK_INFEASIBILITY", selected_candidate_indexes=(),
                           infeasibility_scope="EXHAUSTIVE_MODELED_BANK" if bank.exhaustive else "BOUNDED_BANK")
        return result

    monkeypatch.setattr(selection, "solve_classic_portfolio", solve)

    def policy(attachments):
        slate = parse_salaries(attachments / "salary.csv")
        count = len(parse_entries(attachments / "entries.csv").authorizations)
        return _policy_file(attachments, controls=classic_rung_controls(slate, count, 0),
                            limits=classic_limits(count, len(slate.players), 0, minutes=1.0, window_seconds=60.0))

    # Two entries: no rung caps exposure (a cap needs three), so rung 1 differs
    # from rung 0 only in the bring-back floor. (At three entries this pool's
    # four wide receivers cannot cover nine WR slots under rung 0's cap of two,
    # and the policy would enter the ladder at intake instead.)
    code, report, root = _classic(tmp_path, monkeypatch, run_id="rung-one", policy=policy, entries=2)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    relaxation = report["relaxation"]
    assert relaxation["final_rung"] == "1"
    structural = [item for item in relaxation["relaxations"] if item["constraint"] != "search_limits"]
    assert [item["constraint"] for item in structural] == ["stack_rules.qb-bringback"]
    (bringback,) = structural
    assert bringback["step"] == "STRUCTURE" and bringback["rung_from"] == "SUPPLIED"
    assert (bringback["original"]["minimum_entries"], bringback["final"]["minimum_entries"]) == (2, 1)
    assert bringback["trigger"] == "MODELED_BANK_INFEASIBILITY" and bringback["trigger_origin"] == "SELECTION"
    assert all(item["constraint"] in {"stack_rules.qb-bringback", "search_limits"}
               for item in relaxation["relaxations"])
    assert [item["failure"] for item in relaxation["attempts"]] == ["MODELED_BANK_INFEASIBILITY", None]
    assert report["prior_review_hashes"]["portfolio_policy_normalized"] == (
        relaxation["final_policy"]["normalized_sha256"])
    rosters = _exported_rosters(report)
    assert len(rosters) == 2 and len(set(rosters)) == 2


def test_an_sd3_bank_that_ran_out_is_deepened_before_any_structure(tmp_path, monkeypatch):
    """DAL@NYG retro §6: the bank binds first, so the ladder deepens it before a rung."""

    from nfl_dfs import cli, selection
    from nfl_dfs import prior_review as prior_review_module

    _clocked(monkeypatch, FakeClock())
    real_solve = selection.solve_policy_portfolio
    banks: list[int] = []

    def solve(policy, bank, **kwargs):
        banks.append(bank.candidate_limit)
        result = real_solve(policy, bank, **kwargs)
        if len(banks) == 1:
            return replace(result, status="CANDIDATE_BANK_EXHAUSTED_INCOMPLETE", selected_candidate_indexes=())
        return result

    monkeypatch.setattr(selection, "solve_policy_portfolio", solve)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    attachments = _attachments(tmp_path, salary_path, entry_path)
    slate = parse_salaries(salary_path)
    entries = parse_entries(entry_path)
    policy_path = tmp_path / "policy" / "portfolio.json"
    policy_path.parent.mkdir()
    policy_path.write_text(json.dumps(portfolio_policy_template(
        slate, [entry.entry_id for entry in entries.authorizations],
        controls={"max_pairwise_person_overlap": 4})), encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project))
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id="sd-deeper", portfolio_policy_json=str(policy_path),
        prior_package_dir=str(package_dir)))
    report = json.loads((tmp_path / "outputs" / "sd-deeper" / "cowork_run.json").read_text(encoding="utf-8"))
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    (deeper,) = report["relaxation"]["relaxations"]
    assert (deeper["step"], deeper["constraint"], deeper["trigger"]) == (
        "BANK", "candidate_bank.candidate_limit", "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE")
    assert (deeper["original"], deeper["final"]) == (32, 48)
    assert banks == [32, 48]
    assert report["relaxation"]["final_rung"] == "SUPPLIED"
    assert report["relaxation"]["attempts"][-1]["showdown_candidate_limit"] == 48
    assert _truth_codes(report)["RELAXATION_BANK_RESIZED"] == "S"


def _exported_rosters_showdown(report) -> list[tuple[str, ...]]:
    path = Path(report["latest_deliverable"]["path"])
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    header = rows[0]
    start = header.index("Entry Fee") + 1
    return [tuple(row[start:start + 6]) for row in rows[1:] if row and row[0].strip().isdigit()
            and all(cell.strip() for cell in row[start:start + 6])]


# ----------------------------------------------------------------- the ladder itself


def _supplied():
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Classic.csv")
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    return slate, entries, tuple(item.entry_id for item in entries.authorizations)


def _normalized(document, slate, entry_ids, entries, external=()):
    raw = json.dumps(document).encode("utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash,
        externally_excluded_people=external)
    assert validation.policy is not None, validation.blockers()
    return validation


@pytest.mark.parametrize("rung", (0, 1, 2))
def test_a_generators_rung_k_policy_relaxes_to_rung_k_plus_1_exactly(rung):
    slate, entries, entry_ids = _supplied()
    count = len(entry_ids)
    limits = classic_limits(count, len(slate.players), rung, minutes=1.0)
    policy = _normalized(classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash, controls=classic_rung_controls(slate, count, rung),
        limits=limits), slate, entry_ids, entries).policy
    relaxed = _normalized(classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash, controls=classic_relaxed_controls(policy, rung + 1),
        limits=limits), slate, entry_ids, entries).policy
    table = _normalized(classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash, controls=classic_rung_controls(slate, count, rung + 1),
        limits=limits), slate, entry_ids, entries).policy
    assert relaxed.as_mapping()["controls"] == table.as_mapping()["controls"]
    # The rung the policy is already at changes nothing, so the ladder skips it.
    assert classic_relaxed_controls(policy, rung) == classic_relaxed_controls(policy, None)


def test_a_relaxation_never_tightens_and_keeps_every_exclusion():
    slate, entries, entry_ids = _supplied()
    count = len(entry_ids)
    people = sorted({row.underlying_id: row for row in slate.players}.values(), key=lambda row: row.underlying_id)
    excluded, zeroed, floored = people[0], people[1], people[2]
    controls = {
        "player_exposure_bounds": [
            {"underlying_id": zeroed.underlying_id, "dk_id": zeroed.dk_id, "minimum_entries": 0,
             "maximum_entries": 0, "hard": True},
            {"underlying_id": floored.underlying_id, "dk_id": floored.dk_id, "minimum_entries": 3,
             "maximum_entries": 4, "hard": True},
        ],
        "team_exposure_bounds": [{"team": slate.players[0].team, "minimum_entries": 0, "maximum_entries": 5,
                                  "hard": True}],
        "exact_exclusions": [{"underlying_id": excluded.underlying_id, "dk_id": excluded.dk_id}],
        "stack_rules": [{"rule_id": "stack", "rule_type": "QB_PASS_CATCHER", "minimum_value": 2,
                         "maximum_value": 3, "minimum_entries": count, "maximum_entries": count,
                         "strength": "HARD"}],
        "max_pairwise_person_overlap": 3,
        "require_unique_lineups": True,
    }
    external = (people[3].underlying_id,)
    policy = _normalized(classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash, controls=controls), slate, entry_ids, entries,
        external).policy
    for rung in range(4):
        relaxed = classic_relaxed_controls(policy, rung)
        assert relaxed["require_unique_lineups"] is True
        assert relaxed["exact_exclusions"] == [{"underlying_id": excluded.underlying_id, "dk_id": excluded.dk_id}]
        bounds = {item["underlying_id"]: item for item in relaxed["player_exposure_bounds"]}
        assert bounds[zeroed.underlying_id]["maximum_entries"] == 0  # a zero cap is an exclusion
        assert floored.underlying_id not in bounds or bounds[floored.underlying_id]["maximum_entries"] >= 4
        assert people[3].underlying_id not in bounds  # an outside exclusion is re-derived, not written
        assert relaxed["team_exposure_bounds"] == []
        (rule,) = relaxed["stack_rules"]
        assert rule["minimum_entries"] <= count and rule["minimum_value"] <= 2 and rule["maximum_value"] >= 3
        assert relaxed["max_pairwise_person_overlap"] >= 3
        again = _normalized(classic_portfolio_policy_template(
            slate, entry_ids, entry_sha256=entries.raw_hash, controls=relaxed), slate, entry_ids, entries,
            external).policy
        assert set(own_exclusion_dk_ids(again)) == {excluded.dk_id, zeroed.dk_id}


def test_the_showdown_ladder_widens_captains_first_and_never_touches_an_exclusion():
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    entry_ids = [item.entry_id for item in entries.authorizations]
    people = sorted({row.underlying_id: row for row in slate.players})
    bindings = {person.underlying_id: person for person in
                validate_portfolio_policy_bytes(canonical_decimal_json_bytes(portfolio_policy_template(
                    slate, entry_ids)), slate=slate, entry_ids=entry_ids).policy.people}
    kicker, out, benched = bindings[people[0]], bindings[people[1]], bindings[people[2]]
    controls = {
        "fraction_unit": "FRACTION_0_TO_1",
        "max_combined_person_exposure": {"default_fraction": Decimal("0.4"), "overrides": [
            {**benched.as_mapping(), "fraction": Decimal("0")}]},
        "max_captain_exposure": {"default_fraction": Decimal("0.1"), "overrides": [
            {**kicker.as_mapping(), "fraction": Decimal("0")}]},
        "excluded_people": [out.as_mapping()],
        "max_pairwise_person_overlap": 3,
        "require_unique_lineups": True,
    }
    policy = validate_portfolio_policy_bytes(canonical_decimal_json_bytes(portfolio_policy_template(
        slate, entry_ids, controls=controls)), slate=slate, entry_ids=entry_ids).policy
    one, two, three = (showdown_relaxed_controls(policy, rung) for rung in (1, 2, 3))
    assert one["max_captain_exposure"]["default_fraction"] == Decimal("0.25")
    assert one["max_captain_exposure"]["overrides"][0]["fraction"] == 0  # zeroed Captains wait for rung 2
    assert one["max_combined_person_exposure"] == showdown_relaxed_controls(policy, None)[
        "max_combined_person_exposure"]
    assert two["max_captain_exposure"]["overrides"][0]["fraction"] == Decimal("0.5")
    assert three["max_captain_exposure"] == {"default_fraction": None, "overrides": []}
    assert three["max_combined_person_exposure"]["default_fraction"] is None
    assert [item["fraction"] for item in three["max_combined_person_exposure"]["overrides"]] == [0]
    assert three["max_pairwise_person_overlap"] == 5
    for relaxed in (one, two, three):
        assert relaxed["excluded_people"] == [out.as_mapping()] and relaxed["require_unique_lineups"] is True
    assert set(own_exclusion_dk_ids(policy)) == {out.cpt_dk_id, out.flex_dk_id, benched.cpt_dk_id,
                                                 benched.flex_dk_id}
