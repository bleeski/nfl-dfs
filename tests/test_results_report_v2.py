"""Session 77: first place and washouts in the results report (R38; `nfl_results_metrics_v2`, `nfl_results_report_v2`).

Goal 1's realized reading, per contest: our best entry's place and percentile beside the best of that many random
places, and first-place and top-1% finishes beside each entry's random share. Goal 2's, per portfolio (the paid entries
sharing a contest start time and game type): whether every entry won nothing, beside a random draw's washout. v1's
metrics file, payload, file and table keep their bytes; a v2 report carries every v1 block unchanged. Fixtures are
synthetic bytes written with `write_bytes`; the account export never enters the repository.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from nfl_dfs import cli, contest_facts, entry_history
from nfl_dfs import results_report as rr
from nfl_dfs.hashing import sha256_bytes
from tests.test_entry_history import _history, _row
from tests.test_results_report import STANDARD, TOP_HEAVY, _contest
from tests.test_results_report_command import FIVE_SLATES, RAW, _intake
from tests.test_results_report_table import _cells, _grid

REPO = Path(__file__).resolve().parents[1]
V2_METRICS_SHA256 = "31b47fd054ef5f5df66b07466ebfe644608f6e0411e10ef210d8388e039ac7f1"
# The v1 payload of `BEST + WASHOUT`, hashed on the unmodified tree before Session 77's first edit to the module. No
# bootstrap: every figure is exact, so the hash is the same on every platform.
V1_FIXTURE_PIN = "1dac30d7d690913b91e7be80f52810d6c5dc3be320cf4913c5b783ef94768a06"
ZERO_SHA = "0" * 64
ERA = "2026-09-09"
V1 = rr.load_results_metrics()
V2 = rr.load_results_metrics(rr.METRICS_V2_PATH)
V2_FAST = dataclasses.replace(V2, bootstrap={**V2.bootstrap, "resamples": 200})

CLASSIC = dict(Contest_Date_EST="2026-09-13 13:00:00")
SMALL = dict(Contest_Entries="10", Entry_Fee="$1.00", Prize_Pool="$9.00", Places_Paid="2")
# Three entries in one 1,000-entry Classic (best place 12) and a Showdown entry that finished first of 10.
BEST = (
    _row(Entry_Key="4300000001", Contest_Key="200000001", Place="640", Points="88", Winnings_Non_Ticket="$0.00"),
    _row(Entry_Key="4300000002", Contest_Key="200000001", Place="12"),
    _row(Entry_Key="4300000003", Contest_Key="200000001", Place="300", Points="101", Winnings_Non_Ticket="$0.00"),
    _row(Game_Type="Showdown Captain Mode", Entry_Key="4300000004", Contest_Key="200000002",
         Contest_Date_EST="2026-09-14 20:15:00", Place="1", Points="150", Winnings_Non_Ticket="$5.00", **SMALL),
)
# Three portfolios: a Classic of two contests where nothing paid, a Showdown whose one entry won only a ticket, and an
# earlier Showdown the same day whose entry won cash. Two v1 slates, three portfolios.
WASHOUT = (
    _row(Entry_Key="4400000001", Contest_Key="210000001", Place="5", Winnings_Non_Ticket="$0.00", **CLASSIC, **SMALL),
    _row(Entry_Key="4400000002", Contest_Key="210000002", Place="3", Winnings_Non_Ticket="$0.00", **CLASSIC, **SMALL),
    _row(Entry_Key="4400000003", Contest_Key="210000002", Place="9", Winnings_Non_Ticket="$0.00", **CLASSIC, **SMALL),
    _row(Game_Type="Showdown Captain Mode", Entry_Key="4400000004", Contest_Key="210000003",
         Contest_Date_EST="2026-09-21 20:15:00", Place="2", Winnings_Non_Ticket="$0.00", Winnings_Ticket="$3.00",
         **SMALL),
    _row(Game_Type="Showdown Captain Mode", Entry_Key="4400000005", Contest_Key="210000004",
         Contest_Date_EST="2026-09-21 16:25:00"),
)
FORBIDDEN = re.compile(r"probabilit|chance|odds|equity|win rate|\bEV\b|\bROI\b", re.IGNORECASE)


def _report(*rows: list[str], era: str | None = None, metrics: rr.ResultsMetrics = V2, bootstrap: bool = False,
            source_bytes: int | None = None) -> dict:
    raw = _history(*rows)
    return rr.build_report(entry_history.parse_entry_history(raw), metrics=metrics, source_sha256=ZERO_SHA,
                           source_bytes=len(raw) if source_bytes is None else source_bytes, engine_era_start=era,
                           bootstrap=bootstrap)


def _by(rows: list[dict], key: str, value: object) -> dict:
    [found] = [row for row in rows if row[key] == value]
    return found


# --------------------------------------------------------------------------------------- the metrics file


def test_the_v2_metrics_file_is_the_pinned_bytes_and_copies_v1():
    raw = rr.METRICS_V2_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == V2_METRICS_SHA256, (
        "config/results_metrics_v2.json changed; a registered file is never mutated: register the next version")
    assert rr.METRICS_V2_PATH == REPO / "config" / "results_metrics_v2.json"
    assert (V2.version, V2.sha256) == ("nfl_results_metrics_v2", V2_METRICS_SHA256)
    # Every v1 field carries v1's value; only the version, the hash and the added lines differ.
    shared = {field.name for field in dataclasses.fields(rr.ResultsMetrics)} - {"version", "sha256",
                                                                               "does_not_establish"}
    assert {name: getattr(V2, name) for name in shared} == {name: getattr(V1, name) for name in shared}
    assert V2.does_not_establish[:len(V1.does_not_establish)] == V1.does_not_establish
    assert len(V2.does_not_establish) == len(V1.does_not_establish) + 4
    # The command's default, and where each registered version is read from at call time.
    assert rr.METRICS_VERSIONS == ("nfl_results_metrics_v1", "nfl_results_metrics_v2")
    assert rr.CURRENT_METRICS_VERSION == "nfl_results_metrics_v2"
    assert rr.registered_metrics_path("nfl_results_metrics_v1") == rr.DEFAULT_METRICS_PATH
    assert rr.registered_metrics_path("nfl_results_metrics_v2") == rr.METRICS_V2_PATH
    with pytest.raises(ValueError, match="metrics version"):
        rr.registered_metrics_path("nfl_results_metrics_v3")


def test_the_contracts_doc_names_the_v2_metrics_hash():
    assert V2_METRICS_SHA256 in (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")


def _v2_with(**changes: object) -> bytes:
    document = json.loads(rr.METRICS_V2_PATH.read_bytes())
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        target = document
        for parent in parents:
            target = target[parent]
        if value is _DELETE:
            del target[leaf]
        else:
            target[leaf] = value
    return json.dumps(document).encode("utf-8")


_DELETE = object()


@pytest.mark.parametrize(
    "raw",
    [
        _v2_with(schema_version="nfl_results_metrics_v1"),
        _v2_with(schema_version="nfl_results_metrics_v3"),
        _v2_with(first_place=_DELETE),
        _v2_with(washout=_DELETE),
        _v2_with(first_place__top_1="PLACE_TIMES_100_BELOW_N"),
        _v2_with(first_place__random_top_1="ONE_PERCENT"),
        _v2_with(first_place__surprise="X"),
        _v2_with(first_place__best_entry=_DELETE),
        _v2_with(washout__portfolio="SPORT_EASTERN_DATE_GAME_TYPE"),
        _v2_with(washout__random_washout=1),
        _v2_with(rates__top_10="PLACE_TIMES_10_BELOW_N"),
        _v2_with(bootstrap__seed=True),
        _v2_with(does_not_establish=[]),
    ],
    ids=["v1_schema_with_v2_sections", "unknown_schema", "no_first_place", "no_washout", "top_1_changed",
         "random_top_1_changed", "unknown_first_place_key", "missing_best_entry", "portfolio_changed",
         "random_washout_not_text", "v1_rule_changed", "bool_seed", "no_does_not_establish"],
)
def test_a_malformed_v2_metrics_file_is_refused_by_name(raw):
    with pytest.raises(rr.ResultsMetricsError, match="^results metrics "):
        rr.parse_results_metrics(raw)


# ------------------------------------------------------------------------------------ per-entry definitions


def test_each_new_reading_has_an_exact_random_expectation():
    assert rr.in_first(1) and not rr.in_first(2)
    assert [rr.random_first(n) for n in (1, 10, 1000)] == [1, Fraction(1, 10), Fraction(1, 1000)]
    # A top-1% finish is `place * 100 <= n`: impossible below 100 entries, as v1's top 10% is below 10.
    assert rr.in_top_1(1, 100) and not rr.in_top_1(2, 100) and not rr.in_top_1(1, 99)
    assert rr.in_top_1(2, 250) and not rr.in_top_1(3, 250)
    assert [rr.random_top_1(n) for n in (99, 100, 250, 1000)] == [0, Fraction(1, 100), Fraction(2, 250),
                                                                 Fraction(1, 100)]
    # The best of k random places: (n+1)/((k+1)n), v1's random percentile at k = 1.
    for n in (1, 5, 10, 1000):
        assert rr.random_best_percentile(n, 1) == rr.random_percentile(n)
    assert rr.random_best_percentile(10, 4) == Fraction(11, 50)
    # No entry in the paid places: C(n-p, k) / C(n, k), Places_Paid capped at n.
    assert rr.random_no_paid_place(10, 2, 1) == Fraction(4, 5)
    assert rr.random_no_paid_place(10, 2, 2) == Fraction(28, 45)
    assert rr.random_no_paid_place(10, 0, 3) == 1
    assert rr.random_no_paid_place(10, 8, 3) == 0  # three entries cannot all miss eight paid places of ten
    assert rr.random_no_paid_place(10, 12, 1) == 0  # 12 paid of 10 is all 10
    assert rr.random_washout([(10, 2, 1), (10, 2, 2)]) == Fraction(112, 225)
    assert rr.random_washout([]) == 1


def test_more_of_our_rows_than_the_field_still_reports():
    # A real export cannot hold this, and the parser does not refuse it; v1 reported it, so v2 caps k at n.
    assert rr.random_best_percentile(1, 2) == 1 and rr.random_no_paid_place(1, 0, 2) == 1
    assert rr.random_no_paid_place(1, 1, 2) == 0
    crowded = (_row(Place="1", Contest_Entries="1", Places_Paid="1"),
               _row(Entry_Key="4000000002", Place="1", Contest_Entries="1", Places_Paid="1"))
    scope = _report(*crowded)["scopes"]["nfl"]
    [contest] = scope["first_place"]["contests"]
    assert (contest["entries"], contest["random_best_percentile"], contest["first_place_random"]) == (2, "100.0000", "2")
    assert scope["washouts"]["by_portfolio"][0]["random_exact"] == "0"


def test_the_closed_forms_equal_a_full_enumeration():
    for n, k, paid in ((7, 3, 2), (6, 1, 0), (8, 4, 3), (5, 5, 1)):
        draws = list(itertools.combinations(range(1, n + 1), k))
        best = sum(Fraction(min(draw), n) for draw in draws) / len(draws)
        missed = Fraction(sum(min(draw) > paid for draw in draws), len(draws))
        assert rr.random_best_percentile(n, k) == best, (n, k)
        assert rr.random_no_paid_place(n, paid, k) == missed, (n, k, paid)


# --------------------------------------------------------------------------------------- goal 1: first place


def test_each_contest_reports_its_best_entry():
    first_place = _report(*BEST)["scopes"]["nfl"]["first_place"]
    classic, showdown = first_place["contests"]
    assert classic == {
        "contest_key": "200000001", "date": "2026-09-13", "game_type": "Classic", "contest_entries": 1000,
        "entries": 3, "band": "[1/5, 1/2)", "best_place": 12, "best_percentile": "1.2000",
        "random_best_percentile": "25.0250", "first_place_entries": 0, "first_place_random": "3/1000",
        "top_1_entries": 0, "top_1_random": "3/100"}
    assert showdown == {
        "contest_key": "200000002", "date": "2026-09-14", "game_type": "Showdown Captain Mode", "contest_entries": 10,
        "entries": 1, "band": "[1/5, 1/2)", "best_place": 1, "best_percentile": "10.0000",
        "random_best_percentile": "55.0000", "first_place_entries": 1, "first_place_random": "1/10",
        "top_1_entries": 0, "top_1_random": "0"}
    assert first_place["overall"] == {
        "contests": 2, "entries": 4,
        "best_percentile": {"realized": "5.6000", "random": "40.0125"},  # (12/1000 + 1/10) / 2; (1001/4000 + 11/20) / 2
        "first_place": {"entries": 1, "random": "0.103000"},  # 3/1000 + 1/10
        "top_1": {"entries": 0, "random": "0.030000"}}  # 3 * 10/1000; no top 1% in a field of 10


def test_a_tie_for_first_counts_each_entry_as_given():
    tied = (_row(Place="1", **SMALL), _row(Entry_Key="4000000002", Place="1", **SMALL))
    [contest] = _report(*tied)["scopes"]["nfl"]["first_place"]["contests"]
    assert (contest["best_place"], contest["first_place_entries"], contest["first_place_random"]) == (1, 2, "1/5")


def test_the_random_expectations_are_exact_fractions():
    rows = (_row(Contest_Key="220000001", Place="4", **SMALL),
            _row(Entry_Key="4000000002", Contest_Key="220000002", Place="500"),
            _row(Entry_Key="4000000003", Contest_Key="220000002", Place="700"))
    first_place = _report(*rows)["scopes"]["nfl"]["first_place"]
    assert sum(Fraction(row["first_place_random"]) for row in first_place["contests"]) == Fraction(51, 500)
    assert first_place["overall"]["first_place"] == {"entries": 0, "random": "0.102000"}  # 1/10 + 2/1000, exactly
    assert sum(Fraction(row["top_1_random"]) for row in first_place["contests"]) == Fraction(1, 50)
    assert first_place["overall"]["top_1"]["random"] == "0.020000"


def test_first_place_counts_split_by_payout_band():
    top_heavy = _row(Contest_Key="230000001", Place="1", Places_Paid=TOP_HEAVY)
    flatter = _row(Entry_Key="4000000002", Contest_Key="230000002", Place="9")
    shapes = _report(top_heavy, flatter)["scopes"]["nfl"]["first_place"]["by_payout_shape"]
    assert [(row["band"], row["first_place_label"], row["contests"], row["first_place"]["entries"],
             row["top_1"]["entries"]) for row in shapes] == [
        ("[0, 1/20)", "FIRST_PLACE_OBJECTIVE", 1, 1, 1), ("[1/5, 1/2)", None, 1, 0, 1)]


# ---------------------------------------------------------------------------------------- goal 2: washouts


def test_a_portfolio_with_no_prize_is_a_washout():
    scope = _report(*WASHOUT)["scopes"]["nfl"]
    washouts = scope["washouts"]
    assert scope["slates"] == 2 and scope["fine_slates"] == 3
    assert [(row["contest_start"], row["game_type"], row["entries"], row["contests"], row["washout"])
            for row in washouts["by_portfolio"]] == [
        ("2026-09-13T13:00:00-04:00", "Classic", 3, 2, True),
        ("2026-09-21T16:25:00-04:00", "Showdown Captain Mode", 1, 1, False),  # cash
        ("2026-09-21T20:15:00-04:00", "Showdown Captain Mode", 1, 1, False)]  # a ticket alone is a prize
    assert [(row["random"], row["random_exact"]) for row in washouts["by_portfolio"]] == [
        ("49.7778", "112/225"), ("80.0000", "4/5"), ("80.0000", "4/5")]
    assert {key: washouts[key] for key in ("portfolios", "washouts", "rate")} == {
        "portfolios": 3, "washouts": 1, "rate": {"realized": "33.3333", "random": "69.9259"}}  # 472/675
    assert all(row["sport"] == "NFL" for row in washouts["by_portfolio"])


def test_one_paid_entry_clears_its_whole_portfolio():
    # BEST's Classic shares WASHOUT's start time: the one entry that won $10 clears every contest in that portfolio.
    [classic, *_] = _report(*BEST, *WASHOUT)["scopes"]["nfl"]["washouts"]["by_portfolio"]
    assert (classic["contests"], classic["entries"], classic["washout"]) == (3, 6, False)


def test_an_empty_scope_reports_nulls_not_zeros():
    era = _report(*STANDARD, era="2027-01-01")["scopes"]["engine_era"]
    assert era["first_place"] == {
        "overall": {"contests": 0, "entries": 0, "best_percentile": {"realized": None, "random": None},
                    "first_place": {"entries": 0, "random": None}, "top_1": {"entries": 0, "random": None}},
        "by_payout_shape": [], "contests": []}
    assert era["washouts"] == {"portfolios": 0, "washouts": 0, "rate": {"realized": None, "random": None},
                               "by_portfolio": []}


def test_points_behind_first_are_named_never_estimated():
    report = _report(*BEST)
    assert report["points_behind_first"] == {"state": "NOT_IN_EXPORT",
                                             "named_source": "SESSION_18_PER_CONTEST_THRESHOLDS"}
    assert report["first_place_reading"] == rr.FIRST_PLACE_READING
    assert "best percentile" in rr.FIRST_PLACE_READING and "rare" in rr.FIRST_PLACE_READING


# ------------------------------------------------------------------------------------------- v1 unchanged


def test_a_v1_payload_keeps_its_bytes():
    assert sha256_bytes(contest_facts.canonical_bytes(_report(*BEST, *WASHOUT, metrics=V1))) == V1_FIXTURE_PIN


def test_a_v2_payload_is_the_v1_payload_plus_the_new_keys():
    rows = (*STANDARD, *BEST, *WASHOUT, *[_contest(day, f"2026-10-{10 + day:02d}", 100 * day, TOP_HEAVY)
                                          for day in range(1, 6)])
    v2 = _report(*rows, metrics=V2_FAST, bootstrap=True)  # five slates and more: every slice resamples
    v1 = _report(*rows, metrics=dataclasses.replace(V1, bootstrap=V2_FAST.bootstrap), bootstrap=True)
    assert (v2["schema_version"], v2["metrics"]) == ("nfl_results_report_v2",
                                                     {"version": "nfl_results_metrics_v2", "sha256": V2.sha256})
    assert v2["definitions"] == {**v1["definitions"], **rr.DECLARED_V2["first_place"], **rr.DECLARED_V2["washout"]}
    stripped = json.loads(json.dumps(v2))
    for scope in stripped["scopes"].values():
        assert set(scope) - set(v1["scopes"]["nfl"]) == {"first_place", "washouts"}
        del scope["first_place"], scope["washouts"]
    for key in ("points_behind_first", "first_place_reading"):
        del stripped[key]
    stripped["does_not_establish"] = stripped["does_not_establish"][:len(v1["does_not_establish"])]
    for key in ("schema_version", "metrics", "definitions"):
        stripped[key] = v1[key]
    assert stripped == v1


def test_the_contest_name_is_never_read():
    renamed = [list(row) for row in (*BEST, *WASHOUT)]
    for row in renamed:
        row[3] = "Renamed: Millionaire Single Entry Satellite 50/50"
    assert (contest_facts.canonical_bytes(_report(*renamed, source_bytes=1))
            == contest_facts.canonical_bytes(_report(*BEST, *WASHOUT, source_bytes=1)))


def _texts(value: object, skip: str = "does_not_establish") -> list[str]:
    if isinstance(value, dict):
        return [text for key, item in value.items() if key != skip for text in (key, *_texts(item, skip))]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item, skip)]
    return [value] if isinstance(value, str) else []


def test_no_written_word_claims_a_probability_or_equity():
    texts = _texts(_report(*STANDARD, *BEST, *WASHOUT))
    assert texts and not [text for text in texts if FORBIDDEN.search(text)]


# ------------------------------------------------------------------------------------------- the command


def _v2_target(root: Path, sha: str, era: str = ERA, suffix: str = "json") -> Path:
    return root / "reports" / sha / f"results_report.era-{era}.v2.w1.{suffix}"


def _command(capsys, *argv: str) -> tuple[int, dict]:
    code = cli.main(["results-report", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_the_command_defaults_to_v2_and_keeps_v1_beside_it(tmp_path, capsys):
    root, sha = _intake(tmp_path, RAW)
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (code, printed["status"], printed["contract"]) == (0, "COMPLETE", "nfl_results_report_v2")
    report, table = _v2_target(root, sha), _v2_target(root, sha, suffix="md")
    assert rr.report_name(ERA, rr.REPORT_V2) == report.name and rr.table_name(ERA, rr.REPORT_V2) == table.name
    assert printed["files"]["report"] == {"path": str(report), "state": "WRITTEN",
                                          "sha256": sha256_bytes(report.read_bytes())}
    payload = json.loads(report.read_bytes())
    assert (payload["schema_version"], payload["metrics"]["version"]) == ("nfl_results_report_v2",
                                                                          "nfl_results_metrics_v2")
    assert report.read_bytes() == rr.canonical_bytes(payload)
    again_code, again = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (again_code, again["status"]) == (0, "ALREADY_PRESENT")
    v1_code, v1 = _command(capsys, "--source-sha256", sha, "--results-root", str(root),
                           "--metrics-version", "nfl_results_metrics_v1")
    assert (v1_code, v1["status"], v1["contract"]) == (0, "COMPLETE", "nfl_results_report_v1")
    assert sorted(path.name for path in (root / "reports" / sha).iterdir()) == [
        "results_report.era-2026-09-09.v2.w1.json", "results_report.era-2026-09-09.v2.w1.md",
        "results_report.era-2026-09-09.w1.json", "results_report.era-2026-09-09.w1.md"]


def test_the_metrics_version_flag_defaults_to_v2_and_refuses_another():
    args = cli.build_parser().parse_args(["results-report", "--source-sha256", ZERO_SHA])
    assert args.metrics_version == "nfl_results_metrics_v2"
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["results-report", "--source-sha256", ZERO_SHA,
                                       "--metrics-version", "nfl_results_metrics_v3"])


def test_two_processes_give_byte_identical_v2_files(tmp_path):
    files = []
    for seed in ("0", "12345"):
        root, sha = _intake(tmp_path / seed, FIVE_SLATES)
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run((sys.executable, "-m", "nfl_dfs.cli", "results-report", "--source-sha256", sha,
                               "--results-root", str(root)), capture_output=True, timeout=300, env=environment,
                              check=False)
        assert done.returncode == 0, done.stdout[-400:] + done.stderr[-400:]
        files.append((_v2_target(root, sha).read_bytes(), _v2_target(root, sha, suffix="md").read_bytes()))
    assert files[0] == files[1]
    assert json.loads(files[0][0])["bootstrap"]["resamples"] == 10_000


def test_one_changed_snapshot_byte_is_refused_under_v2(tmp_path):
    root, sha = _intake(tmp_path, RAW)
    snapshot = root / "inbox" / f"{sha}.csv"
    snapshot.write_bytes(snapshot.read_bytes().replace(b"142.36", b"142.37", 1))
    outcome = rr.run_results_report(sha, root, metrics=V2_FAST)
    assert (outcome.status, outcome.contract) == ("REFUSED", "nfl_results_report_v2")
    assert outcome.problems == ("RESULTS_REPORT_SNAPSHOT_INVALID:reason=hash",)
    assert not (root / "reports").exists()


def test_a_v2_metrics_defect_fails_the_command_by_name(tmp_path, capsys, monkeypatch):
    root, sha = _intake(tmp_path, RAW)
    broken = tmp_path / "metrics.json"
    broken.write_bytes(rr.METRICS_V2_PATH.read_bytes().replace(b'"best_entry": "MIN', b'"best_entry": "MAX'))
    monkeypatch.setattr(rr, "METRICS_V2_PATH", broken)
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (code, printed["stage"], printed["error"]) == (2, "CLI_FAILED", "ResultsMetricsError")
    assert "first_place.best_entry" in printed["message"]
    assert not (root / "reports").exists()


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_stdout_carries_no_money_and_neither_list(tmp_path, capsys):
    rich = _row(Entry_Key="4000000099", Contest_Key="100000099", Winnings_Non_Ticket="$1,234.56",
                Winnings_Ticket="$43.21", Entry_Fee="$7.77", Prize_Pool="$9,876.54")
    root, sha = _intake(tmp_path, _history(*STANDARD, *WASHOUT, rich))
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert code == 0
    headline = printed["headline"]
    assert set(headline) == {"nfl", "engine_era", "all_sport_check", "within_slate_trigger"}
    for scope in ("nfl", "engine_era"):
        payload = json.loads(_v2_target(root, sha).read_bytes())["scopes"][scope]
        assert headline[scope]["first_place"] == payload["first_place"]["overall"]
        assert headline[scope]["washouts"] == {key: payload["washouts"][key]
                                               for key in ("portfolios", "washouts", "rate")}
    keys = _keys(printed)
    for fragment in ("cents", "fee", "winnings", "prize", "return", "share", "concentration"):
        assert not [key for key in keys if fragment in key], fragment
    assert not keys & {"net", "by_portfolio", "contest_key", "contest_start"}  # neither list reaches stdout
    for cents in (123456, 4321, 777, 987654):
        assert str(cents) not in json.dumps(headline)


DYNAMIC_KEYS = {"blanks_by_date", "left_out_rule_not_met", "parser_note_counts"}


def _named_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for name, item in value.items() if name not in DYNAMIC_KEYS
                             for key in _named_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _named_keys(item)}
    return set()


def test_the_v2_contract_names_every_written_key(tmp_path, capsys):
    root, sha = _intake(tmp_path, _history(*STANDARD, *BEST, *WASHOUT))
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    v1_code, v1_printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root),
                                   "--metrics-version", "nfl_results_metrics_v1")
    payload = json.loads(_v2_target(root, sha).read_bytes())
    v1_payload = json.loads((root / "reports" / sha / rr.report_name(ERA)).read_bytes())
    assert (code, v1_code) == (0, 0) and payload["scopes"]["nfl"]["first_place"]["contests"]
    text = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    v1 = text.split("\n## NFL results report, nfl_results_report_v1 (Session 71b)\n", 1)[1].split("\n## ", 1)[0]
    v2 = text.split("\n## NFL results report, nfl_results_report_v2 (Session 77)\n", 1)[1].split("\n## ", 1)[0]
    added = ((_named_keys(payload) | _named_keys(printed))
             - (_named_keys(v1_payload) | _named_keys(v1_printed)))
    assert {"first_place", "washouts", "by_portfolio", "points_behind_first"} <= added
    assert not sorted(key for key in added if f"`{key}`" not in v2)
    assert not sorted(key for key in _named_keys(payload) | _named_keys(printed)
                      if f"`{key}`" not in v1 and f"`{key}`" not in v2)
    for name in rr.DECLARED_V2["first_place"].values():
        assert name in text
    for name in rr.DECLARED_V2["washout"].values():
        assert name in text


# --------------------------------------------------------------------------------------------- the table


def _v2_written(tmp_path: Path, raw: bytes) -> tuple[dict, str, str]:
    root, sha = _intake(tmp_path / "v2", raw)
    assert rr.run_results_report(sha, root, metrics=V2_FAST).status == "COMPLETE"
    v1_root, v1_sha = _intake(tmp_path / "v1", raw)
    assert rr.run_results_report(v1_sha, v1_root, metrics=dataclasses.replace(V1, bootstrap=V2_FAST.bootstrap)
                                 ).status == "COMPLETE"
    v1_table = (v1_root / "reports" / v1_sha / rr.table_name(ERA)).read_text(encoding="utf-8")
    return (json.loads(_v2_target(root, sha).read_bytes()), _v2_target(root, sha, suffix="md").read_text(
        encoding="utf-8"), v1_table)


FP_HEADER = ["Band", "Label", "Contests", "Entries", "Best percentile % (random), lower is better",
             "First place (random)", "Top 1% (random)"]


def _fp_cells(block: dict) -> list[str]:
    best = block["best_percentile"]
    return [str(block["contests"]), str(block["entries"]), f"{best['realized']} ({best['random']})",
            f"{block['first_place']['entries']} ({block['first_place']['random']})",
            f"{block['top_1']['entries']} ({block['top_1']['random']})"]


def test_the_v2_table_adds_first_place_and_washouts_after_the_v1_sections(tmp_path):
    raw = _history(*STANDARD, *BEST, *WASHOUT, _row(Entry_Key="4000000077", Contest_Key="100000077",
                                                    Contest_Date_EST="2026-09-06 13:00:00"))
    payload, text, v1_text = _v2_written(tmp_path, raw)
    lines, v1_lines = text.splitlines(), v1_text.splitlines()
    # Up to the first new heading, the v2 table is the v1 table but for the line naming the contract and metrics.
    first = lines.index(f"## {rr.FIRST_PLACE_HEADING}, NFL")
    v1_end = v1_lines.index("## Not established")
    assert [line for index, line in enumerate(lines[:first]) if index != 2] == [
        line for index, line in enumerate(v1_lines[:v1_end]) if index != 2]
    assert "`nfl_results_report_v2`" in lines[2] and "metrics `nfl_results_metrics_v2`" in lines[2]
    assert lines[v1_end:].index("## Not established") > 0
    for scope, title in (("nfl", "NFL"), ("engine_era", "engine era")):
        block = payload["scopes"][scope]["first_place"]
        header = next(line for line in lines[lines.index(f"## {rr.FIRST_PLACE_HEADING}, {title}"):]
                      if line.startswith("|"))
        assert [cell.strip() for cell in header.strip("|").split("|")] == FP_HEADER
        rows = _cells(lines, f"## {rr.FIRST_PLACE_HEADING}, {title}")
        assert rows[0] == ["All shapes", "", *_fp_cells(block["overall"])]
        assert rows[1:] == [[band["band"], band["first_place_label"] or "n/a", *_fp_cells(band)]
                            for band in block["by_payout_shape"]]
    washouts = [payload["scopes"][scope]["washouts"] for scope in ("nfl", "engine_era")]
    grid = _grid(lines, f"## {rr.WASHOUT_HEADING}")
    assert grid == {"Portfolios": [str(block["portfolios"]) for block in washouts],
                    "Washouts": [str(block["washouts"]) for block in washouts],
                    "Washout rate % (random), lower is better": [
                        f"{block['rate']['realized']} ({block['rate']['random']})" for block in washouts]}
    assert payload["scopes"]["nfl"]["washouts"]["portfolios"] != payload["scopes"]["engine_era"]["washouts"][
        "portfolios"]
    assert f"{payload['first_place_reading']} Points behind first: NOT_IN_EXPORT" in text
    section = text.split("\n## Not established\n", 1)[1]
    for line in payload["does_not_establish"]:
        assert f"- {line}\n" in section
    assert "`results_report.era-2026-09-09.v2.w1.json`" in section
    assert text.isascii() and text.endswith("\n") and "\r" not in text
    assert rr.render_table(payload) == text.encode("utf-8")
    outside = text.split("\n## Not established\n", 1)[0]
    assert not FORBIDDEN.search(outside)


def test_an_empty_engine_era_prints_no_zero_in_the_v2_sections(tmp_path):
    early = _history(_row(Contest_Date_EST="2026-09-01 13:00:00"))
    payload, text, _ = _v2_written(tmp_path, early)
    section = text.split(f"\n## {rr.FIRST_PLACE_HEADING}, engine era\n", 1)[1].split("\n## ", 1)[0]
    assert "No entries in this scope." in section and "|" not in section.split("No entries", 1)[0]
    grid = _grid(text.splitlines(), f"## {rr.WASHOUT_HEADING}")
    assert grid["Washout rate % (random), lower is better"][1] == "n/a"
    assert grid["Portfolios"] == ["1", "0"]


def test_the_runbook_and_the_guide_name_the_v2_table():
    runbook = (REPO / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    section = runbook.split("\n## Contest screening checklist", 1)[1].split("\n## ", 1)[0]
    assert "results_report.era-<date>.v2.w1.md" in section and rr.FIRST_PLACE_HEADING in section
    guide = (REPO / "docs" / "OPERATOR_GUIDE.md").read_text(encoding="utf-8")
    results = guide.split("\n## Results report\n", 1)[1].split("\n## ", 1)[0]
    assert rr.table_name(ERA, rr.REPORT_V2) in results and "--metrics-version nfl_results_metrics_v1" in results
