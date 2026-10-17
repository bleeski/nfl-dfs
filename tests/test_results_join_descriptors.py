"""Session 73b: the descriptor comparison (`nfl_results_descriptors_v1`), bust attribution.

Each slate's `entry_results.w1.json` (Session 73) joined to its build record, then the bottom-10% and top-10% entries
compared on the record's descriptors, and finish percentile read against each descriptor. The fixed effect is the contest
(Ben's entries sit in four to twelve contests a slate, of one, two, seven or twenty entries, and contest membership follows
the lineup), the cluster is the slate, and every point figure is an exact ratio of cluster sums that `results_report`'s own
bootstrap-t reads. The oracles here are written independently of the module, with explicit inequalities and `Fraction`s.

Results files are synthetic. The real committed records and salary files are read (copied into a temporary slates
folder, never written back); no `entry_results.w1.json` is committed until operator item O13.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import math
import random
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from nfl_dfs import cli, entry_history
from nfl_dfs import results_descriptors as rd
from nfl_dfs import results_join as rj
from nfl_dfs import results_report as rr
from nfl_dfs.contracts import GateClass
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import canonical_json_bytes, sha256_bytes
from tests.test_gate_registry import scanned_codes

REPO = Path(__file__).resolve().parents[1]
SLATES = REPO / "data" / "inbox" / "slates"
ZERO_SHA = "0" * 64
JOINED, BLANK = "JOINED", "LOCKED_BLANK_WITH_FILE"


def _real(slate: str, line: int = 0) -> dict:
    return json.loads((SLATES / slate / "construction" / "entry_build_record.jsonl").read_bytes().splitlines()[line])


SHOWDOWN_ROW = _real("det-car-sd-2026-10-04")
CLASSIC_ROW = _real("wk4-classic-2026-10-04")


# ------------------------------------------------------------------------------------------- builders


def _record_row(entry_id: str, contest: str, *, mode: str = "SHOWDOWN", salary_left: int = 0, q_count: int = 0,
                later: int = 0, structure: dict | None = None, captain: object = "keep") -> dict:
    row = json.loads(json.dumps(SHOWDOWN_ROW if mode == "SHOWDOWN" else CLASSIC_ROW))
    row.update(entry_id=entry_id, contest_id=contest, mode=mode, salary_left=salary_left, later_window_count=later)
    row["dk_status"] = {**row["dk_status"], "q_count": q_count}
    row["structure"] = {**row["structure"], **(structure or {})}
    if captain != "keep":
        row["captain_dk_id"] = captain
    return row


def _fin(place: int, field: int, points: int = 5000, cls: str = JOINED) -> tuple:
    return place, field, points, cls


def _results_payload(slate: str, rows: list[dict], finishes: dict[str, tuple]) -> dict:
    entries = []
    for row in rows:
        place, field, points, cls = finishes[row["entry_id"]]
        bound = cls in (JOINED, BLANK)
        entries.append({
            "entry_id": row["entry_id"], "class": cls,
            "place": place if bound else None, "contest_entries": field if bound else None,
            "points_hundredths": points if bound else None,
            "percentile": rr._fixed(rr.finishing_percentile(place, field) * 100) if bound else None})
    return {"schema_version": rj.RESULTS_VERSION, "writer": rj.WRITER, "contract": rj.CONTRACT_VERSION,
            "source_sha256": ZERO_SHA, "slate": slate, "record_name": rj.RECORD_NAME, "entries": entries,
            "does_not_establish": list(rj.DOES_NOT_ESTABLISH)}


def _slates(tmp_path: Path, folders: dict[str, tuple[list[dict], dict[str, tuple] | None]],
            name: str = "slates") -> Path:
    """`{slate: (record rows, finishes or None for no results file)}`, created in the order given."""

    root = tmp_path / name
    for slate, (rows, finishes) in folders.items():
        construction = root / slate / "construction"
        construction.mkdir(parents=True, exist_ok=True)
        (construction / rj.RECORD_NAME).write_bytes(b"".join(canonical_json_bytes(row) + b"\n" for row in rows))
        if finishes is not None:
            payload = _results_payload(slate, rows, finishes)
            (construction / rj.RESULTS_NAME).write_bytes(
                (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    return root


def _metrics() -> rr.ResultsMetrics:
    return rr.load_results_metrics(rr.registered_metrics_path(rr.CURRENT_METRICS_VERSION))


def _report(root: Path, **kwargs) -> dict:
    return rd.build_report(rd.load_inputs(root), _metrics(), **kwargs)


def _by_name(report: dict) -> dict[str, dict]:
    return {item["name"]: item for item in report["descriptors"]}


# The hand-checked slate: contest 3001 (field 100) and contest 3002 (field 2).
#   3001: places 5 and 8 are top (place x 10 <= 100), 95 is bottom (950 > 900), 50 is neither.
#   3002: place 2 is bottom (20 > 18); place 1 is neither (10 > 2, so not top; 10 <= 18, so not bottom).
A_ROWS = [
    _record_row("910000001", "3001", salary_left=1000), _record_row("910000002", "3001", salary_left=2000),
    _record_row("910000003", "3001", salary_left=300), _record_row("910000004", "3001", salary_left=500),
    _record_row("910000005", "3002", salary_left=100), _record_row("910000006", "3002", salary_left=9000),
]
A_FIN = {"910000001": _fin(5, 100), "910000002": _fin(8, 100), "910000003": _fin(95, 100), "910000004": _fin(50, 100),
         "910000005": _fin(2, 2), "910000006": _fin(1, 2)}


def _independent_clusters(spec: dict[str, list[tuple]], statistic: str) -> list[tuple[Fraction, Fraction]]:
    """`spec[slate]` is a list of `(contest, value, place, field)`; scores per slate, exact, by explicit inequalities."""

    clusters = []
    for slate in sorted(spec):
        by_contest: dict[str, list[tuple]] = {}
        for contest, value, place, field in spec[slate]:
            by_contest.setdefault(contest, []).append((Fraction(value), place, field))
        y = x = Fraction(0)
        for rows in by_contest.values():
            if statistic == "top_minus_bottom":
                top = [v for v, place, field in rows if place * 10 <= field]
                bottom = [v for v, place, field in rows if place * 10 > 9 * field]
                if top and bottom:
                    weight = Fraction(len(top) * len(bottom), len(top) + len(bottom))
                    y += weight * (sum(top) / len(top) - sum(bottom) / len(bottom))
                    x += weight
            else:
                if len(rows) < 2:
                    continue
                mean_d = sum(v for v, _, _ in rows) / len(rows)
                finish = [Fraction(100 * place, field) for _, place, field in rows]
                mean_p = sum(finish) / len(rows)
                for (v, _, _), p in zip(rows, finish):
                    y += (v - mean_d) * (p - mean_p)
                    x += (v - mean_d) ** 2
        if x:
            clusters.append((y, x))
    return clusters


def _exact(clusters: list[tuple[Fraction, Fraction]]) -> Fraction:
    return sum(y for y, _ in clusters) / sum(x for _, x in clusters)


# ------------------------------------------------------------------------------------ the point estimates


def test_the_difference_is_the_contest_fixed_effect_and_not_the_slate_one(tmp_path):
    """3001's tops average $1,500 left and its bottom $300; 3002 has no top, so it weighs nothing: 12, never 13."""

    root = _slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)})
    figures = _by_name(_report(root))["salary_left"]["top_minus_bottom"]
    assert figures["estimate"] == "12.0000" and figures["slates"] == 1
    # The slate-level contrast pools both contests: tops 15 against bottoms (3 and 1) is 13, and a mixed contest mixes in.
    slate_level = Fraction(10 + 20, 2) - Fraction(3 + 1, 2)
    assert slate_level == 13 and Fraction(figures["estimate"]) != slate_level
    assert figures["reason"] == "FEWER_THAN_5_SLATES" and figures["interval"] is None


