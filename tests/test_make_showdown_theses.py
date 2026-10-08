"""Session 67: `scripts/make_showdown_theses.py` writes Ben's R33 list as thesis files by structure alone.

The list itself, the teams and which files reach a policy are Ben's; the script never reads a model value, a spread, a
total or a contest name, only who is the best by salary at a position. Its output for NE and SEA must be exactly what
the Session 23c acceptance builds (`r33_theses`), and the policy the generator writes from its files must assemble the
same portfolio. A thesis is a choice, not a forecast; with no ownership input leverage is unmeasured.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.portfolio_policy import validate_portfolio_policy_bytes

from .test_showdown_thesis_acceptance import (
    ENTRIES,
    ENTRY_COUNT,
    SALARIES,
    _generator,
    audit_world,
    build_world,
    r33_theses,
    solve_world,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "make_showdown_theses.py"
CLASSIC_SALARIES = REPO_ROOT / "tests" / "fixtures" / "supplied" / "DKSalaries Salary CSV Classic.csv"
SIX = ["NE_WINS_BIG", "SEA_WINS_BIG", "NE_WINS_CLOSE", "SEA_WINS_CLOSE", "DEFENSIVE_BATTLE", "OFFENSIVE_SHOOTOUT"]
EIGHT = ["NE_WINS_BIG", "SEA_WINS_BIG", "NE_WINS_CLOSE_HIGH", "NE_WINS_CLOSE_LOW", "SEA_WINS_CLOSE_HIGH",
         "SEA_WINS_CLOSE_LOW", "DEFENSIVE_BATTLE", "OFFENSIVE_SHOOTOUT"]
KEYS = {"name", "teams", "captain_set", "team_bounds", "position_bounds"}


def _load():
    spec = importlib.util.spec_from_file_location("make_showdown_theses_s67", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expand(out_dir: Path, *extra: str, teams=("NE", "SEA"), salaries: Path = SALARIES):
    code = _load().main(["--salaries", str(salaries), "--teams", *teams, "--out-dir", str(out_dir), *extra])
    return code, sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []


def _loaded(files):
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


def _edited(tmp_path: Path, name: str, edit, reorder=None) -> Path:
    """A copy of the NE@SEA salary bytes with `edit(row, header)` applied to every row, and the rows optionally
    reordered by `reorder(rows, header)`; the rest is left alone."""

    raw = SALARIES.read_bytes()
    text = raw.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    body = [row for row in rows[1:] if row]
    for row in body:
        edit(row, header)
    if reorder is not None:
        body = reorder(body, header)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=eol)
    writer.writerow(header)
    for row in body:
        writer.writerow(row)
    path = tmp_path / name
    path.write_bytes(out.getvalue().encode("utf-8"))
    return path


def _policy_from_files(tmp_path: Path, files):
    """The operator path: the expander's own files, in its order, through `make_showdown_policy.py --thesis`."""

    slate = parse_salaries(SALARIES)
    fillable = list(plan_entries(parse_entries(ENTRIES), slate).fillable)[:ENTRY_COUNT]  # as `build_world` binds them
    tmp_path.mkdir(parents=True, exist_ok=True)
    args = ["--salaries", str(SALARIES), "--entries", str(ENTRIES), "--out", str(tmp_path / "policy.json")]
    for entry_id in fillable:
        args += ["--entry-id", entry_id]
    for path in files:
        args += ["--thesis", str(path)]
    assert _generator().main(args) == 0
    raw = (tmp_path / "policy.json").read_bytes()
    validation = validate_portfolio_policy_bytes(raw, slate=slate, entry_ids=fillable)
    assert validation.valid, validation.blockers()
    return slate, validation.policy, raw, fillable


# ------------------------------------------------------------------ clause 1: the Session 23c portfolio, unchanged


@pytest.mark.parametrize(("variants", "names"), [(False, SIX), (True, EIGHT)])
def test_the_files_are_ben_s_r33_list_exactly_as_the_acceptance_builds_it(tmp_path, variants, names):
    code, files = _expand(tmp_path / "out", *(["--variants"] if variants else []))
    assert code == 0
    assert [path.name for path in files] == [f"{index:02d}_{name}.json" for index, name in enumerate(names, 1)]
    written = _loaded(files)
    expected = r33_theses(parse_salaries(SALARIES), variants=variants)
    assert [item["name"] for item in written] == names
    # Equal as values, and in the same key order: the generator copies a thesis as it reads it.
    assert written == expected
    assert [list(item) for item in written] == [list(item) for item in expected]
    assert all(set(item) <= KEYS for item in written)


