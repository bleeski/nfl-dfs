"""Session 11: entry groups. Per-row authority replaces the whole-file prefilled refusal.

The acceptance, through `run-slate` where it can be:

- a template with prefilled rows ships: every prefilled row is the input's bytes,
  every blank row is filled, and `DELIVERY_STATE` and coverage say so;
- no generated lineup repeats a prefilled one, in the baseline, C1 and C2, and
  the SD3 bank never holds one;
- a partly filled row and an unparseable prefilled row are preserved and named,
  and the rest of the file ships;
- a two-contest template reports each group's coverage, and a problem scoped to
  one group leaves the other group's rows delivered;
- a pointer replacement that drops coverage in one group is refused, even when
  its total is higher;
- writing into a prefilled cell is still refused, `V`.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from nfl_dfs import baseline, delivery
from nfl_dfs.classic_portfolio_policy import classic_portfolio_policy_template
from nfl_dfs.contracts import (
    CertificationBasis,
    DeliveryState,
    GateClass,
    ModelStatus,
    ReleaseEvidenceState,
)
from nfl_dfs.dk import parse_entries, parse_salaries, reconcile_template
from nfl_dfs.entry_groups import group_report, plan_entries, prefilled_cell_id
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_file
from nfl_dfs.lineups import (
    LineupValidationError,
    roster_canonical_key,
    validate_lineup,
    write_upload_bytes,
)
from nfl_dfs.referee import audit_output_bytes
from nfl_dfs.release import (
    DeliveryStateError,
    derive_delivery_state,
    derive_release_policy,
    release_truths_v3,
)

from .test_baseline import CLASSIC_ENTRIES_20, CLASSIC_SALARY, tiny_classic, tiny_classic_template
from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_deadline_controller import FakeClock, _clocked
from .test_prior_review_profile import _attachments, _cowork_args

C1 = "run-slate:prior_review:CLASSIC_C1"
C2 = "run-slate:prior_review:CLASSIC"
BASELINE = "run-slate:baseline"


# ----------------------------------------------------------------- helpers


def _rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def _edit(path: Path, *, cells: dict[str, list[str]] | None = None,
          columns: dict[str, dict[int, str]] | None = None) -> Path:
    """Rewrite an entries file: roster cells by Entry ID, and any other column by index."""

    raw = path.read_bytes().decode("utf-8")
    ending = "\r\n" if "\r\n" in raw else "\n"
    rows = _rows(path)
    header = rows[0]
    start = header.index("Entry Fee") + 1
    width = 9 if header[start] == "QB" else 6
    for row in rows[1:]:
        if not row:
            continue
        if cells and row[0] in cells:
            row[start:start + width] = cells[row[0]]
        for index, value in ((columns or {}).get(row[0]) or {}).items():
            row[index] = value
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator=ending).writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    return path


def _raw_lines(path: Path) -> dict[str, bytes]:
    """Each entry row's raw bytes, line ending included, by Entry ID."""

    lines = path.read_bytes().splitlines(keepends=True)
    return {line.split(b",", 1)[0].decode(): line for line in lines[1:]
            if line.split(b",", 1)[0].strip().isdigit()}


def _cells(path: Path) -> dict[str, tuple[str, ...]]:
    return {entry.entry_id: entry.existing_cells for entry in parse_entries(path).authorizations}


def _keys(slate, rosters) -> set[str]:
    return {roster_canonical_key(slate, roster) for roster in rosters}


def _codes(report) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for item in report["release_truths"]["delivery_limitations"]:
        found.setdefault(item["code"], []).extend(item["entry_ids"])
    return found


def _salary_top(slate, count: int) -> list[tuple[str, ...]]:
    built = baseline.build_distinct_lineups(
        slate, count=count, excluded_ids=(), per_solve_seconds=5.0, deadline=1e12, clock=lambda: 0.0)
    return [lineup.roster for lineup in built.lineups]


def _named(slate, roster) -> list[str]:
    by_id = {player.dk_id: player for player in slate.players}
    return [f"{by_id[dk_id].name} ({dk_id})" for dk_id in roster]


def _run_slate(tmp_path, monkeypatch, *, run_id, entries, edit=None, policy=None):
    """`run-slate` on the synthetic Classic fixture, its entries edited first.

    `policy(attachments, plan)` writes a Classic policy and returns its path; the
    run then goes to C2/C3, otherwise to C1.
    """

    from nfl_dfs import cli

    _clocked(monkeypatch, FakeClock())
    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=entries)
    if edit is not None:
        edit(entry, parse_salaries(salary))
    attachments = _attachments(tmp_path, salary, entry)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    values = dict(
        label=run_id, run_id=run_id, prior_package_dir=str(package), official_status_csv=str(status),
        offensive_role_evidence_json=str(role), as_of=AS_OF.isoformat(),
        delivery_deadline_utc=(AS_OF + timedelta(minutes=6)).isoformat())
    if policy is not None:
        slate = parse_salaries(attachments / "salary.csv")
        template = parse_entries(attachments / "entries.csv")
        values["portfolio_policy_json"] = str(policy(attachments, plan_entries(template, slate)))
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, **values))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, attachments / "entries.csv", root


def _policy(attachments: Path, plan) -> Path:
    slate = parse_salaries(attachments / "salary.csv")
    template = parse_entries(attachments / "entries.csv")
    path = attachments.parent / "classic_policy.json"
    path.write_text(json.dumps(classic_portfolio_policy_template(
        slate, plan.fillable, entry_sha256=template.raw_hash)), encoding="utf-8")
    return path


# ----------------------------------------------------------------- the plan


def test_a_prefilled_cell_is_a_bare_id_or_ends_in_its_id_and_nothing_else():
    assert prefilled_cell_id(" 39971296 ") == "39971296"
    assert prefilled_cell_id("Josh Allen (39971296)") == "39971296"
    assert prefilled_cell_id("Josh Allen") is None
    assert prefilled_cell_id("39971296 (Josh Allen)") is None
    assert prefilled_cell_id("") is None


def test_the_plan_classifies_every_row_and_seeds_only_exact_current_slate_rosters(tmp_path):
    slate = parse_salaries(tiny_classic(tmp_path))
    first, second = _salary_top(slate, 2)
    template_path = _edit(tiny_classic_template(tmp_path, 6), cells={
        "5300000002": list(first),                                   # bare IDs
        "5300000003": _named(slate, second),                         # 'Name (ID)'
        "5300000004": [first[0], *[""] * 8],                         # partly filled
        "5300000005": ["Somebody", *second[1:]],                     # a name, no ID
        "5300000006": ["99999999", *second[1:]],                     # not in this slate
    })
    template = parse_entries(template_path)
    reconcile_template(template, slate)
    plan = plan_entries(template, slate)

    assert plan.fillable == ("5300000001",)
    assert plan.preserved == ("5300000002", "5300000003")
    assert plan.unresolved == ("5300000004", "5300000005", "5300000006")
    assert plan.kinds["5300000004"] == "PARTLY_FILLED"
    findings = {code: ids for code, ids, _detail in plan.findings}
    assert findings == {"ENTRY_ROW_PARTLY_PREFILLED": ("5300000004",),
                        "ENTRY_PREFILLED_ROSTER_UNRESOLVED": ("5300000005", "5300000006")}
    assert plan.forbidden_keys == _keys(slate, [first, second])
    classes = {item.code: item.gate_class for item in plan.limitations(load_gate_registry())}
    assert classes == {"ENTRY_ROW_PARTLY_PREFILLED": GateClass.P,
                       "ENTRY_PREFILLED_ROSTER_UNRESOLVED": GateClass.P}