def test_the_slope_is_the_contest_fixed_effect_with_hand_checked_sums(tmp_path):
    """3001: Sxy -756 and Sxx 173 (d in $100, p in percent); 3002: Sxy -2225 and Sxx 3960.5."""

    root = _slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)})
    figures = _by_name(_report(root))["salary_left"]["percentile_slope"]
    # (-756 - 2225) / (173 + 3960.5) = -2981 / 4133.5 = -5962 / 8267
    assert Fraction(figures["estimate"]) == round(Fraction(-5962, 8267), 4) == Fraction("-0.7212")
    assert figures["slates"] == 1


def test_two_contests_in_one_slate_weigh_by_group_sizes_not_equally(tmp_path):
    """4001 has two tops (10, 20) and a bottom (3): diff 12, weight 2/3. 4002 has a top (40) and a bottom (20): diff 20,
    weight 1/2. The slate is (8 + 10) / (7/6) = 108/7 = 15.4286; equal weights give 16, and pooling the rows gives 11.83."""

    rows = [_record_row("930000001", "4001", salary_left=1000), _record_row("930000002", "4001", salary_left=2000),
            _record_row("930000003", "4001", salary_left=300), _record_row("930000004", "4002", salary_left=4000),
            _record_row("930000005", "4002", salary_left=2000)]
    finishes = {"930000001": _fin(5, 100), "930000002": _fin(8, 100), "930000003": _fin(95, 100),
                "930000004": _fin(3, 100), "930000005": _fin(97, 100)}
    root = _slates(tmp_path, {"b-sd": (rows, finishes)})
    figures = _by_name(_report(root))["salary_left"]["top_minus_bottom"]
    assert Fraction(figures["estimate"]) == round(Fraction(108, 7), 4) == Fraction("15.4286")


def _spec(count: int, seed: int = 7) -> dict[str, list[dict]]:
    """Per slate, 8 entries in a 200-entry contest (two top, two bottom, four between) and 2 in a 3-entry one."""

    rng = random.Random(seed)
    entry = 0
    spec: dict[str, list[dict]] = {}
    for index in range(count):
        rows = []
        for contest, field, places in ((f"{5000 + index}1", 200, [(1, 20)] * 2 + [(181, 200)] * 2 + [(21, 180)] * 4),
                                       (f"{5000 + index}2", 3, [(1, 3)] * 2)):
            for low, high in places:
                entry += 1
                left = rng.randint(0, 40)
                kickers, stack, mix = rng.randint(0, 1), rng.randint(0, 3), rng.randint(1, 5)
                rows.append({"entry_id": str(8_000_000 + entry), "contest": contest, "field": field,
                             "place": rng.randint(low, high), "left": 100 * left, "kickers": kickers,
                             "stack": stack, "mix": mix})
        spec[f"s{index:02d}-sd"] = rows
    return spec


def _folders(spec: dict[str, list[dict]], mode: str = "SHOWDOWN") -> dict:
    folders = {}
    for slate, rows in spec.items():
        records = [_record_row(row["entry_id"], row["contest"], mode=mode, salary_left=row["left"],
                               structure={"kicker_count": row["kickers"], "qb_count": 1,
                                          "pass_catchers_with_rostered_qb": [row["stack"]],
                                          "team_split": {"AAA": row["mix"], "BBB": 6 - row["mix"]}})
                   for row in rows]
        folders[slate] = (records, {row["entry_id"]: _fin(row["place"], row["field"]) for row in rows})
    return folders


