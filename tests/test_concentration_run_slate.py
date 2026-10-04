"""Session 56 (R35, review F-02): a Showdown `run-slate` that supplied no policy builds under the concentration defaults.

Acceptance, from the card: (1) 20 rows legal and distinct with no person above 12 and no Captain above 4, recomputed
from the delivered bytes; (2) explicit values win; (3) an infeasible small pool and (4) a short deadline deliver the
baseline and name the relaxed preference without touching an evidence gate; (5) the review's counterexample is bounded
(`tests/test_concentration_counterexample.py`). The engine's numbers are never read back from its own report here: the
delivered file is parsed independently.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

import pytest

from nfl_dfs import cli, delivery
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.portfolio_policy import portfolio_policy_template

from .test_deadline_controller import FakeClock, _clocked, _truth_codes
from .test_participation import _slate
from .test_prior_review_profile import AS_OF, _attachments, _cowork_args, _prepared_run
from .test_prior_selection import _entries_bytes

ENTRY_COUNT = 20
# Two small pools carved out of the shared synthetic pool by operator exclusions (which no rung ever relaxes).
# Session 60: "Sea Third RB" stands where "Sea Backup RB" did. Seattle's lead back is DraftKings `OUT` in the shared pool,
# so his backup now inherits the carries (7.1 became 19.2 prior points) and became the carve's one dominant score. In this
# ten-person pool, at the edge of what the caps can hold, that was enough to leave the capped bank unfillable inside its
# limits (about 10 s became 45 to 96 s and the ladder ended at the baseline), which is a property of a pool this small and
# not what this test pins. The third back keeps a Seattle running back in the pool without being the room's inheritor.
# Both tests that use the pool are otherwise unchanged. Other carves fail with or without the change (checked).
NINE = ("Starter QB", "Lead RB", "Alpha WR", "Starting TE", "Sea QB", "Sea Alpha WR", "Sea Third RB", "Seahawks",
        "Patriots")
TEN = NINE + ("NE Kicker",)
# What a run delivering an improvement, and a run left with the baseline, each report before this session and after it.
EVIDENCE_GAPS = {"OFFICIAL_STATUS_REQUIRED", "MODEL_INPUTS_REQUIRED", "SOURCE_LEDGER_REQUIRED"}
BASELINE_GAPS = {"OFFICIAL_STATUS_REQUIRED", "WEATHER_CAPTURE_REQUIRED", "MODEL_NOT_PROSPECTIVELY_VALIDATED"}


def _entry_ids(count: int) -> tuple[str, ...]:
    return tuple(str(900000001 + index) for index in range(count))


def _all_but(tmp_path: Path, keep) -> list[str]:
    """The DraftKings IDs of every row of every person outside `keep`, from the shared pool."""

    folder = tmp_path / "pool"
    folder.mkdir(parents=True, exist_ok=True)
    return [row.dk_id for row in _slate(folder).players if row.name not in keep]


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, run_id: str = "concentration", entries: int = ENTRY_COUNT,
         policy=None, before_review=None, **overrides):
    """A Showdown `run-slate` over `entries` template rows on the shared synthetic pre-lock sources.

    `policy` is a callable `(slate, entry_ids, folder) -> Path` that writes a supplied policy; none supplies none.
    `before_review` is called with the review's keyword arguments just before each attempt runs.
    """

    from nfl_dfs import prior_review as prior_review_module

    tmp_path.mkdir(parents=True, exist_ok=True)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    entry_path.write_bytes(_entries_bytes(_entry_ids(entries)))
    attachments = _attachments(tmp_path, salary_path, entry_path)
    slate = parse_salaries(salary_path)
    if policy is not None:
        overrides["portfolio_policy_json"] = str(policy(slate, _entry_ids(entries), tmp_path))
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review

    def review(**kwargs):
        if before_review is not None:
            before_review(kwargs)
        return real(**kwargs, project=project)

    monkeypatch.setattr(cli, "run_prior_review", review)
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id=run_id, prior_package_dir=str(package_dir), **overrides))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, root, slate


def _delivered_rosters(report) -> list[tuple[str, ...]]:
    """The roster cells of every filled row of the file the pointer names, read straight from its bytes."""

    path = Path(report["latest_deliverable"]["path"])
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    start = rows[0].index("Entry Fee") + 1
    return [tuple(row[start:start + 6]) for row in rows[1:]
            if row and row[0].strip().isdigit() and all(cell.strip() for cell in row[start:start + 6])]


def _people_by_row(slate, rosters) -> list[list[str]]:
    person = {row.dk_id: row.underlying_id for row in slate.players}
    return [[person[cell] for cell in roster] for roster in rosters]


def _counts(slate, rosters):
    people: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    for underlying in _people_by_row(slate, rosters):
        people.update(set(underlying))
        captains[underlying[0]] += 1
    return people, captains


def _worst_overlap(slate, rosters) -> int:
    rows = [set(row) for row in _people_by_row(slate, rosters)]
    return max((len(a & b) for a, b in combinations(rows, 2)), default=0)


def _codes(report) -> dict[str, str]:
    return _truth_codes(report)


def _is_baseline(report, root) -> None:
    latest = delivery.read_latest(root)
    assert latest is not None and latest.deliverable.producer == "run-slate:baseline"
    assert report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert report["DELIVERY_STATE"] == "DELIVERABLE" and report["improvement"]["status"] == "NOT_PRODUCED"


def _evidence_gates_untouched(report) -> None:
    """The run still names every evidence gap it named before this session, and never calls itself uploadable."""

    codes = _codes(report)
    gaps = EVIDENCE_GAPS if report["improvement"]["status"] == "DELIVERED" else BASELINE_GAPS
    assert gaps <= set(codes)
    assert {codes[gap] for gap in gaps} == {"P"}  # still truth-claim gaps: not relaxed, not cleared
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert "V" not in codes.values()


# --------------------------------------------------------------------------- #
# Acceptance 1
# --------------------------------------------------------------------------- #


def test_a_no_policy_showdown_run_delivers_20_legal_distinct_rows_within_the_default_caps(tmp_path, monkeypatch):
    code, report, root, slate = _run(tmp_path, monkeypatch)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_REVIEW_EXPORT" and report["improvement"]["status"] == "DELIVERED"
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    rosters = _delivered_rosters(report)
    assert len(rosters) == ENTRY_COUNT and len(set(rosters)) == ENTRY_COUNT
    keys = {(r[0], tuple(sorted(r[1:]))) for r in rosters}
    assert len(keys) == ENTRY_COUNT  # R29: the exact roster, Captain included
    for roster in rosters:
        assert validate_lineup(slate, roster).valid
    people, captains = _counts(slate, rosters)
    assert max(people.values()) <= 12 and max(captains.values()) <= 4  # 0.60 and 0.20 of 20 rows
    assert _worst_overlap(slate, rosters) <= 4

    block = report["concentration"]
    assert block["status"] == "AS_REQUESTED" and block["started_from"] == "DEFAULT" and block["steps_taken"] == []
    assert block["requested"] == {"person_fraction": "0.60", "captain_fraction": "0.20", "pairwise_person_overlap": 4}
    assert block["effective"] == {"person_fraction": "0.6", "captain_fraction": "0.2", "pairwise_person_overlap": 4}
    assert block["version"] == "showdown_concentration_defaults_v1" and block["defaults_sha256"]
    # The report's own delivered counts are a recount of the file, and they agree with this test's.
    delivered = block["delivered"]
    assert delivered["scope"] == "ALL_FILLED_ROWS_INCLUDING_PREFILLED"  # the caps bind the fillable rows; the file may hold more
    assert (delivered["rows"], delivered["distinct_lineups"]) == (ENTRY_COUNT, ENTRY_COUNT)
    assert (delivered["max_person_entries"], delivered["max_captain_entries"]) == (
        max(people.values()), max(captains.values()))
    assert "LINEUP_QUALITY" in block["does_not_establish"]

    # The independent audit read the delivered bytes against the same caps and passed.
    audit = report["prior_review_reports"]["portfolio_policy_audit"]
    assert audit["status"] == "PASS"
    # Its own recount, from the final roster IDs, agrees with this test's recount of the file's bytes.
    assert max(audit["combined_person_counts"].values()) == max(people.values()) <= 12
    assert max(audit["captain_counts"].values()) == max(captains.values()) <= 4
    # The policy was written, hash-bound and re-checked like any rung's, and no relaxation was needed.
    relaxation = report["relaxation"]
    assert relaxation["started_from"]["rung"] == "DEFAULT" and relaxation["relaxations"] == []
    assert relaxation["final_policy"]["normalized_sha256"] == report["prior_review_hashes"]["portfolio_policy_normalized"]
    assert Path(relaxation["final_policy"]["source_path"]).parent.name == "attempt_0_rung_DEFAULT"
    codes = _codes(report)
    assert not [c for c in codes if c.startswith("SHOWDOWN_CONCENTRATION_") or c.startswith("RELAXATION_")]
    _evidence_gates_untouched(report)


def test_the_same_run_without_the_default_breaches_both_caps(tmp_path, monkeypatch):
    """The control: what the sequential floor builds on this pool, and why the default exists."""

    monkeypatch.setattr(cli, "_begin_concentration_defaults",
                        lambda *args, **kwargs: (None, cli._ConcentrationRun()))
    code, report, root, slate = _run(tmp_path, monkeypatch)
    assert code == 0 and "concentration" not in report and "relaxation" not in report
    people, captains = _counts(slate, _delivered_rosters(report))
    assert max(people.values()) > 12 and max(captains.values()) > 4


# --------------------------------------------------------------------------- #
# Acceptance 2: an explicit value wins
# --------------------------------------------------------------------------- #


def _explicit_policy(slate, entry_ids, folder):
    path = folder / "explicit_policy.json"
    path.write_text(json.dumps(portfolio_policy_template(slate, entry_ids, controls={
        "max_combined_person_exposure": {"default_fraction": 0.9, "overrides": []},
        "max_captain_exposure": {"default_fraction": 0.5, "overrides": []},
        "max_pairwise_person_overlap": 5})), encoding="utf-8")
    return path


def test_a_supplied_policy_is_never_replaced_by_the_default(tmp_path, monkeypatch):
    code, report, root, slate = _run(tmp_path, monkeypatch, policy=_explicit_policy)
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    assert "concentration" not in report  # the defaults are for a run that supplied no policy
    relaxation = report["relaxation"]
    assert relaxation["started_from"]["rung"] == "SUPPLIED" and relaxation["relaxations"] == []
    rosters = _delivered_rosters(report)
    people, captains = _counts(slate, rosters)
    assert len(set(rosters)) == ENTRY_COUNT and max(people.values()) <= 18 and max(captains.values()) <= 10
    assert _worst_overlap(slate, rosters) <= 5
    assert not [c for c in _codes(report) if c.startswith("SHOWDOWN_CONCENTRATION_")]


def test_the_requests_own_overlap_is_the_defaults_overlap(tmp_path, monkeypatch):
    code, report, root, slate = _run(tmp_path, monkeypatch, max_person_overlap=5)
    assert code == 0 and report["concentration"]["effective"]["pairwise_person_overlap"] == 5
    assert report["concentration"]["requested"]["pairwise_person_overlap"] == 4  # the registered value, for the record
    rosters = _delivered_rosters(report)
    assert _worst_overlap(slate, rosters) <= 5
    people, captains = _counts(slate, rosters)
    assert max(people.values()) <= 12 and max(captains.values()) <= 4


# --------------------------------------------------------------------------- #
# Acceptance 3: a pool the requested caps cannot hold
# --------------------------------------------------------------------------- #


def test_a_pool_too_small_for_the_requested_caps_relaxes_by_name_and_still_delivers(tmp_path, monkeypatch):
    code, report, root, slate = _run(tmp_path, monkeypatch, exclude=_all_but(tmp_path, TEN))
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    rosters = _delivered_rosters(report)
    assert len(rosters) == ENTRY_COUNT and len(set(rosters)) == ENTRY_COUNT
    people, captains = _counts(slate, rosters)
    assert max(people.values()) <= 16 and max(captains.values()) <= 8  # 0.80 and 0.40 of 20 rows
    block = report["concentration"]
    assert block["status"] == "RELAXED" and block["steps_taken"] == ["CAPS_0_80_0_40"]
    assert block["effective"]["person_fraction"] == "0.8" and block["effective"]["captain_fraction"] == "0.4"
    assert block["delivered"]["max_person_entries"] == max(people.values())
    codes = _codes(report)
    assert codes["SHOWDOWN_CONCENTRATION_RELAXED"] == "S"
    (record,) = [r for r in report["relaxation"]["relaxations"] if r["limitation_code"] == "SHOWDOWN_CONCENTRATION_RELAXED"]
    assert record["original"] == {"person_fraction": "0.6", "captain_fraction": "0.2"}
    assert record["final"] == {"person_fraction": "0.8", "captain_fraction": "0.4"}
    assert record["trigger_origin"] == "SELECTION"
    _evidence_gates_untouched(report)


def test_a_pool_nothing_can_fill_ships_the_baseline_and_names_every_step(tmp_path, monkeypatch):
    code, report, root, slate = _run(tmp_path, monkeypatch, exclude=_all_but(tmp_path, NINE))
    assert code == 2
    _is_baseline(report, root)
    block = report["concentration"]
    assert block["status"] == "NOT_APPLIED" and block["effective"] is None
    assert block["steps_taken"] == ["CAPS_0_80_0_40", "4"] and block["final_rung"] == "4"
    assert any("SOLVER_RETURNED_NO_LINEUP" in reason for reason in block["reasons"])
    codes = _codes(report)
    assert codes["SHOWDOWN_CONCENTRATION_RELAXED"] == "S" and codes["RELAXATION_POLICY_DROPPED"] == "S"
    assert codes["IMPROVEMENT_NOT_DELIVERED"] == "P"
    # The baseline's own concentration is reported from its bytes, never assumed.
    rosters = _delivered_rosters(report)
    people, captains = _counts(slate, rosters)
    assert len(rosters) == len(set(rosters))  # R29: nothing repeated to fill a row
    assert block["delivered"]["max_person_entries"] == max(people.values())
    assert block["delivered"]["max_captain_entries"] == max(captains.values())
    # Operator exclusions were never relaxed: no excluded person is in the file.
    gone = set(_all_but(tmp_path, NINE))
    assert not gone & {cell for roster in rosters for cell in roster}
    _evidence_gates_untouched(report)


# --------------------------------------------------------------------------- #
# Acceptance 4: a short deadline
# --------------------------------------------------------------------------- #


def _windowed(tmp_path, monkeypatch, *, run_id: str, window: float):
    """The run with `window` seconds before the improvement stops, on a clock only the test moves."""

    _clocked(monkeypatch, FakeClock())
    deadline = AS_OF + timedelta(minutes=5, seconds=window)
    return _run(tmp_path, monkeypatch, run_id=run_id, as_of=AS_OF.isoformat(), delivery_deadline_utc=deadline.isoformat())


def test_a_window_that_cannot_hold_the_capped_search_starts_at_rung_4_and_still_improves(tmp_path, monkeypatch):
    """40 s holds rung 4's 21 half-second solves but not 60 s of declared bank and joint solve plus them.

    The regression this guards: a capped joint solve that used the window up and left the baseline as the file where
    the sequential floor would have delivered.
    """

    code, report, root, slate = _windowed(tmp_path, monkeypatch, run_id="tight", window=40.0)
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    rosters = _delivered_rosters(report)
    assert len(rosters) == ENTRY_COUNT and len(set(rosters)) == ENTRY_COUNT
    block = report["concentration"]
    assert block["status"] == "RELAXED" and block["final_rung"] == "4" and block["effective"] is None
    codes = _codes(report)
    assert codes["SHOWDOWN_CONCENTRATION_RELAXED"] == "S" and codes["RELAXATION_POLICY_DROPPED"] == "S"
    for record in report["relaxation"]["relaxations"]:
        assert record["trigger"] == "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW" and record["trigger_origin"] == "DEADLINE"
    people, captains = _counts(slate, rosters)  # the floor has no person cap: the file's own numbers are named
    assert block["delivered"]["max_person_entries"] == max(people.values())
    _evidence_gates_untouched(report)


def test_a_window_that_cannot_hold_rung_4_ships_the_baseline_and_names_the_lost_preference(tmp_path, monkeypatch):
    code, report, root, slate = _windowed(tmp_path, monkeypatch, run_id="short", window=8.0)
    assert code == 2
    _is_baseline(report, root)
    block = report["concentration"]
    assert block["status"] == "NOT_APPLIED" and block["effective"] is None and block["final_rung"] == "DEFAULT"
    codes = _codes(report)
    assert codes["SHOWDOWN_CONCENTRATION_NOT_APPLIED"] == "S" and codes["RELAXATION_LADDER_STOPPED"] == "S"
    assert codes["DEADLINE_IMPROVEMENT_WINDOW_SPENT"] == "S"
    assert any(b.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:") for b in report["blockers"])
    rosters = _delivered_rosters(report)
    people, _captains = _counts(slate, rosters)
    assert block["delivered"]["max_person_entries"] == max(people.values())  # the baseline's own, from its bytes
    _evidence_gates_untouched(report)


def test_a_deadline_already_passed_ships_the_baseline_and_names_the_lost_preference(tmp_path, monkeypatch):
    code, report, root, slate = _windowed(tmp_path, monkeypatch, run_id="passed", window=-60.0)
    assert code == 2
    _is_baseline(report, root)
    assert report["stage"] == "DEADLINE_IMPROVEMENT_SKIPPED"
    assert report["concentration"]["status"] == "NOT_APPLIED"
    codes = _codes(report)
    assert codes["SHOWDOWN_CONCENTRATION_NOT_APPLIED"] == "S"
    (text,) = [b for b in report["blockers"] if b.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:")]
    assert "the delivery deadline left the run's own review no time" in text
    _evidence_gates_untouched(report)


def test_a_roomy_window_takes_the_capped_search(tmp_path, monkeypatch):
    code, report, root, slate = _windowed(tmp_path, monkeypatch, run_id="roomy", window=3600.0)
    assert code == 0 and report["concentration"]["status"] == "AS_REQUESTED"


# --------------------------------------------------------------------------- #
# The default never adds a stop
# --------------------------------------------------------------------------- #


def test_too_few_entries_leave_the_run_exactly_as_it_was(tmp_path, monkeypatch):
    """Under five entries a 0.20 Captain default floors to no Captain slot at all: reported, not applied, no limitation."""

    code, report, root, slate = _run(tmp_path, monkeypatch, entries=4)
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    block = report["concentration"]
    assert block["status"] == "NOT_APPLICABLE" and block["effective"] is None and block["steps_taken"] == []
    assert "4 fillable entries is fewer than the 5" in block["reasons"][0]
    assert "relaxation" not in report  # no ladder was built: the run is the sequential path it always was
    assert not [c for c in _codes(report) if c.startswith("SHOWDOWN_CONCENTRATION_") or c.startswith("RELAXATION_")]


def _intake(tmp_path, monkeypatch, **request_values):
    """`_begin_concentration_defaults` on the shared pool and a 20-row template, with a hand-built request."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    salary_path, entry_path, _package, _project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    entry_path.write_bytes(_entries_bytes(_entry_ids(ENTRY_COUNT)))
    slate, entries = parse_salaries(salary_path), parse_entries(entry_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    request = SimpleNamespace(**{"lineup_count": None, "max_person_overlap": 4, "official_status_csv": None,
                                 "exclude_dk_ids": (), "unavailable_statuses": (), "available_statuses": (),
                                 **request_values})
    return cli._begin_concentration_defaults(
        request, slate=slate, entries=entries, entry_plan=plan_entries(entries, slate), run_id="intake", budget=None)


def test_a_lineup_count_the_policy_cannot_bind_is_named_not_applied_and_never_a_stop(tmp_path, monkeypatch):
    ladder, run = _intake(tmp_path, monkeypatch, lineup_count=7)
    assert ladder is None and run.applies and run.not_applicable is None
    (text,) = run.texts()
    assert text.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:") and "lineup_count=7" in text


def test_an_exclusion_input_with_a_problem_of_its_own_leaves_the_default_off_and_names_it(tmp_path, monkeypatch):
    ladder, run = _intake(tmp_path, monkeypatch, exclude_dk_ids=("99999999",))
    assert ladder is None and run.applies
    (text,) = run.texts()
    assert text.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:")
    assert "PORTFOLIO_POLICY_EXTERNAL_EXCLUSION_DK_ID_UNKNOWN" in text  # the problem keeps its own blocker elsewhere


def test_an_unreadable_defaults_file_is_named_not_applied_and_never_a_stop(tmp_path, monkeypatch):
    from nfl_dfs.concentration import ConcentrationDefaultsError

    def unreadable():
        raise ConcentrationDefaultsError("concentration defaults unreadable: gone")

    monkeypatch.setattr(cli, "load_concentration_defaults", unreadable)
    ladder, run = _intake(tmp_path / "run", monkeypatch)
    assert ladder is None and run.applies and run.defaults is None
    (text,) = run.texts()
    assert text.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:") and "could not be read" in text


def test_the_default_policy_is_written_hash_bound_and_binds_every_fillable_row(tmp_path, monkeypatch):
    ladder, run = _intake(tmp_path, monkeypatch)
    assert ladder is not None and run.not_applicable is None and not run.unapplied and run.texts() == []
    rung = ladder.current
    assert rung.label == "DEFAULT" and rung.engine_default and rung.policy.entry_ids == _entry_ids(ENTRY_COUNT)
    source = Path(rung.source_path)
    assert source.read_bytes() and Path(rung.normalized_path).is_file()
    assert (tmp_path / "runs" / "intake" / "relaxation" / "attempt_0_rung_DEFAULT" / "portfolio_policy.json") == source


def test_the_same_inputs_write_byte_identical_default_policies(tmp_path, monkeypatch):
    written = []
    for name in ("first", "second"):
        ladder, _run_record = _intake(tmp_path / name, monkeypatch)
        rung = ladder.current
        written.append((Path(rung.source_path).read_bytes(), Path(rung.normalized_path).read_bytes(),
                        rung.source_sha256, rung.normalized_sha256))
    assert written[0] == written[1]


def test_a_default_policy_changed_after_it_is_written_is_refused_before_selection(tmp_path, monkeypatch):
    """The review re-checks the engine's own policy bytes as it does a supplied one's: nothing is selected on a moved byte."""

    def tamper(kwargs):
        source = Path(kwargs["portfolio_policy_source_path"])
        source.write_bytes(source.read_bytes() + b" ")  # one byte after the ladder hashed it

    code, report, root, slate = _run(tmp_path, monkeypatch, run_id="moved", before_review=tamper)
    assert code == 2
    _is_baseline(report, root)
    assert any("PORTFOLIO_POLICY_SOURCE_CHANGED_BEFORE_SELECTION" in text for text in report["blockers"])
    assert not list((root / "review").glob("DK_REVIEW_ENTRY_*.csv"))
    assert report["concentration"]["status"] == "NOT_APPLIED"
    _evidence_gates_untouched(report)


def test_the_independent_audit_refuses_a_default_portfolio_that_breaks_the_caps(tmp_path, monkeypatch):
    """The caps are recomputed from the final rosters, not trusted from the solve: hand the audit the bank's twenty
    most alike candidates in place of the joint solve's choice and it refuses, so no file is exported."""

    from dataclasses import replace

    from nfl_dfs import selection

    real = selection.solve_policy_portfolio

    def alike(policy, bank, **kwargs):
        solved = real(policy, bank, **kwargs)
        return replace(solved, selected_candidate_indexes=tuple(range(len(solved.selected_candidate_indexes))))

    monkeypatch.setattr(selection, "solve_policy_portfolio", alike)
    code, report, root, slate = _run(tmp_path, monkeypatch, run_id="overcap")
    assert code == 2
    _is_baseline(report, root)
    joined = ";".join(report["blockers"])
    assert "PORTFOLIO_POLICY_INDEPENDENT_AUDIT_FAILED" in joined
    for code_name in ("PORTFOLIO_AUDIT_COMBINED_PERSON_CAP_EXCEEDED", "PORTFOLIO_AUDIT_CAPTAIN_CAP_EXCEEDED",
                      "PORTFOLIO_AUDIT_PAIRWISE_OVERLAP_EXCEEDED"):
        assert code_name in joined, code_name  # each control the default declares is recomputed and refused on its own
    assert not list((root / "review").glob("DK_REVIEW_ENTRY_*.csv"))
    _evidence_gates_untouched(report)


def test_an_unexpected_failure_building_the_default_never_costs_the_run_its_review(tmp_path, monkeypatch):
    from nfl_dfs import relaxation

    def broken(self, **kwargs):
        raise KeyError("an unforeseen failure")

    monkeypatch.setattr(relaxation.Ladder, "begin_with_defaults", broken)
    code, report, root, slate = _run(tmp_path, monkeypatch, run_id="unforeseen")
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"  # the sequential path, as before this session
    block = report["concentration"]
    assert block["status"] == "NOT_APPLIED" and any("KeyError" in reason for reason in block["reasons"])
    assert _codes(report)["SHOWDOWN_CONCENTRATION_NOT_APPLIED"] == "S"
    _evidence_gates_untouched(report)


def test_an_unexpected_failure_reading_the_exclusion_inputs_is_named_not_applied(tmp_path, monkeypatch):
    def broken(request, slate):
        raise RuntimeError("an unforeseen failure")

    monkeypatch.setattr(cli, "_policy_exclusion_inputs", broken)
    ladder, run = _intake(tmp_path, monkeypatch)
    assert ladder is None and run.applies
    (text,) = run.texts()
    assert text.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:") and "RuntimeError" in text


def test_a_report_that_cannot_be_built_never_costs_the_run_its_result(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("an unforeseen failure")

    monkeypatch.setattr(cli, "_concentration_report_body", broken)
    code, report, root, slate = _run(tmp_path, monkeypatch, run_id="noreport")
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    assert report["concentration"]["status"] == "REPORT_UNAVAILABLE" and "ValueError" in report["concentration"]["problem"]


def test_an_unexpected_failure_in_the_defaults_ladder_ends_it_by_name_and_never_costs_the_run(tmp_path, monkeypatch):
    """Nine people cannot hold 20 rows, so the review fails and asks the ladder for a step, which then fails unforeseen:
    the ladder ends by name and the run ships its baseline instead of leaving through the outer failure exit."""

    from nfl_dfs import relaxation

    def broken(self, failure, *, overhead_seconds=0.0):
        raise KeyError("an unforeseen failure")

    monkeypatch.setattr(relaxation.Ladder, "next", broken)
    code, report, root, slate = _run(tmp_path, monkeypatch, run_id="halted", exclude=_all_but(tmp_path, NINE))
    assert code == 2 and report["stage"] == "PRIOR_REVIEW_SELECT_BLOCKED"  # not the outer handler's failure exit
    _is_baseline(report, root)
    stop = report["relaxation"]["stop"]
    assert stop.startswith("RELAXATION_RUNG_UNBUILDABLE:") and "KeyError" in stop
    texts = [b for b in report["blockers"] if b.startswith("SHOWDOWN_CONCENTRATION_NOT_APPLIED:")]
    assert texts and "RELAXATION_RUNG_UNBUILDABLE" in texts[0] and "window" not in texts[0].split("stopped", 1)[0]
    _evidence_gates_untouched(report)