def test_a_prefilled_roster_that_repeats_an_earlier_one_is_named_and_still_forbidden(tmp_path):
    slate = parse_salaries(tiny_classic(tmp_path))
    (first,) = _salary_top(slate, 1)
    template = parse_entries(_edit(tiny_classic_template(tmp_path, 3), cells={
        "5300000001": list(first), "5300000002": _named(slate, first)}))
    plan = plan_entries(template, slate)
    assert plan.preserved == ("5300000001",) and plan.unresolved == ("5300000002",)
    assert "repeats the prefilled roster of Entry 5300000001" in plan.findings[0][2]
    assert plan.forbidden_keys == _keys(slate, [first])


# ----------------------------------------------------------------- the writer and the truths


def test_writing_into_a_prefilled_cell_is_still_refused_v(tmp_path):
    slate = parse_salaries(tiny_classic(tmp_path))
    first, second = _salary_top(slate, 2)
    path = _edit(tiny_classic_template(tmp_path, 2), cells={"5300000002": list(first)})
    template = parse_entries(path)

    with pytest.raises(LineupValidationError, match="^ENTRY_BLANK_CELL_AUTHORITY_REQUIRED"):
        write_upload_bytes(template, {"5300000001": second, "5300000002": second})
    with pytest.raises(LineupValidationError, match="^ENTRY_BLANK_CELL_AUTHORITY_REQUIRED"):
        write_upload_bytes(template, {"5300000001": second}, unfilled=("5300000002",))
    assert load_gate_registry().family_of("ENTRY_BLANK_CELL_AUTHORITY_REQUIRED").gate_class is GateClass.V

    written = write_upload_bytes(template, {"5300000001": second})
    assert _raw_lines(path)["5300000002"] in written.splitlines(keepends=True)
    forged = written.replace(b",".join(c.encode() for c in first), b",".join(c.encode() for c in second))
    audit = audit_output_bytes(path, forged, template, {"5300000001": second, "5300000002": second})
    assert not audit.valid and any("a prefilled roster cell was written" in p for p in audit.problems)


def test_a_preserved_row_is_neither_delivered_nor_unfilled_and_an_unresolved_one_is_partial():
    registry = load_gate_registry()
    partly = registry.limitation("ENTRY_ROW_PARTLY_PREFILLED", entry_ids=("3",))
    truth = derive_delivery_state(file_valid=True, authorized_entry_ids=("1", "2"),
                                  delivered_entry_ids=("1", "2"), preserved_entry_ids=("4",))
    assert truth.delivery_state is DeliveryState.DELIVERABLE and truth.preserved_entry_ids == ("4",)

    truth = derive_delivery_state(file_valid=True, authorized_entry_ids=("1", "2"),
                                  delivered_entry_ids=("1", "2"), preserved_entry_ids=("4",),
                                  unresolved_entry_ids=("3",), limitations=(partly,))
    assert truth.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert truth.unfilled_entry_ids == () and truth.unresolved_entry_ids == ("3",)

    group = registry.limitation("ENTRY_GROUP_UNRESOLVED", entry_ids=("3",))
    truth = derive_delivery_state(file_valid=True, authorized_entry_ids=("1",), delivered_entry_ids=("1",),
                                  unresolved_entry_ids=("3",), limitations=(group,))
    assert truth.delivery_state is DeliveryState.DELIVERABLE_PARTIAL  # a V gate scoped to its rows

    on_preserved = registry.limitation("ENTRY_GROUP_UNRESOLVED", entry_ids=("4",))
    truth = derive_delivery_state(file_valid=True, authorized_entry_ids=("1",), delivered_entry_ids=("1",),
                                  preserved_entry_ids=("4",), limitations=(on_preserved,))
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE  # a V gate on a kept row is file-wide

    with pytest.raises(DeliveryStateError, match="DELIVERY_UNRESOLVED_ROW_UNNAMED"):
        derive_delivery_state(file_valid=True, authorized_entry_ids=("1",), delivered_entry_ids=("1",),
                              unresolved_entry_ids=("3",))
    with pytest.raises(DeliveryStateError, match="DELIVERY_ROW_KIND_OVERLAP"):
        derive_delivery_state(file_valid=True, authorized_entry_ids=("1",), delivered_entry_ids=("1",),
                              preserved_entry_ids=("1",))


# ----------------------------------------------------------------- through run-slate