def _oracle_spec(spec: dict, name: str) -> dict[str, list[tuple]]:
    pick = {"salary_left": lambda row: Fraction(row["left"], 100), "kicker_count": lambda row: row["kickers"],
            "max_pass_catchers_with_qb": lambda row: row["stack"],
            "max_team_count": lambda row: max(row["mix"], 6 - row["mix"])}
    return {slate: [(row["contest"], pick[name](row), row["place"], row["field"]) for row in rows]
            for slate, rows in spec.items()}


@pytest.mark.parametrize("name", ["salary_left", "kicker_count", "max_pass_catchers_with_qb", "max_team_count"])
@pytest.mark.parametrize("statistic", ["top_minus_bottom", "percentile_slope"])
def test_each_primary_figure_equals_the_independent_oracle(tmp_path, name, statistic):
    spec = _spec(6)
    root = _slates(tmp_path, _folders(spec))
    figures = _by_name(_report(root))[name][statistic]
    clusters = _independent_clusters(_oracle_spec(spec, name), statistic)
    assert len(clusters) == figures["slates"] == 6  # the fixture gives every slate both groups in a contest
    exact = _exact(clusters)
    assert Fraction(figures["estimate"]) == round(exact, 4)
    residuals = [float(y - exact * x) for y, x in clusters]
    count = len(clusters)
    assert any(residuals)
    error = math.sqrt(count / (count - 1) * math.fsum(r * r for r in residuals)) / float(sum(x for _, x in clusters))
    assert abs(float(figures["standard_error"]) - error) <= 0.00005 + 1e-12
    assert figures["method"] == rr.WILD and figures["interval"] is not None and figures["mde"] is not None
    assert Fraction(figures["interval"]["low"]) <= Fraction(figures["interval"]["high"])


def test_the_interval_is_the_shared_bootstrap_on_the_oracle_clusters_with_the_documented_seed(tmp_path):
    spec = _spec(6)
    report = _report(_slates(tmp_path, _folders(spec)))
    metrics = _metrics()
    settings = rr.bootstrap_settings(metrics)
    for statistic in ("top_minus_bottom", "percentile_slope"):
        clusters = _independent_clusters(_oracle_spec(spec, "salary_left"), statistic)
        key = json.dumps([settings.seed, "RESULTS_DESCRIPTORS", rd.POPULATION, "salary_left", statistic],
                         sort_keys=True).encode("utf-8")
        draw = random.Random(int(sha256_bytes(key), 16)).random
        assert _by_name(report)["salary_left"][statistic] == rr._statistic(clusters, settings, draw, scale=1)


def test_thirty_slates_switch_to_the_pairs_bootstrap(tmp_path):
    spec = _spec(30)
    root = _slates(tmp_path, _folders(spec))
    inputs = rd.load_inputs(root)
    settings = dataclasses.replace(rr.bootstrap_settings(_metrics()), resamples=200)
    figures = _by_name(rd.build_report(inputs, _metrics(), settings=settings))["salary_left"]["top_minus_bottom"]
    assert figures["method"] == rr.PAIRS and figures["slates"] == 30
    figures = _by_name(rd.build_report(rd.load_inputs(_slates(tmp_path, _folders(_spec(6)), "six")), _metrics(),
                                       settings=settings))["salary_left"]["top_minus_bottom"]
    assert figures["method"] == rr.WILD


def test_the_secondary_descriptors_carry_an_estimate_and_a_standard_error_and_never_an_interval(tmp_path):
    spec = _spec(6)
    folders = _folders(spec)
    for slate, (records, finishes) in folders.items():  # q_count varies with the row's salary, so it has spread
        for record in records:
            record["dk_status"]["q_count"] = record["salary_left"] // 1000 % 3
    report = _report(_slates(tmp_path, folders))
    found = _by_name(report)["q_count"]
    assert found["primary"] is False
    for statistic in ("top_minus_bottom", "percentile_slope"):
        figures = found[statistic]
        assert figures["interval"] is None and figures["mde"] is None and figures["method"] is None
        assert figures["reason"] == "SECONDARY_DESCRIPTOR"
        assert figures["estimate"] is not None and figures["standard_error"] is not None and figures["slates"] == 6
    primary = {item["name"] for item in report["descriptors"] if item["primary"]}
    assert primary == {"salary_left", "max_pass_catchers_with_qb", "max_team_count", "kicker_count"}
    assert report["family"]["intervals"] == 8 and report["family"]["adjustment"] == "NONE"


def test_a_secondary_descriptor_with_no_spread_has_an_estimate_and_no_standard_error(tmp_path):
    report = _report(_slates(tmp_path, _folders(_spec(6))))
    figures = _by_name(report)["qb_count"]["top_minus_bottom"]  # the fixture gives every row one quarterback
    assert figures["estimate"] == "0.0000" and figures["slates"] == 6
    assert figures["standard_error"] is None and figures["interval"] is None


def test_a_descriptor_with_no_spread_names_it_and_a_contest_with_no_top_weighs_nothing(tmp_path):
    spec = _spec(6)
    folders = _folders(spec)
    for _slate, (records, _finishes) in folders.items():
        for record in records:
            record["structure"]["kicker_count"] = 1
    figures = _by_name(_report(_slates(tmp_path, folders)))["kicker_count"]
    assert figures["top_minus_bottom"]["reason"] == "ZERO_STANDARD_ERROR"
    assert figures["top_minus_bottom"]["estimate"] == "0.0000"
    assert figures["percentile_slope"]["estimate"] is None and figures["percentile_slope"]["slates"] == 0


# ---------------------------------------------------------------------------------- rows and descriptors


