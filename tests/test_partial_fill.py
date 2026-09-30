"""Session 39b: a fill that runs out of distinct lineups delivers the rows it built and names the rest.

R29: "within a given portfolio keep all submitted lineups distinct and unique." A subset policy binds
some rows and the fill (sequential Showdown, or Classic C1) writes the others. When the fill has no
distinct lineup left at row k, the review delivers the bound rows and the k filled ones, names every
unfilled Entry ID, leaves those rows blank in the file, and never repeats or cycles a lineup. A blank
row nobody named still fails every layer that reads the file.

The exhaustion in the end-to-end tests is forced by stopping the fill's sequential run at `ROWS`
built rows and recording the stop the way a real run records it; the real solver stop (an infeasible
model at row k) is proven in `tests/test_portfolio_policy.py`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nfl_dfs import selection
from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
    write_normalized_classic_portfolio_policy,
)
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.projection import build_projection_package

from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_entry_groups import _cells, _keys, _raw_lines


def _stop_the_fill_after(monkeypatch, rows: int, *, proved: bool = True) -> None:
    """Make the unbound fill's sequential run stop after `rows` lineups, as an exhausted pool does."""

    real = selection._sequential_lineups

    def clamped(*args, **kwargs):
        if kwargs.get("stage") != "UNBOUND_FILL":
            return real(*args, **kwargs)
        wanted = kwargs["count"]
        kwargs["count"] = min(wanted, rows)
        run = real(*args, **kwargs)
        if wanted > rows:
            run.stopped = {"index": kwargs["first_index"] + rows,
                           "status": "INFEASIBLE" if proved else "NO_SOLUTION", "proved_exhausted": proved}
        return run

    monkeypatch.setattr(selection, "_sequential_lineups", clamped)


def _classic_review(tmp_path: Path, *, entries: int = 4, bound: int = 2, controls=None):
    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=entries)
    slate = parse_salaries(salary)
    template = parse_entries(entry)
    fillable = plan_entries(template, slate).fillable
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(classic_portfolio_policy_template(
        slate, fillable[:bound], entry_sha256=template.raw_hash, controls=controls)), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(), slate=slate, entry_ids=fillable, entry_sha256=template.raw_hash)
    assert validation.valid, validation.blockers()
    normalized = write_normalized_classic_portfolio_policy(tmp_path / "policy.normalized.json", validation.policy)

    def run(label: str = "partial"):
        return run_prior_review(
            salary_csv=salary, entry_csv=entry, label=label, as_of=AS_OF,
            run_root=tmp_path / f"run-{label}", output_root=tmp_path / f"out-{label}", prior_package_dir=package,
            official_status_csv=status, offensive_role_evidence_json=role,
            portfolio_policy=validation.policy, portfolio_policy_source_path=policy_path,
            portfolio_policy_source_sha256=sha256_file(policy_path), portfolio_policy_normalized_path=normalized,
            portfolio_policy_normalized_sha256=sha256_file(normalized), project=build_projection_package,
        )

    return slate, entry, fillable, run