def test_a_template_with_prefilled_rows_ships_and_no_producer_repeats_one(tmp_path, monkeypatch):
    """C1's own first lineup and the baseline's first lineup are prefilled; neither comes back."""

    _code, first_run, _entries, _root = _run_slate(tmp_path / "first", monkeypatch, run_id="plain", entries=2)
    assert first_run["latest_deliverable"]["producer"] == C1
    c1_top = _cells(Path(first_run["latest_deliverable"]["path"]))["910000001"]
    slate_holder: dict[str, object] = {}

    def prefill(entry, slate):
        slate_holder["slate"] = slate
        salary_top = _salary_top(slate, 1)[0]
        _edit(entry, cells={"910000002": list(c1_top), "910000004": _named(slate, salary_top)})
        slate_holder["forbidden"] = [c1_top, salary_top]

    code, report, entries, root = _run_slate(tmp_path / "second", monkeypatch, run_id="prefilled",
                                             entries=4, edit=prefill)
    slate = slate_holder["slate"]

    assert code == 0, report["blockers"]
    assert report["latest_deliverable"]["producer"] == C1
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    truths = report["release_truths"]
    assert truths["schema_version"] == "nfl_release_truths_v3"
    assert truths["delivered_entry_ids"] == ["910000001", "910000003"]
    assert truths["preserved_entry_ids"] == ["910000002", "910000004"]
    assert truths["unfilled_entry_ids"] == [] and truths["unresolved_entry_ids"] == []
    assert (truths["MODEL_STATUS"], truths["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert "ENTRY_BLANK_CELL_AUTHORITY_REQUIRED" not in _codes(report)

    forbidden = _keys(slate, slate_holder["forbidden"])
    for producer_file in (Path(report["latest_deliverable"]["path"]), Path(report["baseline"]["path"])):
        before, after = _raw_lines(entries), _raw_lines(producer_file)
        assert after["910000002"] == before["910000002"]  # byte for byte, 'Name (ID)' form too
        assert after["910000004"] == before["910000004"]
        cells = _cells(producer_file)
        filled = [cells[eid] for eid in ("910000001", "910000003")]
        assert all(validate_lineup(slate, roster).valid for roster in filled)
        assert not _keys(slate, filled) & forbidden  # R29 across the whole portfolio
        assert len(_keys(slate, filled)) == 2
    assert report["baseline"]["preserved_entry_ids"] == ["910000002", "910000004"]

    (group,) = report["entry_groups"]
    assert group["contest_id"] == "200000001" and group["contest_name"] == "C1 Classic"
    assert group["filled"] == ["910000001", "910000003"]
    assert group["preserved"] == ["910000002", "910000004"]
    assert group["blank"] == ["910000001", "910000003"]
    pointer = json.loads((root / delivery.POINTER_NAME).read_text(encoding="utf-8"))
    assert pointer["schema_version"] == "nfl_latest_deliverable_v2"
    assert pointer["coverage"]["preserved_entry_ids"] == ["910000002", "910000004"]
    assert pointer["coverage"]["entry_groups"][0]["filled"] == ["910000001", "910000003"]


def test_c2_never_selects_a_prefilled_roster(tmp_path, monkeypatch):
    _code, first_run, _entries, _root = _run_slate(tmp_path / "first", monkeypatch, run_id="c2-plain",
                                                   entries=3, policy=_policy)
    assert first_run["latest_deliverable"]["producer"] == C2, first_run["blockers"]
    c2_rosters = [cells for eid, cells in _cells(Path(first_run["latest_deliverable"]["path"])).items()]
    slate_holder: dict[str, object] = {}

    def prefill(entry, slate):
        slate_holder["slate"] = slate
        _edit(entry, cells={"910000001": list(c2_rosters[0]), "910000004": list(c2_rosters[1])})

    code, report, entries, _root = _run_slate(tmp_path / "second", monkeypatch, run_id="c2-prefilled",
                                              entries=5, edit=prefill, policy=_policy)
    slate = slate_holder["slate"]
    assert code == 0 and report["latest_deliverable"]["producer"] == C2, report["blockers"]
    truths = report["release_truths"]
    assert truths["delivered_entry_ids"] == ["910000002", "910000003", "910000005"]
    assert truths["preserved_entry_ids"] == ["910000001", "910000004"]
    output = Path(report["latest_deliverable"]["path"])
    before, after = _raw_lines(entries), _raw_lines(output)
    assert after["910000001"] == before["910000001"] and after["910000004"] == before["910000004"]
    cells = _cells(output)
    filled = [cells[eid] for eid in truths["delivered_entry_ids"]]
    assert not _keys(slate, filled) & _keys(slate, c2_rosters[:2])
    assert len(_keys(slate, filled)) == 3


def test_a_partly_filled_row_and_an_unparseable_prefilled_row_are_named_and_the_rest_ships(
    tmp_path, monkeypatch
):
    def damage(entry, slate):
        (top,) = _salary_top(slate, 1)
        _edit(entry, cells={"910000002": [top[0], *[""] * 8], "910000003": ["Somebody", *top[1:]]})

    code, report, entries, _root = _run_slate(tmp_path, monkeypatch, run_id="damaged", entries=4,
                                              edit=damage)

    assert code == 0, report["blockers"]
    assert report["DELIVERY_STATE"] == "DELIVERABLE_PARTIAL"  # never labelled complete
    truths = report["release_truths"]
    assert truths["delivered_entry_ids"] == ["910000001", "910000004"]
    assert truths["unresolved_entry_ids"] == ["910000002", "910000003"]
    assert truths["unfilled_entry_ids"] == [] and truths["preserved_entry_ids"] == []
    codes = _codes(report)
    assert codes["ENTRY_ROW_PARTLY_PREFILLED"] == ["910000002"]
    assert codes["ENTRY_PREFILLED_ROSTER_UNRESOLVED"] == ["910000003"]
    classes = {item["code"]: item["class"] for item in truths["delivery_limitations"]}
    assert classes["ENTRY_ROW_PARTLY_PREFILLED"] == classes["ENTRY_PREFILLED_ROSTER_UNRESOLVED"] == "P"
    before, after = _raw_lines(entries), _raw_lines(Path(report["latest_deliverable"]["path"]))
    assert after["910000002"] == before["910000002"] and after["910000003"] == before["910000003"]
    (group,) = report["entry_groups"]
    assert group["unresolved"] == ["910000002", "910000003"]
    assert group["reasons"] == {"910000002": ["ENTRY_ROW_PARTLY_PREFILLED"],
                                "910000003": ["ENTRY_PREFILLED_ROSTER_UNRESOLVED"]}


def test_two_contests_report_each_group_and_a_group_problem_spares_the_other(tmp_path, monkeypatch):
    def two_contests(entry, _slate):
        # Rows 3 and 4 are another contest; row 4 disagrees on its fee, so that
        # group's contest cannot be stated.
        _edit(entry, columns={"910000003": {2: "200000002"},
                              "910000004": {2: "200000002", 3: "$20"}})

    code, report, entries, root = _run_slate(tmp_path, monkeypatch, run_id="two-contests", entries=4,
                                             edit=two_contests)

    assert code == 0, report["blockers"]
    assert report["DELIVERY_STATE"] == "DELIVERABLE_PARTIAL"
    truths = report["release_truths"]
    assert truths["delivered_entry_ids"] == ["910000001", "910000002"]
    assert truths["unresolved_entry_ids"] == ["910000003", "910000004"]
    assert _codes(report)["ENTRY_GROUP_UNRESOLVED"] == ["910000003", "910000004"]
    first, second = report["entry_groups"]
    assert (first["contest_id"], first["filled"], first["unresolved"]) == (
        "200000001", ["910000001", "910000002"], [])
    assert (second["contest_id"], second["filled"], second["unresolved"]) == (
        "200000002", [], ["910000003", "910000004"])
    assert second["contest_name"] is None and second["entry_fees"] == [5.0, 20.0]
    assert second["reasons"]["910000004"] == ["ENTRY_GROUP_UNRESOLVED"]
    before, after = _raw_lines(entries), _raw_lines(Path(report["latest_deliverable"]["path"]))
    assert after["910000003"] == before["910000003"] and after["910000004"] == before["910000004"]


def test_two_clean_contests_are_each_filled_and_reported(tmp_path, monkeypatch):
    def two_contests(entry, _slate):
        _edit(entry, columns={"910000003": {1: "C2 Classic", 2: "200000002", 3: "$20"}})

    code, report, _entries, _root = _run_slate(tmp_path, monkeypatch, run_id="clean-two", entries=3,
                                               edit=two_contests)
    assert code == 0 and report["DELIVERY_STATE"] == "DELIVERABLE", report["blockers"]
    groups = {group["contest_id"]: group for group in report["entry_groups"]}
    assert groups["200000001"]["filled"] == ["910000001", "910000002"]
    assert (groups["200000002"]["filled"], groups["200000002"]["entry_fee"]) == (["910000003"], 20.0)
    assert groups["200000002"]["contest_name"] == "C2 Classic"


# ----------------------------------------------------------------- distinctness at the edges


def test_prefilled_rosters_use_up_a_small_pool_and_the_short_rows_are_named(tmp_path):
    """Five distinct lineups exist; two are prefilled, so four blank rows get three."""

    salary = tiny_classic(tmp_path)
    slate = parse_salaries(salary)
    first, second = _salary_top(slate, 2)
    entries = _edit(tiny_classic_template(tmp_path, 6), cells={
        "5300000001": list(first), "5300000004": list(second)})

    outcome = baseline.run_baseline(salaries=salary, entries=entries, out_dir=tmp_path / "runs", now=AS_OF)

    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL and outcome.exit_code == 3
    assert truths.preserved_entry_ids == ("5300000001", "5300000004")
    assert truths.delivered_entry_ids == ("5300000002", "5300000003", "5300000005")
    assert truths.unfilled_entry_ids == ("5300000006",)
    named = {item.code: item.entry_ids for item in truths.delivery_limitations}
    assert named["BASELINE_DISTINCT_LINEUPS_EXHAUSTED"] == ("5300000006",)
    cells = _cells(outcome.output_path)
    keys = _keys(slate, [cells[eid] for eid in truths.delivered_entry_ids])
    assert len(keys) == 3 and not keys & _keys(slate, [first, second])


def test_the_audit_refuses_a_generated_roster_equal_to_a_prefilled_one(tmp_path):
    salary = tiny_classic(tmp_path)
    slate = parse_salaries(salary)
    first, second = _salary_top(slate, 2)
    entries = _edit(tiny_classic_template(tmp_path, 2), cells={"5300000002": list(first)})
    template = parse_entries(entries)
    raw = write_upload_bytes(template, {"5300000001": first})
    problems = baseline.audit_baseline_bytes(
        raw, salary_path=salary, entries_path=entries, assignments={"5300000001": first}, unfilled=())
    assert problems == ["ENTRY_PREFILLED_LINEUP_REPEATED:5300000001"]
    assert load_gate_registry().family_of("ENTRY_PREFILLED_LINEUP_REPEATED").gate_class is GateClass.V
    clean = write_upload_bytes(template, {"5300000001": second})
    assert baseline.audit_baseline_bytes(
        clean, salary_path=salary, entries_path=entries, assignments={"5300000001": second},
        unfilled=()) == []


def test_the_c2_and_sd3_banks_never_hold_a_forbidden_roster():
    from nfl_dfs.portfolio_enforcement import build_policy_candidate_bank

    showdown = parse_salaries(Path(__file__).resolve().parent / "fixtures" / "supplied"
                              / "DKSalaries Salary CSV Showdown.csv")
    objective = {player.dk_id: float(player.salary) for player in showdown.players}
    plain = build_policy_candidate_bank(showdown, objective, candidate_limit=6,
                                        total_time_limit_seconds=30.0)
    forbidden = [plain.candidates[0].roster, plain.candidates[2].roster]
    seeded = build_policy_candidate_bank(showdown, objective, candidate_limit=6,
                                         total_time_limit_seconds=30.0, forbidden_rosters=forbidden)
    keys = {candidate.canonical_key for candidate in seeded.candidates}
    assert keys and not keys & _keys(showdown, forbidden)

    from nfl_dfs.classic_portfolio import build_classic_candidate_bank
    from nfl_dfs.classic_portfolio_policy import validate_classic_portfolio_policy_bytes

    classic = parse_salaries(CLASSIC_SALARY)
    template = parse_entries(CLASSIC_ENTRIES_20)
    entry_ids = tuple(entry.entry_id for entry in template.authorizations)[:3]
    document = classic_portfolio_policy_template(classic, entry_ids, entry_sha256=template.raw_hash)
    policy = validate_classic_portfolio_policy_bytes(
        json.dumps(document).encode(), slate=classic, entry_ids=entry_ids,
        entry_sha256=template.raw_hash).policy
    assert policy is not None
    small = replace(policy, search_limits=replace(policy.search_limits, candidate_limit=12))
    scores = {player.dk_id: float(player.salary) for player in classic.players}
    plain_bank = build_classic_candidate_bank(classic, scores, small)
    forbidden = [plain_bank.candidates[0].roster, plain_bank.candidates[1].roster]
    seeded_bank = build_classic_candidate_bank(classic, scores, small, forbidden_rosters=forbidden)
    keys = {candidate.canonical_key for candidate in seeded_bank.candidates}
    assert keys and not keys & _keys(classic, forbidden)


# ----------------------------------------------------------------- the pointer, per group


def _file(tmp_path: Path, template_path: Path, salary: Path, assignments, name: str):
    """A baseline-shaped file of `assignments`, with its v3 truths, ready for the pointer."""

    template = parse_entries(template_path)
    slate = parse_salaries(salary)
    plan = plan_entries(template, slate)
    unfilled = tuple(eid for eid in plan.fillable if eid not in assignments)
    raw = write_upload_bytes(template, assignments, unfilled=unfilled)
    path = tmp_path / "run" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    registry = load_gate_registry()
    limitations = ([registry.limitation("BASELINE_DISTINCT_LINEUPS_EXHAUSTED", entry_ids=unfilled)]
                   if unfilled else [])
    truths = release_truths_v3(
        derive_release_policy(file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN,
                              model_status=ModelStatus.PRIOR_ONLY,
                              certification_basis=CertificationBasis.MODEL_ASSISTED),
        derive_delivery_state(file_valid=True, authorized_entry_ids=plan.fillable,
                              delivered_entry_ids=tuple(assignments), limitations=limitations,
                              preserved_entry_ids=plan.preserved, unresolved_entry_ids=plan.unresolved))
    return delivery.Deliverable(
        path=path, sha256=sha256_file(path), file_kind="nfl_baseline_entry_csv_v1", producer=name,
        run_id="groups", salary_path=salary, salary_sha256=sha256_file(salary),
        entry_path=template_path, entry_sha256=sha256_file(template_path), truths=truths)


def test_a_replacement_that_drops_a_group_is_refused_even_with_a_higher_total(tmp_path):
    salary = tmp_path / "inputs" / "salary.csv"
    salary.parent.mkdir()
    salary.write_bytes(CLASSIC_SALARY.read_bytes())
    entries = tmp_path / "inputs" / "entries.csv"
    entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())
    ids = [entry.entry_id for entry in parse_entries(entries).authorizations]
    group_b = ids[3]
    _edit(entries, columns={eid: {2: "999000001"} for eid in ids[3:]})
    slate = parse_salaries(salary)
    rosters = _salary_top(slate, 5)

    current = _file(tmp_path, entries, salary, {ids[0]: rosters[0], group_b: rosters[1]}, "current")
    wider = _file(tmp_path, entries, salary, {ids[0]: rosters[0], ids[1]: rosters[2], ids[2]: rosters[3]},
                  "wider")
    root = tmp_path / "run"
    delivery.publish(root, current, now=AS_OF)
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_COVERAGE_REGRESSION") as refused:
        delivery.replace(root, wider, now=AS_OF)
    assert "Contest ID 999000001: 0 of the current 1" in str(refused.value)
    assert "it delivers 3 in all, the current file 2" in str(refused.value)
    assert delivery.read_latest(root).deliverable.producer == "current"

    keeps = _file(tmp_path, entries, salary,
                  {ids[0]: rosters[0], ids[1]: rosters[2], group_b: rosters[1]}, "keeps")
    latest = delivery.replace(root, keeps, now=AS_OF)
    group_a = parse_entries(entries).authorizations[0].contest_id
    assert latest.record["supersedes"]["delivered_rows_by_group"] == {group_a: 1, "999000001": 1}
    groups = {group["contest_id"]: group for group in latest.record["coverage"]["entry_groups"]}
    assert groups["999000001"]["filled"] == [group_b]


def test_the_group_report_names_a_withheld_files_rows_unfilled(tmp_path):
    slate = parse_salaries(tiny_classic(tmp_path))
    template = parse_entries(tiny_classic_template(tmp_path, 2))
    plan = plan_entries(template, slate)
    (group,) = group_report(plan, delivered=(), unfilled=plan.fillable)
    assert group["unfilled"] == ["5300000001", "5300000002"] and group["filled"] == []


# ----------------------------------------------------------------- Showdown (review finding 1)


def _run_showdown(tmp_path, monkeypatch, *, run_id, entry_ids, cells=None, policy_controls=None, bound=None):
    """`run-slate` on the Showdown fixture with `entry_ids` rows, some prefilled.

    `bound` (Session 11b) is the Entry IDs the policy binds; every fillable row
    when it is None.
    """

    from datetime import datetime, timezone

    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module
    from nfl_dfs.portfolio_policy import portfolio_policy_template

    from .test_prior_review_profile import _prepared_run
    from .test_prior_selection import _entries_bytes

    _clocked(monkeypatch, FakeClock())
    tmp_path.mkdir(parents=True, exist_ok=True)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    entry_path.write_bytes(_entries_bytes(entry_ids))
    if cells:
        _edit(entry_path, cells=cells)
    attachments = _attachments(tmp_path, salary_path, entry_path)
    values = dict(run_id=run_id, prior_package_dir=str(package_dir))
    if policy_controls is not None:
        slate = parse_salaries(salary_path)
        plan = plan_entries(parse_entries(entry_path), slate)
        policy_path = tmp_path / "policy" / "portfolio.json"
        policy_path.parent.mkdir()
        policy_path.write_text(json.dumps(portfolio_policy_template(
            slate, list(plan.fillable if bound is None else bound), controls=policy_controls)),
            encoding="utf-8")
        values["portfolio_policy_json"] = str(policy_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project))
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, **values))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, attachments / "entries.csv", parse_salaries(salary_path)


