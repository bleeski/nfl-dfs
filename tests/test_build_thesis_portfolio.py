"""Acceptance for `scripts/build_thesis_portfolio.py`.

Promoted from a 2026-09-27 slate-day scratchpad (`build_theses.py`) that
called `scripts/build_classic_portfolio.py` once per thesis and seed, then
picked across every thesis's candidates under a global cap. The one bug that
slipped through that session -- an `--out` path good enough to be reused
across calls, with no check on the builder's exit code -- gets its own
regression tests here, using an injected fake `runner` in place of a real
`build_classic_portfolio.py` subprocess so every test stays fast and
deterministic; a real end-to-end call is exercised once, at the bottom.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_thesis_portfolio.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


thesis = _load("build_thesis_portfolio", SCRIPT)

SALARY_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"
STATUS_HEADER = "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"
TEAMS = {"AAA": "AAA@BBB", "BBB": "AAA@BBB", "CCC": "CCC@DDD", "DDD": "CCC@DDD"}
COUNTS = {"QB": 1, "RB": 3, "WR": 4, "TE": 2, "DST": 1}


def _roster_position(pos: str) -> str:
    return pos if pos in ("QB", "DST") else f"{pos}/FLEX"


def make_salaries(tmp_path: Path) -> tuple[Path, dict]:
    rows, scores = [], {}
    for team, game in TEAMS.items():
        for pos, n in COUNTS.items():
            for k in range(n):
                dk_id = f"{team}{pos}{k}"
                name = f"{team} {pos}{k}"
                salary = 4000 + k * 100
                rows.append(
                    f"{pos},{name} ({dk_id}),{name},{dk_id},{_roster_position(pos)},{salary},"
                    f"{game} 09/28/2026 01:00PM ET,{team},0,\n"
                )
                scores[dk_id] = 10.0 + k
    path = tmp_path / "sal.csv"
    path.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    return path, scores


def make_scores(tmp_path: Path, scores: dict) -> Path:
    path = tmp_path / "scores.json"
    path.write_text(json.dumps({"by_dk_id": scores}), encoding="utf-8")
    return path


def make_status(tmp_path: Path) -> Path:
    path = tmp_path / "status.csv"
    path.write_text(STATUS_HEADER, encoding="utf-8")
    return path


def make_entries(tmp_path: Path, n: int) -> Path:
    body = "".join(f"5263200{i:03d},Contest,1,$1,,,,,,,,,,,\n" for i in range(n))
    path = tmp_path / "entries.csv"
    path.write_text(ENTRY_HEADER + body, encoding="utf-8")
    return path


def make_context(tmp_path: Path, totals: dict) -> Path:
    path = tmp_path / "ctx.json"
    path.write_text(json.dumps({"implied_team_totals": totals}), encoding="utf-8")
    return path


def make_config(tmp_path: Path, **overrides) -> Path:
    doc = {
        "schema": thesis.CONFIG_SCHEMA,
        "seeds": [1],
        "lineups_per_thesis_multiplier": 1,
        "global": {"max_exposure": 9, "max_overlap": 9, "per_thesis_qb_cap": 9},
        "theses": [
            {"name": "T1", "quota": 2, "team_totals": "market"},
            {"name": "T2", "quota": 2, "team_totals": "flip"},
        ],
        "flip_pairs": [["AAA", "BBB"]],
    }
    doc.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _args(tmp_path, **overrides):
    salaries, scores = make_salaries(tmp_path)
    defaults = dict(
        scores=str(make_scores(tmp_path, scores)),
        salaries=str(salaries),
        status=str(make_status(tmp_path)),
        entries=str(make_entries(tmp_path, 4)),
        config=str(make_config(tmp_path)),
        slate_context=str(make_context(tmp_path, {"AAA": 24.0, "BBB": 20.0, "CCC": 22.0, "DDD": 21.0})),
        work_dir=str(tmp_path / "work"),
        out=str(tmp_path / "portfolio.json"),
        python=sys.executable, builder="unused", exclude_entry_id=[],
        max_exposure=None, max_overlap=None, per_thesis_qb_cap=None,
        min_salary=0, require_bringback=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults), scores


class FakeBuilder:
    """Stands in for `build_classic_portfolio.py`: writes `lineups` distinct
    two-element rosters drawn from `pool`, honoring `--lineups` and `--out`,
    and lets a test script a specific call's exit code and file contents."""

    def __init__(self, pool):
        self.pool = pool
        self.calls: list[list[str]] = []
        self.script = {}  # call index (0-based) -> (returncode, write_file: bool)

    def __call__(self, command, capture_output=True, text=True):
        self.calls.append(command)
        index = len(self.calls) - 1
        out_path = Path(command[command.index("--out") + 1])
        lineups = int(command[command.index("--lineups") + 1])
        returncode, write_file = self.script.get(index, (0, True))
        if write_file:
            rosters = [self.pool[(index + n) % len(self.pool)] for n in range(lineups)]
            out_path.write_text(json.dumps({
                "lineups": [{"index": n + 1, "roster": roster} for n, roster in enumerate(rosters)],
            }), encoding="utf-8")
        return SimpleNamespace(returncode=returncode, stdout="", stderr="mock refusal" if returncode else "")