def test_descriptor_values_come_from_the_record_in_the_documented_units():
    values = rd.descriptor_values(SHOWDOWN_ROW)
    assert values["salary_left"] == Fraction(SHOWDOWN_ROW["salary_left"], 100)
    assert values["max_team_count"] == max(SHOWDOWN_ROW["structure"]["team_split"].values())
    assert values["team_count"] is None  # Showdown always has two teams
    assert values["q_count"] == SHOWDOWN_ROW["dk_status"]["q_count"]
    classic = rd.descriptor_values(CLASSIC_ROW)
    assert classic["team_count"] == len(CLASSIC_ROW["structure"]["team_split"])
    assert classic["bring_backs"] == CLASSIC_ROW["structure"]["bring_backs"]
    assert set(values) == {item.name for item in rd.DESCRIPTORS}


def test_stack_size_is_null_not_zero_when_the_row_has_no_quarterback():
    row = _record_row("1", "2", structure={"qb_count": 0, "pass_catchers_with_rostered_qb": []})
    assert rd.descriptor_values(row)["max_pass_catchers_with_qb"] is None
    row = _record_row("1", "2", structure={"qb_count": 1, "pass_catchers_with_rostered_qb": [0]})
    assert rd.descriptor_values(row)["max_pass_catchers_with_qb"] == 0
    row = _record_row("1", "2", structure={"qb_count": 2, "pass_catchers_with_rostered_qb": [1, 3]})
    assert rd.descriptor_values(row)["max_pass_catchers_with_qb"] == 3


def test_an_unfilled_record_row_has_null_descriptors():
    row = dict(SHOWDOWN_ROW, roster=None, captain_dk_id=None, salary_left=None, structure=None, dk_status=None,
               later_window_count=None)
    assert set(rd.descriptor_values(row).values()) == {None}


def test_only_joined_rows_are_compared_and_blanks_are_counted_by_class(tmp_path):
    rows = A_ROWS + [_record_row("910000007", "3001", salary_left=777700)]
    finishes = {**A_FIN, "910000007": _fin(99, 100, points=0, cls=BLANK)}
    report = _report(_slates(tmp_path, {"a-sd": (rows, finishes)}))
    assert _by_name(report)["salary_left"]["top_minus_bottom"]["estimate"] == "12.0000"  # the blank's $7,777 left is absent
    assert report["sample"]["excluded"] == {BLANK: 1}
    [slate] = report["slates"]
    assert slate["joined"] == 6 and slate["excluded"] == {BLANK: 1}
    assert report["reading"]["rows"] == "JOINED_ONLY_BLANKS_REMOVED_BY_CONSTRUCTION"


def test_place_and_field_are_read_as_integers_never_from_the_percentile_text(tmp_path):
    root = _slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)})
    before = _report(root)
    _rewrite(root / "a-sd" / "construction" / rj.RESULTS_NAME,
             lambda payload: [entry.update(percentile="not a percentile") for entry in payload["entries"]])
    after = _report(root)
    assert after["descriptors"] == before["descriptors"] and after["sample"] == before["sample"]


def test_the_sample_is_declared(tmp_path):
    report = _report(_slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)}))
    sample = report["sample"]
    assert sample["slates"] == 1 and sample["joined_entries"] == 6 and sample["contests"] == 2
    assert sample["contests_with_both_groups"] == 1  # 3001 only
    assert (sample["top"], sample["bottom"], sample["neither"]) == (2, 2, 2)
    assert sample["by_mode"] == {"SHOWDOWN": {"slates": 1, "joined_entries": 6}}
    assert report["population"] == "ALL_JOINED"


# --------------------------------------------------------------------------------------- named gaps


def test_a_slate_with_no_results_file_is_named_and_never_imputed(tmp_path):
    spec = _spec(6)
    folders = _folders(spec)
    extra = _record_row("999000001", "9001", salary_left=500)
    with_gap = {**folders, "z-late-sd": ([extra], None)}
    report = _report(_slates(tmp_path, with_gap, "with"))
    without = _report(_slates(tmp_path, folders, "without"))
    [gap] = [item for item in report["slates"] if item["slate"] == "z-late-sd"]
    assert gap["gap"] == "NO_RESULTS_FILE" and gap["results_sha256"] is None and gap["joined"] == 0
    assert report["descriptors"] == without["descriptors"]
    assert report["sample"]["slates_not_compared"] == ["z-late-sd"] and without["sample"]["slates_not_compared"] == []
    assert {**report["sample"], "slates_not_compared": []} == without["sample"]


def test_a_results_file_that_does_not_list_the_records_entry_ids_is_named_and_withheld(tmp_path):
    folders = {"a-sd": (A_ROWS, A_FIN)}
    root = _slates(tmp_path, folders)
    results = root / "a-sd" / "construction" / rj.RESULTS_NAME
    payload = json.loads(results.read_bytes())
    payload["entries"] = payload["entries"][:-1]  # a record row added since the join
    results.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    report = _report(root)
    [slate] = report["slates"]
    assert slate["gap"] == "RESULTS_DO_NOT_MATCH_RECORD" and slate["joined"] == 0
    assert report["sample"]["slates"] == 0 and _by_name(report)["salary_left"]["top_minus_bottom"]["estimate"] is None


# --------------------------------------------------------------------------------------- refusals


def _refusal(root: Path) -> rd.ResultsDescriptorsRefused:
    with pytest.raises(rd.ResultsDescriptorsRefused) as caught:
        rd.load_inputs(root)
    return caught.value


def _rewrite(path: Path, change) -> None:
    payload = json.loads(path.read_bytes())
    change(payload)
    path.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