@pytest.mark.parametrize("policy_controls", [None, {
    "max_captain_exposure": {"default_fraction": 0.5, "overrides": []}, "max_pairwise_person_overlap": 4,
}], ids=["sequential", "sd3"])
def test_a_showdown_review_with_a_prefilled_row_ships_and_never_repeats_it(
    tmp_path, monkeypatch, policy_controls
):
    _code, plain, _entries, _slate = _run_showdown(
        tmp_path / "plain", monkeypatch, run_id="sd-plain", entry_ids=("900000001", "900000002"),
        policy_controls=policy_controls)
    assert plain["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN", plain["blockers"]
    first = _cells(Path(plain["latest_deliverable"]["path"]))["900000001"]

    code, report, entries, slate = _run_showdown(
        tmp_path / "prefilled", monkeypatch, run_id="sd-prefilled",
        entry_ids=("900000001", "900000002", "900000003"), cells={"900000002": list(first)},
        policy_controls=policy_controls)

    assert code == 0, report["blockers"]
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    truths = report["release_truths"]
    assert truths["delivered_entry_ids"] == ["900000001", "900000003"]
    assert truths["preserved_entry_ids"] == ["900000002"]
    output = Path(report["latest_deliverable"]["path"])
    assert _raw_lines(output)["900000002"] == _raw_lines(entries)["900000002"]
    cells = _cells(output)
    filled = [cells["900000001"], cells["900000003"]]
    assert not _keys(slate, filled) & _keys(slate, [first]) and len(_keys(slate, filled)) == 2


def test_an_illegal_showdown_prefilled_roster_never_stops_the_baseline(tmp_path):
    """A FLEX-role ID in the Captain cell shares a legal lineup's person-level key.

    It does not resolve, so it stays out of the distinctness set; before the
    review's fix it was forbidden by key but not cut by ID, and the baseline
    stopped on SOLVER_REPEATED_A_LINEUP with nothing delivered.
    """

    from .test_baseline import showdown_template, tiny_showdown

    salary = tiny_showdown(tmp_path)
    entries = showdown_template(tmp_path, 3, salary, prefilled={
        2: ["8105", "8103", "8100", "8102", "8104", "8101"]})
    outcome = baseline.run_baseline(salaries=salary, entries=entries, out_dir=tmp_path / "runs", now=AS_OF)

    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL and outcome.exit_code == 3
    assert truths.delivered_entry_ids == ("4880000001", "4880000003")
    assert truths.unresolved_entry_ids == ("4880000002",)
    named = {item.code: item.entry_ids for item in truths.delivery_limitations}
    assert named["ENTRY_PREFILLED_ROSTER_UNRESOLVED"] == ("4880000002",)
    assert "DUPLICATE_LINEUP_SELECTED" not in named


# ----------------------------------------------------------------- the generators (review finding 3)


def test_both_policy_generators_bind_only_the_fillable_rows(tmp_path, capsys):
    import importlib.util

    from nfl_dfs.classic_portfolio_policy import validate_classic_portfolio_policy_bytes
    from nfl_dfs.portfolio_policy import validate_portfolio_policy_bytes

    def load(name):
        path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    supplied = Path(__file__).resolve().parent / "fixtures" / "supplied"
    classic = parse_salaries(CLASSIC_SALARY)
    top = _salary_top(classic, 1)[0]
    classic_entries = tmp_path / "classic_entries.csv"
    classic_entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())
    first_id = parse_entries(classic_entries).authorizations[0].entry_id
    _edit(classic_entries, cells={first_id: list(top)})
    template = parse_entries(classic_entries)
    fillable = plan_entries(template, classic).fillable
    assert first_id not in fillable and len(fillable) == 19
    out = tmp_path / "classic_policy.json"
    from .test_classic_policy_generator import IMPROVEMENT_STOP

    code = load("make_classic_policy").main(
        ["--salaries", str(CLASSIC_SALARY), "--entries", str(classic_entries), "--out", str(out),
         "--host-rates", str(tmp_path / "absent.json")],
        wall=lambda: IMPROVEMENT_STOP - timedelta(days=1))  # the fixture's lock has passed
    capsys.readouterr()
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["bindings"]["entry_ids"] == list(fillable)
    assert validate_classic_portfolio_policy_bytes(
        out.read_bytes(), slate=classic, entry_ids=fillable, entry_sha256=template.raw_hash).valid

    from .test_baseline import showdown_template

    showdown_salary = supplied / "DKSalaries Salary CSV Showdown.csv"
    showdown = parse_salaries(showdown_salary)
    lineup = _salary_top(showdown, 1)[0]
    sd_entries = showdown_template(tmp_path, 3, showdown_salary, prefilled={1: list(lineup)})
    sd_fillable = plan_entries(parse_entries(sd_entries), showdown).fillable
    assert len(sd_fillable) == 2
    sd_out = tmp_path / "showdown_policy.json"
    code = load("make_showdown_policy").main(
        ["--salaries", str(showdown_salary), "--entries", str(sd_entries), "--out", str(sd_out),
         "--combined-default", "0.5", "--captain-default", "0.5"])
    capsys.readouterr()
    assert code == 0
    assert validate_portfolio_policy_bytes(sd_out.read_bytes(), slate=showdown, entry_ids=sd_fillable).valid