def _pool_from_salaries(scores):
    # Two-"player" rosters, just enough for the orchestration tests below --
    # this fake never runs real legality, only records what was asked of it.
    ids = sorted(scores)
    return [[ids[i], ids[i + 1]] for i in range(0, len(ids) - 1, 2)]


def test_every_builder_call_gets_a_unique_out_path(tmp_path):
    a, scores = _args(tmp_path)
    fake = FakeBuilder(_pool_from_salaries(scores))
    result = thesis.build(a, runner=fake)
    out_paths = [call[call.index("--out") + 1] for call in fake.calls]
    assert len(out_paths) == len(set(out_paths)) and len(out_paths) >= 2
    assert result["built"] > 0


def test_a_refused_builder_call_is_never_read_as_a_success(tmp_path):
    """The 2026-09-27 defect: a call whose builder refused (exit 2) must never
    contribute candidates, even if a file happens to sit at its own --out --
    the exit code is checked before the file is ever opened."""

    a, scores = _args(tmp_path)
    fake = FakeBuilder(_pool_from_salaries(scores))
    fake.script[0] = (2, True)  # first call: refused, but (buggily) still writes a file
    result = thesis.build(a, runner=fake)
    # The run still completes: nothing from the refused call was ever
    # candidate material, and later calls cover the quota.
    assert result["built"] > 0
    doc = json.loads(Path(a.out).read_text(encoding="utf-8"))
    assert doc["construction"]["candidates_generated"]["T1"] >= 0