RESULTS_FAULTS = {
    "not_json": (lambda path: path.write_bytes(b"not json\n"), "a-sd:unreadable"),
    "extra_key": (lambda path: _rewrite(path, lambda p: p.update(extra=1)), "a-sd:keys"),
    "source_not_a_hash": (lambda path: _rewrite(path, lambda p: p.update(source_sha256="abc")), "a-sd:source_sha256"),
    "other_slate": (lambda path: _rewrite(path, lambda p: p.update(slate="b-sd")), "a-sd:slate"),
    "other_writer": (lambda path: _rewrite(path, lambda p: p.update(writer="w2")), "a-sd:writer"),
    "place_past_field": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(place=101)),
                         "a-sd:entry_id=910000001:place"),
    "number_on_a_gap_class": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(**{"class": "ENTERED_NO_RECORD"})),
                              "a-sd:entry_id=910000001:place"),
    "unknown_class": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(**{"class": "WON"})),
                      "a-sd:entry_id=910000001:class"),
    "place_zero": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(place=0)),
                   "a-sd:entry_id=910000001:place"),
    "field_zero": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(contest_entries=0)),
                   "a-sd:entry_id=910000001:contest_entries"),
    "place_boolean": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(place=True)),
                      "a-sd:entry_id=910000001:place"),
    "field_boolean": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(contest_entries=True)),
                      "a-sd:entry_id=910000001:contest_entries"),
    "points_negative": (lambda path: _rewrite(path, lambda p: p["entries"][0].update(points_hundredths=-1)),
                        "a-sd:entry_id=910000001:points_hundredths"),
    "entry_repeated": (lambda path: _rewrite(path, lambda p: p["entries"][1].update(entry_id="910000001")),
                       "a-sd:entry_id=910000001:entry_id_repeated"),
    "entries_not_a_list": (lambda path: _rewrite(path, lambda p: p.update(entries={})), "a-sd:entries"),
}


@pytest.mark.parametrize("fault", list(RESULTS_FAULTS), ids=list(RESULTS_FAULTS))
def test_a_malformed_results_file_is_refused_by_name(tmp_path, fault):
    root = _slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)})
    change, detail = RESULTS_FAULTS[fault]
    change(root / "a-sd" / "construction" / rj.RESULTS_NAME)
    refusal = _refusal(root)
    assert (refusal.code, refusal.detail) == ("RESULTS_DESCRIPTORS_RESULTS_INVALID", detail)


RECORD_FAULTS = {
    "string_count": (lambda row: row["structure"].update(qb_count="1"), "line=1:structure.qb_count"),
    "boolean_count": (lambda row: row["dk_status"].update(q_count=True), "line=1:dk_status.q_count"),
    "negative_salary": (lambda row: row.update(salary_left=-1), "line=1:salary_left"),
    "split_not_counts": (lambda row: row["structure"].update(team_split={"AAA": "x"}), "line=1:structure.team_split"),
    "list_not_ints": (lambda row: row["structure"].update(pass_catchers_with_rostered_qb=["x"]),
                      "line=1:structure.pass_catchers_with_rostered_qb"),
    "no_salary_hash": (lambda row: row["hashes"].pop("salary_sha256"), "line=1:hashes.salary_sha256"),
}


@pytest.mark.parametrize("fault", list(RECORD_FAULTS), ids=list(RECORD_FAULTS))
def test_a_record_with_a_bad_descriptor_field_is_refused_by_name(tmp_path, fault):
    rows = [json.loads(json.dumps(row)) for row in A_ROWS]
    change, detail = RECORD_FAULTS[fault]
    change(rows[0])
    root = _slates(tmp_path, {"a-sd": (rows, A_FIN)})
    refusal = _refusal(root)
    assert refusal.code == "RESULTS_DESCRIPTORS_RECORD_INVALID"
    assert refusal.detail == f"a-sd/construction/{rj.RECORD_NAME}:{detail}"


def test_a_symlinked_results_file_is_refused_never_followed(tmp_path, monkeypatch):
    """A real symlink needs a privilege this host may lack (and a skip would be a finding), so the check is simulated."""

    root = _slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)})
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == rj.RESULTS_NAME)
    refusal = _refusal(root)
    assert (refusal.code, refusal.detail) == ("RESULTS_DESCRIPTORS_RESULTS_INVALID", "a-sd:symlink")


def test_the_join_fields_are_still_checked_by_the_joins_own_loader(tmp_path):
    rows = [dict(A_ROWS[0], entry_id="x"), *A_ROWS[1:]]
    root = _slates(tmp_path, {"a-sd": (rows, None)})
    refusal = _refusal(root)
    assert refusal.code == "RESULTS_DESCRIPTORS_RECORD_INVALID" and "entry_id" in refusal.detail


def test_a_slates_root_that_is_not_a_folder_is_refused(tmp_path):
    outcome = rd.run_results_descriptors(tmp_path / "results", tmp_path / "missing")
    assert outcome.status == "REFUSED" and outcome.exit_code == 2
    assert outcome.problems == ("RESULTS_DESCRIPTORS_INPUT_INVALID:field=slates_root",)
    assert not (tmp_path / "results").exists()


# --------------------------------------------------------------------------------------- captain table


TB_DAL = "tb-dal-sd-2026-10-08"


def _real_slate(tmp_path: Path, name: str = TB_DAL, drop_salary: bool = False) -> tuple[Path, list[dict]]:
    root = tmp_path / "slates"
    folder = root / name
    (folder / "construction").mkdir(parents=True)
    (folder / "input").mkdir()
    shutil.copy(SLATES / name / "construction" / rj.RECORD_NAME, folder / "construction" / rj.RECORD_NAME)
    if not drop_salary:
        shutil.copy(SLATES / name / "input" / "DKSalaries.csv", folder / "input" / "DKSalaries.csv")
    rows = [json.loads(line) for line in (folder / "construction" / rj.RECORD_NAME).read_bytes().splitlines()]
    return root, rows


