"""Session 76b: `qa_showdown_portfolio.py --theses`, the relabelled thesis map after the contest pass.

The contest pass moves lineups between Entry IDs, so a run's claim can no longer say which thesis each Entry ID holds
(`showdown_thesis_check.py` refuses moved lineups) and Session 75's first-place table read no labels after the pass.
`diversify_showdown_contests.py --theses-out` writes `nfl_entry_thesis_map_v1`. The QA labels each export row by its exact
lineup first, so a lineup moved whole after the pass keeps its label; a row whose roster changed takes its own Entry ID's
label and is named. The map feeds the reading only: a map that does not bind is named and changes no other key, no verdict
and no exit code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import first_place_coverage as fpc

from . import test_qa_showdown_portfolio as sd

LEGAL, OTHER = sd.LEGAL, sd.OTHER
THIRD = ["den_qb", "kc_wr1", "den_wr1", "kc_rb", "den_te", "kc_te"]
OTHER_EDITED = ["den_qb", "den_wr2", "kc_rb", "kc_wr2", "den_te", "kc_k"]
LEGAL_EDITED = ["kc_qb", "kc_wr2", "den_rb", "den_wr2", "kc_te", "kc_k"]
E0, E1, E2 = sd.entry_id(0), sd.entry_id(1), sd.entry_id(2)
WRITTEN = {0: (LEGAL, "T1"), 1: (OTHER, "T2"), 2: (THIRD, "T3")}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _map(tmp_path: Path, lineups=WRITTEN, **override) -> Path:
    """A map as `diversify_showdown_contests.py` writes it, for the lineups and labels given by row number."""

    doc = {
        "schema_version": "nfl_entry_thesis_map_v1",
        "written_by": "scripts/diversify_showdown_contests.py",
        "mode": "SHOWDOWN",
        "contest_assignment_version": "within_contest_diversity_v2",
        "salary_sha256": _sha(sd.salary_csv(tmp_path)),
        "entries_sha256": "0" * 64,
        "source_theses_sha256": "0" * 64,
        "entries": {sd.entry_id(n): {"thesis": thesis, "roster": sd.ids(lineup)} for n, (lineup, thesis) in lineups.items()},
        "does_not_establish": [],
    }
    doc.update(override)
    path = tmp_path / "map.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _reading(tmp_path: Path, lineups, labels) -> dict:
    rows = [(sd.entry_id(n), "9001", sd.ids(lineup)) for n, lineup in enumerate(lineups)]
    want = fpc.reading(rows, mode=ca.MODE_SHOWDOWN, players=fpc.players_from_salary_csv(tmp_path / "sal.csv"),
                       thesis_by_entry=labels, source="EXPORT")
    return json.loads(json.dumps(want))


def _qa(tmp_path, capsys, lineups, thesis_map):
    tpl, exp = sd.files(tmp_path, lineups)
    if callable(thesis_map):
        thesis_map = thesis_map(exp)
    code, report = sd.check(tmp_path, capsys, tpl, exp, ["--theses", str(thesis_map)])
    plain_code, plain = sd.check(tmp_path, capsys, tpl, exp)
    return code, report, plain_code, plain


def _same_but_the_reading(code, report, plain_code, plain) -> bool:
    report = {k: v for k, v in report.items() if k not in ("first_place_thesis_map", "first_place_coverage")}
    plain = {k: v for k, v in plain.items() if k != "first_place_coverage"}
    return (code, report) == (plain_code, plain)


def test_a_bound_map_labels_every_row_and_moves_nothing_but_the_reading(tmp_path, capsys):
    code, report, plain_code, plain = _qa(
        tmp_path, capsys, [LEGAL, OTHER, THIRD],
        lambda exp: _map(tmp_path, {0: (LEGAL, "T1"), 1: (OTHER, "T2"), 2: (THIRD, "T1")}, entries_sha256=_sha(exp)))
    block = report["first_place_thesis_map"]
    assert block["map_version"] == "nfl_entry_thesis_map_v1"
    assert (block["binding"], block["refusal"], block["labels_from"]) == ("BOUND", None, "THESES_MAP")
    assert block["same_file_as_written"] is True and block["labelled_rows"] == 3
    assert block["roster_changed"] == block["moved_since_written"] == block["unlabelled_entry_ids"] == []
    assert report["first_place_coverage"] == _reading(tmp_path, [LEGAL, OTHER, THIRD], {E0: "T1", E1: "T2", E2: "T1"})
    assert report["first_place_coverage"]["contests"][0]["statistics"]["distinct_theses"] == 2
    assert list(report)[-3:] == ["first_place_thesis_map", "first_place_coverage", "VERDICT"]
    # Without the flag there is no map key and the reading has no labels, as before Session 76b.
    assert "first_place_thesis_map" not in plain and plain["first_place_coverage"]["thesis_labels"] == "NONE"
    assert _same_but_the_reading(code, report, plain_code, plain)


def test_a_lineup_moved_whole_after_the_pass_keeps_its_label(tmp_path, capsys):
    # The map was written for LEGAL, OTHER, THIRD; a contest-targeted placement then exchanged rows 0 and 1.
    code, report, plain_code, plain = _qa(tmp_path, capsys, [OTHER, LEGAL, THIRD], _map(tmp_path))
    block = report["first_place_thesis_map"]
    assert block["binding"] == "BOUND" and block["same_file_as_written"] is False
    assert block["moved_since_written"] == [E0, E1] and block["roster_changed"] == []
    assert block["labelled_rows"] == 3
    assert report["first_place_coverage"] == _reading(tmp_path, [OTHER, LEGAL, THIRD], {E0: "T2", E1: "T1", E2: "T3"})
    assert _same_but_the_reading(code, report, plain_code, plain)


def test_a_row_edited_after_the_pass_takes_its_entry_s_label_and_is_named(tmp_path, capsys):
    # Session 66's rule: the thesis is read by Entry ID, never looked up from an edited roster.
    _code, report, _plain_code, _plain = _qa(tmp_path, capsys, [LEGAL, OTHER_EDITED, THIRD], _map(tmp_path))
    block = report["first_place_thesis_map"]
    assert block["roster_changed"] == [E1] and block["moved_since_written"] == [] and block["labelled_rows"] == 3
    assert report["first_place_coverage"] == _reading(
        tmp_path, [LEGAL, OTHER_EDITED, THIRD], {E0: "T1", E1: "T2", E2: "T3"})


def test_an_edited_row_whose_own_lineup_moved_elsewhere_and_a_row_the_map_never_named_are_unlabelled(tmp_path, capsys):
    # Row 0 now holds OTHER, moved from row 1; row 1 holds an edit of LEGAL, so row 1's own lineup (OTHER) carries its
    # label elsewhere and row 1 takes none. The map never named row 2.
    lineups = [OTHER, LEGAL_EDITED, THIRD]
    _code, report, _plain_code, _plain = _qa(
        tmp_path, capsys, lineups, _map(tmp_path, {0: (LEGAL, "T1"), 1: (OTHER, "T2")}))
    block = report["first_place_thesis_map"]
    assert block["moved_since_written"] == [E0] and block["roster_changed"] == []
    assert block["unlabelled_entry_ids"] == [E1, E2] and block["labelled_rows"] == 1
    assert report["first_place_coverage"] == _reading(tmp_path, lineups, {E0: "T2"})


NOT_BOUND = [
    pytest.param("unreadable", "THESES_MAP_UNREADABLE", id="unreadable"),
    pytest.param("missing", "THESES_MAP_UNREADABLE", id="missing"),
    pytest.param({"schema_version": "nfl_entry_thesis_map_v0"}, "THESES_MAP_SCHEMA", id="schema"),
    pytest.param({"mode": "CLASSIC"}, "THESES_MAP_NOT_SHOWDOWN", id="mode"),
    pytest.param({"salary_sha256": "f" * 64}, "THESES_MAP_SALARY_MISMATCH", id="salary"),
    pytest.param({"entries": []}, "THESES_MAP_ENTRY_MALFORMED", id="entries_list"),
    pytest.param({"entries": {E0: {"thesis": 3, "roster": sd.ids(LEGAL)}}}, "THESES_MAP_ENTRY_MALFORMED", id="thesis"),
    pytest.param({"entries": {E0: {"thesis": "T1", "roster": sd.ids(LEGAL)[:5]}}}, "THESES_MAP_ENTRY_MALFORMED",
                 id="roster"),
    pytest.param({"entries": {"999": {"thesis": "T1", "roster": sd.ids(LEGAL)}}}, "THESES_MAP_ENTRY_IDS_NOT_IN_TEMPLATE",
                 id="foreign"),
    pytest.param({"entries": {E0: {"thesis": "T1", "roster": sd.ids(LEGAL)},
                              E1: {"thesis": "T2", "roster": sd.ids(LEGAL)}}}, "THESES_MAP_REPEATED_LINEUP", id="repeat"),
    # The right salary file and Entry IDs, but written for other lineups (the Session 76b review): every row would have
    # fallen back to its Entry ID's label.
    pytest.param({"lineups": {0: (LEGAL_EDITED, "T1"), 1: (OTHER_EDITED, "T2")}}, "THESES_MAP_MATCHES_NO_LINEUP",
                 id="no_match"),
]


@pytest.mark.parametrize("override, code", NOT_BOUND)
def test_a_map_that_does_not_bind_supplies_no_labels_and_moves_nothing_else(tmp_path, capsys, override, code):
    if override == "unreadable":
        thesis_map = tmp_path / "map.json"
        thesis_map.write_bytes(b"{not json")
    elif override == "missing":
        thesis_map = tmp_path / "absent.json"
    else:
        thesis_map = _map(tmp_path, **override)
    got, report, plain_code, plain = _qa(tmp_path, capsys, [LEGAL, OTHER, THIRD], thesis_map)
    block = report["first_place_thesis_map"]
    assert block["binding"] == "NOT_BOUND" and block["refusal"]["code"] == code
    assert block["labels_from"] == "NONE" and block["labelled_rows"] == 0 and block["same_file_as_written"] is None
    assert report["first_place_coverage"]["thesis_labels"] == "NONE"
    assert report["first_place_coverage"] == plain["first_place_coverage"]
    assert _same_but_the_reading(got, report, plain_code, plain)


def test_an_unbound_map_falls_back_to_the_claim_s_labels_and_a_bound_one_comes_first(tmp_path):
    tpl, exp = sd.files(tmp_path, [LEGAL, OTHER, THIRD])
    claimed = {"status": "CHECKED", "entries": {E0: {"thesis": "C1"}, E1: {"thesis": "C2"}, E2: {"thesis": "C3"}}}

    def args(thesis_map):
        return argparse.Namespace(salaries=str(tmp_path / "sal.csv"), template=str(tpl), export=str(exp),
                                  theses=str(thesis_map))

    block, labels = sd.qa.thesis_map_pass(args(_map(tmp_path, salary_sha256="f" * 64)), claimed)
    assert block["binding"] == "NOT_BOUND" and block["labels_from"] == "CLAIM"
    assert labels == {E0: "C1", E1: "C2", E2: "C3"}
    block, labels = sd.qa.thesis_map_pass(args(_map(tmp_path)), claimed)
    assert block["binding"] == "BOUND" and block["labels_from"] == "THESES_MAP"
    assert labels == {E0: "T1", E1: "T2", E2: "T3"}
    block, labels = sd.qa.thesis_map_pass(args(_map(tmp_path, mode="CLASSIC")), {"status": "REFUSED"})
    assert block["labels_from"] == "NONE" and labels is None
