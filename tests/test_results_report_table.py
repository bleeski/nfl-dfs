"""Session 71c: the readable results table written once beside the `nfl_results_report_v1` JSON.

Synthetic bytes only, built with Session 69's and Session 71b's helpers and taken in through `results-intake`; Ben's
export carries winnings and never enters the repository. The table carries money and sits under the gitignored results
root beside the JSON, which already carries it; stdout stays money-free (`test_stdout_carries_no_money`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nfl_dfs import entry_history
from nfl_dfs import results_report as rr
from nfl_dfs.hashing import sha256_bytes
from tests.test_entry_history import _history, _row
from tests.test_results_report_command import ERA, FAST, RAW, REGISTERED, REPO, _intake, _run, _target

# The JSON `RAW` gives under the registered metrics, hashed on the unmodified tree before Session 71c's first edit. Two
# slates, so every slice stops before the bootstrap: each figure is exact and the hash is the same on every platform.
PIN = "c386564fca63a99d37e4b626d837e6d61b9dee1c82aa47f0016a67b44b4da1ea"
# The table beside it. Its layout is frozen under `w1` with the JSON: a changed byte at the old name would refuse a
# rerun beside a table already on disk, so a layout change takes a new writer and a new pin.
TABLE_PIN = "8bb4f8dbb314358fc2e0dd1ba5ec26fa2897876a086ccc7d5c11203c4a6aa80f"
OVERALL = "## Overall"
WITHIN = "## Within-slate test: top-heavy against flatter"
RATES = (("Percentile % (random), lower is better", "percentile"), ("Top 10% (random), higher is better", "top_10"),
         ("Bottom 10% (random), lower is better", "bottom_10"))
DECIMAL = re.compile(r"-?\$?[0-9][0-9,]*\.[0-9]+")
MONEY = re.compile(r"-?\$[0-9]{1,3}(,[0-9]{3})*\.[0-9]{2}")


def _fixture(days: tuple[str, ...]) -> bytes:
    """Each day a top-heavy (10 of 1,000 paid) and a flatter (200 of 1,000) contest; fees above winnings, one blank,
    and an MLB entry for the all-sport column."""

    rows = []
    for index, day in enumerate(days):
        for side, paid in enumerate(("10", "200")):
            number = 2 * index + side
            rows.append(_row(Entry_Key=str(4200000000 + number), Contest_Key=str(120000000 + number),
                             Contest_Date_EST=f"{day} 13:00:00", Place=str((137 * number + 61) % 1000 + 1),
                             Places_Paid=paid, Points="0" if number == 3 else "120",
                             Winnings_Non_Ticket="$12.50" if number % 5 == 0 else "$0.00"))
    rows.append(_row(Sport="MLB", Entry_Key="4200000999", Contest_Key="120000999",
                     Contest_Date_EST="2026-07-04 19:05:00", Place="3", Points="12", Winnings_Non_Ticket="$0.00",
                     Contest_Entries="50", Entry_Fee="$1.00", Prize_Pool="$45.00", Places_Paid="10"))
    return _history(*rows)


# One slate before the era, so the NFL and engine-era columns differ, then six from 2026-09-13.
MAIN = _fixture(("2026-09-06", *(f"2026-09-{13 + index:02d}" for index in range(6))))
EARLY = _fixture(("2026-09-01", "2026-09-02"))  # every NFL slate before the era: the engine era is empty


def _table_path(root: Path, sha: str, era: str = ERA) -> Path:
    return root / "reports" / sha / f"results_report.era-{era}.w1.md"


def _written(tmp_path: Path, raw: bytes = MAIN) -> tuple[Path, str, dict, str]:
    root, sha = _intake(tmp_path, raw)
    outcome = _run(root, sha)
    assert outcome.status == "COMPLETE", outcome.problems
    return root, sha, json.loads(_target(root, sha).read_bytes()), _table_path(root, sha).read_bytes().decode("utf-8")


def _cells(lines: list[str], heading: str) -> list[list[str]]:
    """The data rows of the first table under `heading`, each row's cells stripped; header and rule left out."""

    rows = []
    for line in lines[lines.index(heading) + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return [row for row in rows[1:] if set(row) != {"---"}]


def _grid(lines: list[str], heading: str) -> dict[str, list[str]]:
    return {row[0]: row[1:] for row in _cells(lines, heading)}


def _cents(token: str) -> int:
    assert MONEY.fullmatch(token), token
    value = int(token.lstrip("-").replace("$", "").replace(",", "").replace(".", ""))
    return -value if token.startswith("-") else value


def _assert_group(rows: list[list[str]], band: str, label: str, block: dict) -> None:
    """One group's three lines against its slice: band, label, entries and slates on the first line only, then each
    rate beside random and its excess's estimate, interval (or `n/a` and the reason) and MDE."""

    assert rows[0][:4] == [band, label, str(block["entries"]), str(block["slates"])]
    assert [row[:4] for row in rows[1:]] == [["", "", "", ""]] * 2
    for row, (title, name) in zip(rows, (("Percentile", "percentile"), ("Top 10%", "top_10"),
                                         ("Bottom 10%", "bottom_10"))):
        figures = block["uncertainty"][f"{name}_excess"]
        pair = block["with_blanks"][name]
        interval = figures["interval"]
        span = f"[{interval['low']}, {interval['high']}]" if interval else f"n/a ({figures['reason']})"
        assert row[4:] == [title, f"{pair['realized']} ({pair['random']})", figures["estimate"], span,
                           "n/a" if figures["mde"] is None else figures["mde"]]


def _columns(payload: dict) -> list[dict]:
    scopes = payload["scopes"]
    return [scopes["nfl"]["overall"], scopes["engine_era"]["overall"], payload["all_sport_check"]["overall"]]


def _strings_and_cents(value: object, strings: set[str], cents: set[int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_cents") and isinstance(item, int):
                cents.add(item)
            _strings_and_cents(item, strings, cents)
    elif isinstance(value, list):
        for item in value:
            _strings_and_cents(item, strings, cents)
    elif isinstance(value, str):
        strings.add(value)


# ------------------------------------------------------------------------------------------- the acceptance


def test_the_table_figures_equal_the_json_as_strings(tmp_path):
    *_, payload, text = _written(tmp_path)
    lines = text.splitlines()
    columns = _columns(payload)
    overall = _grid(lines, OVERALL)
    assert overall["Entries"] == ["14", "12", "15"]  # the fixture's three columns differ, so a swapped one shows
    for label, key in (("Entries", "entries"), ("Slates", "slates"), ("Blanks", "blanks")):
        assert overall[label] == [str(block[key]) for block in columns], label
    for label, key in (("Realized return on fees, %", "realized_return_on_fees"),
                       ("Rake-implied return, %", "rake_implied_return")):
        assert overall[label] == [block[key] for block in columns], label
    for label, name in RATES:
        assert overall[label] == [f"{block['with_blanks'][name]['realized']} ({block['with_blanks'][name]['random']})"
                                  for block in columns], label
    tests = [payload["scopes"][scope]["within_slate_test"] for scope in ("nfl", "engine_era")]
    within = _grid(lines, WITHIN)
    assert within["Slates with both"] == [str(test["slates_with_both"]) for test in tests]
    assert within["Top-heavy worse / better / tied"] == [f"{test['worse']} / {test['better']} / {test['tied']}"
                                                         for test in tests]
    assert within["Mean difference, points"] == [test["mean_difference_points"] for test in tests]
    assert within["p, one-sided"] == [test["p_one_sided"] for test in tests]
    assert within["p, two-sided"] == [test["p_two_sided"] for test in tests]
    fresh = [test["after_registration"] for test in tests]
    assert within["After registration: slates with both"] == [str(block["slates_with_both"]) for block in fresh]
    assert within["After registration: worse / better"] == [f"{block['worse']} / {block['better']}" for block in fresh]
    assert within["After registration: p, one-sided"] == [block["p_one_sided"] for block in fresh]
    # Both payout sections, every group (All shapes first) line by line; the two scopes differ on this fixture.
    for scope, title in (("nfl", "NFL"), ("engine_era", "engine era")):
        block = payload["scopes"][scope]
        rows = _cells(lines, f"## Payout shape, {title}")
        groups = [("All shapes", "", block["overall"]),
                  *((band["band"], band["first_place_label"] or "n/a", band) for band in block["by_payout_shape"])]
        assert len(rows) == 3 * len(groups) == 9
        for index, (band, label, figures) in enumerate(groups):
            _assert_group(rows[3 * index:3 * index + 3], band, label, figures)
    # One interval pinned (correctly rounded arithmetic only); no bottom-10% finish, so that excess has no spread.
    rows = _cells(lines, "## Payout shape, engine era")
    assert rows[3][:2] == ["[0, 1/20)", "FIRST_PLACE_OBJECTIVE"] and rows[3][7] == "[-23.0765, 24.6811]"
    assert rows[5][7:] == ["n/a (ZERO_STANDARD_ERROR)", "n/a"]
    # Every decimal figure anywhere in the table is the payload's own string, or money whose cents it holds.
    strings: set[str] = set()
    cents: set[int] = set()
    _strings_and_cents(payload, strings, cents)
    tokens = DECIMAL.findall(text)
    assert len(tokens) > 60
    for token in tokens:
        assert (_cents(token) in cents) if "$" in token else (token in strings), token


def test_the_overall_section_with_fees_and_net_is_in_the_first_20_lines(tmp_path):
    *_, payload, text = _written(tmp_path)
    lines = text.splitlines()
    start = lines.index(OVERALL)
    end = next(index for index in range(start + 1, len(lines)) if lines[index].startswith("## "))
    assert end <= 20  # the whole section, its table included, sits in lines[:20]
    overall = _grid(lines[:20], OVERALL)
    assert list(overall) == ["Entries", "Slates", "Blanks", "Fees", "Net, tickets at face value",
                             "Realized return on fees, %", "Rake-implied return, %", *(label for label, _ in RATES)]
    assert overall["Fees"] == ["$70.00", "$60.00", "$71.00"]
    assert [_cents(cell) for cell in overall["Fees"]] == [block["fees_cents"] for block in _columns(payload)]
    assert [_cents(cell) for cell in overall["Net, tickets at face value"]] == [
        block["net_cents"] for block in _columns(payload)]
    assert lines[start + 2] == "|  | NFL | Engine era | All sports |"


def test_a_rerun_beside_a_report_on_disk_writes_only_the_table(tmp_path):
    root, sha = _intake(tmp_path, MAIN)
    assert _run(root, sha).status == "COMPLETE"
    report, table = _target(root, sha), _table_path(root, sha)
    before = (report.read_bytes(), report.stat().st_mtime_ns)
    first = table.read_bytes()
    table.unlink()  # what a run of Session 71b's code leaves: the JSON alone, whose bytes do not move
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code, outcome.problems) == ("COMPLETE", 0, ())
    assert outcome.files["report"]["state"] == "ALREADY_PRESENT"
    assert outcome.files["table"] == {"path": str(table), "state": "WRITTEN", "sha256": sha256_bytes(first)}
    assert (report.read_bytes(), report.stat().st_mtime_ns) == before and table.read_bytes() == first
    again = _run(root, sha)
    assert (again.status, again.files["table"]["state"]) == ("ALREADY_PRESENT", "ALREADY_PRESENT")


def test_two_runs_give_byte_identical_tables(tmp_path):
    tables = []
    for name in ("one", "two"):
        root, sha = _intake(tmp_path / name, MAIN)
        assert _run(root, sha).status == "COMPLETE"
        tables.append(_table_path(root, sha).read_bytes())
    assert tables[0] == tables[1]
    # A function of the written JSON alone: its sorted keys rebuild the same bytes.
    assert rr.render_table(json.loads(_target(root, sha).read_bytes())) == tables[1]
    assert tables[1].isascii() and tables[1].endswith(b"\n") and b"\r" not in tables[1]


def test_the_json_bytes_do_not_move(tmp_path):
    root, sha = _intake(tmp_path, RAW)
    outcome = _run(root, sha, metrics=REGISTERED)
    assert outcome.status == "COMPLETE"
    assert sha256_bytes(_target(root, sha).read_bytes()) == outcome.files["report"]["sha256"] == PIN
    assert "table" not in json.loads(_target(root, sha).read_bytes())


def test_the_table_layout_is_frozen_under_w1(tmp_path):
    root, sha = _intake(tmp_path, RAW)
    outcome = _run(root, sha, metrics=REGISTERED)
    assert sha256_bytes(_table_path(root, sha).read_bytes()) == outcome.files["table"]["sha256"] == TABLE_PIN


# ------------------------------------------------------------------------------------------- figures


def test_a_negative_net_prints_with_a_leading_minus(tmp_path):
    assert [rr._dollars(cents) for cents in (-14596, -5, 0, 5, 100, 123456789)] == [
        "-$145.96", "-$0.05", "$0.00", "$0.05", "$1.00", "$1,234,567.89"]
    *_, text = _written(tmp_path)
    [net] = [line for line in text.splitlines() if line.startswith("| Net, ")]
    assert net == "| Net, tickets at face value | -$32.50 | -$35.00 | -$33.50 |"


def test_an_empty_scope_prints_no_zero(tmp_path):
    *_, payload, text = _written(tmp_path, EARLY)
    era = payload["scopes"]["engine_era"]
    assert era["overall"]["entries"] == 0 and era["overall"]["realized_return_on_fees"] is None
    lines = text.splitlines()
    overall = _grid(lines, OVERALL)
    nulls = ["Realized return on fees, %", "Rake-implied return, %", *(label for label, _ in RATES)]
    assert [overall[label][1] for label in nulls] == ["n/a"] * 5
    assert [overall[label][0] for label in nulls] != ["n/a"] * 5  # the NFL column holds figures
    # Counts and money are the payload's own integer zeros.
    assert [overall[label][1] for label in ("Entries", "Slates", "Blanks", "Fees", "Net, tickets at face value")] == [
        "0", "0", "0", "$0.00", "$0.00"]
    section = text.split("\n## Payout shape, engine era\n", 1)[1].split("\n## ", 1)[0]
    assert section.strip() == "No entries in this scope."
    assert _grid(lines, WITHIN)["Mean difference, points"][1] == "n/a"


def test_a_null_label_and_a_short_slice_print_n_a(tmp_path):
    *_, payload, text = _written(tmp_path, RAW)
    [band] = payload["scopes"]["nfl"]["by_payout_shape"]
    assert band["first_place_label"] is None
    assert band["uncertainty"]["percentile_excess"]["reason"] == "FEWER_THAN_5_SLATES"
    rows = _cells(text.splitlines(), "## Payout shape, NFL")
    start = [row[0] for row in rows].index(band["band"])
    assert rows[start][1] == "n/a" and rows[start][6] == band["uncertainty"]["percentile_excess"]["estimate"]
    assert rows[start][7:] == ["n/a (FEWER_THAN_5_SLATES)", "n/a"]
    assert rows[0][:2] == ["All shapes", ""]  # the overall slice has no label field: an empty cell, not a null


# ------------------------------------------------------------------------------------------- the writer


def test_another_file_at_the_table_name_is_never_overwritten(tmp_path):
    root, sha = _intake(tmp_path, MAIN)
    table = _table_path(root, sha)
    table.parent.mkdir(parents=True)
    table.write_bytes(b"# not this report\n")
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code, outcome.problems) == (
        "REFUSED", 2, ("RESULTS_REPORT_ARTIFACT_CONFLICT:file=table",))
    assert outcome.files["report"]["state"] == "WRITTEN" and _target(root, sha).exists()
    assert outcome.files["table"]["state"] == "REFUSED" and "results-report" in outcome.files["table"]["recovery"]
    assert outcome.files["table"]["sha256"] is None and table.read_bytes() == b"# not this report\n"
    table.unlink()
    rerun = _run(root, sha)
    assert (rerun.status, rerun.files["report"]["state"], rerun.files["table"]["state"]) == (
        "COMPLETE", "ALREADY_PRESENT", "WRITTEN")


def test_a_table_write_failure_leaves_the_report(tmp_path, monkeypatch):
    root, sha = _intake(tmp_path, MAIN)
    real_link = entry_history.os.link

    def no_table(source, target):
        if Path(target).suffix == ".md":
            raise PermissionError("held")
        return real_link(source, target)

    monkeypatch.setattr(entry_history.os, "link", no_table)
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code) == ("WRITE_FAILED", 2)
    assert outcome.problems == ("RESULTS_REPORT_WRITE_FAILED:file=table:exception=PermissionError",)
    assert (outcome.files["report"]["state"], outcome.files["table"]["state"]) == ("WRITTEN", "WRITE_FAILED")
    assert _target(root, sha).exists() and not _table_path(root, sha).exists()  # by name: a dotted temporary may stay
    monkeypatch.undo()
    rerun = _run(root, sha)
    assert (rerun.status, rerun.files["report"]["state"], rerun.files["table"]["state"]) == (
        "COMPLETE", "ALREADY_PRESENT", "WRITTEN")