# ----------------------------------------------------------------- revalidation mutations


def _prefilled_root(tmp_path):
    salary = tmp_path / "inputs" / "salary.csv"
    salary.parent.mkdir(parents=True)
    salary.write_bytes(CLASSIC_SALARY.read_bytes())
    entries = tmp_path / "inputs" / "entries.csv"
    entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())
    ids = [entry.entry_id for entry in parse_entries(entries).authorizations]
    rosters = _salary_top(parse_salaries(salary), 3)
    _edit(entries, cells={ids[1]: list(rosters[0])})
    return salary, entries, ids, rosters


def test_revalidation_refuses_a_changed_preserved_row_wrong_truths_and_a_prefilled_repeat(tmp_path):
    salary, entries, ids, rosters = _prefilled_root(tmp_path)
    fill = {eid: roster for eid, roster in zip(
        [eid for eid in ids if eid != ids[1]], _salary_top(parse_salaries(salary), 20)[1:])}
    good = _file(tmp_path, entries, salary, fill, "good")
    root = tmp_path / "run"
    assert delivery.revalidate(good, root=root) == ()

    raw = good.path.read_bytes()
    kept = _raw_lines(entries)[ids[1]]
    changed = kept.replace(rosters[0][0].encode(), rosters[1][0].encode(), 1)
    assert changed != kept
    tampered = good.path.with_name("tampered.csv")
    tampered.write_bytes(raw.replace(kept, changed, 1))
    item = delivery.Deliverable(**{**good.__dict__, "path": tampered, "sha256": sha256_file(tampered)})
    assert any(p.startswith("DELIVERABLE_BYTE_AUDIT_FAILED") for p in delivery.revalidate(item, root=root))

    wrong = derive_delivery_state(file_valid=True, authorized_entry_ids=good.truths.delivered_entry_ids,
                                  delivered_entry_ids=good.truths.delivered_entry_ids)
    unaware = release_truths_v3(
        derive_release_policy(file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN,
                              model_status=ModelStatus.PRIOR_ONLY,
                              certification_basis=CertificationBasis.MODEL_ASSISTED), wrong)
    item = delivery.Deliverable(**{**good.__dict__, "truths": unaware})
    assert any("DELIVERABLE_COVERAGE_MISMATCH" in p and "preserves" in p
               for p in delivery.revalidate(item, root=root))

    repeat = _file(tmp_path, entries, salary, {**fill, ids[0]: rosters[0]}, "repeat")
    assert any(p == f"DELIVERABLE_LINEUP_DUPLICATE:{ids[0]} repeats a prefilled roster"
               for p in delivery.revalidate(repeat, root=root))


