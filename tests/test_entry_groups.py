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