def _finishes_for(rows: list[dict]) -> dict[str, tuple]:
    """Every contest a 100-entry field: its rows take places 3, 98, 7, 95 (top, bottom, top, bottom), then the middle."""

    seen: dict[str, int] = {}
    finishes = {}
    for row in rows:
        turn = seen.get(row["contest_id"], 0)
        seen[row["contest_id"]] = turn + 1
        finishes[row["entry_id"]] = _fin((3, 98, 7, 95)[turn] if turn < 4 else 40 + turn, 100)
    return finishes


def _write_results(root: Path, name: str, rows: list[dict], finishes: dict[str, tuple]) -> None:
    payload = _results_payload(name, rows, finishes)
    (root / name / "construction" / rj.RESULTS_NAME).write_bytes(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def _salary_positions(name: str = TB_DAL) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO((SLATES / name / "input" / "DKSalaries.csv").read_bytes().decode("utf-8-sig")))
    return {line["ID"]: line["Position"] for line in reader}


def test_the_captain_table_reads_positions_from_the_salary_file_the_record_binds(tmp_path):
    root, rows = _real_slate(tmp_path)
    finishes = _finishes_for(rows)
    _write_results(root, TB_DAL, rows, finishes)
    report = _report(root)
    positions = _salary_positions()
    expected: dict[str, dict[str, int]] = {}
    for row in rows:
        place, field, _points, _cls = finishes[row["entry_id"]]
        group = "top" if place * 10 <= field else "bottom" if place * 10 > 9 * field else "neither"
        slot = expected.setdefault(positions[row["captain_dk_id"]], {"top": 0, "bottom": 0, "neither": 0, "entries": 0})
        slot[group] += 1
        slot["entries"] += 1
    table = report["captain_table"]
    assert {pos: {key: found[key] for key in ("top", "bottom", "neither", "entries")}
            for pos, found in table["slates"][TB_DAL]["positions"].items()} == expected
    assert table["pooled"]["positions"].keys() == expected.keys()
    for pos, found in table["slates"][TB_DAL]["positions"].items():
        mean = sum(Fraction(100 * finishes[row["entry_id"]][0], 100) for row in rows
                   if positions[row["captain_dk_id"]] == pos) / expected[pos]["entries"]
        assert Fraction(found["mean_percentile"]) == round(mean, 4)
    assert table["unresolved"] == {} and table["slates"][TB_DAL]["gap"] is None


def test_the_pooled_captain_table_is_the_sum_of_every_slate(tmp_path):
    first, rows_a = _real_slate(tmp_path, TB_DAL)
    _, rows_b = _real_slate(tmp_path, "det-car-sd-2026-10-04")
    finishes = {TB_DAL: _finishes_for(rows_a), "det-car-sd-2026-10-04": _finishes_for(rows_b)}
    _write_results(first, TB_DAL, rows_a, finishes[TB_DAL])
    _write_results(first, "det-car-sd-2026-10-04", rows_b, finishes["det-car-sd-2026-10-04"])
    table = _report(first)["captain_table"]
    assert set(table["slates"]) == {TB_DAL, "det-car-sd-2026-10-04"}
    pooled = table["pooled"]["positions"]
    for position, found in pooled.items():
        parts = [table["slates"][name]["positions"].get(position) for name in table["slates"]]
        parts = [part for part in parts if part is not None]
        for key in ("entries", "top", "bottom", "neither"):
            assert found[key] == sum(part[key] for part in parts)
        mean = sum(Fraction(part["mean_percentile"]) * part["entries"] for part in parts) / found["entries"]
        assert abs(Fraction(found["mean_percentile"]) - mean) <= Fraction(1, 10000)
    assert sum(found["entries"] for found in pooled.values()) == len(rows_a) + len(rows_b)


def test_a_classic_slate_has_no_captain_rows(tmp_path):
    rows = [_record_row(f"92000000{i}", "3003", mode="CLASSIC", salary_left=100 * i) for i in range(1, 5)]
    report = _report(_slates(tmp_path, {"b-classic": (rows, {r["entry_id"]: _fin(i * 9, 100) for i, r in enumerate(rows, 1)})}))
    assert report["captain_table"]["slates"] == {} and report["captain_table"]["pooled"]["positions"] == {}


def test_a_missing_salary_file_is_named_and_the_other_descriptors_still_run(tmp_path):
    root, rows = _real_slate(tmp_path, drop_salary=True)
    _write_results(root, TB_DAL, rows, _finishes_for(rows))
    report = _report(root)
    assert report["captain_table"]["unresolved"] == {"SALARY_FILE_NOT_FOUND": len(rows)}
    assert report["captain_table"]["slates"][TB_DAL]["gap"] == "SALARY_FILE_NOT_FOUND"
    assert _by_name(report)["salary_left"]["top_minus_bottom"]["slates"] == 1


def test_an_unreadable_salary_file_is_named(tmp_path):
    root, rows = _real_slate(tmp_path, drop_salary=True)
    junk = b"not,a,draftkings,file\n1,2,3,4\n"
    (root / TB_DAL / "input" / "DKSalaries.csv").write_bytes(junk)
    for row in rows:
        row["hashes"]["salary_sha256"] = sha256_bytes(junk)
    (root / TB_DAL / "construction" / rj.RECORD_NAME).write_bytes(
        b"".join(canonical_json_bytes(row) + b"\n" for row in rows))
    _write_results(root, TB_DAL, rows, _finishes_for(rows))
    assert _report(root)["captain_table"]["unresolved"] == {"SALARY_FILE_UNREADABLE": len(rows)}


def test_a_captain_the_salary_file_does_not_hold_is_named(tmp_path):
    root, rows = _real_slate(tmp_path)
    rows[0]["captain_dk_id"] = "1"
    (root / TB_DAL / "construction" / rj.RECORD_NAME).write_bytes(
        b"".join(canonical_json_bytes(row) + b"\n" for row in rows))
    _write_results(root, TB_DAL, rows, _finishes_for(rows))
    table = _report(root)["captain_table"]
    assert table["unresolved"] == {"CAPTAIN_NOT_IN_SALARY_FILE": 1}
    assert sum(found["entries"] for found in table["slates"][TB_DAL]["positions"].values()) == len(rows) - 1