def test_the_expander_s_files_build_the_session_23c_portfolio_unchanged(tmp_path):
    _code, files = _expand(tmp_path / "out")
    slate, policy, raw, fillable = _policy_from_files(tmp_path / "expander", files)
    slate_r, policy_r, raw_r, objective, unavailable, fillable_r = build_world(tmp_path / "r33", variants=False)
    assert fillable == fillable_r
    assert policy.canonical_bytes() == policy_r.canonical_bytes()  # the normalized policy, byte for byte
    assert [item.rows for item in policy.theses] == [4, 4, 3, 3, 3, 3]

    bank, selection = solve_world(slate, policy, objective, unavailable)
    bank_r, selection_r = solve_world(slate_r, policy_r, objective, unavailable)
    # The bank stopped on its candidate count, not on the clock, so the two builds are comparable pick for pick.
    assert bank.status in {"CANDIDATE_LIMIT_REACHED_INCOMPLETE", "COMPLETE_MODELED_BANK"}, bank.status
    assert bank_r.status == bank.status
    assert selection.passed and selection_r.passed
    audit, picks = audit_world(slate, policy, raw, bank, selection, fillable)
    _audit_r, picks_r = audit_world(slate_r, policy_r, raw_r, bank_r, selection_r, fillable_r)
    assert [(c.canonical_key, name) for c, name in picks] == [(c.canonical_key, name) for c, name in picks_r]
    assert audit.passed, audit.problems

    # The Session 23c changelog's "R33's six" column (NE@SEA, 20 entries, salary-shaped objective).
    measures = audit.as_report()["theses"]["measures"]
    assert len(picks) == ENTRY_COUNT
    assert measures["distinct_captains"] == 9
    assert measures["max_captain_share_percentage"] == 20
    assert len(measures["people_in_more_than_half"]) == 3
    assert measures["most_rows_one_player_sinks"]["rows"] == 11
    assert measures["most_rows_one_thesis_sinks"]["rows"] == 4
    assert measures["same_core_pairs"] == []


def test_the_first_team_named_comes_first_in_every_pair(tmp_path):
    code, files = _expand(tmp_path / "out", teams=("SEA", "NE"))
    assert code == 0
    written = _loaded(files)
    assert [item["name"] for item in written] == [
        "SEA_WINS_BIG", "NE_WINS_BIG", "SEA_WINS_CLOSE", "NE_WINS_CLOSE", "DEFENSIVE_BATTLE", "OFFENSIVE_SHOOTOUT"]
    assert written[4]["teams"] == ["SEA", "NE"] and written[5]["teams"] == ["SEA", "NE"]
    sea_k = [p.underlying_id for p in parse_salaries(SALARIES).players if p.team == "SEA" and p.position == "K"][0]
    assert written[4]["captain_set"][0] == sea_k


def test_the_same_bytes_give_the_same_files(tmp_path):
    _c1, first = _expand(tmp_path / "one")
    _c2, second = _expand(tmp_path / "two")
    assert [p.name for p in first] == [p.name for p in second]
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]


# ------------------------------------------------------------------ structure only: who is the best by salary


def test_an_out_or_ir_player_is_never_in_a_captain_set(tmp_path):
    slate = parse_salaries(SALARIES)
    qbs = sorted((p for p in slate.players if p.team == "NE" and p.position == "QB" and p.role == "FLEX"),
                 key=lambda p: (-p.salary, p.dk_id))
    top, second = qbs[0].underlying_id, qbs[1].underlying_id

    def mark_out(row, header):
        if row[header.index("Name")] == qbs[0].name and row[header.index("TeamAbbrev")] == "NE":
            row[header.index("Status")] = "OUT"

    code, files = _expand(tmp_path / "out", salaries=_edited(tmp_path, "out.csv", mark_out))
    assert code == 0
    written = {item["name"]: item for item in _loaded(files)}
    assert all(top not in item["captain_set"] for item in written.values())
    assert written["NE_WINS_BIG"]["captain_set"][0] == second


def test_a_salary_tie_goes_to_the_lower_draftkings_id(tmp_path):
    slate = parse_salaries(SALARIES)
    backs = [p for p in slate.players if p.team == "NE" and p.position == "RB" and p.role == "FLEX"
             and p.status_raw not in {"OUT", "IR"}][:3]
    tied = {p.dk_id: p for p in backs}
    names = {p.name for p in backs}
    assert len(tied) == 3

    def tie(row, header):
        if row[header.index("TeamAbbrev")] == "NE" and row[header.index("Name")] in names:
            flex = row[header.index("Roster Position")] == "FLEX"
            row[header.index("Salary")] = "9000" if flex else "13500"

    def highest_id_first(rows, header):
        # The three tied FLEX rows keep their places in the file but hold them in descending DraftKings ID order, so a
        # sort without the ID tie-break (which keeps the file's order) would pick the two highest IDs.
        at = [index for index, row in enumerate(rows)
              if row[header.index("ID")] in tied and row[header.index("Roster Position")] == "FLEX"]
        moved = sorted((rows[index] for index in at), key=lambda row: row[header.index("ID")], reverse=True)
        for index, row in zip(at, moved):
            rows[index] = row
        return rows

    code, files = _expand(tmp_path / "out", salaries=_edited(tmp_path, "tie.csv", tie, highest_id_first))
    assert code == 0
    wins_big = {item["name"]: item for item in _loaded(files)}["NE_WINS_BIG"]
    lowest_two = [tied[dk_id].underlying_id for dk_id in sorted(tied)[:2]]
    running_backs = [uid for uid in wins_big["captain_set"] if uid.split("|")[1] == "RB"]
    assert running_backs == lowest_two