def test_a_v1_pointer_still_reads_back(tmp_path):
    salary, entries, ids, rosters = _prefilled_root(tmp_path)
    entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())  # a v1 template: every row blank
    fill = dict(zip(ids, _salary_top(parse_salaries(salary), 20)))
    item = _file(tmp_path, entries, salary, fill, "v1")
    root = tmp_path / "run"
    delivery.publish(root, item, now=AS_OF)
    pointer = root / delivery.POINTER_NAME
    record = json.loads(pointer.read_text(encoding="utf-8"))
    record["schema_version"] = "nfl_latest_deliverable_v1"
    truths = record["release_truths"]
    truths["schema_version"] = "nfl_release_truths_v2"
    del truths["preserved_entry_ids"], truths["unresolved_entry_ids"]
    record["coverage"] = {key: record["coverage"][key]
                          for key in ("delivered_entry_ids", "unfilled_entry_ids")}
    pointer.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    latest = delivery.read_latest(root)
    assert latest is not None and latest.deliverable.truths.schema_version == "nfl_release_truths_v2"
    assert latest.summary()["preserved_entry_ids"] == [] and latest.summary()["entry_groups"] == []
    assert delivery.as_v3(latest.deliverable.truths).schema_version == "nfl_release_truths_v3"


def test_c3s_export_audit_still_refuses_a_written_prefilled_row(tmp_path):
    from nfl_dfs.classic_review import _audit_template_bytes

    slate = parse_salaries(tiny_classic(tmp_path))
    first, second = _salary_top(slate, 2)
    path = _edit(tiny_classic_template(tmp_path, 1), cells={"5300000001": list(first)})
    source = path.read_bytes()
    forged = source.replace(",".join(first).encode(), ",".join(second).encode(), 1)
    template = parse_entries(path)
    problems = _audit_template_bytes(
        source_bytes=source, output_bytes=forged, encoding=template.encoding,
        roster_start=template.roster_start_index, roster_width=9, assignments={"5300000001": second})
    assert "CLASSIC_C3_EXPORT_PREFILLED_AUTHORIZED_ENTRY:5300000001" in problems


# ----------------------------------------------------------------- Session 11b: subset binding
#
# A policy may bind a subset of the fillable rows, in template order. Its joint
# solve fills its rows; sequential Showdown fills the rest with every policy
# lineup and every prefilled roster as a no-good (R29). A Classic subset is
# refused by name until Session 11c. A policy binding every fillable row gives
# the file it gave before: the hashes below were captured on main at bd5a97f,
# before any Session 11b change, with these fixtures and their pinned clock.

SD3_FULL_FILLABLE_SHA256 = "1918820d809eea637425f1970b5bae65c406efca7b35fa3264b867863e43eed1"
C2_FULL_FILLABLE_SHA256 = "48027a40a9fd9de47138ca1c619e72d78cd3a7cf76c6017f6ea1627aba28f8ce"
SD3_CONTROLS = {"max_captain_exposure": {"default_fraction": 0.5, "overrides": []},
                "max_pairwise_person_overlap": 4}


def _readable(report) -> dict:
    path = Path(report["prior_review_artifacts"]["readable_review_json"])
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_showdown_subset_policy_fills_its_rows_and_sequential_showdown_the_rest(tmp_path, monkeypatch):
    """Five rows: one prefilled, two bound by an SD3 policy, two left to sequential Showdown."""

    _code, plain, _entries, _slate = _run_showdown(
        tmp_path / "plain", monkeypatch, run_id="sd-plain", entry_ids=("900000001", "900000002"),
        policy_controls=SD3_CONTROLS)
    first = _cells(Path(plain["latest_deliverable"]["path"]))["900000001"]
    rows = tuple(f"90000000{index}" for index in range(1, 6))

    code, report, entries, slate = _run_showdown(
        tmp_path / "subset", monkeypatch, run_id="sd-subset", entry_ids=rows,
        cells={"900000002": list(first)}, policy_controls=SD3_CONTROLS, bound=("900000003", "900000005"))

    assert code == 0, report["blockers"]
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    truths = report["release_truths"]
    assert truths["delivered_entry_ids"] == ["900000001", "900000003", "900000004", "900000005"]
    assert truths["preserved_entry_ids"] == ["900000002"] and truths["unfilled_entry_ids"] == []
    assert (truths["MODEL_STATUS"], truths["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert report["row_sources"] == {
        "900000001": "SHOWDOWN_SEQUENTIAL", "900000003": "POLICY",
        "900000004": "SHOWDOWN_SEQUENTIAL", "900000005": "POLICY"}

    policy = report["portfolio_policy"]
    assert policy["enforcement_status"] == "ENFORCED_AND_INDEPENDENTLY_AUDITED"
    assert policy["entry_count_denominator"] == 2
    assert policy["bound_entry_ids"] == ["900000003", "900000005"]
    assert policy["unbound_entry_ids"] == ["900000001", "900000004"]
    assert policy["independent_audit"]["entry_ids"] == ["900000003", "900000005"]
    assert policy["selector"]["entry_ids"] == ["900000003", "900000005"]
    captains = [count for count in policy["independent_audit"]["captain_counts"].values()]
    assert max(captains) <= 1  # floor(0.5 x 2 bound rows), not x 4 filled rows

    output = Path(report["latest_deliverable"]["path"])
    assert _raw_lines(output)["900000002"] == _raw_lines(entries)["900000002"]
    cells = _cells(output)
    filled = [cells[eid] for eid in truths["delivered_entry_ids"]]
    assert all(validate_lineup(slate, roster).valid for roster in filled)
    assert len(_keys(slate, filled)) == 4  # no policy lineup, fill lineup or prefilled one repeats
    assert not _keys(slate, filled) & _keys(slate, [first])

    readable = _readable(report)
    assert readable["schema_version"] == "prior_only_readable_review_sd5_v2"
    assert {entry["entry_id"]: entry["source"] for entry in readable["entries"]} == report["row_sources"]
    assert readable["exposure"]["entry_count_denominator"] == 2
    assert readable["reconciliation"]["entry_count"] == 4
    assert readable["unbound_rows"]["entry_ids"] == ["900000001", "900000004"]
    assert readable["unbound_rows"]["source"] == "SHOWDOWN_SEQUENTIAL"
    assert [(row["entry_id_a"], row["entry_id_b"]) for row in readable["exposure"]["pairwise_overlap"]] == [
        ("900000003", "900000005")]
    selection = report["prior_review_reports"]["selection"]["selection"]
    assert selection["selected_lineup_count"] == 2  # the policy's own summary: its rows only
    assert selection["unbound_fill"]["lineups"] == 2
    assert selection["unbound_fill"]["no_good_rosters"] == {"policy_lineups": 2, "prefilled_rosters": 1}


def test_a_bound_prefilled_row_is_refused_v_and_the_baseline_ships(tmp_path, monkeypatch):
    registry = load_gate_registry()
    _code, plain, _entries, _slate = _run_showdown(
        tmp_path / "plain", monkeypatch, run_id="sd-plain", entry_ids=("900000001",))
    lineup = _cells(Path(plain["latest_deliverable"]["path"]))["900000001"]

    code, report, _entries, _slate = _run_showdown(
        tmp_path / "bound-prefilled", monkeypatch, run_id="sd-bound-prefilled",
        entry_ids=("900000001", "900000002", "900000003"), cells={"900000002": list(lineup)},
        policy_controls=SD3_CONTROLS, bound=("900000002", "900000003"))

    assert code == 2
    refusals = [text for text in report["blockers"]
                if text.startswith("PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH")]
    assert refusals and "900000002" in refusals[0], report["blockers"]
    assert registry.family_of("PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH").gate_class is GateClass.V
    assert report["latest_deliverable"]["producer"] == BASELINE
    assert report["release_truths"]["preserved_entry_ids"] == ["900000002"]


def test_a_bound_row_outside_the_fillable_rows_is_refused_by_both_validators(tmp_path):
    from nfl_dfs.classic_portfolio_policy import validate_classic_portfolio_policy_bytes
    from nfl_dfs.portfolio_policy import portfolio_policy_template, validate_portfolio_policy_bytes

    from .test_baseline import showdown_template

    registry = load_gate_registry()
    showdown_salary = Path(__file__).resolve().parent / "fixtures" / "supplied" / "DKSalaries Salary CSV Showdown.csv"
    showdown = parse_salaries(showdown_salary)
    lineup = _salary_top(showdown, 1)[0]
    template = parse_entries(showdown_template(tmp_path, 4, showdown_salary, prefilled={1: list(lineup)}))
    plan = plan_entries(template, showdown)
    (prefilled,) = plan.preserved
    fillable = list(plan.fillable)
    assert prefilled not in fillable and len(fillable) == 3
    for bound in ((prefilled, fillable[0]), ("4880009999",), (fillable[2], fillable[0]),
                  (fillable[0], fillable[0])):
        raw = json.dumps(portfolio_policy_template(showdown, list(bound))).encode("utf-8")
        codes = {issue.code for issue in validate_portfolio_policy_bytes(
            raw, slate=showdown, entry_ids=plan.fillable).problems}
        assert "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH" in codes, bound
    subset = json.dumps(portfolio_policy_template(showdown, [fillable[0], fillable[2]])).encode("utf-8")
    valid = validate_portfolio_policy_bytes(subset, slate=showdown, entry_ids=plan.fillable)
    assert valid.valid and valid.policy.entry_ids == (fillable[0], fillable[2])

    classic = parse_salaries(CLASSIC_SALARY)
    classic_entries = tmp_path / "classic_entries.csv"
    classic_entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())
    ids = [entry.entry_id for entry in parse_entries(classic_entries).authorizations]
    _edit(classic_entries, cells={ids[0]: list(_salary_top(classic, 1)[0])})
    classic_template = parse_entries(classic_entries)
    classic_fillable = plan_entries(classic_template, classic).fillable
    for bound in ((ids[0], ids[1]), ("999",), (ids[3], ids[2]), ()):
        raw = json.dumps(classic_portfolio_policy_template(
            classic, list(bound), entry_sha256=classic_template.raw_hash)).encode("utf-8")
        codes = {issue.code for issue in validate_classic_portfolio_policy_bytes(
            raw, slate=classic, entry_ids=classic_fillable, entry_sha256=classic_template.raw_hash).problems}
        assert "CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH" in codes, bound
    assert registry.family_of("CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH").gate_class is GateClass.V
    raw = json.dumps(classic_portfolio_policy_template(
        classic, [ids[2], ids[5]], entry_sha256=classic_template.raw_hash)).encode("utf-8")
    valid = validate_classic_portfolio_policy_bytes(
        raw, slate=classic, entry_ids=classic_fillable, entry_sha256=classic_template.raw_hash)
    assert valid.valid, valid.blockers()
    assert valid.policy.entry_ids == (ids[2], ids[5]) and valid.policy.entry_count == 2


