"""Session 04: `nfl baseline`, a deliverable file from the DraftKings bytes alone (R28, R29).

The card's acceptance: the supplied Classic (719 salary rows) and Showdown
(126) fixtures at 1, 20 and 150 entries produce `DELIVERABLE` files, and a pool
too small for distinct lineups yields `DELIVERABLE_PARTIAL` with the exact
unfilled Entry IDs. Its must-holds: `AvgPointsPerGame` is never read, and a
prefilled row is refused exactly as `prior_review` refuses it today.

Only the 2- and 20-entry Classic templates are supplied, so the 1- and
150-entry Classic templates are cut from the 20-entry bytes in `tmp_path`, and
every Showdown template is built here, beside the supplied Showdown salary
file. Nothing writes into `tests/fixtures/supplied/`. No test touches the
network.
"""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nfl_dfs import baseline
from nfl_dfs.cli import main
from nfl_dfs.contracts import (
    DeliveryState,
    EngineMode,
    GateClass,
    UNAVAILABLE_DK_STATUSES,
)
from nfl_dfs.dk import DraftKingsParseError, parse_entries, parse_salaries, reconcile_template
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.lineups import LineupValidationError, validate_lineup, write_upload_bytes
from nfl_dfs.optimizer import LineupOptimizer

from .conftest import FIXTURE_ROOT

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
CLASSIC_SALARY = FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"
SHOWDOWN_SALARY = FIXTURE_ROOT / "DKSalaries Salary CSV Showdown.csv"
CLASSIC_ENTRIES_20 = FIXTURE_ROOT / "DKEntries CSV 20 entries.csv"
SALARY_HEADER = [
    "Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
    "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status",
]
POOL_COLUMNS = SALARY_HEADER[:-1]  # the table DraftKings embeds in an entries export


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_of(raw: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))


def write_rows(path: Path, rows: list[list[str]]) -> Path:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    return path


# ------------------------------------------------------------ templates


def classic_template(tmp_path: Path, count: int) -> Path:
    """The supplied 20-entry Classic export, cut or extended to `count` entries.

    Rows past the twentieth already carry the embedded pool table to the right,
    so an extra entry fills only the four metadata cells of an existing row.
    """

    rows = rows_of(CLASSIC_ENTRIES_20.read_bytes())
    meta = rows[1][:4]
    assert count <= len(rows) - 1
    for index in range(1, len(rows)):
        if index <= count:
            if not rows[index][0].strip():
                rows[index][:4] = [str(5_400_000_000 + index), *meta[1:]]
        else:
            rows[index][:4] = ["", "", "", ""]
    return write_rows(tmp_path / f"classic_{count}.csv", rows)


def showdown_template(tmp_path: Path, count: int, salary: Path = SHOWDOWN_SALARY,
                      *, pool: bool = True, prefilled: dict[int, list[str]] | None = None,
                      name: str = "showdown") -> Path:
    """A DraftKings-shaped Showdown entries export with `count` blank rows.

    Like a real export it carries the salary file's pool table beside the entry
    block, starting in the Instructions column, unless `pool` is false.
    """

    header = ["Entry ID", "Contest Name", "Contest ID", "Entry Fee",
              "CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX", "", "Instructions"]
    table: list[list[str]] = []
    if pool:
        salary_rows = rows_of(salary.read_bytes())
        index = {name: salary_rows[0].index(name) for name in POOL_COLUMNS}
        table = [POOL_COLUMNS] + [[row[index[name]] for name in POOL_COLUMNS]
                                  for row in salary_rows[1:]]
    start = 7  # six instruction lines, then the table, as DraftKings lays it out
    rows = [header]
    for index in range(1, max(count, start + len(table) - 1) + 1):
        row = [""] * 11
        if index <= count:
            cells = (prefilled or {}).get(index, [""] * 6)
            row[:10] = [f"48800{index:05d}", "NFL Showdown $5", "9001", "$5.00", *cells]
        tail = ["See instructions"] if index < start else []
        if pool and start <= index < start + len(table):
            tail = table[index - start]
        rows.append(row + (tail or [""]))
    return write_rows(tmp_path / f"{name}_{count}.csv", rows)