def test_a_classic_fill_that_runs_out_at_row_k_delivers_the_bound_rows_and_k_filled_ones(tmp_path, monkeypatch):
    _stop_the_fill_after(monkeypatch, 1)
    slate, entry, fillable, run = _classic_review(tmp_path, entries=4, bound=2)

    outcome = run()

    assert not outcome.blocked, outcome.blockers
    assert outcome.unfilled_entry_ids == (fillable[3],)
    selection_report = outcome.reports["selection"]
    assert selection_report["unfilled_entry_ids"] == [fillable[3]]
    assert selection_report["row_sources"] == {
        fillable[0]: "POLICY", fillable[1]: "POLICY", fillable[2]: "C1"}
    fill = selection_report["selection"]["unbound_fill"]
    assert (fill["requested"], fill["lineups"], fill["unfilled_rows"]) == (2, 1, 1)
    assert fill["stopped"]["proved_exhausted"] is True

    (export,) = list((tmp_path / "out-partial").rglob("DK_REVIEW_ENTRY_*.csv"))
    cells = _cells(export)
    delivered = [fillable[0], fillable[1], fillable[2]]
    assert all(validate_lineup(slate, cells[eid]).valid for eid in delivered)
    assert len(_keys(slate, [cells[eid] for eid in delivered])) == 3  # no repeat, none cycled
    assert not any(cells[fillable[3]])  # the unfilled row is blank
    assert _raw_lines(export)[fillable[3]] == _raw_lines(entry)[fillable[3]]  # and byte-identical to the template
    audit = outcome.reports["classic_export_audit"]
    assert audit["unfilled_entry_ids"] == [fillable[3]]
    assert audit["unbound_entry_ids"] == [fillable[2], fillable[3]]
    truths = outcome.export
    assert (truths["MODEL_STATUS"], truths["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")


def test_a_classic_fill_that_finds_no_lineup_delivers_the_bound_portfolio(tmp_path, monkeypatch):
    _stop_the_fill_after(monkeypatch, 0)
    slate, _entry, fillable, run = _classic_review(tmp_path, entries=4, bound=2)

    outcome = run()

    assert not outcome.blocked, outcome.blockers
    assert outcome.unfilled_entry_ids == (fillable[2], fillable[3])
    (export,) = list((tmp_path / "out-partial").rglob("DK_REVIEW_ENTRY_*.csv"))
    cells = _cells(export)
    assert all(validate_lineup(slate, cells[eid]).valid for eid in fillable[:2])
    assert not any(cells[fillable[2]]) and not any(cells[fillable[3]])


# ------------------------------------------------------ the whole run-slate path, both modes

def _retained_review(root: Path) -> Path:
    """The review CSV a run keeps on disk beside a pointer that still names the baseline."""

    (review,) = sorted(root.rglob("DK_REVIEW_ENTRY_*.csv"))
    return review


def test_a_showdown_subset_run_whose_fill_runs_out_names_the_unfilled_rows_and_reviews_the_rest(tmp_path, monkeypatch):
    from .test_entry_groups import SD3_CONTROLS, _run_showdown

    _stop_the_fill_after(monkeypatch, 1)
    rows = tuple(f"90000000{index}" for index in range(1, 6))
    code, report, entries, slate = _run_showdown(
        tmp_path, monkeypatch, run_id="sd-partial", entry_ids=rows, policy_controls=SD3_CONTROLS,
        bound=("900000003", "900000005"))

    review = _retained_review(tmp_path / "outputs" / "sd-partial")
    cells = _cells(review)
    filled = ("900000001", "900000003", "900000005")
    assert all(validate_lineup(slate, cells[eid]).valid for eid in filled)
    assert len(_keys(slate, [cells[eid] for eid in filled])) == 3  # nothing repeated, nothing cycled
    for blank in ("900000002", "900000004"):
        assert not any(cells[blank]) and _raw_lines(review)[blank] == _raw_lines(entries)[blank]
    selection_report = report["prior_review_reports"]["selection"]
    assert selection_report["unfilled_entry_ids"] == ["900000002", "900000004"]
    assert selection_report["row_sources"] == {
        "900000001": "SHOWDOWN_SEQUENTIAL", "900000003": "POLICY", "900000005": "POLICY"}
    assert report["export"]["unfilled_entry_ids"] == ["900000002", "900000004"]
    # Every layer passed: the only thing that kept the review off the pointer is that the baseline
    # holds more rows (the pointer never regresses coverage), and the truths still describe the baseline.
    assert [b for b in report["blockers"] if "READABLE" in b or "AUDIT" in b or "SELECTION" in b] == []
    assert report["improvement"]["withheld_by"].startswith("DELIVERY_POINTER_COVERAGE_REGRESSION")
    assert report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert report["release_truths"]["delivered_entry_ids"] == list(rows)
    assert (report["release_truths"]["MODEL_STATUS"], report["release_truths"]["RELEASE_DECISION"]) == (
        "PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert code == 2


def test_a_classic_subset_run_whose_fill_runs_out_names_the_unfilled_row_through_c3(tmp_path, monkeypatch):
    from .test_entry_groups import _classic_subset_run, _readable

    _stop_the_fill_after(monkeypatch, 1)
    code, report, entries, root, slate, prefilled = _classic_subset_run(tmp_path, monkeypatch, run_id="c3-partial")

    review = _retained_review(root)
    cells = _cells(review)
    filled = ("910000001", "910000003", "910000005")
    assert all(validate_lineup(slate, cells[eid]).valid for eid in filled)
    assert len(_keys(slate, [cells[eid] for eid in filled])) == 3
    assert not any(cells["910000004"]) and _raw_lines(review)["910000004"] == _raw_lines(entries)["910000004"]
    assert _raw_lines(review)["910000002"] == _raw_lines(entries)["910000002"]  # the prefilled row is untouched
    reports = report["prior_review_reports"]
    assert reports["selection"]["unfilled_entry_ids"] == ["910000004"]
    (audit_file,) = sorted(root.rglob("classic_review_export_audit.json"))
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    assert audit["unfilled_entry_ids"] == ["910000004"] and audit["passed"] is True
    assert set(audit["row_sources"]) == {"910000001", "910000003", "910000005"}  # the blank row has no source
    assert report["export"]["unfilled_entry_ids"] == ["910000004"]
    assert [b for b in report["blockers"] if "READABLE" in b or "C3" in b or "AUDIT" in b] == []
    assert report["improvement"]["withheld_by"].startswith("DELIVERY_POINTER_COVERAGE_REGRESSION")
    assert report["release_truths"]["delivered_entry_ids"] == [
        "910000001", "910000003", "910000004", "910000005"]  # the baseline's, which holds all four
    assert code == 2


# ------------------------------------- an unnamed blank row, or a fill row the review forbids, still fails

def _capture_c3(monkeypatch):
    from nfl_dfs import prior_review
    from nfl_dfs.classic_review import create_classic_review_package

    captured: dict[str, object] = {}

    def record(**kwargs):
        captured.update({key: dict(value) if isinstance(value, dict) else value for key, value in kwargs.items()})
        return create_classic_review_package(**kwargs)

    monkeypatch.setattr(prior_review, "create_classic_review_package", record)
    return captured


def _replay_c3(tmp_path, captured, name, selection_payload):
    from nfl_dfs.classic_review import ClassicReviewError, create_classic_review_package

    folder = tmp_path / name
    folder.mkdir()
    path = folder / Path(captured["artifacts"]["selection_report"]).name
    path.write_bytes((json.dumps(selection_payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
    artifacts = {**captured["artifacts"], "selection_report": str(path)}
    hashes = {**captured["expected_hashes"], "selection_report": sha256_file(path)}
    values = dict(captured, artifacts=artifacts, expected_hashes=hashes,
                  output_path=folder / "review" / "DK_REVIEW_ENTRY_mutated.csv", output_dir=folder / "review")
    with pytest.raises(ClassicReviewError) as caught:
        create_classic_review_package(**values)
    assert not list((folder / "review").glob("DK_REVIEW_ENTRY_*.csv"))
    return str(caught.value)


def test_c3_takes_a_named_unfilled_row_and_refuses_each_way_of_naming_it_wrong(tmp_path, monkeypatch):
    from .test_entry_groups import _classic_subset_run

    captured = _capture_c3(monkeypatch)
    _stop_the_fill_after(monkeypatch, 1)
    _code, _report, _entries, _root, _slate, _prefilled = _classic_subset_run(
        tmp_path / "run", monkeypatch, run_id="c3-names")
    selection_path = Path(captured["artifacts"]["selection_report"])
    original = json.loads(selection_path.read_text(encoding="utf-8"))
    assert original["unfilled_entry_ids"] == ["910000004"]
    assert set(original["assignments_by_entry_id"]) == {"910000001", "910000003", "910000005"}

    def changed(**edits):
        payload = json.loads(json.dumps(original))
        for key, value in edits.items():
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
        return payload

    unnamed = _replay_c3(tmp_path, captured, "unnamed", changed(unfilled_entry_ids=None))
    assert "CLASSIC_C3_UNBOUND_ROWS_MISMATCH" in unnamed  # a blank row nobody named
    bound = _replay_c3(tmp_path, captured, "bound", changed(unfilled_entry_ids=["910000004", "910000003"]))
    assert "CLASSIC_C3_UNBOUND_ROWS_MISMATCH" in bound  # a bound row cannot be unfilled
    stranger = _replay_c3(tmp_path, captured, "stranger", changed(unfilled_entry_ids=["910000004", "910000009"]))
    assert "CLASSIC_C3_UNBOUND_ROWS_MISMATCH" in stranger
    repeated = _replay_c3(tmp_path, captured, "repeated", changed(unfilled_entry_ids=["910000004", "910000004"]))
    assert "CLASSIC_C3_UNBOUND_ROWS_MISMATCH" in repeated
    present = changed(unfilled_entry_ids=["910000004", "910000001"])
    assert "CLASSIC_C3_UNBOUND_ROWS_MISMATCH" in _replay_c3(tmp_path, captured, "present", present)  # named but held


def test_c3_holds_a_fill_row_to_the_policys_exclusions_and_to_the_cap_the_selection_names(tmp_path, monkeypatch):
    from .test_entry_groups import _classic_subset_run

    _stop_the_fill_after(monkeypatch, 1)
    _code, plain, _entries, _root, slate, _prefilled = _classic_subset_run(
        tmp_path / "plain", monkeypatch, run_id="c3-plain")
    by_id = {player.dk_id: player for player in slate.players}
    fill_row = json.loads(Path(plain["prior_review_artifacts"]["selection_report"]).read_text(encoding="utf-8"))[
        "assignments_by_entry_id"]["910000001"]
    person = by_id[fill_row[0]]

    captured = _capture_c3(monkeypatch)
    _classic_subset_run(
        tmp_path / "excluded", monkeypatch, run_id="c3-excluded",
        controls={"exact_exclusions": [{"underlying_id": person.underlying_id, "dk_id": person.dk_id}]})
    selection_path = Path(captured["artifacts"]["selection_report"])
    original = json.loads(selection_path.read_text(encoding="utf-8"))
    assert person.dk_id not in original["assignments_by_entry_id"]["910000001"]  # the selector kept him out

    # A regression in the selector that let him back into a fill row is caught by the review alone.
    sneaked = json.loads(json.dumps(original))
    sneaked["assignments_by_entry_id"]["910000001"][0] = person.dk_id
    message = _replay_c3(tmp_path, captured, "sneaked", sneaked)
    assert f"CLASSIC_C3_EXACT_EXCLUSION_SELECTED:{person.underlying_id}:unbound_entry=910000001" in message

    # A cap of zero people cannot hold: the fill row shares people with the policy lineups.
    capped = json.loads(json.dumps(original))
    assert capped["unbound_fill"]["max_person_overlap"] is not None
    capped["unbound_fill"]["max_person_overlap"] = 0
    assert "CLASSIC_C3_PAIRWISE_OVERLAP_EXCEEDED" in _replay_c3(tmp_path, captured, "capped", capped)
    assert ":fill_cap=0" in _replay_c3(tmp_path, captured, "capped-again", capped)


def test_the_readable_review_takes_a_named_unfilled_row_and_refuses_an_unnamed_or_forbidden_one(tmp_path, monkeypatch):
    from nfl_dfs import cli
    from nfl_dfs.readable_review import ReadableReviewError, create_readable_review

    from .test_entry_groups import SD3_CONTROLS, _run_showdown

    captured: dict[str, object] = {}

    def record(**kwargs):
        captured.update(kwargs)
        return create_readable_review(**kwargs)

    monkeypatch.setattr(cli, "create_readable_review", record)
    _stop_the_fill_after(monkeypatch, 1)
    rows = tuple(f"90000000{index}" for index in range(1, 6))
    _run_showdown(tmp_path / "run", monkeypatch, run_id="sd-names", entry_ids=rows,
                  policy_controls=SD3_CONTROLS, bound=("900000003", "900000005"))
    assert captured
    original = json.loads(Path(captured["artifacts"]["selection_report"]).read_text(encoding="utf-8"))
    assert original["unfilled_entry_ids"] == ["900000002", "900000004"]

    def replay(name, *, selection=None, policy=None):
        artifacts = dict(captured["artifacts"])
        hashes = dict(captured["expected_hashes"])
        (tmp_path / name).mkdir()
        if selection is not None:
            path = tmp_path / name / "selection_report.json"
            path.write_text(json.dumps(selection), encoding="utf-8")
            artifacts["selection_report"] = str(path)
            hashes["selection_report"] = sha256_file(path)
        if policy is not None:
            path = tmp_path / name / "policy.normalized.json"
            path.write_bytes(policy)
            artifacts["portfolio_policy_normalized"] = str(path)
            hashes["portfolio_policy_normalized"] = sha256_file(path)
        values = dict(captured, artifacts=artifacts, expected_hashes=hashes, output_dir=tmp_path / name / "review")
        try:
            create_readable_review(**values)
        except ReadableReviewError as exc:
            return str(exc)
        return ""

    assert replay("clean") == ""  # the run's own review, replayed, still passes

    def edited(**edits):
        payload = json.loads(json.dumps(original))
        payload.update(edits)
        return payload

    unnamed = replay("unnamed", selection={k: v for k, v in original.items() if k != "unfilled_entry_ids"})
    # The artifact holds three rows and the row 900000002 is blank with no name: it fails twice over.
    assert "READABLE_REVIEW_ASSIGNMENT_ENTRY_ORDER_MISMATCH" in unnamed
    assert "READABLE_REVIEW_LINEUP_INVALID:entry=900000002" in unnamed
    assert replay("bound", selection=edited(unfilled_entry_ids=["900000002", "900000004", "900000003"]))
    assert replay("stranger", selection=edited(unfilled_entry_ids=["900000002", "900000004", "900000009"]))
    assert replay("repeat", selection=edited(unfilled_entry_ids=["900000002", "900000004", "900000004"]))
    shorter = json.loads(json.dumps(original))
    shorter["selection"]["unbound_fill"]["unfilled_rows"] = 1
    assert "READABLE_REVIEW_UNBOUND_FILL_REPORT_MISMATCH" in replay("count", selection=shorter)

    # The policy's own exclusion binds a fill row: mark the fill row's captain excluded in the policy.
    output = _cells(_retained_review(tmp_path / "run" / "outputs" / "sd-names"))
    policy = json.loads(Path(captured["artifacts"]["portfolio_policy_normalized"]).read_text(encoding="utf-8"))
    captain = output["900000001"][0]
    (row,) = [item for item in policy["effective"]["people"] if captain in (item["cpt_dk_id"], item["flex_dk_id"])]
    row["excluded"] = True
    message = replay("policy-excluded", policy=json.dumps(policy).encode())
    assert "READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON" in message and "excluded_by=the_policy" in message

    # A fraction of 0.3 over 3 bound rows floors to a maximum of 0 rows but does not remove the person:
    # the selector may use him in a fill row (`own_exclusion_dk_ids` reads the fraction), so the review must too.
    row["excluded"] = False
    row["combined_max_entries"], row["combined_fraction"] = 0, "0.3"
    assert "excluded_by=the_policy" not in replay("fraction", policy=json.dumps(policy).encode())
    row["combined_fraction"] = "0"
    row["combined_max_entries"] = 0
    assert "excluded_by=the_policy" in replay("zero-fraction", policy=json.dumps(policy).encode())


# ------------------------------------------------ release truths, export writer, determinism

def test_the_review_release_truths_deliver_the_rest_and_name_the_unfilled_rows(tmp_path):
    from types import SimpleNamespace

    from nfl_dfs import cli
    from nfl_dfs.contracts import (
        CertificationBasis,
        DeliveryState,
        ModelStatus,
        ReleaseEvidenceState,
    )
    from nfl_dfs.gate_registry import load_gate_registry
    from nfl_dfs.release import derive_release_policy

    salary, entry, *_ = classic_fixture(tmp_path / "fixture", entries=4)
    plan = plan_entries(parse_entries(entry), parse_salaries(salary))
    policy = derive_release_policy(
        file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN, model_status=ModelStatus.PRIOR_ONLY,
        certification_basis=CertificationBasis.MODEL_ASSISTED)
    truths = policy.truth_values()
    registry = load_gate_registry()

    def build(unfilled):
        outcome = SimpleNamespace(file_valid=True, artifacts={"bulk_entry_csv": "review.csv"},
                                  unfilled_entry_ids=tuple(unfilled))
        return cli._review_release_truths(
            outcome=outcome, truths=truths, plan=plan, blockers=(), extra=(), registry=registry)

    whole = build(())
    assert whole.delivery_state is DeliveryState.DELIVERABLE and whole.unfilled_entry_ids == ()
    partial = build((plan.fillable[3],))
    assert partial.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert partial.delivered_entry_ids == plan.fillable[:3] and partial.unfilled_entry_ids == (plan.fillable[3],)
    named = {item.code: item.entry_ids for item in partial.delivery_limitations}
    assert named["SOLVER_RETURNED_NO_LINEUP"] == (plan.fillable[3],)
    assert "UNFILLED_AUTHORIZED_ROWS" not in named  # the row is named by its reason, not by the fallback
    (item,) = [item for item in partial.delivery_limitations if item.code == "SOLVER_RETURNED_NO_LINEUP"]
    assert "no proof that none is left" in item.detail  # no stop record: the claim is not stronger than the facts
    proved = SimpleNamespace(file_valid=True, artifacts={"bulk_entry_csv": "review.csv"},
                             unfilled_entry_ids=(plan.fillable[3],), reports={"selection": {"selection": {
                                 "unbound_fill": {"stopped": {"status": "INFEASIBLE", "proved_exhausted": True}}}}})
    said = cli._review_release_truths(
        outcome=proved, truths=truths, plan=plan, blockers=(), extra=(), registry=registry)
    assert "proved no distinct lineup is left" in [
        item for item in said.delivery_limitations if item.code == "SOLVER_RETURNED_NO_LINEUP"][0].detail
    no_file = cli._review_release_truths(
        outcome=SimpleNamespace(file_valid=True, artifacts={}, unfilled_entry_ids=(plan.fillable[3],)),
        truths=truths, plan=plan, blockers=(), extra=(), registry=registry)
    assert no_file.delivered_entry_ids == ()  # no file, nothing delivered ...
    assert {item.code: item.entry_ids for item in no_file.delivery_limitations}["SOLVER_RETURNED_NO_LINEUP"] == (
        plan.fillable[3],)  # ... and the rows the fill could not build are still named
    nothing = build(plan.fillable[2:])
    assert nothing.delivered_entry_ids == plan.fillable[:2] and nothing.unfilled_entry_ids == plan.fillable[2:]
    dumped = partial.model_dump(mode="json", by_alias=True)
    assert (dumped["MODEL_STATUS"], dumped["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")


def test_the_showdown_export_writes_a_named_unfilled_row_blank_and_refuses_an_unnamed_one(tmp_path):
    from datetime import datetime, timedelta, timezone

    from nfl_dfs.review_export import export_review_entries

    from .test_prior_review_profile import _prepared_run
    from .test_prior_selection import _entries_bytes

    salary_path, entry_path, *_ = _prepared_run(tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    entry_path.write_bytes(_entries_bytes(("900000001", "900000002", "900000003")))
    slate = parse_salaries(salary_path)
    template = parse_entries(entry_path)
    rosters: list[tuple[str, ...]] = []
    for player in (row for row in slate.players if row.role == "CPT"):
        flex = [row.dk_id for row in slate.players if row.role == "FLEX" and row.underlying_id != player.underlying_id]
        for start in range(0, len(flex) - 4):
            roster = (player.dk_id, *flex[start:start + 5])
            if validate_lineup(slate, roster).valid:
                rosters.append(roster)
                break
        if len(rosters) == 2:
            break
    assert len(rosters) == 2
    assignments = {"900000001": rosters[0], "900000002": rosters[1]}

    def export(name, **kwargs):
        return export_review_entries(slate=slate, template=template, assignments=assignments,
                                     output_path=tmp_path / name / "DK_REVIEW_ENTRY_x.csv", **kwargs)

    named = export("named", unfilled_entry_ids=("900000003",))
    assert named.file_valid, named.problems
    assert named.unfilled_entry_ids == ("900000003",)
    assert named.as_report()["unfilled_entry_ids"] == ["900000003"]
    cells = _cells(Path(named.output_path))
    assert not any(cells["900000003"]) and cells["900000001"] == rosters[0]
    again = export("named-again", unfilled_entry_ids=("900000003",))
    assert again.output_sha256 == named.output_sha256  # deterministic: same bytes in, same bytes out

    unnamed = export("unnamed")
    assert not unnamed.file_valid and any(p.startswith("ENTRY_AUTHORIZATION_MISMATCH") for p in unnamed.problems)
    both = export("both", unfilled_entry_ids=("900000003", "900000002"))
    assert not both.file_valid and "assigned_and_unfilled=['900000002']" in " ".join(both.problems)
    stranger = export("stranger", unfilled_entry_ids=("900000003", "900000009"))
    assert not stranger.file_valid
    assert not list((tmp_path / "unnamed").rglob("*.csv")) and not list((tmp_path / "both").rglob("*.csv"))


def test_a_partial_classic_review_is_deterministic_byte_for_byte(tmp_path, monkeypatch):
    _stop_the_fill_after(monkeypatch, 1)
    _slate, _entry, _fillable, run = _classic_review(tmp_path, entries=4, bound=2)
    first, second = run("one"), run("two")
    assert first.unfilled_entry_ids == second.unfilled_entry_ids
    (csv_one,) = list((tmp_path / "out-one").rglob("DK_REVIEW_ENTRY_*.csv"))
    (csv_two,) = list((tmp_path / "out-two").rglob("DK_REVIEW_ENTRY_*.csv"))
    assert csv_one.read_bytes() == csv_two.read_bytes()
    assert first.hashes["selection_report"] == second.hashes["selection_report"]


# ------------------------------- a regression in the fill's exclusions is caught by the reviews alone

def _without_the_policys_exclusions(monkeypatch) -> None:
    """The regression Session 39's reviewer named: `_fill_exclusions` forgets the policy's own."""

    monkeypatch.setattr(selection, "_fill_exclusions",
                        lambda run_excluded, policy: tuple(sorted(map(str, run_excluded))))


def test_c3_catches_a_fill_that_forgets_the_policys_exclusions(tmp_path, monkeypatch):
    _stop_the_fill_after(monkeypatch, 1)
    slate, _entry, fillable, run = _classic_review(tmp_path / "plain", entries=4, bound=2)
    plain = run()
    picked = json.loads(Path(plain.artifacts["selection_report"]).read_text(encoding="utf-8"))[
        "assignments_by_entry_id"][fillable[2]]
    person = {row.dk_id: row for row in slate.players}[picked[0]]
    controls = {"exact_exclusions": [{"underlying_id": person.underlying_id, "dk_id": person.dk_id}]}

    _slate, _entry, _fillable, honest = _classic_review(tmp_path / "honest", entries=4, bound=2, controls=controls)
    ok = honest()
    assert not ok.blocked, ok.blockers
    held = json.loads(Path(ok.artifacts["selection_report"]).read_text(encoding="utf-8"))["assignments_by_entry_id"]
    assert all(person.dk_id not in roster for roster in held.values())

    _without_the_policys_exclusions(monkeypatch)
    _slate, _entry, _fillable, regressed = _classic_review(tmp_path / "regressed", entries=4, bound=2, controls=controls)
    outcome = regressed()
    assert outcome.blocked
    assert f"CLASSIC_C3_EXACT_EXCLUSION_SELECTED:{person.underlying_id}:unbound_entry={fillable[2]}" in " ".join(
        outcome.blockers)


def test_the_showdown_readable_review_catches_a_fill_that_forgets_the_policys_exclusions(tmp_path, monkeypatch):
    from nfl_dfs.portfolio_policy import salary_person_bindings

    from .test_entry_groups import SD3_CONTROLS, _run_showdown

    _stop_the_fill_after(monkeypatch, 1)
    rows = tuple(f"90000000{index}" for index in range(1, 6))
    _code, plain, _entries, slate = _run_showdown(
        tmp_path / "plain", monkeypatch, run_id="sd-plain", entry_ids=rows, policy_controls=SD3_CONTROLS,
        bound=("900000003", "900000005"))
    picked = _cells(_retained_review(tmp_path / "plain" / "outputs" / "sd-plain"))["900000001"][0]
    person = {row.dk_id: row for row in slate.players}[picked].underlying_id
    identity = next(item for item in salary_person_bindings(slate) if item.underlying_id == person)
    controls = {**SD3_CONTROLS, "excluded_people": [identity.as_mapping()]}

    _without_the_policys_exclusions(monkeypatch)
    _code, regressed, _entries, _slate = _run_showdown(
        tmp_path / "regressed", monkeypatch, run_id="sd-regressed", entry_ids=rows, policy_controls=controls,
        bound=("900000003", "900000005"))
    text = " ".join(regressed["blockers"]) + json.dumps(regressed["prior_review_stages"], default=str)
    assert f"READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON:entry=900000001:person={person}:excluded_by=the_policy" in text


def test_the_readable_reviews_unbound_section_refuses_an_empty_roster_nobody_named():
    from nfl_dfs.readable_review import _unbound_rows_section

    def section(unfilled, rosters):
        problems: list[str] = []
        payload = _unbound_rows_section(
            ("1", "2"), output_rosters=rosters, people_by_entry={}, by_id={},
            selection_payload={"unbound_fill": {"lineups": 2 - len(unfilled), "unfilled_rows": len(unfilled),
                                                "differentiation": {"max_person_overlap": 4}}},
            excluded_people=set(), official_statuses={}, problems=problems, unfilled=set(unfilled))
        return payload, problems

    _payload, unnamed = section((), {"1": ("a",), "2": ()})
    assert any("READABLE_REVIEW_LINEUP_INVALID" in problem and "entry=2" in problem for problem in unnamed)
    payload, named = section(("2",), {"1": ("a",), "2": ()})
    assert named == [] and payload["unfilled_entry_ids"] == ["2"]
    _payload, wrong_count = section(("2",), {"1": ("a",), "2": ()})
    assert wrong_count == []
    _payload, lie = section((), {"1": ("a",), "2": ("b",)})
    assert lie == []


def test_a_stop_that_proved_nothing_is_worded_as_such_and_a_missing_cap_record_is_refused(tmp_path, monkeypatch):
    _stop_the_fill_after(monkeypatch, 1, proved=False)
    _slate, _entry, fillable, run = _classic_review(tmp_path, entries=4, bound=2)
    outcome = run()
    assert not outcome.blocked, outcome.blockers
    note = outcome.reports["selection"]["assignment_summary"]["note"]
    assert "did not prove that none was left" in note and "proved no distinct lineup was left" not in note
    fill = outcome.reports["selection"]["selection"]["unbound_fill"]
    assert fill["stopped"] == {"index": 4, "status": "NO_SOLUTION", "proved_exhausted": False}


def test_c3_refuses_a_selection_record_that_names_no_fill_cap(tmp_path, monkeypatch):
    from .test_entry_groups import _classic_subset_run

    captured = _capture_c3(monkeypatch)
    _classic_subset_run(tmp_path / "run", monkeypatch, run_id="c3-nocap")
    original = json.loads(Path(captured["artifacts"]["selection_report"]).read_text(encoding="utf-8"))
    assert original["unbound_fill"]["max_person_overlap"] is not None
    stripped = {key: value for key, value in original.items() if key != "unbound_fill"}
    assert "the selection record names no unbound_fill" in _replay_c3(tmp_path, captured, "nocap", stripped)