def test_a_classic_subset_policy_is_refused_by_name_until_session_11c(tmp_path, monkeypatch):
    def subset(attachments: Path, plan) -> Path:
        slate = parse_salaries(attachments / "salary.csv")
        template = parse_entries(attachments / "entries.csv")
        path = attachments.parent / "classic_subset.json"
        path.write_text(json.dumps(classic_portfolio_policy_template(
            slate, plan.fillable[:2], entry_sha256=template.raw_hash)), encoding="utf-8")
        return path

    code, report, _entries, _root = _run_slate(tmp_path, monkeypatch, run_id="c2-subset", entries=3,
                                               policy=subset)
    assert code == 2
    (refusal,) = [text for text in report["blockers"] if text.startswith("CLASSIC_POLICY_SUBSET_UNSUPPORTED")]
    assert "2 of 3 fillable rows" in refusal and "Session 11c" in refusal
    assert load_gate_registry().family_of("CLASSIC_POLICY_SUBSET_UNSUPPORTED").gate_class is GateClass.P
    assert report["latest_deliverable"]["producer"] == BASELINE
    assert report["DELIVERY_STATE"] == "DELIVERABLE"


def test_a_policy_binding_every_fillable_row_gives_the_same_file_as_before(tmp_path, monkeypatch):
    code, report, _entries, _slate = _run_showdown(
        tmp_path / "sd", monkeypatch, run_id="sd-full", entry_ids=("900000001", "900000002", "900000003"),
        policy_controls=SD3_CONTROLS)
    assert code == 0 and report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    assert sha256_file(report["latest_deliverable"]["path"]) == SD3_FULL_FILLABLE_SHA256
    assert set(report["row_sources"].values()) == {"POLICY"}
    assert _readable(report)["unbound_rows"] is None


def test_a_classic_policy_binding_every_fillable_row_gives_the_same_file_as_before(tmp_path, monkeypatch):
    code, report, _entries, _root = _run_slate(tmp_path, monkeypatch, run_id="c2-full", entries=3,
                                               policy=_policy)
    assert code == 0 and report["latest_deliverable"]["producer"] == C2, report["blockers"]
    assert sha256_file(report["latest_deliverable"]["path"]) == C2_FULL_FILLABLE_SHA256


def test_both_generators_bind_a_subset_with_entry_id_and_refuse_a_row_that_is_not_fillable(
        tmp_path, capsys):
    import importlib.util

    from nfl_dfs.classic_portfolio_policy import validate_classic_portfolio_policy_bytes
    from nfl_dfs.portfolio_policy import validate_portfolio_policy_bytes

    from .test_baseline import showdown_template
    from .test_classic_policy_generator import IMPROVEMENT_STOP

    def load(name):
        path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    showdown_salary = Path(__file__).resolve().parent / "fixtures" / "supplied" / "DKSalaries Salary CSV Showdown.csv"
    showdown = parse_salaries(showdown_salary)
    sd_entries = showdown_template(tmp_path, 4, showdown_salary, prefilled={1: list(_salary_top(showdown, 1)[0])})
    template = parse_entries(sd_entries)
    fillable = plan_entries(template, showdown).fillable
    (prefilled,) = plan_entries(template, showdown).preserved
    generator = load("make_showdown_policy")
    sd_out = tmp_path / "showdown_subset.json"
    arguments = ["--salaries", str(showdown_salary), "--entries", str(sd_entries), "--out", str(sd_out),
                 "--combined-default", "0.5", "--captain-default", "0.5"]
    assert generator.main([*arguments, "--entry-id", fillable[2], "--entry-id", fillable[0]]) == 0
    capsys.readouterr()
    written = json.loads(sd_out.read_text(encoding="utf-8"))
    assert written["bindings"]["entry_ids"] == [fillable[0], fillable[2]]  # template order
    validation = validate_portfolio_policy_bytes(sd_out.read_bytes(), slate=showdown, entry_ids=fillable)
    assert validation.valid and validation.policy.entry_count == 2
    for refused in (prefilled, "4880009999"):
        with pytest.raises(SystemExit, match="ENTRY_ID_NOT_FILLABLE"):
            generator.main([*arguments, "--entry-id", refused])
    with pytest.raises(SystemExit, match="ENTRY_ID_REPEATED"):
        generator.main([*arguments, "--entry-id", fillable[0], "--entry-id", fillable[0]])
    rung_out = tmp_path / "showdown_subset_rung1.json"
    assert generator.main(["--salaries", str(showdown_salary), "--entries", str(sd_entries), "--out",
                           str(rung_out), "--combined-default", "0.5", "--captain-default", "0.1",
                           "--entry-id", fillable[1], "--rung", "1"]) == 0
    capsys.readouterr()
    assert json.loads(rung_out.read_text(encoding="utf-8"))["bindings"]["entry_ids"] == [fillable[1]]

    classic_entries = tmp_path / "classic_entries.csv"
    classic_entries.write_bytes(CLASSIC_ENTRIES_20.read_bytes())
    classic = parse_salaries(CLASSIC_SALARY)
    classic_template = parse_entries(classic_entries)
    classic_fillable = plan_entries(classic_template, classic).fillable
    out = tmp_path / "classic_subset.json"
    arguments = ["--salaries", str(CLASSIC_SALARY), "--entries", str(classic_entries), "--out", str(out),
                 "--host-rates", str(tmp_path / "absent.json")]
    wall = lambda: IMPROVEMENT_STOP - timedelta(days=1)  # noqa: E731 - the fixture's lock has passed
    chosen = [classic_fillable[7], classic_fillable[1], classic_fillable[4], classic_fillable[12]]
    code = load("make_classic_policy").main(
        [*arguments, *(item for eid in chosen for item in ("--entry-id", eid))], wall=wall)
    printed = capsys.readouterr().out
    assert code == 0 and "Session 11c" in printed
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["bindings"]["entry_ids"] == [classic_fillable[i] for i in (1, 4, 7, 12)]
    classic_validation = validate_classic_portfolio_policy_bytes(
        out.read_bytes(), slate=classic, entry_ids=classic_fillable, entry_sha256=classic_template.raw_hash)
    assert classic_validation.valid, classic_validation.blockers()
    assert classic_validation.policy.entry_count == 4
    rules = {rule["rule_id"]: rule for rule in document["controls"]["stack_rules"]}
    assert rules["qb-pass-catcher"]["minimum_entries"] <= 4  # the rung table counts the bound rows
    with pytest.raises(SystemExit, match="ENTRY_ID_NOT_FILLABLE"):
        load("make_classic_policy").main([*arguments, "--entry-id", "999"], wall=wall)