def tiny_classic(tmp_path: Path) -> Path:
    """Ten people in two games; exactly five distinct legal lineups exist.

    Nine of the ten fill a lineup and the tenth is left out. Dropping any of the
    five receivers leaves a legal roster; dropping a back, the tight end, the
    quarterback or the defence does not.
    """

    game_one, game_two = "AAA@BBB 09/27/2026 01:00PM ET", "CCC@DDD 09/27/2026 01:00PM ET"
    people = [
        ("QB", "Q One", "AAA", 6000, game_one), ("RB", "R One", "BBB", 6000, game_one),
        ("RB", "R Two", "CCC", 6000, game_two), ("TE", "T One", "DDD", 5000, game_two),
        ("DST", "Defence", "CCC", 3000, game_two),
        ("WR", "W One", "AAA", 3000, game_one), ("WR", "W Two", "BBB", 3100, game_one),
        ("WR", "W Three", "CCC", 3200, game_two), ("WR", "W Four", "DDD", 3300, game_two),
        ("WR", "W Five", "AAA", 3400, game_one),
    ]
    roster = {"QB": "QB", "RB": "RB/FLEX", "WR": "WR/FLEX", "TE": "TE/FLEX", "DST": "DST"}
    rows = [SALARY_HEADER] + [
        [pos, f"{name} ({7000 + n})", name, str(7000 + n), roster[pos], str(salary),
         game, team, "12.5", ""]
        for n, (pos, name, team, salary, game) in enumerate(people)
    ]
    return write_rows(tmp_path / "tiny_classic_salaries.csv", rows)


def tiny_classic_template(tmp_path: Path, count: int) -> Path:
    header = ["Entry ID", "Contest Name", "Contest ID", "Entry Fee",
              "QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST", "", "Instructions"]
    rows = [header] + [[f"5300000{n:03d}", "Classic $5", "7001", "$5.00", *[""] * 9, "", ""]
                       for n in range(1, count + 1)]
    return write_rows(tmp_path / f"tiny_classic_{count}.csv", rows)


def tiny_showdown(tmp_path: Path) -> Path:
    """Six people, three a team: every lineup holds all six, so six captains, six lineups."""

    game = "KC@DEN 09/28/2026 08:15PM ET"
    people = [("QB", "K Q", "KC"), ("WR", "K W", "KC"), ("RB", "K R", "KC"),
              ("QB", "D Q", "DEN"), ("WR", "D W", "DEN"), ("RB", "D R", "DEN")]
    rows = [SALARY_HEADER]
    for n, (pos, name, team) in enumerate(people):
        for role, ident, price in (("CPT", 8000 + n, 7500), ("FLEX", 8100 + n, 5000)):
            rows.append([pos, f"{name} ({ident})", name, str(ident), role, str(price),
                         game, team, "3.1", ""])
    return write_rows(tmp_path / "tiny_showdown_salaries.csv", rows)


def run(tmp_path: Path, salaries: Path, entries: Path, **kwargs) -> baseline.BaselineOutcome:
    kwargs.setdefault("now", NOW)
    return baseline.run_baseline(salaries=salaries, entries=entries,
                                 out_dir=kwargs.pop("out_dir", tmp_path / "runs"), **kwargs)


def codes(outcome: baseline.BaselineOutcome) -> dict[str, tuple[str, ...]]:
    return {item.code: item.entry_ids for item in outcome.truths.delivery_limitations}


def delivered_rosters(outcome: baseline.BaselineOutcome) -> dict[str, tuple[str, ...]]:
    assert outcome.output_path is not None
    template = parse_entries(outcome.output_path)
    return {entry.entry_id: entry.existing_cells for entry in template.authorizations
            if any(entry.existing_cells)}


# ------------------------------------------------------------ acceptance


