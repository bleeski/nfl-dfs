"""`scripts/practice_squad_check.py`: the ATL@NO (2026-10-05) practice-squad check as one command."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SALARY_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,Status"
ROSTER_HEADER = "season,team,position,depth_chart_position,jersey_number,status,full_name,week,game_type"


def _load():
    spec = importlib.util.spec_from_file_location("practice_squad_check", REPO_ROOT / "scripts" / "practice_squad_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _salaries(path: Path, people: list[tuple[str, str, str, str]]) -> Path:
    lines = [SALARY_HEADER]
    next_id = 1000
    for name, team, position, status in people:
        for role, salary in (("CPT", 3000), ("FLEX", 2000)):
            lines.append(f"{position},{name} ({next_id}),{name},{next_id},{role},{salary},ATL@NO 10/05/2026 08:15PM ET,{team},{status}")
            next_id += 1
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def _rosters(path: Path, rows: list[tuple[str, str, str, int]]) -> Path:
    body = [ROSTER_HEADER] + [f"2026,{team},WR,WR,10,{status},{name},{week},REG" for name, team, status, week in rows]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def test_practice_squad_players_are_listed_with_both_ids_and_exclude_args(tmp_path):
    module = _load()
    salaries = _salaries(
        tmp_path / "s.csv",
        [
            ("Active Guy", "NO", "WR", ""),
            ("Squad Guy", "NO", "WR", ""),
            ("Antwane Wells Jr.", "ATL", "WR", ""),
            ("Jalen Moreno-Cropper", "NO", "WR", ""),
            ("Hurt Guy", "ATL", "WR", "IR"),
            ("Nobody Here", "ATL", "WR", ""),
            ("Saints", "NO", "DST", ""),
        ],
    )
    rosters = _rosters(
        tmp_path / "r.csv",
        [
            ("Active Guy", "NO", "ACT", 4),
            ("Squad Guy", "NO", "DEV", 4),
            ("Antwane Wells", "ATL", "DEV", 4),
            ("Jalen Cropper", "NO", "DEV", 4),
            ("Hurt Guy", "ATL", "RES", 4),
        ],
    )
    report = module.check(salaries, rosters)
    flagged = {entry["name"]: entry for entry in report["not_active"]}
    assert set(flagged) == {"Squad Guy", "Antwane Wells Jr.", "Jalen Moreno-Cropper"}
    assert flagged["Squad Guy"]["match_method"] == "EXACT_NAME_TEAM"
    assert flagged["Antwane Wells Jr."]["match_method"] == "NAME_WITHOUT_SUFFIX_TEAM"
    assert flagged["Jalen Moreno-Cropper"]["match_method"] == "HYPHENATED_SURNAME_HALF_TEAM"
    assert all(len(entry["dk_ids"]) == 2 for entry in flagged.values())
    assert report["exclude_args"].split().count("--exclude") == 6
    assert [entry["name"] for entry in report["no_roster_row"]] == ["Nobody Here"]
    assert report["people"] == 6  # the DST is not a roster person
    assert "OFFICIAL_ACTIVE_STATUS" in report["does_not_establish"]


def test_the_latest_week_on_the_team_decides(tmp_path):
    module = _load()
    salaries = _salaries(tmp_path / "s.csv", [("Promoted Guy", "NO", "WR", ""), ("Demoted Guy", "NO", "WR", "")])
    rosters = _rosters(
        tmp_path / "r.csv",
        [
            ("Promoted Guy", "NO", "DEV", 3),
            ("Promoted Guy", "NO", "ACT", 4),
            ("Demoted Guy", "NO", "ACT", 3),
            ("Demoted Guy", "NO", "DEV", 4),
        ],
    )
    report = module.check(salaries, rosters)
    assert [(entry["name"], entry["nflverse_week"]) for entry in report["not_active"]] == [("Demoted Guy", 4)]


def test_run_dir_finds_the_roster_file_by_header(tmp_path, capsys):
    module = _load()
    raw = tmp_path / "run" / "prior_review" / "priors" / "proposal" / "raw"
    raw.mkdir(parents=True)
    (raw / "aaa.csv").write_text("dt,team,player_name\n", encoding="utf-8")
    _rosters(raw / "bbb.csv", [("Squad Guy", "NO", "DEV", 4)])
    salaries = _salaries(tmp_path / "s.csv", [("Squad Guy", "NO", "WR", "")])
    assert module.main(["--salaries", str(salaries), "--run-dir", str(tmp_path / "run")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rosters"].endswith("bbb.csv")
    assert [entry["name"] for entry in report["not_active"]] == ["Squad Guy"]