def test_run_builder_returns_nothing_for_a_refused_call_directly(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    fake = FakeBuilder([["1", "2"]])
    fake.script[0] = (2, True)
    a, _scores = _args(tmp_path)
    rosters = thesis.run_builder(
        a, work_dir, label="X", scores={"1": 1.0}, team_totals={}, role_boosts={},
        lineups=1, seed=1, max_overlap=5, runner=fake,
    )
    assert rosters == []


def test_team_totals_variants():
    market = {"AAA": 24.0, "BBB": 20.0, "CCC": 22.0, "DDD": 21.0}
    config = {"flip_pairs": [["AAA", "BBB"]], "bust_overrides": {"CCC": 30.0}, "flat_team_total": 22.5}
    assert thesis.team_totals_variant("market", market, config) == market
    flipped = thesis.team_totals_variant("flip", market, config)
    assert flipped["AAA"] == 20.0 and flipped["BBB"] == 24.0 and flipped["CCC"] == 22.0
    bust = thesis.team_totals_variant("bust", market, config)
    assert bust["CCC"] == 30.0 and bust["AAA"] == 24.0
    flat = thesis.team_totals_variant("flat", market, config)
    assert set(flat.values()) == {22.5}


def test_thesis_scores_restricts_qb_and_dst_teams(tmp_path):
    sal, scores = thesis_sal_and_scores(tmp_path)
    restricted = thesis.thesis_scores(scores, sal, {"restrict_qb_teams": ["AAA"]})
    qb_teams = {sal[dk_id]["TeamAbbrev"] for dk_id, row in restricted.items() if sal[dk_id]["Position"] == "QB"}
    assert qb_teams == {"AAA"}
    dst_restricted = thesis.thesis_scores(scores, sal, {"exclude_dst_unless_teams": ["CCC"]})
    dst_teams = {sal[dk_id]["TeamAbbrev"] for dk_id in dst_restricted if sal[dk_id]["Position"] == "DST"}
    assert dst_teams == {"CCC"}


def thesis_sal_and_scores(tmp_path):
    salaries, scores = make_salaries(tmp_path)
    sal = thesis.load_salaries(str(salaries))
    return sal, scores


def test_thesis_role_boosts_maps_team_position_to_name(tmp_path):
    sal, _scores = thesis_sal_and_scores(tmp_path)
    boosts = thesis.thesis_role_boosts(sal, {"AAA": {"WR": 0.8}, "CCC": {"QB": 1.0}})
    assert boosts == {f"AAA WR{k}": 0.8 for k in range(COUNTS["WR"])}


def test_select_portfolio_respects_quotas_exposure_overlap_and_qb_cap(tmp_path):
    sal, _scores = thesis_sal_and_scores(tmp_path)
    base_scores = {f"AAAWR{k}": 10.0 + k for k in range(4)}
    candidates = {
        "T1": [["AAAQB0", "AAAWR0"], ["AAAQB0", "AAAWR1"], ["AAAQB0", "AAAWR2"]],
    }
    chosen, tags = thesis.select_portfolio(
        candidates, base_scores, {"T1": 3},
        max_exposure=1, max_overlap=0, per_thesis_qb_cap=9, sal=sal,
    )
    # AAAQB0 appears in every candidate; exposure 1 allows only the first.
    assert len(chosen) == 1
    assert tags == ["T1"]


def test_select_portfolio_enforces_the_per_thesis_qb_cap(tmp_path):
    sal, _scores = thesis_sal_and_scores(tmp_path)
    base_scores = {}
    candidates = {"T1": [
        ["AAAQB0", "AAAWR0"], ["AAAQB0", "AAAWR1"], ["AAAQB0", "AAAWR2"], ["CCCQB0", "CCCWR0"],
    ]}
    chosen, tags = thesis.select_portfolio(
        candidates, base_scores, {"T1": 4},
        max_exposure=9, max_overlap=9, per_thesis_qb_cap=1, sal=sal,
    )
    qbs = [roster[0] for roster in chosen]
    assert qbs.count("AAAQB0") <= 1


def test_refuses_an_existing_out_path(tmp_path):
    a, _scores = _args(tmp_path)
    Path(a.out).write_text("stale", encoding="utf-8")
    with pytest.raises(thesis.Refused, match="OUTPUT_EXISTS"):
        thesis.build(a, runner=FakeBuilder([]))


def test_refuses_an_existing_work_dir(tmp_path):
    a, _scores = _args(tmp_path)
    Path(a.work_dir).mkdir()
    with pytest.raises(thesis.Refused, match="WORK_DIR_EXISTS"):
        thesis.build(a, runner=FakeBuilder([]))


def test_refuses_a_config_schema_mismatch(tmp_path):
    a, scores = _args(tmp_path, config=str(tmp_path / "bad.json"))
    Path(a.config).write_text(json.dumps({"schema": "wrong", "theses": []}), encoding="utf-8")
    with pytest.raises(thesis.Refused, match="CONFIG_SCHEMA_MISMATCH"):
        thesis.build(a, runner=FakeBuilder(_pool_from_salaries(scores)))


def test_refuses_with_no_team_totals(tmp_path):
    a, scores = _args(tmp_path, slate_context=None)
    config = json.loads(Path(a.config).read_text(encoding="utf-8"))
    config.pop("market_team_totals", None)
    Path(a.config).write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(thesis.Refused, match="NO_TEAM_TOTALS"):
        thesis.build(a, runner=FakeBuilder(_pool_from_salaries(scores)))


def test_exit_code_reflects_a_shortfall(tmp_path):
    """More fillable entries than the theses' combined quota (T1:2 + T2:2 =
    4 in the default config) can supply: exit 3, every gap named, R29 never
    repeats a lineup to close it."""

    a, scores = _args(tmp_path, entries=None)
    a.entries = str(make_entries(tmp_path, 6))  # six blank rows, only 4 lineups' worth of quota
    code = thesis.main([
        "--scores", a.scores, "--salaries", a.salaries, "--status", a.status,
        "--entries", a.entries, "--config", a.config, "--slate-context", a.slate_context,
        "--work-dir", a.work_dir, "--out", a.out,
    ], runner=FakeBuilder(_pool_from_salaries(scores)))
    assert code == thesis.EXIT_PARTIAL
    doc = json.loads(Path(a.out).read_text(encoding="utf-8"))
    built = len(doc["assignments_by_entry_id"])
    assert built <= 4  # the config's own quota (T1:2 + T2:2) is the ceiling
    assert built + len(doc["unfilled_entry_ids"]) == 6
    assert doc["unfilled_entry_ids"]


def test_excluded_entry_ids_are_named_and_never_assigned(tmp_path):
    a, scores = _args(tmp_path, exclude_entry_id=["5263200000:NFL FREE 200-Player: Ben, 2026-09-27"])
    code = thesis.main([
        "--scores", a.scores, "--salaries", a.salaries, "--status", a.status,
        "--entries", a.entries, "--config", a.config, "--slate-context", a.slate_context,
        "--work-dir", a.work_dir, "--out", a.out,
        "--exclude-entry-id", "5263200000:NFL FREE 200-Player: Ben, 2026-09-27",
    ], runner=FakeBuilder(_pool_from_salaries(scores)))
    doc = json.loads(Path(a.out).read_text(encoding="utf-8"))
    assert "5263200000" not in doc["assignments_by_entry_id"]
    assert "5263200000" in doc["unfilled_entry_ids"]
    assert doc["operator_excluded_entry_ids"]["5263200000"].startswith("NFL FREE")


def test_priors_wrong_thesis_fades_the_most_rostered_non_dst_players(tmp_path):
    a, scores = _args(tmp_path, config=str(tmp_path / "config2.json"))
    doc = {
        "schema": thesis.CONFIG_SCHEMA,
        "seeds": [1],
        "lineups_per_thesis_multiplier": 1,
        "global": {"max_exposure": 9, "max_overlap": 9, "per_thesis_qb_cap": 9},
        "theses": [{"name": "T1", "quota": 2, "team_totals": "market"}],
        "priors_wrong": {"quota": 1, "fade_count": 1},
    }
    Path(a.config).write_text(json.dumps(doc), encoding="utf-8")
    ids = sorted(scores)
    pool = [ids[0:2], ids[0:2], ids[2:4]]  # ids[0] and ids[1] are heavily rostered
    thesis.build(a, runner=FakeBuilder(pool))
    construction = json.loads(Path(a.out).read_text(encoding="utf-8"))["construction"]
    assert "PRIORS_WRONG_SALARY_FLAT" in construction["theses"]
    assert construction["faded_in_priors_wrong"]


def test_real_builder_end_to_end(tmp_path):
    """One real call into `build_classic_portfolio.py`, to prove the wiring
    (arguments, scores/context files, --out path) actually works, not just
    the orchestration around a fake."""

    import subprocess

    a, scores = _args(tmp_path, min_salary=0)
    a.builder = str(REPO_ROOT / "scripts" / "build_classic_portfolio.py")
    config = json.loads(Path(a.config).read_text(encoding="utf-8"))
    config["theses"] = [{"name": "ONLY", "quota": 2, "team_totals": "market"}]
    config.pop("priors_wrong", None)
    Path(a.config).write_text(json.dumps(config), encoding="utf-8")
    code = thesis.main([
        "--scores", a.scores, "--salaries", a.salaries, "--status", a.status,
        "--entries", a.entries, "--config", a.config, "--slate-context", a.slate_context,
        "--work-dir", a.work_dir, "--out", a.out, "--min-salary", "0",
    ], runner=subprocess.run)
    assert code in (thesis.EXIT_OK, thesis.EXIT_PARTIAL)
    doc = json.loads(Path(a.out).read_text(encoding="utf-8"))
    assert doc["lineups"]
    for lineup in doc["lineups"]:
        assert len(set(lineup["roster"])) == 9
