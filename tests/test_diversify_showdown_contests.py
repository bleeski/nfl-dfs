"""`scripts/diversify_showdown_contests.py`: within-contest reassignment of a filled file."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diversify_showdown_contests.py"


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
    code, out, record = _run(tmp_path)
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
    code, _out, record = _run(tmp_path, theses=theses, thesis_penalty=penalty)
    assert code == 0
    assert json.loads(record.read_text(encoding="utf-8"))["score"]["thesis_penalty"] == penalty