def test_the_readable_reviews_second_section_refuses_each_mutation(tmp_path, monkeypatch):
    """Each new readable-review check fires on its own mutation of the subset run's inputs.

    The review is replayed from the run's own call with one input changed:
    the selection's row sources, its fill report, the run's exclusions, an
    official status, and a template whose prefilled roster equals a filled one.
    """

    from nfl_dfs import cli
    from nfl_dfs.readable_review import ReadableReviewError, create_readable_review

    captured: dict[str, object] = {}

    def record(**kwargs):
        captured.update(kwargs)
        return create_readable_review(**kwargs)

    monkeypatch.setattr(cli, "create_readable_review", record)
    rows = ("900000001", "900000002", "900000003", "900000004")
    code, report, _entries, slate = _run_showdown(
        tmp_path / "run", monkeypatch, run_id="sd-mutate", entry_ids=rows,
        policy_controls=SD3_CONTROLS, bound=("900000002", "900000004"))
    assert code == 0 and captured, report["blockers"]
    output = _cells(Path(report["latest_deliverable"]["path"]))
    by_id = {player.dk_id: player for player in slate.players}
    selection_path = Path(captured["artifacts"]["selection_report"])
    original = json.loads(selection_path.read_text(encoding="utf-8"))

    def replay(name, *, selection=None, reports=None, entry_bytes=None):
        artifacts = dict(captured["artifacts"])
        hashes = dict(captured["expected_hashes"])
        values = dict(captured, output_dir=tmp_path / name / "review")
        (tmp_path / name).mkdir()
        if selection is not None:
            path = tmp_path / name / "selection_report.json"
            path.write_text(json.dumps(selection), encoding="utf-8")
            artifacts["selection_report"] = str(path)
            hashes["selection_report"] = sha256_file(path)
        if entry_bytes is not None:
            path = tmp_path / name / "entries.csv"
            path.write_bytes(entry_bytes)
            values["entry_path"] = str(path)
        values.update(artifacts=artifacts, expected_hashes=hashes, reports=reports or captured["reports"])
        with pytest.raises(ReadableReviewError) as caught:
            create_readable_review(**values)
        return str(caught.value)

    flipped = json.loads(json.dumps(original))
    flipped["row_sources"]["900000002"] = "SHOWDOWN_SEQUENTIAL"
    assert "READABLE_REVIEW_ROW_SOURCE_MISMATCH" in replay("sources", selection=flipped)

    short = json.loads(json.dumps(original))
    short["selection"]["unbound_fill"]["lineups"] = 3
    assert "READABLE_REVIEW_UNBOUND_FILL_REPORT_MISMATCH" in replay("fill", selection=short)

    fill_person = by_id[output["900000001"][0]].underlying_id
    excluded = json.loads(json.dumps(original))
    excluded["participation_detail"]["operator_excluded_people"].append(fill_person)
    assert f"READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON:entry=900000001:person={fill_person}" in replay(
        "excluded", selection=excluded)

    reports = json.loads(json.dumps(captured["reports"], default=str))
    reports.setdefault("official_status", {}).setdefault("statuses", {})[output["900000003"][1]] = "INACTIVE"
    assert f"READABLE_REVIEW_UNBOUND_ROW_NOT_ACTIVE:entry=900000003:id={output['900000003'][1]}" in replay(
        "inactive", reports=reports)

    template = tmp_path / "template.csv"
    template.write_bytes(Path(captured["entry_path"]).read_bytes())
    _edit(template, cells={"900000003": list(output["900000001"])})  # a prefilled row repeating a filled one
    assert "ENTRY_PREFILLED_LINEUP_REPEATED:900000001" in replay("prefilled", entry_bytes=template.read_bytes())


def test_a_classic_subset_is_refused_by_prior_review_and_selection_called_directly(tmp_path):
    from nfl_dfs.classic_portfolio_policy import (
        validate_classic_portfolio_policy_bytes,
        write_normalized_classic_portfolio_policy,
    )
    from nfl_dfs.prior_review import run_prior_review
    from nfl_dfs.projection import build_projection_package
    from nfl_dfs.selection import SelectionError, select_prior_lineups

    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=3)
    slate = parse_salaries(salary)
    entries = parse_entries(entry)
    fillable = plan_entries(entries, slate).fillable
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(classic_portfolio_policy_template(
        slate, fillable[:2], entry_sha256=entries.raw_hash)), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(), slate=slate, entry_ids=fillable, entry_sha256=entries.raw_hash)
    assert validation.valid and validation.policy.entry_count == 2, validation.blockers()

    with pytest.raises(SelectionError, match="CLASSIC_POLICY_SUBSET_UNSUPPORTED"):
        select_prior_lineups(slate, None, {}, None, count=2, fill_count=1, portfolio_policy=validation.policy)

    normalized = write_normalized_classic_portfolio_policy(tmp_path / "policy.normalized.json", validation.policy)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-subset", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package,
        official_status_csv=status, offensive_role_evidence_json=role,
        portfolio_policy=validation.policy, portfolio_policy_source_path=policy_path,
        portfolio_policy_source_sha256=sha256_file(policy_path), portfolio_policy_normalized_path=normalized,
        portfolio_policy_normalized_sha256=sha256_file(normalized), project=build_projection_package,
    )
    assert outcome.blocked and outcome.stage == "SELECT"
    (blocker,) = outcome.blockers
    assert "CLASSIC_POLICY_SUBSET_UNSUPPORTED" in blocker and "2 of 3 fillable rows" in blocker
    assert not list((tmp_path / "out").rglob("DK_REVIEW_ENTRY_*.csv"))


def test_every_prior_review_exit_names_its_row_sources(tmp_path, monkeypatch):
    """C1 names every row `C1`; C2 names every row `POLICY` (a Classic file is one or the other)."""

    code, c1, _entries, _root = _run_slate(tmp_path / "c1", monkeypatch, run_id="c1-sources", entries=2)
    assert code == 0 and c1["latest_deliverable"]["producer"] == C1, c1["blockers"]
    assert c1["row_sources"] == {"910000001": "C1", "910000002": "C1"}
    code, c2, _entries, _root = _run_slate(tmp_path / "c2", monkeypatch, run_id="c2-sources", entries=2,
                                           policy=_policy)
    assert code == 0 and c2["latest_deliverable"]["producer"] == C2, c2["blockers"]
    assert c2["row_sources"] == {"910000001": "POLICY", "910000002": "POLICY"}
    assert c2["portfolio_policy"]["unbound_entry_ids"] == []
