"""Session 23d: how `contest_facts_csv` reaches a run (request v5, schema classification, the CLI flag).

Files are classified by their first row, never their name; a near-miss header is an unclassified CSV and not a
facts file; the request carries the field from v5 on and refuses it on an older schema; supplying facts never
clears a certification-only blocker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs import cowork
from nfl_dfs.cli import build_parser
from nfl_dfs.cowork import (
    COWORK_REQUEST_VERSION,
    COWORK_REQUEST_VERSION_V4,
    COWORK_REQUEST_VERSION_V5,
    PATH_FIELDS,
    SUPPORTED_REQUEST_VERSIONS,
    CoworkInputError,
    CoworkRunRequest,
    classify_csv,
    discover_csv_inputs,
    request_version_for,
    required_next_inputs,
    resolve_request_inputs,
)

FACTS_HEADER = "contest_id,field_size,places_paid,entry_fee"
FACTS_BODY = FACTS_HEADER + "\n111,1000,49,20\n222,200,40,5\n"
SALARY_LINE = "Position,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
ENTRY_LINE = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX\n"


def _facts(tmp_path: Path, name: str = "facts.csv", body: str = FACTS_BODY) -> Path:
    path = tmp_path / name
    path.write_bytes(body.encode("utf-8"))
    return path


def _input_dir(tmp_path: Path, **extra: str) -> Path:
    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / "s.csv").write_bytes(SALARY_LINE.encode())
    (folder / "e.csv").write_bytes(ENTRY_LINE.encode())
    for name, body in extra.items():
        (folder / name).write_bytes(body.encode())
    return folder


# ------------------------------------------------------------------- classification by schema


def test_the_exact_header_classifies_a_facts_file_whatever_its_name(tmp_path):
    for name in ("facts.csv", "payouts.csv", "whatever-Ben-called-it.csv", "DKEntries.csv"):
        assert classify_csv(_facts(tmp_path, name)) == "contest_facts_csv", name


def test_the_header_is_the_only_thing_read_and_a_payout_table_stays_a_payout_table(tmp_path):
    payout = tmp_path / "contest_facts.csv"
    payout.write_bytes(b"rank_start,rank_end,prize_type,value\n1,1,CASH,1000\n")
    assert classify_csv(payout) == "payout_csv"


@pytest.mark.parametrize(
    "header",
    [
        "contest_id,field_size,places_paid,entry_fee,",           # a trailing comma
        "contest_id,field_size,places_paid",                      # a missing column
        "Contest_ID,field_size,places_paid,entry_fee",            # renamed
        "contest_id, field_size,places_paid,entry_fee",           # a stray space
        "field_size,contest_id,places_paid,entry_fee",            # reordered
    ],
)
def test_a_near_miss_header_is_an_unclassified_csv_and_never_a_facts_file(tmp_path, header):
    folder = _input_dir(tmp_path, **{"near.csv": header + "\n111,1000,49,20\n"})
    discovered = discover_csv_inputs(folder)
    assert "contest_facts_csv" not in discovered.classified
    assert [path.name for path in discovered.unclassified_csvs] == ["near.csv"]


def test_discovery_attaches_one_facts_file_and_refuses_two(tmp_path):
    folder = _input_dir(tmp_path, **{"a.csv": FACTS_BODY})
    assert discover_csv_inputs(folder).classified["contest_facts_csv"].name == "a.csv"
    (folder / "b.csv").write_bytes(FACTS_BODY.replace("1000", "2000").encode())
    with pytest.raises(CoworkInputError, match="ambiguous Cowork CSV inputs: contest_facts_csv="):
        discover_csv_inputs(folder)


# --------------------------------------------------------------------------- the request v5


def test_the_request_carries_the_field_from_v5_and_older_versions_stay_unmutated(tmp_path):
    assert COWORK_REQUEST_VERSION == COWORK_REQUEST_VERSION_V5 == "nfl_cowork_run_request_v5"
    assert COWORK_REQUEST_VERSION_V4 == "nfl_cowork_run_request_v4"
    assert SUPPORTED_REQUEST_VERSIONS[-2:] == (COWORK_REQUEST_VERSION_V4, COWORK_REQUEST_VERSION_V5)
    assert len(SUPPORTED_REQUEST_VERSIONS) == 5
    assert "contest_facts_csv" in PATH_FIELDS
    path = _facts(tmp_path)
    request = CoworkRunRequest.from_mapping(
        {"schema_version": COWORK_REQUEST_VERSION_V5, "contest_facts_csv": str(path)}, allowed_roots=(tmp_path,))
    assert request.contest_facts_csv == str(path.resolve())
    unversioned = CoworkRunRequest.from_mapping({"contest_facts_csv": str(path)}, allowed_roots=(tmp_path,))
    assert unversioned.schema_version == COWORK_REQUEST_VERSION_V5
    assert CoworkRunRequest().contest_facts_csv is None and CoworkRunRequest().to_dict()["contest_facts_csv"] is None
    for older in SUPPORTED_REQUEST_VERSIONS[:-1]:
        with pytest.raises(CoworkInputError, match="introduced in 'nfl_cowork_run_request_v5'"):
            CoworkRunRequest.from_mapping(
                {"schema_version": older, "contest_facts_csv": str(path)}, allowed_roots=(tmp_path,))
    # an older request without the field still loads and keeps its own version string
    kept = CoworkRunRequest.from_mapping({"schema_version": COWORK_REQUEST_VERSION_V4, "label": "archived"})
    assert kept.schema_version == COWORK_REQUEST_VERSION_V4 and kept.contest_facts_csv is None


def test_a_flag_for_the_new_field_raises_an_older_request_and_session_61s_field_still_means_v4():
    assert request_version_for(COWORK_REQUEST_VERSION_V4, {"contest_facts_csv": "x"}) == COWORK_REQUEST_VERSION_V5
    assert request_version_for(COWORK_REQUEST_VERSION_V5, {}) == COWORK_REQUEST_VERSION_V5
    assert request_version_for("nfl_cowork_run_request_v1", {"construction_judgment_json": "x"}) == COWORK_REQUEST_VERSION_V4
    assert cowork.REQUEST_FIELDS_ADDED_AFTER_V1["contest_facts_csv"] == COWORK_REQUEST_VERSION_V5
    assert cowork.REQUEST_FIELDS_ADDED_AFTER_V1["construction_judgment_json"] == COWORK_REQUEST_VERSION_V4


def test_discovery_raises_a_replayed_v4_request_to_v5_instead_of_refusing_it(tmp_path):
    folder = _input_dir(tmp_path, **{"facts.csv": FACTS_BODY})
    old = CoworkRunRequest.from_mapping({"schema_version": COWORK_REQUEST_VERSION_V4, "label": "replay"})
    resolved, unclassified = resolve_request_inputs(old, input_dir=folder, allowed_roots=(folder,))
    assert resolved.schema_version == COWORK_REQUEST_VERSION_V5
    assert Path(resolved.contest_facts_csv).name == "facts.csv" and unclassified == ()


def test_a_run_with_no_facts_file_keeps_its_request_version_and_leaves_the_field_empty(tmp_path):
    folder = _input_dir(tmp_path)
    old = CoworkRunRequest.from_mapping({"schema_version": COWORK_REQUEST_VERSION_V4, "label": "replay"})
    resolved, _ = resolve_request_inputs(old, input_dir=folder, allowed_roots=(folder,))
    assert resolved.schema_version == COWORK_REQUEST_VERSION_V4 and resolved.contest_facts_csv is None


def test_a_path_that_does_not_exist_is_the_existing_named_stop_before_anything_is_written(tmp_path):
    folder = _input_dir(tmp_path)
    request = CoworkRunRequest.from_mapping(
        {"contest_facts_csv": str(folder / "nowhere.csv")}, allowed_roots=(folder,))
    with pytest.raises(CoworkInputError, match="contest_facts_csv does not exist"):
        resolve_request_inputs(request, input_dir=folder, allowed_roots=(folder,))


def test_a_path_outside_the_allowed_roots_is_refused_like_every_other_input(tmp_path):
    outside = _facts(tmp_path, "outside.csv")
    inside = tmp_path / "roots"
    inside.mkdir()
    with pytest.raises(CoworkInputError, match="outside the supplied attachment"):
        CoworkRunRequest.from_mapping({"contest_facts_csv": str(outside)}, allowed_roots=(inside,))


# ---------------------------------------------------------------------------- the command line


def test_the_flag_exists_on_run_slate_and_its_alias_and_defaults_to_nothing():
    parser = build_parser()
    for command in ("run-slate", "cowork-run"):
        assert parser.parse_args([command, "--contest-facts-csv", "c.csv"]).contest_facts_csv == "c.csv"
        assert parser.parse_args([command]).contest_facts_csv is None


# ---------------------------------------------------- certification-only blockers are never cleared


def test_supplying_facts_never_clears_the_payout_or_field_size_blockers(tmp_path):
    path = _facts(tmp_path)
    request = CoworkRunRequest.from_mapping({"contest_facts_csv": str(path)}, allowed_roots=(tmp_path,))
    blockers = required_next_inputs(request)
    assert any(value.startswith("CONTEST_PAYOUT_REQUIRED:") for value in blockers)
    assert any(value.startswith("FIELD_SIZE_REQUIRED:") for value in blockers)
    assert any(value.startswith("ADVERTISED_PRIZE_VALUE_REQUIRED:") for value in blockers)