# ----------------------------------------------------------------------------- run fields and the report


def test_thesis_method_and_rung_are_counted_not_compared(tmp_path):
    report = _report(_slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)}))
    assert report["run_fields"] == {"final_rung": {"rows": 6, "rows_with_value": 0},
                                    "method": {"rows": 6, "rows_with_value": 0},
                                    "thesis": {"rows": 6, "rows_with_value": 0}}
    rows = [json.loads(json.dumps(row)) for row in A_ROWS]
    rows[0]["run"] = dict(rows[0]["run"], thesis="T1", method={"kind": "ENGINE_FILE", "stage": "S", "final_rung": "R2"})
    report = _report(_slates(tmp_path, {"a-sd": (rows, A_FIN)}, "other"))
    assert report["run_fields"]["thesis"] == {"rows": 6, "rows_with_value": 1}
    assert report["run_fields"]["method"] == {"rows": 6, "rows_with_value": 1}
    assert report["run_fields"]["final_rung"] == {"rows": 6, "rows_with_value": 1}


def test_the_report_states_its_limits_and_cannot_be_read_as_a_claim(tmp_path):
    report = _report(_slates(tmp_path, {"a-sd": (A_ROWS, A_FIN)}))
    settings = rr.bootstrap_settings(_metrics())
    assert report["limits"]["webb_distinct_weight_vectors_at_the_minimum"] == 6 ** settings.interval_min_slates
    assert report["limits"]["resamples"] == settings.resamples
    assert set(report["does_not_establish"]) == {*rj.DOES_NOT_ESTABLISH, "CAUSE_OF_A_BUST"}
    assert report["reading"]["top_minus_bottom"] == "POSITIVE_MEANS_TOP_ENTRIES_CARRY_MORE"
    assert report["reading"]["percentile_slope"] == "NEGATIVE_MEANS_MORE_GOES_WITH_A_BETTER_FINISH"
    assert report["family"] == {"descriptors": len(rd.DESCRIPTORS), "intervals": 8, "adjustment": "NONE"}
    text = json.dumps(report).encode("utf-8")
    assert b"$" not in text


# ------------------------------------------------------------------------------ writing and determinism


def _run(tmp_path: Path, folders: dict, name: str = "slates", results: str = "results") -> rd.DescriptorOutcome:
    root = _slates(tmp_path, folders, name)
    return rd.run_results_descriptors(tmp_path / results, root)


def test_the_report_is_written_once_and_a_second_run_is_byte_identical(tmp_path):
    folders = _folders(_spec(6))
    first = _run(tmp_path, folders)
    assert first.status == "COMPLETE" and first.exit_code == 0 and first.file["state"] == "WRITTEN"
    path = Path(first.file["path"])
    assert path.parent == tmp_path / "results" / "reports" / "descriptors"
    assert path.name.startswith("results_descriptors.") and path.name.endswith(f".{rd.WRITER}.json")
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and sha256_bytes(raw) == first.file["sha256"]
    second = rd.run_results_descriptors(tmp_path / "results", tmp_path / "slates")
    assert second.status == "ALREADY_PRESENT" and second.file["sha256"] == first.file["sha256"]
    assert path.read_bytes() == raw


def test_the_bytes_do_not_depend_on_the_order_the_folders_were_made(tmp_path):
    folders = _folders(_spec(6))
    forward = _run(tmp_path, folders, "forward", "results-forward")
    backward = _run(tmp_path, dict(reversed(list(folders.items()))), "backward", "results-backward")
    assert forward.file["sha256"] == backward.file["sha256"]
    assert Path(forward.file["path"]).name == Path(backward.file["path"]).name