# ------------------------------------------------------------------ refusals by name, nothing written


@pytest.mark.parametrize(("teams", "code_name"), [
    (("NE", "DAL"), "THESES_TEAM_NOT_ON_SLATE"),
    (("NE",), "THESES_TEAMS_NOT_TWO"),
    (("NE", "SEA", "DAL"), "THESES_TEAMS_NOT_TWO"),
    (("NE", "NE"), "THESES_TEAMS_NOT_TWO"),
])
def test_the_teams_are_ben_s_and_exactly_the_slate_s_two(tmp_path, capsys, teams, code_name):
    code, files = _expand(tmp_path / "out", teams=teams)
    assert code == 1 and code_name in capsys.readouterr().err
    assert files == []


def test_a_classic_file_is_refused(tmp_path, capsys):
    code, files = _expand(tmp_path / "out", salaries=CLASSIC_SALARIES)
    assert code == 1 and "THESES_NOT_SHOWDOWN" in capsys.readouterr().err
    assert files == []


def test_a_truncated_salary_file_is_refused(tmp_path, capsys):
    raw = SALARIES.read_bytes()
    cut = tmp_path / "cut.csv"
    cut.write_bytes(raw[: len(raw) // 2 + 7])
    code, files = _expand(tmp_path / "out", salaries=cut)
    assert code == 1 and "THESES_SALARY_UNREADABLE" in capsys.readouterr().err
    assert files == []


def test_a_thesis_with_no_captain_left_is_refused_by_name(tmp_path, capsys):
    def no_kicker_or_defense(row, header):
        if row[header.index("TeamAbbrev")] == "NE" and row[header.index("Position")] in {"K", "DST"}:
            row[header.index("Status")] = "OUT"

    code, files = _expand(tmp_path / "out", salaries=_edited(tmp_path, "nokd.csv", no_kicker_or_defense))
    assert code == 1 and "THESES_EMPTY_CAPTAIN_SET:NE_WINS_CLOSE" in capsys.readouterr().err
    assert files == []


def test_an_existing_file_is_never_overwritten_and_nothing_else_is_written(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "03_NE_WINS_CLOSE.json"
    existing.write_bytes(b"Ben's own file\n")
    code, files = _expand(out)
    assert code == 1 and "THESES_OUTPUT_EXISTS" in capsys.readouterr().err
    assert files == [existing] and existing.read_bytes() == b"Ben's own file\n"


@pytest.mark.parametrize("failure", ["disk", "race"])
def test_a_write_that_fails_part_way_leaves_nothing_of_this_run_behind(tmp_path, capsys, monkeypatch, failure):
    # The third file fails: a full disk, or a file of that name appearing after the up-front check (a race). The two
    # files this run already wrote are removed; a file this run did not write is never touched.
    out = tmp_path / "out"
    real_open = Path.open
    opened = []

    def failing_open(self, mode="r", *args, **kwargs):
        if mode == "x":
            opened.append(self)
            if len(opened) == 3:
                if failure == "disk":
                    raise OSError(28, "No space left on device", str(self))
                self.write_bytes(b"someone else's file\n")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    code, files = _expand(out)
    monkeypatch.setattr(Path, "open", real_open)
    err = capsys.readouterr().err
    assert code == 1
    if failure == "disk":
        assert "THESES_WRITE_FAILED" in err and files == []
    else:
        assert "THESES_OUTPUT_EXISTS" in err
        assert files == [opened[2]] and opened[2].read_bytes() == b"someone else's file\n"


# ------------------------------------------------------------------ what it reads, and what it says


def test_the_script_reads_salary_bytes_only(tmp_path, capsys):
    source = SCRIPT.read_text(encoding="utf-8")
    assert "AvgPointsPerGame" not in source
    assert "roof" not in source.lower()  # the registry's weather scan reads scripts
    code, files = _expand(tmp_path / "out")
    printed = capsys.readouterr().out
    assert code == 0
    assert "choice, not a forecast" in printed and "leverage is unmeasured" in printed
    # The flags to paste, in the declared order.
    flags = printed[printed.index("--thesis"):]
    assert [flags.index(str(path)) for path in files] == sorted(flags.index(str(path)) for path in files)