@pytest.mark.parametrize("mode", ["CLASSIC", "SHOWDOWN"])
@pytest.mark.parametrize("count", [1, 20, 150])
def test_the_supplied_fixtures_deliver_at_1_20_and_150_entries(tmp_path, mode, count):
    salary = CLASSIC_SALARY if mode == "CLASSIC" else SHOWDOWN_SALARY
    if mode == "CLASSIC":
        entries = CLASSIC_ENTRIES_20 if count == 20 else classic_template(tmp_path, count)
    else:
        entries = showdown_template(tmp_path, count)
    before = {path: sha(path) for path in (salary, entries)}

    outcome = run(tmp_path, salary, entries)

    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE, codes(outcome)
    assert outcome.exit_code == 0
    assert truths.file_valid and truths.delivered_file_valid
    assert truths.model_status.value == "PRIOR_ONLY"
    assert truths.release_decision.value == "DO_NOT_UPLOAD"
    assert truths.unfilled_entry_ids == ()
    authorized = [entry.entry_id for entry in parse_entries(entries).authorizations]
    assert list(truths.delivered_entry_ids) == authorized and len(authorized) == count

    output = outcome.output_path
    assert output is not None and output.name.startswith("DK_BASELINE_ENTRY_V1_")
    assert "DK_UPLOAD" not in output.name and output.parent == outcome.run_dir
    assert outcome.output_sha256 == sha(output)
    slate = parse_salaries(salary)
    assert slate.mode is EngineMode(mode)
    rosters = delivered_rosters(outcome)
    assert list(rosters) == authorized
    unavailable = {p.dk_id for p in slate.players
                   if p.status_raw.strip().upper() in UNAVAILABLE_DK_STATUSES}
    keys = set()
    for roster in rosters.values():
        result = validate_lineup(slate, roster)
        assert result.valid, result.errors
        assert not unavailable.intersection(roster)
        keys.add(result.lineup.canonical_key)
    assert len(keys) == count  # R29: every lineup distinct
    salaries = [validate_lineup(slate, r).lineup.salary for r in rosters.values()]
    assert salaries == sorted(salaries, reverse=True)  # BASELINE_SALARY_RANK_V1 order

    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "nfl_baseline_report_v1"
    assert report["objective"]["version"] == "BASELINE_SALARY_RANK_V1"
    assert report["output"]["contract_version"] == "nfl_baseline_entry_csv_v1"
    assert report["release_truths"]["schema_version"] == "nfl_release_truths_v2"
    assert report["release_truths"]["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["audit"]["status"] == "PASS"
    assert report["timing"]["wall_seconds"] > 0
    carried = set(codes(outcome))
    assert {"OFFICIAL_STATUS_REQUIRED", "OFFENSIVE_CURRENT_ROLE_UNRESOLVED",
            "WEATHER_CAPTURE_REQUIRED", "MODEL_NOT_PROSPECTIVELY_VALIDATED"} <= carried
    assert all(item.gate_class is not GateClass.V for item in truths.delivery_limitations)
    for path in (salary, entries):  # inputs are snapshotted, never written
        assert sha(path) == before[path]
        assert (outcome.run_dir / "inputs" / f"{before[path]}.csv").read_bytes() == path.read_bytes()


def test_a_pool_too_small_for_distinct_lineups_delivers_partial(tmp_path):
    salary = tiny_classic(tmp_path)
    entries = tiny_classic_template(tmp_path, 7)

    outcome = run(tmp_path, salary, entries)

    truths = outcome.truths
    authorized = [entry.entry_id for entry in parse_entries(entries).authorizations]
    assert truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert outcome.exit_code == 3
    assert list(truths.delivered_entry_ids) == authorized[:5]
    assert list(truths.unfilled_entry_ids) == authorized[5:]
    assert codes(outcome)["BASELINE_DISTINCT_LINEUPS_EXHAUSTED"] == tuple(authorized[5:])

    # The five delivered lineups are every legal lineup the pool holds.
    slate = parse_salaries(salary)
    legal = {validate_lineup(slate, combo).lineup.canonical_key
             for combo in _classic_rosters(slate) if validate_lineup(slate, combo).valid}
    rosters = delivered_rosters(outcome)
    assert {validate_lineup(slate, r).lineup.canonical_key for r in rosters.values()} == legal
    totals = [validate_lineup(slate, r).lineup.salary for r in rosters.values()]
    assert totals == sorted(totals, reverse=True) and totals[0] == max(
        validate_lineup(slate, combo).lineup.salary
        for combo in _classic_rosters(slate) if validate_lineup(slate, combo).valid)

    # The unfilled rows leave byte-identical; the report names them.
    source_lines = entries.read_bytes().split(b"\r\n")
    output_lines = outcome.output_path.read_bytes().split(b"\r\n")
    assert source_lines[6:] == output_lines[6:]
    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert report["release_truths"]["unfilled_entry_ids"] == authorized[5:]
    assert report["construction"]["stop_reason"] == "DISTINCT_LINEUPS_EXHAUSTED"


def _classic_rosters(slate):
    by_pos = {pos: [p.dk_id for p in slate.players if p.position == pos]
              for pos in ("QB", "RB", "WR", "TE", "DST")}
    flex_pool = by_pos["RB"] + by_pos["WR"] + by_pos["TE"]
    for qb, dst in itertools.product(by_pos["QB"], by_pos["DST"]):
        for rbs in itertools.combinations(by_pos["RB"], 2):
            for wrs in itertools.combinations(by_pos["WR"], 3):
                for te in by_pos["TE"]:
                    for flex in flex_pool:
                        if flex not in (*rbs, *wrs, te):
                            yield (qb, *rbs, *wrs, te, flex, dst)


def test_a_different_captain_is_a_different_lineup(tmp_path):
    """R29 identity: six people, all six in every lineup, so six captains and no more."""

    salary = tiny_showdown(tmp_path)
    entries = showdown_template(tmp_path, 8, salary)

    outcome = run(tmp_path, salary, entries)

    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert len(truths.delivered_entry_ids) == 6 and len(truths.unfilled_entry_ids) == 2
    slate = parse_salaries(salary)
    rosters = delivered_rosters(outcome).values()
    people = {frozenset(slate.players[[p.dk_id for p in slate.players].index(i)].underlying_id
                        for i in roster) for roster in rosters}
    assert len(people) == 1  # the same six people every time
    assert len({roster[0] for roster in rosters}) == 6  # a different captain each time
    assert codes(outcome)["BASELINE_DISTINCT_LINEUPS_EXHAUSTED"] == truths.unfilled_entry_ids


# ------------------------------------------------------------ must hold


def test_avg_points_per_game_is_never_read(tmp_path):
    """Scrambling every AvgPointsPerGame cell, in both files, moves no lineup."""

    salary_rows = rows_of(CLASSIC_SALARY.read_bytes())
    column = salary_rows[0].index("AvgPointsPerGame")
    for n, row in enumerate(salary_rows[1:]):
        row[column] = "not-a-number" if n % 2 else str(10_000 - n)
    mutated_salary = write_rows(tmp_path / "salary_appg.csv", salary_rows)
    entry_rows = rows_of(CLASSIC_ENTRIES_20.read_bytes())
    table_row = next(i for i, row in enumerate(entry_rows) if "AvgPointsPerGame" in row)
    entry_column = entry_rows[table_row].index("AvgPointsPerGame")
    for row in entry_rows[table_row + 1:]:
        if len(row) > entry_column:
            row[entry_column] = "-1e308"
    mutated_entries = write_rows(tmp_path / "entries_appg.csv", entry_rows)

    original = run(tmp_path, CLASSIC_SALARY, CLASSIC_ENTRIES_20, run_id="appg-original")
    mutated = run(tmp_path, mutated_salary, mutated_entries, run_id="appg-mutated")

    assert original.truths.delivery_state is DeliveryState.DELIVERABLE
    assert delivered_rosters(original) == delivered_rosters(mutated)
    assert "AvgPointsPerGame" not in (REPO / "src" / "nfl_dfs" / "baseline.py").read_text(
        encoding="utf-8")


def test_a_prefilled_row_is_refused_as_today(tmp_path):
    slate = parse_salaries(tiny_showdown(tmp_path))
    lineup = [p.dk_id for p in slate.players if p.role == "CPT"][:1] + [
        p.dk_id for p in slate.players if p.role == "FLEX"][1:6]
    entries = showdown_template(tmp_path, 3, tmp_path / "tiny_showdown_salaries.csv",
                                prefilled={2: lineup})

    outcome = run(tmp_path, tmp_path / "tiny_showdown_salaries.csv", entries)

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert outcome.exit_code == 2 and outcome.output_path is None
    assert codes(outcome)["ENTRY_BLANK_CELL_AUTHORITY_REQUIRED"] == ("4880000002",)
    assert not list(outcome.run_dir.glob("DK_*.csv"))


def test_a_classic_showdown_mismatch_hard_stops(tmp_path):
    outcome = run(tmp_path, CLASSIC_SALARY, showdown_template(tmp_path, 2))

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "DK_TEMPLATE_MODE_MISMATCH" in codes(outcome)
    assert outcome.output_path is None and outcome.exit_code == 2


def test_inputs_are_bound_by_schema_not_by_flag(tmp_path):
    swapped = run(tmp_path, CLASSIC_ENTRIES_20, CLASSIC_SALARY, run_id="swapped")
    assert swapped.truths.delivery_state is DeliveryState.DELIVERABLE
    report = json.loads(swapped.report_path.read_text(encoding="utf-8"))
    assert report["inputs"]["salaries"]["supplied_as"] == "--entries"
    assert report["inputs"]["entries"]["supplied_as"] == "--salaries"

    payout = tmp_path / "payouts.csv"
    payout.write_text("rank_start,rank_end,prize_type,value\n1,1,CASH,100\n", encoding="utf-8")
    refused = run(tmp_path, payout, CLASSIC_ENTRIES_20, run_id="unclassified")
    assert refused.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "BASELINE_INPUT_SCHEMA_UNRESOLVED" in codes(refused)


def test_the_entries_pool_table_must_hold_the_exact_salary_ids(tmp_path):
    rows = rows_of(CLASSIC_ENTRIES_20.read_bytes())
    table_row = next(i for i, row in enumerate(rows) if "AvgPointsPerGame" in row)
    column = rows[table_row].index("ID", rows[table_row].index("Position"))
    rows[table_row + 3][column] = "99999999"
    entries = write_rows(tmp_path / "other_slate.csv", rows)

    outcome = run(tmp_path, CLASSIC_SALARY, entries)

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "BASELINE_ENTRY_POOL_ID_MISMATCH" in codes(outcome)


def test_a_template_without_the_pool_table_ships_and_says_so(tmp_path):
    outcome = run(tmp_path, SHOWDOWN_SALARY, showdown_template(tmp_path, 3, pool=False))

    assert outcome.truths.delivery_state is DeliveryState.DELIVERABLE
    assert "BASELINE_ENTRY_POOL_CROSS_CHECK_UNAVAILABLE" in codes(outcome)


@pytest.mark.parametrize(("mutate", "code"), [
    (lambda rows: rows.__setitem__(3, rows[3][:4]), "DK_SALARY_ROW_SHORT"),
    (lambda rows: rows[3].__setitem__(3, rows[2][3]), "DK_SALARY_ID_INVALID"),
    # A missing required column fails the schema classifier before the parser.
    (lambda rows: [row.pop(5) for row in rows], "BASELINE_INPUT_SCHEMA_UNRESOLVED"),
    (lambda rows: [row.append(row[5]) for row in rows], "DK_SALARY_COLUMNS_DUPLICATED"),
    (lambda rows: rows[4].__setitem__(6, "bad game info"), "DK_SALARY_GAME_INFO_INVALID"),
])
def test_a_broken_salary_file_is_refused_by_name(tmp_path, mutate, code):
    rows = rows_of(CLASSIC_SALARY.read_bytes())
    mutate(rows)
    outcome = run(tmp_path, write_rows(tmp_path / "broken.csv", rows), CLASSIC_ENTRIES_20)

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert code in codes(outcome), codes(outcome)
    assert outcome.output_path is None


# ------------------------------------------------------------ budget and writer


def test_an_exhausted_run_budget_ships_what_it_built_and_names_the_rest(tmp_path):
    salary = tiny_classic(tmp_path)
    entries = tiny_classic_template(tmp_path, 4)
    ticks = itertools.count()

    outcome = run(tmp_path, salary, entries, budget_seconds=10.0,
                  clock=lambda: 4.0 * next(ticks))

    truths = outcome.truths
    assert truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    found = codes(outcome)
    assert "BASELINE_RUN_BUDGET_EXHAUSTED" in found
    assert found["UNFILLED_AUTHORIZED_ROWS"] == truths.unfilled_entry_ids
    family = load_gate_registry().family_of("BASELINE_RUN_BUDGET_EXHAUSTED")
    assert family.gate_class is GateClass.S


def test_the_same_bytes_give_the_same_file_replayed_from_a_copied_snapshot(tmp_path):
    first = run(tmp_path, CLASSIC_SALARY, CLASSIC_ENTRIES_20, run_id="first")
    copied = tmp_path / "copied"
    copied.mkdir()
    for snapshot in (first.run_dir / "inputs").iterdir():
        (copied / snapshot.name).write_bytes(snapshot.read_bytes())
    salary, entries = sorted(copied.iterdir(), key=lambda path: path.read_bytes().startswith(b"Entry ID"))

    second = run(tmp_path, salary, entries, run_id="second")

    assert first.output_path.read_bytes() == second.output_path.read_bytes()
    first_report = json.loads(first.report_path.read_text(encoding="utf-8"))
    second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert first_report["lineups"] == [
        {**row, "solve_seconds": first_row["solve_seconds"]}
        for row, first_row in zip(second_report["lineups"], first_report["lineups"])]


def test_a_template_changed_during_the_run_withholds_the_file(tmp_path, monkeypatch):
    real = baseline.build_distinct_lineups

    def tamper(*args, **kwargs):
        built = real(*args, **kwargs)
        for path in (tmp_path / "runs" / "tamper" / "inputs").glob("*.csv"):
            if path.read_bytes().startswith(b"Entry ID"):
                path.write_bytes(path.read_bytes() + b"\r\n")
        return built

    monkeypatch.setattr(baseline, "build_distinct_lineups", tamper)
    outcome = run(tmp_path, SHOWDOWN_SALARY, showdown_template(tmp_path, 2), run_id="tamper")

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE" in codes(outcome)
    assert not list(outcome.run_dir.glob("DK_*.csv"))


def test_the_independent_audit_withholds_bytes_the_writer_got_wrong(tmp_path, monkeypatch):
    real = baseline.write_upload_bytes

    def corrupt(template, assignments, **kwargs):
        raw = real(template, assignments, **kwargs)
        first = next(iter(assignments.values()))
        return raw.replace(first[1].encode(), first[2].encode(), 1)

    monkeypatch.setattr(baseline, "write_upload_bytes", corrupt)
    outcome = run(tmp_path, SHOWDOWN_SALARY, showdown_template(tmp_path, 3))

    assert outcome.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "BYTE_AUDIT" in codes(outcome)
    assert not list(outcome.run_dir.glob("DK_*.csv"))


def test_a_run_folder_is_never_reused(tmp_path):
    entries = showdown_template(tmp_path, 1)
    first = run(tmp_path, SHOWDOWN_SALARY, entries, run_id="once")
    before = first.output_path.read_bytes()

    second = run(tmp_path, SHOWDOWN_SALARY, entries, run_id="once")

    assert second.truths.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "RUN_ID_COLLISION" in codes(second)
    assert first.output_path.read_bytes() == before


def test_every_limitation_is_built_from_the_registry(tmp_path):
    registry = load_gate_registry()
    outcome = run(tmp_path, tiny_classic(tmp_path),
                  tiny_classic_template(tmp_path, 6))

    for item in outcome.truths.delivery_limitations:
        family = registry.family_of(item.code)
        assert (item.gate_class, item.stops, item.provenance) == (
            family.gate_class, family.stops, family.provenance)
    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert report["gate_registry_sha256"] == registry.sha256


def test_the_objective_is_registered_with_what_it_does_not_establish():
    objective = baseline.OBJECTIVE
    assert objective["version"] == baseline.OBJECTIVE_VERSION == "BASELINE_SALARY_RANK_V1"
    assert objective["direction"] == "MAXIMIZE" and objective["does_not_establish"]
    contracts = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    for name in ("BASELINE_SALARY_RANK_V1", "nfl_baseline_entry_csv_v1", "nfl_baseline_report_v1"):
        assert name in contracts


# ------------------------------------------------------------ shared pieces


def test_the_writer_fills_a_named_subset_and_refuses_anything_else(tmp_path):
    salary = tiny_classic(tmp_path)
    template = parse_entries(tiny_classic_template(tmp_path, 3))
    slate = parse_salaries(salary)
    roster = next(c for c in _classic_rosters(slate) if validate_lineup(slate, c).valid)
    first, second, third = (entry.entry_id for entry in template.authorizations)

    raw = write_upload_bytes(template, {first: roster}, unfilled=(second, third))
    lines = raw.split(b"\r\n")
    assert lines[2:] == template.path.read_bytes().split(b"\r\n")[2:]
    with pytest.raises(LineupValidationError, match="ENTRY_AUTHORIZATION_MISMATCH"):
        write_upload_bytes(template, {first: roster}, unfilled=(second,))
    with pytest.raises(LineupValidationError, match="ENTRY_AUTHORIZATION_MISMATCH"):
        write_upload_bytes(template, {first: roster}, unfilled=(first, second, third))
    with pytest.raises(LineupValidationError, match="ENTRY_AUTHORIZATION_MISMATCH"):
        write_upload_bytes(template, {first: roster, "999": roster}, unfilled=(second, third))


def test_a_prefilled_row_is_refused_by_the_writer_even_when_left_unfilled(tmp_path):
    salary = tiny_showdown(tmp_path)
    slate = parse_salaries(salary)
    lineup = [p.dk_id for p in slate.players if p.role == "CPT"][:1] + [
        p.dk_id for p in slate.players if p.role == "FLEX"][1:6]
    template = parse_entries(showdown_template(tmp_path, 2, salary, prefilled={2: lineup}))
    first, second = (entry.entry_id for entry in template.authorizations)

    with pytest.raises(LineupValidationError, match="ENTRY_BLANK_CELL_AUTHORITY_REQUIRED"):
        write_upload_bytes(template, {first: tuple(lineup)}, unfilled=(second,))


def test_the_salary_floor_keeps_every_solve_at_or_above_it(tmp_path):
    slate = parse_salaries(tiny_classic(tmp_path))
    optimizer = LineupOptimizer(slate)
    zero = {p.dk_id: 0.0 for p in slate.players}
    optimizer.set_salary_floor(38_800)  # the five lineups total 39,000 down to 38,600
    result = optimizer.solve(zero)
    assert result.validation.lineup.salary >= 38_800
    optimizer.set_salary_floor(39_100)
    assert optimizer.solve(zero).status == "INFEASIBLE"
    optimizer.set_salary_floor(None)
    assert optimizer.solve(zero).roster is not None
    with pytest.raises(ValueError):
        optimizer.set_salary_floor(-1)


def test_the_parser_and_validator_name_their_refusals(tmp_path):
    showdown = parse_salaries(SHOWDOWN_SALARY)
    with pytest.raises(DraftKingsParseError, match="^DK_TEMPLATE_MODE_MISMATCH: template is CLASSIC"):
        reconcile_template(parse_entries(CLASSIC_ENTRIES_20), showdown)
    cpt = next(p.dk_id for p in showdown.players if p.role == "CPT")
    errors = validate_lineup(showdown, (cpt, "1", "2", "3", "4", "")).errors
    assert all(error.split(":")[0] in {"LINEUP_BLANK_CELL", "LINEUP_DK_ID_NOT_IN_POOL"}
               for error in errors), errors


def test_the_cli_runs_the_baseline_and_prints_its_truths(tmp_path, capsys):
    entries = showdown_template(tmp_path, 2)
    code = main(["baseline", "--salaries", str(SHOWDOWN_SALARY), "--entries", str(entries),
                 "--out-dir", str(tmp_path / "cli"), "--run-id", "cli-run"])

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["DELIVERY_STATE"] == "DELIVERABLE"
    assert printed["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and printed["status"] == "DO_NOT_UPLOAD"
    assert "PRIOR_ONLY" in printed["warning"] and "DO_NOT_UPLOAD" in printed["warning"]
    assert Path(printed["baseline_entry_csv"]).is_file()
    assert printed["unfilled_entry_ids"] == []
