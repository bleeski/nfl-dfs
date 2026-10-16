"""`scripts/diversify_showdown_contests.py`: within-contest reassignment of a filled file."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import first_place_coverage as fpc

from . import test_qa_showdown_portfolio as sd_qa

SCRIPT =Path(__file__).resolve().parents[1] / "scripts" / "diversify_showdown_contests.py"
V1, V2 = "within_contest_diversity_v1", "within_contest_diversity_v2"


def _load():
    spec = importlib.util.spec_from_file_location("diversify_showdown_contests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PEOPLE = [f"P{index:02d}" for index in range(14)]  # P00..P06 team AAA, P07..P13 team BBB
HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions"


def _salaries(tmp_path: Path) -> Path:
    lines = ["Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"]
    for index, name in enumerate(PEOPLE):
        team = "AAA" if index < 7 else "BBB"
        for role, offset in (("CPT", 1000), ("FLEX", 2000)):
            dk_id = str(offset + index)
            lines.append(f"WR,{name} ({dk_id}),{name},{dk_id},{role},5000,AAA@BBB 09/28/2026 08:15PM ET,{team},1")
    path = tmp_path / "salaries.csv"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


def _roster(captain: int, flex: list[int]) -> list[str]:
    return [str(1000 + captain)] + [str(2000 + index) for index in flex]


# Contest 1 holds three near-copies under one Captain; contest 2 holds three
# lineups that are nothing alike. A good reassignment trades between them.
LINEUPS = {
    "900000001": ("C1", _roster(0, [1, 2, 3, 7, 8])),
    "900000002": ("C1", _roster(0, [1, 2, 3, 7, 9])),
    "900000003": ("C1", _roster(0, [1, 2, 4, 7, 8])),
    "900000004": ("C2", _roster(10, [11, 12, 13, 5, 6])),
    "900000005": ("C2", _roster(4, [9, 10, 11, 5, 6])),
    "900000006": ("C2", _roster(12, [13, 8, 9, 3, 6])),
}
PREFILLED = ("900000007", "C2", _roster(13, [0, 1, 2, 10, 11]))


def _template(tmp_path: Path, *, filled: bool, prefilled: bool = True) -> Path:
    lines = [HEADER]
    rows = [(entry_id, contest, roster) for entry_id, (contest, roster) in LINEUPS.items()]
    if prefilled:
        rows.append(PREFILLED)
    for entry_id, contest, roster in rows:
        keep = filled or (prefilled and entry_id == PREFILLED[0])
        cells = roster if keep else [""] * 6
        lines.append(",".join([entry_id, f"Contest {contest}", contest, "$1", *cells, "", ""]))
    lines.append(",,,,,,,,,,,1. instructions stay byte for byte")
    path = tmp_path / ("filled.csv" if filled else "template.csv")
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


def _rows(path: Path) -> dict[str, list[str]]:
    out = {}
    for line in path.read_bytes().decode("utf-8").split("\r\n"):
        fields = line.split(",")
        if fields and fields[0].isdigit():
            out[fields[0]] = fields[4:10]
    return out


def _run(tmp_path: Path, **extra) -> tuple[int, Path, Path]:
    module = _load()
    out = tmp_path / "out.csv"
    record = tmp_path / "record.json"
    argv = ["--salaries", str(_salaries(tmp_path)), "--template", str(_template(tmp_path, filled=False)),
            "--entries", str(_template(tmp_path, filled=True)), "--out", str(out), "--record", str(record),
            "--restarts", "20"]
    for key, value in extra.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    return module.main(argv), out, record


def test_reassignment_lowers_the_score_and_keeps_every_lineup(tmp_path):
    code, out, record = _run(tmp_path, version=V1)
    assert code == 0
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["score"]["after"] < data["score"]["before"]
    before, after = data["contests_before"]["C1"], data["contests_after"]["C1"]
    assert before["distinct_captains"] == 1 and after["distinct_captains"] > 1
    assert after["max_shared_people"] < before["max_shared_people"]
    filled = _rows(tmp_path / "filled.csv")
    written = _rows(out)
    assert sorted(map(tuple, filled.values())) == sorted(map(tuple, written.values()))


def test_a_row_the_template_already_filled_never_moves(tmp_path):
    code, out, _record = _run(tmp_path)
    assert code == 0
    assert _rows(out)[PREFILLED[0]] == PREFILLED[2]


def test_only_blank_roster_cells_differ_from_the_template(tmp_path):
    code, out, _record = _run(tmp_path)
    assert code == 0
    template = (tmp_path / "template.csv").read_bytes().split(b"\r\n")
    written = out.read_bytes().split(b"\r\n")
    assert len(template) == len(written)
    for t_line, o_line in zip(template, written):
        if t_line != o_line:
            t_fields, o_fields = t_line.split(b","), o_line.split(b",")
            assert t_fields[:4] == o_fields[:4] and t_fields[10:] == o_fields[10:]
            assert all(cell == b"" for cell in t_fields[4:10])


def test_the_result_is_deterministic(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    assert _run(first)[0] == 0 and _run(second)[0] == 0
    assert (first / "out.csv").read_bytes() == (second / "out.csv").read_bytes()


def test_an_existing_output_is_refused_and_left_alone(tmp_path, capsys):
    (tmp_path / "out.csv").write_bytes(b"keep")
    code, out, _record = _run(tmp_path)
    assert code == 1 and out.read_bytes() == b"keep"
    assert "OUTPUT_EXISTS" in capsys.readouterr().err


def test_a_changed_prefilled_row_is_refused(tmp_path, capsys):
    module = _load()
    salaries = _salaries(tmp_path)
    template = _template(tmp_path, filled=False)
    entries = _template(tmp_path, filled=True)
    raw = entries.read_bytes().replace(",".join(PREFILLED[2]).encode(), ",".join(LINEUPS["900000001"][1]).encode())
    entries.write_bytes(raw)
    code = module.main(["--salaries", str(salaries), "--template", str(template), "--entries", str(entries),
                        "--out", str(tmp_path / "out.csv"), "--restarts", "1"])
    assert code == 1 and "PREFILLED_ROW_CHANGED" in capsys.readouterr().err
    assert not (tmp_path / "out.csv").exists()


@pytest.mark.parametrize("penalty", [0, 50])
def test_theses_are_optional_and_only_add_a_term(tmp_path, penalty):
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    code, _out, record = _run(tmp_path, theses=theses, thesis_penalty=penalty, version=V1)
    assert code == 0
    assert json.loads(record.read_text(encoding="utf-8"))["score"]["thesis_penalty"] == penalty


# --- Classic (Session 50) ---------------------------------------------------------

CLASSIC_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions"
CLASSIC_PEOPLE = (
    [("QB", "AAA", index) for index in range(2)] + [("QB", "BBB", index) for index in range(2)]
    + [("RB", "AAA", index) for index in range(4)] + [("RB", "BBB", index) for index in range(4)]
    + [("WR", "AAA", index) for index in range(6)] + [("WR", "BBB", index) for index in range(6)]
    + [("TE", "AAA", index) for index in range(2)] + [("TE", "BBB", index) for index in range(2)]
    + [("DST", "AAA", 0), ("DST", "BBB", 0)]
)


def _classic_salaries(tmp_path: Path) -> tuple[Path, dict[tuple[str, str, int], str]]:
    lines = ["Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"]
    ids = {}
    for offset, (position, team, index) in enumerate(CLASSIC_PEOPLE):
        dk_id = str(3000 + offset)
        ids[(position, team, index)] = dk_id
        name = f"{position}{team}{index}"
        lines.append(f"{position},{name} ({dk_id}),{name},{dk_id},{position},5000,AAA@BBB 09/28/2026 08:15PM ET,{team},1")
    path = tmp_path / "classic_salaries.csv"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path, ids


def _classic_roster(ids, qb, rbs, wrs, te, flex, dst):
    def pick(position, team, index):
        return ids[(position, team, index)]
    return [pick("QB", *qb), *(pick("RB", *r) for r in rbs), *(pick("WR", *w) for w in wrs),
            pick("TE", *te), pick("RB", *flex), pick("DST", *dst)]


def _classic_files(tmp_path: Path, ids) -> tuple[Path, Path, dict[str, str]]:
    a, b = "AAA", "BBB"
    rosters = {
        "910000001": ("K1", _classic_roster(ids, (a, 0), [(a, 0), (a, 1)], [(a, 0), (a, 1), (a, 2)], (a, 0), (a, 2), (b, 0))),
        "910000002": ("K1", _classic_roster(ids, (a, 0), [(a, 0), (a, 1)], [(a, 0), (a, 1), (a, 3)], (a, 0), (a, 3), (b, 0))),
        "910000003": ("K2", _classic_roster(ids, (b, 0), [(b, 0), (b, 1)], [(b, 0), (b, 1), (b, 2)], (b, 0), (b, 2), (a, 0))),
        "910000004": ("K2", _classic_roster(ids, (b, 0), [(b, 0), (b, 1)], [(b, 0), (b, 1), (b, 3)], (b, 0), (b, 3), (a, 0))),
    }
    for path_name, filled in (("classic_template.csv", False), ("classic_filled.csv", True)):
        lines = [CLASSIC_HEADER]
        for entry_id, (contest, roster) in rosters.items():
            cells = roster if filled else [""] * 9
            lines.append(",".join([entry_id, f"Contest {contest}", contest, "$1", *cells, "", ""]))
        lines.append(",,,,,,,,,,,,,,1. instructions stay byte for byte")
        (tmp_path / path_name).write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return tmp_path / "classic_template.csv", tmp_path / "classic_filled.csv", {k: v[0] for k, v in rosters.items()}


def _classic_qbs(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_bytes().decode("utf-8").split("\r\n"):
        fields = line.split(",")
        if fields and fields[0].isdigit():
            out[fields[0]] = fields[4]
    return out


def test_classic_files_are_supported_and_no_two_entry_contest_repeats_a_qb(tmp_path, capsys):
    module = _load()
    salaries, ids = _classic_salaries(tmp_path)
    template, filled, contest_of = _classic_files(tmp_path, ids)
    before = _classic_qbs(filled)
    # the solver's order: both entries of each contest hold one QB
    assert all(before[e] == before[f] for e, f in (("910000001", "910000002"), ("910000003", "910000004")))
    out, record = tmp_path / "classic_out.csv", tmp_path / "classic_record.json"
    code = module.main(["--salaries", str(salaries), "--template", str(template), "--entries", str(filled),
                        "--out", str(out), "--record", str(record), "--restarts", "20", "--version", V1])
    assert code == 0, capsys.readouterr().err
    after = _classic_qbs(out)
    assert after["910000001"] != after["910000002"] and after["910000003"] != after["910000004"]
    assert sorted(after.values()) == sorted(before.values())
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["schema_version"] == "nfl_contest_diversification_v2" and data["mode"] == "CLASSIC"
    assert data["contest_assignment"]["contest_assignment_version"] == "within_contest_diversity_v1"
    assert data["contest_assignment"]["weights"]["registered"] is True
    assert all(row["distinct_qbs"] == 2 for row in data["contests_after"].values())
    assert data["score"]["after"] < data["score"]["before"]


def test_a_weight_override_is_recorded_as_not_the_registered_weights(tmp_path):
    code, _out, record = _run(tmp_path, captain_penalty=30, version=V1)
    assert code == 0
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["contest_assignment"]["weights"]["registered"] is False
    assert data["score"]["captain_penalty"] == 30


def test_the_record_carries_the_registered_version_and_what_it_does_not_establish(tmp_path):
    code, _out, record = _run(tmp_path, version=V1)
    assert code == 0
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["contest_assignment"]["contest_assignment_version"] == "within_contest_diversity_v1"
    assert "UPLOAD_CLEARANCE" in data["does_not_establish"] and "LINEUP_LEGALITY" in data["does_not_establish"]


# --- Session 76b: v2 by default, the v3 record, the relabelled thesis map ---------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(path: Path) -> dict:
    raw = path.read_bytes()
    assert b"\r" not in raw  # written as bytes with LF endings, so every host writes the same file
    return json.loads(raw.decode("utf-8"))


def _without_seconds(record: dict) -> dict:
    return {**record, "contest_assignment": {k: v for k, v in record["contest_assignment"].items() if k != "seconds"}}


def test_the_default_is_v2_and_its_record_carries_the_objective_and_calls_v1_s_score_a_reading(tmp_path):
    code, out, record = _run(tmp_path)
    assert code == 0
    data = _record(record)
    assert data["schema_version"] == "nfl_contest_diversification_v3" and data["mode"] == "SHOWDOWN"
    step = data["contest_assignment"]
    assert step["contest_assignment_version"] == V2 and step["weights"]["registered"] is True
    assert step["objective_order"] == list(ca.OBJECTIVE_ORDER)
    # C1 held one Captain three times. Three lineups of his over two contests must repeat once: the floor, in total
    # and per contest.
    before, after = step["objective_before"], step["objective_after"]
    assert (before["contests_with_a_repeated_key_person"], before["lost_key_people"], before["same_key_person_pairs"]) == (1, 2, 3)
    assert (after["contests_with_a_repeated_key_person"], after["lost_key_people"], after["same_key_person_pairs"]) == (1, 1, 1)
    assert step["contest_objective_before"]["C1"]["same_key_person_pairs"] == 3
    assert sum(c["same_key_person_pairs"] for c in step["contest_objective_after"].values()) == 1
    # v1's score is a reading under its own definition; no top-level score can be read as v2's.
    assert "score" not in data and "contests_after" not in data and "contests_after" not in step
    reading = data["reading"]
    assert reading["definition"] == ca.READING_DEFINITION
    assert (reading["score_before"], reading["score_after"]) == (
        float(step["total_score_before"]), float(step["total_score_after"]))
    assert reading["contests_after"]["C1"]["distinct_captains"] > reading["contests_before"]["C1"]["distinct_captains"]
    assert data["search"] == {"restarts": 20, "seed": ca.DEFAULT_SEED, "time_limit_seconds": 60.0}
    assert {"UPLOAD_CLEARANCE", "LINEUP_LEGALITY"} <= set(data["does_not_establish"])
    # The record binds the bytes it read and the bytes it wrote.
    assert data["inputs"] == {
        "salaries_sha256": _sha((tmp_path / "salaries.csv").read_bytes()),
        "template_sha256": _sha((tmp_path / "template.csv").read_bytes()),
        "entries_sha256": _sha((tmp_path / "filled.csv").read_bytes()),
        "theses_sha256": None,
    }
    assert data["out_sha256"] == _sha(out.read_bytes())
    filled, written = _rows(tmp_path / "filled.csv"), _rows(out)
    assert sorted(map(tuple, filled.values())) == sorted(map(tuple, written.values()))
    assert written[PREFILLED[0]] == PREFILLED[2]
    by_roster = {tuple(cells): entry for entry, cells in filled.items()}
    assert data["mapping_entry_to_source_entry"] == {entry: by_roster[tuple(cells)] for entry, cells in written.items()}


@pytest.mark.parametrize("flag", ["captain_penalty", "thesis_penalty"], ids=["captain", "thesis"])
def test_v1_s_penalty_flags_are_refused_by_name_under_v2(tmp_path, capsys, flag):
    # Refused even at the registered value: v2 ranks these terms and has no weight for them.
    code, out, record = _run(tmp_path, **{flag: 12})
    assert code == 1 and not out.exists() and not record.exists()
    assert f"V1_PENALTY_FLAG_UNDER_V2:--{flag.replace('_', '-')}" in capsys.readouterr().err


def test_v2_counts_same_thesis_pairs_only_when_labels_are_given(tmp_path):
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    labelled, plain = tmp_path / "labelled", tmp_path / "plain"
    labelled.mkdir()
    plain.mkdir()
    assert _run(labelled, theses=theses)[0] == 0 and _run(plain)[0] == 0
    with_labels, without = _record(labelled / "record.json"), _record(plain / "record.json")
    # Six labelled lineups, three in each contest whatever the placement: three pairs a contest.
    assert with_labels["contest_assignment"]["objective_after"]["same_thesis_pairs"] == 6
    assert without["contest_assignment"]["objective_after"]["same_thesis_pairs"] == 0
    assert with_labels["inputs"]["theses_sha256"] == _sha(theses.read_bytes())


def test_classic_files_take_v2_by_default(tmp_path, capsys):
    module = _load()
    salaries, ids = _classic_salaries(tmp_path)
    template, filled, _contest_of = _classic_files(tmp_path, ids)
    out, record = tmp_path / "classic_out.csv", tmp_path / "classic_record.json"
    code = module.main(["--salaries", str(salaries), "--template", str(template), "--entries", str(filled),
                        "--out", str(out), "--record", str(record), "--restarts", "20"])
    assert code == 0, capsys.readouterr().err
    after = _classic_qbs(out)
    assert after["910000001"] != after["910000002"] and after["910000003"] != after["910000004"]
    data = _record(record)
    assert data["schema_version"] == "nfl_contest_diversification_v3" and data["mode"] == "CLASSIC"
    assert data["contest_assignment"]["contest_assignment_version"] == V2
    assert all(not row["repeated_key_person"] for row in data["contest_assignment"]["contest_objective_after"].values())
    assert all(row["distinct_qbs"] == 2 for row in data["reading"]["contests_after"].values())


def test_a_v2_stack_override_is_audited_with_the_override_and_recorded(tmp_path, capsys):
    """Three of four Classic lineups stack AAA with four distinct QBs, in two two-entry contests: one contest must pair two
    AAA stacks, so the stack weight reaches the spread. The script's audit recomputes the objective from the written bytes
    with the weight the step used; with the registered weight it would not bear out and nothing would be written."""

    module = _load()
    salaries, ids = _classic_salaries(tmp_path)
    a, b = "AAA", "BBB"
    rosters = {
        "920000001": ("K1", _classic_roster(ids, (a, 0), [(a, 0), (a, 1)], [(a, 0), (a, 1), (a, 2)], (a, 0), (a, 2), (b, 0))),
        "920000002": ("K1", _classic_roster(ids, (a, 1), [(a, 3), (b, 0)], [(a, 3), (a, 4), (a, 5)], (a, 1), (b, 1), (b, 0))),
        "920000003": ("K2", _classic_roster(ids, (b, 0), [(a, 0), (a, 1)], [(a, 0), (a, 1), (a, 2)], (a, 0), (a, 2), (a, 0))),
        "920000004": ("K2", _classic_roster(ids, (b, 1), [(b, 2), (b, 3)], [(b, 3), (b, 4), (b, 5)], (b, 1), (b, 0), (a, 0))),
    }
    for path_name, filled in (("stack_template.csv", False), ("stack_filled.csv", True)):
        lines = [CLASSIC_HEADER]
        for entry_id, (contest, roster) in rosters.items():
            cells = roster if filled else [""] * 9
            lines.append(",".join([entry_id, f"Contest {contest}", contest, "$1", *cells, "", ""]))
        (tmp_path / path_name).write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    out, record = tmp_path / "stack_out.csv", tmp_path / "stack_record.json"
    code = module.main(["--salaries", str(salaries), "--template", str(tmp_path / "stack_template.csv"),
                        "--entries", str(tmp_path / "stack_filled.csv"), "--out", str(out), "--record", str(record),
                        "--restarts", "20", "--stack-penalty", "50"])
    assert code == 0, capsys.readouterr().err
    step = _record(record)["contest_assignment"]
    assert step["weights"] == {"shared_people_exponent": 2, "same_stack_team": 50, "registered": False}
    # The best placement pairs the two AAA stacks that share nobody: the spread is that one pair's stack term, 50, worst
    # plus mean; with the registered weight it would be 12.
    assert float(step["objective_after"]["spread"]) == 100.0


def test_the_thesis_map_relabels_through_the_mapping_and_binds_the_file_it_labels(tmp_path):
    labels = {entry_id: f"T{n % 3}" for n, entry_id in enumerate(LINEUPS)}
    labels[PREFILLED[0]] = None  # a row with no claim carries no label
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps(labels), encoding="utf-8")
    code, out, record = _run(tmp_path, theses=theses, theses_out=tmp_path / "map.json")
    assert code == 0
    raw = (tmp_path / "map.json").read_bytes()
    assert b"\r" not in raw
    data = json.loads(raw.decode("utf-8"))
    assert data["schema_version"] == "nfl_entry_thesis_map_v1" and data["mode"] == "SHOWDOWN"
    assert data["written_by"] == "scripts/diversify_showdown_contests.py"
    assert data["contest_assignment_version"] == V2
    assert data["entries_sha256"] == _sha(out.read_bytes())
    assert data["salary_sha256"] == _sha((tmp_path / "salaries.csv").read_bytes())
    assert data["source_theses_sha256"] == _sha(theses.read_bytes())
    assert "UPLOAD_CLEARANCE" in data["does_not_establish"]
    mapping = _record(record)["mapping_entry_to_source_entry"]
    written = _rows(out)
    assert set(data["entries"]) == set(LINEUPS)
    for entry_id, item in data["entries"].items():
        assert item == {"thesis": labels[mapping[entry_id]], "roster": written[entry_id]}
    # The same inputs write the same bytes.
    again = tmp_path / "again"
    again.mkdir()
    (again / "theses.json").write_bytes(theses.read_bytes())
    assert _run(again, theses=again / "theses.json", theses_out=again / "map.json")[0] == 0
    assert (again / "map.json").read_bytes() == raw


def test_v1_writes_the_map_too_and_its_record_is_unchanged(tmp_path):
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    code, _out, record = _run(tmp_path, version=V1, theses=theses, theses_out=tmp_path / "map.json")
    assert code == 0
    assert json.loads((tmp_path / "map.json").read_text(encoding="utf-8"))["contest_assignment_version"] == V1
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["schema_version"] == "nfl_contest_diversification_v2"
    assert set(data) == {"schema_version", "mode", "does_not_establish", "contest_assignment", "score",
                         "mapping_entry_to_source_entry", "contests_before", "contests_after"}


def test_the_thesis_map_needs_labels_a_new_path_and_a_showdown_file(tmp_path, capsys):
    code, out, record = _run(tmp_path, theses_out=tmp_path / "map.json")
    assert code == 1 and "THESES_OUT_NEEDS_THESES" in capsys.readouterr().err
    assert not out.exists() and not record.exists() and not (tmp_path / "map.json").exists()
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    (tmp_path / "map.json").write_bytes(b"keep")
    code, out, _record = _run(tmp_path, theses=theses, theses_out=tmp_path / "map.json")
    assert code == 1 and "OUTPUT_EXISTS" in capsys.readouterr().err
    assert (tmp_path / "map.json").read_bytes() == b"keep" and not out.exists()
    module = _load()
    salaries, ids = _classic_salaries(tmp_path)
    template, filled, _contest_of = _classic_files(tmp_path, ids)
    classic_theses = tmp_path / "classic_theses.json"
    classic_theses.write_text(json.dumps({"910000001": "A"}), encoding="utf-8")
    code = module.main(["--salaries", str(salaries), "--template", str(template), "--entries", str(filled),
                        "--out", str(tmp_path / "c.csv"), "--theses", str(classic_theses),
                        "--theses-out", str(tmp_path / "c_map.json"), "--restarts", "5"])
    assert code == 1 and "THESES_OUT_SHOWDOWN_ONLY" in capsys.readouterr().err
    assert not (tmp_path / "c.csv").exists() and not (tmp_path / "c_map.json").exists()


@pytest.mark.parametrize("doc, code", [
    (b"{not json", "THESES_UNREADABLE"),
    ([["900000001", "A"]], "THESES_NOT_AN_ENTRY_MAP"),
    ({"900000001": {"thesis": "A"}}, "THESES_NOT_AN_ENTRY_MAP"),
    ({"900000001": 3}, "THESES_NOT_AN_ENTRY_MAP"),
    ({"schema_version": "nfl_entry_thesis_map_v1", "entries": {}}, "THESES_NOT_AN_ENTRY_MAP"),
    ({"999999999": "A"}, "THESES_ENTRY_IDS_NOT_IN_TEMPLATE"),
], ids=["unreadable", "list", "nested", "number", "versioned_map", "foreign_entry"])
def test_a_theses_input_that_is_not_an_entry_map_is_refused_by_name(tmp_path, capsys, doc, code):
    theses = tmp_path / "theses.json"
    theses.write_bytes(doc if isinstance(doc, bytes) else json.dumps(doc).encode("utf-8"))
    status, out, record = _run(tmp_path, theses=theses)
    assert status == 1 and code in capsys.readouterr().err
    assert not out.exists() and not record.exists()


@pytest.mark.parametrize("target", ["record", "theses_out"], ids=["record", "map"])
def test_an_output_folder_that_does_not_exist_is_refused_before_anything_is_written(tmp_path, capsys, target):
    # Found by the Session 76b review: a missing folder for the second or third file used to leave the first written.
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    extra = {"theses": theses, "theses_out": tmp_path / "map.json", target: tmp_path / "no_such_folder" / "x.json"}
    module = _load()
    argv = ["--salaries", str(_salaries(tmp_path)), "--template", str(_template(tmp_path, filled=False)),
            "--entries", str(_template(tmp_path, filled=True)), "--out", str(tmp_path / "out.csv"), "--restarts", "1"]
    for key, value in {"record": tmp_path / "record.json", **extra}.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    assert module.main(argv) == 1 and "OUTPUT_DIR_MISSING" in capsys.readouterr().err
    assert not any((tmp_path / name).exists() for name in ("out.csv", "record.json", "map.json"))


def test_a_changed_prefilled_row_writes_no_file_record_or_map(tmp_path, capsys):
    module = _load()
    salaries = _salaries(tmp_path)
    template = _template(tmp_path, filled=False)
    entries = _template(tmp_path, filled=True)
    entries.write_bytes(entries.read_bytes().replace(
        ",".join(PREFILLED[2]).encode(), ",".join(LINEUPS["900000001"][1]).encode()))
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps({entry_id: "A" for entry_id in LINEUPS}), encoding="utf-8")
    code = module.main(["--salaries", str(salaries), "--template", str(template), "--entries", str(entries),
                        "--out", str(tmp_path / "out.csv"), "--record", str(tmp_path / "record.json"),
                        "--theses", str(theses), "--theses-out", str(tmp_path / "map.json"), "--restarts", "1"])
    assert code == 1 and "PREFILLED_ROW_CHANGED" in capsys.readouterr().err
    assert not any((tmp_path / name).exists() for name in ("out.csv", "record.json", "map.json"))


def test_the_v1_stdout_keeps_its_keys_and_v2_s_names_the_objective(tmp_path, capsys):
    first, second = tmp_path / "v1", tmp_path / "v2"
    first.mkdir()
    second.mkdir()
    assert _run(first, version=V1)[0] == 0
    assert set(json.loads(capsys.readouterr().out)) == {
        "status", "out", "score_before", "score_after", "moved_rows", "timed_out", "contests_after"}
    assert _run(second)[0] == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {
        "status", "out", "contest_assignment_version", "objective_before", "objective_after", "reading_score_before",
        "reading_score_after", "moved_rows", "timed_out", "contest_objective_after", "theses_out"}
    assert printed["contest_assignment_version"] == V2 and printed["theses_out"] is None


# --- Session 76b: the committed files ---------------------------------------------------

SLATES = Path(__file__).resolve().parents[1] / "data" / "inbox" / "slates"
PHI = SLATES / "phi-chi-sd-2026-09-28"
MIN = SLATES / "min-no-sd-2026-10-11"
# salaries, template, entries, the record of the pass that last moved lineups, that pass's thesis map
CARD_FILES = {
    "phi-chi-v4": (PHI / "bdc34f2b-DKSalaries_119.csv", PHI / "5ed750e7-DKEntries_97.csv",
                   PHI / "DK_REVIEW_ENTRY_phi-chi-sd-v4.csv", PHI / "assignment_v4.json", PHI / "theses_v3.json"),
    "min-no-v10": (MIN / "input" / "DKSalaries_169.csv", MIN / "input" / "DKEntries_141.csv",
                   MIN / "construction" / "DK_REVIEW_ENTRY_min-no-sd_final_v10.csv",
                   MIN / "construction" / "contest_diversify_record_v7.json", MIN / "construction" / "theses_by_entry.json"),
}
# The relabelled thesis map each card file's v2 pass writes, measured 2026-10-16 on Windows.
MAP_SHA256 = {
    "phi-chi-v4": "d55b73179889e932af601e3784e0377fc008282cd3a66581434e25670b10a3fd",
    "min-no-v10": "d78aa166293bba1a9597416de00ebbbe9322334d57cf16f543a0321c2f12066d",
}
# Every committed record written by the module's v1 (`nfl_contest_diversification_v2`): slate, template, salaries, the
# pass's input, its thesis map or None, the record, the pass's output. PHI@CHI's `assignment_v2..v4.json` came from the
# pre-module script (`nfl_showdown_contest_diversification_v1`, a raw sum) and cannot replay.
RECORDS = {
    "bal-atl-v4": ("bal-atl-sd-2026-10-11", "DKEntries_150.csv", "DKSalaries_176.csv", "DK_REVIEW_ENTRY_bal-atl-sd_judgment_v3.csv",
                   "theses_by_entry.json", "contest_diversify_record_v4.json", "DK_REVIEW_ENTRY_bal-atl-sd_final_v4.csv"),
    "buf-lar-v1": ("buf-lar-sd-2026-10-12", "DKEntries.csv", "DKSalaries.csv", "DK_REVIEW_ENTRY_buf-lar-sd_ceiling_v1.csv",
                   None, "contest_diversify_record_v1.json", "DK_REVIEW_ENTRY_buf-lar-sd_final_v1.csv"),
    "buf-lar-v2": ("buf-lar-sd-2026-10-12", "DKEntries.csv", "DKSalaries.csv", "DK_REVIEW_ENTRY_buf-lar-sd_ceiling_v2.csv",
                   None, "contest_diversify_record_v2.json", "DK_REVIEW_ENTRY_buf-lar-sd_final_v2.csv"),
    "min-no-v7": ("min-no-sd-2026-10-11", "DKEntries_141.csv", "DKSalaries_169.csv", "DK_REVIEW_ENTRY_min-no-sd_judgment_v6.csv",
                  "theses_by_entry.json", "contest_diversify_record_v7.json", "DK_REVIEW_ENTRY_min-no-sd_final_v7.csv"),
    "sea-den-v1": ("sea-den-sd-2026-10-15", "DKEntries.csv", "DKSalaries.csv", "DK_REVIEW_ENTRY_sea-den-sd_judgment_v1.csv",
                   None, "contest_diversify_record_v1.json", "DK_REVIEW_ENTRY_sea-den-sd_contest_v1.csv"),
    "tb-dal-v2": ("tb-dal-sd-2026-10-08", "DKEntries.csv", "DKSalaries.csv", "DK_REVIEW_ENTRY_tb-dal-sd_ceiling_v2.csv",
                  None, "contest_diversify_record_v2.json", "DK_REVIEW_ENTRY_tb-dal-sd_final_v2.csv"),
    "tb-dal-v3": ("tb-dal-sd-2026-10-08", "DKEntries.csv", "DKSalaries.csv", "DK_REVIEW_ENTRY_tb-dal-sd_iter3.csv",
                  None, "contest_diversify_record_v3.json", "DK_REVIEW_ENTRY_tb-dal-sd_final_v3.csv"),
}


def _card_labels(name: str) -> dict[str, str]:
    """Each Entry ID's thesis in the card file, through the record of the pass that last moved lineups between Entry IDs,
    as `tests/test_contest_assignment_v2_files.py` binds them."""

    *_files, record, theses = CARD_FILES[name]
    mapping = json.loads(record.read_text("utf-8"))["mapping_entry_to_source_entry"]
    labels = json.loads(theses.read_text("utf-8"))
    return {entry: labels[source] for entry, source in mapping.items()}


def _module_placement(name: str, version: str, restarts: int | None, labels: dict[str, str]):
    """What the module itself assigns on a card file, read through `first_place_coverage`'s reader, not the script's."""

    salaries, template, entries, *_rest = CARD_FILES[name]
    template_rows, state = fpc.read_entries_file(template, mode=ca.MODE_SHOWDOWN)
    assert state == fpc.READ
    filled = {entry for entry, _contest, roster in template_rows if roster is not None}
    rows, state = fpc.read_entries_file(entries, mode=ca.MODE_SHOWDOWN)
    assert state == fpc.READ
    entry_rows = [ca.EntryRow(e, c, tuple(r), None if e in filled else "template") for e, c, r in rows]
    if restarts is None:
        restarts = ca.restarts_for([ca.Slot(r.entry_id, r.contest_id, r.pool) for r in entry_rows])
    out = ca.diversify(entry_rows, mode=ca.MODE_SHOWDOWN, people=fpc.people(fpc.players_from_salary_csv(salaries)),
                       thesis_by_roster={r.roster: labels[r.entry_id] for r in entry_rows}, restarts=restarts,
                       time_limit_seconds=None, version=version)
    return entry_rows, out, restarts


def _expected_bytes(entries: Path, assignments) -> bytes:
    """The input's bytes with each moved row's six roster cells replaced by the cells its assigned lineup had."""

    raw = entries.read_bytes()
    ending = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = raw.split(ending)

    def roster_of(fields):
        return tuple(fpc.cell_dk_id(cell.decode("utf-8")) for cell in fields[4:10])

    cells = {}
    for line in lines:
        fields = line.split(b",")
        if len(fields) > 10 and fields[0].isdigit():
            cells[roster_of(fields)] = fields[4:10]
    out = []
    for line in lines:
        fields = line.split(b",")
        entry = fields[0].decode("utf-8") if fields[0].isdigit() else None
        if entry in assignments and len(fields) > 10:
            fields[4:10] = cells[tuple(assignments[entry])]
            line = b",".join(fields)
        out.append(line)
    return ending.join(out)


@pytest.mark.parametrize("name", sorted(CARD_FILES))
def test_v2_writes_the_module_s_assignment_byte_for_byte_and_the_qa_reads_the_relabelled_theses(tmp_path, capsys, name):
    salaries, template, entries, *_rest = CARD_FILES[name]
    labels = _card_labels(name)
    rows, expected, restarts = _module_placement(name, V2, None, labels)
    # The run path's entry-sized count: PHI@CHI's is capped at 300, MIN@NO's 20-entry contest gives 57.
    assert restarts == {"phi-chi-v4": 300, "min-no-v10": 57}[name]
    folders = []
    for folder in ("first", "second"):
        here = tmp_path / folder
        here.mkdir()
        (here / "theses.json").write_text(json.dumps(labels, sort_keys=True), encoding="utf-8")
        code = _load().main(["--salaries", str(salaries), "--template", str(template), "--entries", str(entries),
                             "--out", str(here / "out.csv"), "--record", str(here / "record.json"),
                             "--theses", str(here / "theses.json"), "--theses-out", str(here / "map.json"),
                             "--time-limit-seconds", "600"])
        assert code == 0, capsys.readouterr().err
        capsys.readouterr()
        folders.append(here)
    first, second = folders
    assert (first / "out.csv").read_bytes() == _expected_bytes(entries, expected.assignments)
    record = _record(first / "record.json")
    step = record["contest_assignment"]
    assert step["contest_assignment_version"] == V2 and step["timed_out"] is False
    for key in ("status", "moved_rows", "objective_before", "objective_after", "contest_objective_before",
                "contest_objective_after", "single_entry_contests_moved", "total_score_before", "total_score_after"):
        assert step[key] == json.loads(json.dumps(expected.report[key])), key
    assert record["search"]["restarts"] == restarts
    held = {r.entry_id: r.roster for r in rows}
    assert all(held[source] == tuple(expected.assignments.get(entry, held[entry]))
               for entry, source in record["mapping_entry_to_source_entry"].items())
    # Replay: the same inputs give the same file, the same map and the same record but for its clock. The map's hash is
    # pinned, so the Linux and Windows CI jobs prove it is the same bytes on both hosts (it is written as LF bytes).
    assert (second / "out.csv").read_bytes() == (first / "out.csv").read_bytes()
    assert (second / "map.json").read_bytes() == (first / "map.json").read_bytes()
    assert _sha((first / "map.json").read_bytes()) == MAP_SHA256[name]
    assert _without_seconds(_record(second / "record.json")) == _without_seconds(record)
    # The after-table: the QA reads the relabelled theses, every row labelled, and the reading is the module's own
    # placement read with each lineup's label.
    argv = ["--salaries", str(salaries), "--template", str(template), "--export", str(first / "out.csv")]
    code = sd_qa.qa.main([*argv, "--theses", str(first / "map.json")])
    report = json.loads(capsys.readouterr().out)
    block = report.pop("first_place_thesis_map")
    assert (block["binding"], block["labels_from"], block["same_file_as_written"]) == ("BOUND", "THESES_MAP", True)
    assert block["labelled_rows"] == len(rows)
    assert block["roster_changed"] == block["moved_since_written"] == block["unlabelled_entry_ids"] == []
    final = [(r.entry_id, r.contest_id, tuple(expected.assignments.get(r.entry_id, r.roster))) for r in rows]
    by_roster = {r.roster: labels[r.entry_id] for r in rows}
    want = fpc.reading(final, mode=ca.MODE_SHOWDOWN, players=fpc.players_from_salary_csv(salaries),
                       thesis_by_entry={e: by_roster[roster] for e, _c, roster in final}, source="EXPORT")
    assert report["first_place_coverage"]["thesis_labels"] == "SUPPLIED"
    assert report["first_place_coverage"] == json.loads(json.dumps(want))
    # Nothing else moves with the map: the same QA without it differs only in the reading's labels.
    plain_code = sd_qa.qa.main(argv)
    plain = json.loads(capsys.readouterr().out)
    assert plain["first_place_coverage"]["thesis_labels"] == "NONE"
    report.pop("first_place_coverage")
    plain.pop("first_place_coverage")
    assert (code, report) == (plain_code, plain)


@pytest.mark.parametrize("name", sorted(CARD_FILES))
def test_v1_on_the_card_files_writes_the_module_s_v1_assignment(tmp_path, capsys, name):
    salaries, template, entries, *_rest = CARD_FILES[name]
    labels = _card_labels(name)
    _rows_, expected, _restarts = _module_placement(name, V1, ca.DEFAULT_RESTARTS, labels)
    (tmp_path / "theses.json").write_text(json.dumps(labels, sort_keys=True), encoding="utf-8")
    code = _load().main(["--salaries", str(salaries), "--template", str(template), "--entries", str(entries),
                         "--out", str(tmp_path / "out.csv"), "--theses", str(tmp_path / "theses.json"),
                         "--version", V1, "--time-limit-seconds", "600"])
    assert code == 0, capsys.readouterr().err
    assert (tmp_path / "out.csv").read_bytes() == _expected_bytes(entries, expected.assignments)


@pytest.mark.parametrize("name", sorted(RECORDS))
def test_v1_reproduces_every_committed_module_record(tmp_path, capsys, name):
    slate, template, salaries, entries, theses, record, output = RECORDS[name]
    here = SLATES / slate
    argv = ["--salaries", str(here / "input" / salaries), "--template", str(here / "input" / template),
            "--entries", str(here / "construction" / entries), "--out", str(tmp_path / "out.csv"),
            "--record", str(tmp_path / "record.json"), "--version", V1, "--time-limit-seconds", "600"]
    if theses is not None:
        argv += ["--theses", str(here / "construction" / theses)]
    assert _load().main(argv) == 0, capsys.readouterr().err
    assert (tmp_path / "out.csv").read_bytes() == (here / "construction" / output).read_bytes()
    # Compared parsed: the committed records are LF in git, and a text-mode write on Windows is CRLF.
    written = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    committed = json.loads((here / "construction" / record).read_text(encoding="utf-8"))
    assert _without_seconds(written) == _without_seconds(committed)