def test_a_changed_input_byte_gets_a_new_name_and_the_old_report_stays(tmp_path):
    folders = _folders(_spec(6))
    first = _run(tmp_path, folders)
    slate = sorted(folders)[0]
    results = tmp_path / "slates" / slate / "construction" / rj.RESULTS_NAME
    payload = json.loads(results.read_bytes())
    payload["entries"][0]["points_hundredths"] += 1
    results.write_bytes((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    second = rd.run_results_descriptors(tmp_path / "results", tmp_path / "slates")
    assert second.status == "COMPLETE" and second.file["path"] != first.file["path"]
    assert Path(first.file["path"]).is_file() and Path(second.file["path"]).is_file()
    record = tmp_path / "slates" / slate / "construction" / rj.RECORD_NAME
    lines = record.read_bytes().splitlines(keepends=True)
    changed = json.loads(lines[0])
    changed["salary_left"] += 100
    lines[0] = canonical_json_bytes(changed) + b"\n"
    record.write_bytes(b"".join(lines))
    third = rd.run_results_descriptors(tmp_path / "results", tmp_path / "slates")
    assert third.status == "COMPLETE" and third.file["path"] not in (first.file["path"], second.file["path"])


def test_a_changed_metrics_file_gets_a_new_name(tmp_path, monkeypatch):
    folders = _folders(_spec(6))
    first = _run(tmp_path, folders)
    copy = tmp_path / "metrics_v2.json"
    copy.write_bytes(rr.METRICS_V2_PATH.read_bytes() + b" ")
    monkeypatch.setattr(rr, "METRICS_V2_PATH", copy)
    second = rd.run_results_descriptors(tmp_path / "results", tmp_path / "slates")
    assert second.status == "COMPLETE" and second.file["path"] != first.file["path"]
    assert json.loads(Path(second.file["path"]).read_bytes())["metrics_sha256"] == sha256_bytes(copy.read_bytes())


def test_a_hand_edited_report_is_never_overwritten(tmp_path):
    folders = _folders(_spec(6))
    first = _run(tmp_path, folders)
    path = Path(first.file["path"])
    path.write_bytes(path.read_bytes().replace(b"salary_left", b"salary_lefx", 1))
    edited = path.read_bytes()
    second = rd.run_results_descriptors(tmp_path / "results", tmp_path / "slates")
    assert second.status == "REFUSED" and second.exit_code == 2 and second.file["state"] == "REFUSED"
    assert second.problems == ("RESULTS_DESCRIPTORS_ARTIFACT_CONFLICT:file=report",)
    assert path.read_bytes() == edited


def test_a_failed_write_is_named(tmp_path, monkeypatch):
    def no_link(source, target):
        raise PermissionError("held")

    monkeypatch.setattr(entry_history.os, "link", no_link)
    outcome = _run(tmp_path, _folders(_spec(6)))
    assert outcome.status == "WRITE_FAILED" and outcome.exit_code == 2
    assert outcome.problems == ("RESULTS_DESCRIPTORS_WRITE_FAILED:file=report:exception=PermissionError",)


def test_no_slate_with_a_results_file_still_writes_a_named_empty_report(tmp_path):
    outcome = _run(tmp_path, {"a-sd": (A_ROWS, None)})
    assert outcome.status == "COMPLETE"
    report = json.loads(Path(outcome.file["path"]).read_bytes())
    assert [(item["slate"], item["gap"]) for item in report["slates"]] == [("a-sd", "NO_RESULTS_FILE")]
    assert report["sample"]["slates"] == 0
    assert all(item["top_minus_bottom"]["estimate"] is None for item in report["descriptors"])


# ----------------------------------------------------------------------------------------- the command


def _command(capsys, *argv: str) -> tuple[int, dict]:
    code = cli.main(["results-descriptors", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_the_command_prints_the_outcome_and_exits_by_status(tmp_path, capsys):
    root = _slates(tmp_path, _folders(_spec(6)))
    code, printed = _command(capsys, "--results-root", str(tmp_path / "results"), "--slates-root", str(root))
    assert code == 0 and printed["status"] == "COMPLETE" and printed["contract"] == rd.CONTRACT_VERSION
    assert printed["headline"]["sample"]["slates"] == 6
    assert printed["headline"]["primary"]["salary_left"]["top_minus_bottom"]["estimate"] is not None
    assert printed["headline"]["family"] == {"descriptors": len(rd.DESCRIPTORS), "intervals": 8, "adjustment": "NONE"}
    assert printed["headline"]["captain_unresolved"] == {"SALARY_FILE_NOT_FOUND": 60}
    code, printed = _command(capsys, "--results-root", str(tmp_path / "results"), "--slates-root", str(tmp_path / "nope"))
    assert code == 2 and printed["problems"] == ["RESULTS_DESCRIPTORS_INPUT_INVALID:field=slates_root"]


def test_the_windows_wrapper_lists_the_command():
    assert "'results-descriptors'" in (REPO / "nfl.ps1").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------ the shared bootstrap


def test_the_default_scale_leaves_every_existing_figure_unchanged():
    settings = rr.bootstrap_settings(_metrics())
    clusters = [(Fraction(3, 10), Fraction(1, 2)), (Fraction(1, 5), Fraction(1, 3)), (Fraction(-1, 7), Fraction(1, 2)),
                (Fraction(2, 9), Fraction(2, 3)), (Fraction(1, 11), Fraction(1, 4))]
    exact = sum(y for y, _ in clusters) / sum(x for _, x in clusters)
    by_default = rr._statistic(clusters, settings, random.Random(5).random)
    explicit = rr._statistic(clusters, settings, random.Random(5).random, scale=100)
    unit = rr._statistic(clusters, settings, random.Random(5).random, scale=1)
    assert by_default == explicit
    assert Fraction(by_default["estimate"]) == round(exact * 100, 4)
    assert Fraction(unit["estimate"]) == round(exact, 4)
    assert by_default["method"] == unit["method"] == rr.WILD and by_default["slates"] == unit["slates"] == 5
    interval = rr.interval_figures(0.25, 0.1, [-1.0, 0.0, 1.0] * 4000, settings)
    assert interval == rr.interval_figures(0.25, 0.1, [-1.0, 0.0, 1.0] * 4000, settings, scale=100)


# ----------------------------------------------------------------------------- registry and contract


def test_every_descriptor_code_is_registered_p_in_its_family_and_emitted_by_this_module():
    registry = load_gate_registry()
    assert registry.families["results_descriptors"].gate_class is GateClass.P
    assert {code for code, name in registry.codes.items() if name == "results_descriptors"} == set(rd.DESCRIPTOR_CODES)
    scanned = scanned_codes()
    for code in rd.DESCRIPTOR_CODES:
        assert scanned.get(code) == frozenset({"results_descriptors.py"}), code


def test_the_contract_names_every_descriptor_gap_code_and_key():
    text = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    section = text[text.index("## NFL results descriptors, nfl_results_descriptors_v1"):]
    section = section[: section.index("\n## ", 1)]
    names = {*(item.name for item in rd.DESCRIPTORS), *rd.GAPS, *rd.DESCRIPTOR_CODES, rd.CONTRACT_VERSION, rd.POPULATION,
             "top_minus_bottom", "percentile_slope", "SECONDARY_DESCRIPTOR", "captain_table", "run_fields", "family",
             "limits", "sample", "contests_with_both_groups", "joined_entries", "results_sha256", "inputs_digest",
             "metrics_sha256", "CAUSE_OF_A_BUST", *rj.DOES_NOT_ESTABLISH}
    assert not sorted(name for name in names if f"`{name}`" not in section)