def test_a_refused_report_names_the_table_and_leaves_it_unwritten(tmp_path):
    root, sha = _intake(tmp_path, MAIN)
    _target(root, sha).parent.mkdir(parents=True)
    _target(root, sha).write_bytes(b"{}\n")
    outcome = _run(root, sha)
    assert (outcome.status, outcome.problems) == ("REFUSED", ("RESULTS_REPORT_ARTIFACT_CONFLICT:file=report",))
    # Both paths are known once the payload is built; the table waits behind the report.
    assert outcome.files["table"] == {"path": str(_table_path(root, sha)), "state": "NOT_ATTEMPTED", "sha256": None}
    assert not _table_path(root, sha).exists()


def test_a_render_fault_writes_nothing(tmp_path, monkeypatch):
    root, sha = _intake(tmp_path, MAIN)

    def broken(payload):
        raise RuntimeError("render fault")

    monkeypatch.setattr(rr, "render_table", broken)
    with pytest.raises(RuntimeError):
        _run(root, sha)
    assert not (root / "reports").exists()


def test_the_runbook_checklist_names_the_table(tmp_path):
    runbook = (REPO / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    section = runbook.split("\n## Contest screening checklist", 1)[1].split("\n## ", 1)[0]
    assert "results_report.era-" in section and ".w1.md" in section and rr.PAYOUT_SHAPE_HEADING in section
    guide = (REPO / "docs" / "OPERATOR_GUIDE.md").read_text(encoding="utf-8")
    assert ".w1.md" in guide.split("\n## Results report\n", 1)[1].split("\n## ", 1)[0]
    assert rr.table_name(ERA) == "results_report.era-2026-09-09.w1.md"
    *_, text = _written(tmp_path, RAW)
    for title in ("NFL", "engine era"):
        assert f"\n## {rr.PAYOUT_SHAPE_HEADING}, {title}\n" in text


def test_the_table_flags_what_it_does_not_establish(tmp_path):
    *_, payload, text = _written(tmp_path, RAW)
    assert text.splitlines()[0] == "# NFL results report"
    section = text.split("\n## Not established\n", 1)[1]
    for line in payload["does_not_establish"]:
        assert f"- {line}\n" in section
    assert "results_report.era-2026-09-09.w1.json" in section
    assert f"source `{payload['source']['sha256']}`" in text.splitlines()[2]
    trigger = payload["within_slate_trigger"]
    assert f"met: {json.dumps(trigger['met'])}" in text and trigger["when_met"] in text
    assert (f"Trigger, on {trigger['scope']} from {trigger['engine_era_start']} (registered {trigger['registered_on']}): "
            f"{trigger['slates']} slates against a minimum of {trigger['min_slates']}, p one-sided "
            f"{trigger['p_one_sided']} against alpha {trigger['alpha']};") in text
