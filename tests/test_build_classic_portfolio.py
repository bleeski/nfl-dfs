"""Acceptance for `scripts/build_classic_portfolio.py`.

This is the construction layer that shipped the 2026-09-13 Week 1 portfolio when
the engine's C2 solver could not. It had no test until 2026-09-20, the day it
emitted an empty `assignments_by_entry_id` for the second slate running and the
mapping was filled by hand again.

Session 02b (2026-09-23) added the exit contract the writer and Classic QA
already honour: 0 every blank authorized row has a lineup, 2 refused by name
with nothing written, 3 written with each unfilled Entry ID named. It also added
R29 distinctness, a real ratchet ceiling, the DraftKings status filter, and
blank rows only.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_classic_portfolio.py"
WRITER = REPO_ROOT / "scripts" / "write_dk_entries.py"
QA = REPO_ROOT / "scripts" / "qa_classic_portfolio.py"
SUPPLIED = REPO_ROOT / "tests" / "fixtures" / "supplied"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = _load("build_classic_portfolio", SCRIPT)

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"
STATUS_HEADER = "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"

# Four teams across two games, deep enough at every slot to fill nine-man
# lineups many different ways.
TEAMS = {"AAA": "AAA@BBB", "BBB": "AAA@BBB", "CCC": "CCC@DDD", "DDD": "CCC@DDD"}
COUNTS = {"QB": 1, "RB": 4, "WR": 6, "TE": 2, "DST": 1}

_OUTS = itertools.count()


def roster_position(pos: str) -> str:
    return pos if pos in ("QB", "DST") else f"{pos}/FLEX"


def make_pool(tmp_path: Path, statuses=None, scores_override=None, status_column=True):
    """The four-team pool. `statuses` maps a DraftKings ID to its salary-file Status."""

    statuses = statuses or {}
    rows, scores, dk = [], {}, 1000
    for team, game in TEAMS.items():
        for pos, n in COUNTS.items():
            for k in range(n):
                dk += 1
                ident = str(dk)
                name = f"{team}{pos}{k}"
                salary = 3000 + (k * 400) + (500 if pos == "QB" else 0)
                row = (f"{pos},{name} ({ident}),{name},{ident},"
                       f"{roster_position(pos)},{salary},{game} 09/20/2026 01:00PM ET,{team},0")
                rows.append(row + (f",{statuses.get(ident, '')}\n" if status_column else "\n"))
                scores[ident] = 10.0 + k
    scores.update(scores_override or {})
    header = SALARY_HEADER if status_column else SALARY_HEADER.replace(",Status\n", "\n")
    sal = tmp_path / "sal.csv"
    sal.write_text(header + "".join(rows), encoding="utf-8")
    sc = tmp_path / "scores.json"
    sc.write_text(json.dumps({"by_dk_id": scores}), encoding="utf-8")
    st = tmp_path / "status.csv"
    st.write_text(STATUS_HEADER, encoding="utf-8")
    return sal, sc, st


def make_tiny_pool(tmp_path: Path):
    """Exactly two legal lineups exist: every skill player, and one of two defences.

    Eight skill players fill QB, RB, RB, WR, WR, WR, TE and FLEX exactly. Both
    defences play each other in a third game, so no anti-correlation rule fires.
    """

    people = [("QB", "AAA", "AAA@BBB"), ("WR", "AAA", "AAA@BBB"), ("WR", "AAA", "AAA@BBB"),
              ("RB", "CCC", "CCC@DDD"), ("RB", "CCC", "CCC@DDD"), ("RB", "CCC", "CCC@DDD"),
              ("WR", "CCC", "CCC@DDD"), ("TE", "CCC", "CCC@DDD"),
              ("DST", "EEE", "EEE@FFF"), ("DST", "FFF", "EEE@FFF")]
    rows, scores = [], {}
    for n, (pos, team, game) in enumerate(people):
        ident, name = str(2001 + n), f"{team}{pos}{n}"
        rows.append(f"{pos},{name} ({ident}),{name},{ident},{roster_position(pos)},3000,"
                    f"{game} 09/20/2026 01:00PM ET,{team},0,\n")
        scores[ident] = 10.0
    sal = tmp_path / "sal.csv"
    sal.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    sc = tmp_path / "scores.json"
    sc.write_text(json.dumps({"by_dk_id": scores}), encoding="utf-8")
    st = tmp_path / "status.csv"
    st.write_text(STATUS_HEADER, encoding="utf-8")
    return sal, sc, st


def entry_id(n: int) -> str:
    return f"52632{n:05d}"


def make_entries(tmp_path: Path, n: int, prefilled=None, crlf=False) -> Path:
    """`n` reserved rows; `prefilled` maps a row index to its nine roster cells."""

    prefilled = prefilled or {}
    body = "".join(
        f"{entry_id(i)},Contest,1234,$1,{','.join(prefilled[i])},,\n" if i in prefilled
        else f"{entry_id(i)},Contest,1234,$1,,,,,,,,,,,\n"
        for i in range(n)
    )
    text = ENTRY_HEADER + body
    p = tmp_path / "entries.csv"
    p.write_bytes(text.replace("\n", "\r\n").encode() if crlf else text.encode())
    return p


def invoke(tmp_path, extra=(), lineups=4, pool=None, out=None):
    """Run the builder; return (exit code, portfolio or None when nothing was written)."""

    sal, sc, st = pool or make_pool(tmp_path)
    out = out or tmp_path / f"portfolio_{next(_OUTS)}.json"
    args = ["--scores", str(sc), "--salaries", str(sal), "--status", str(st), "--out", str(out)]
    if lineups is not None:
        args += ["--lineups", str(lineups)]
    code = build.main([*args, *extra])
    written = code != build.EXIT_REFUSED and out.exists()
    return code, (json.loads(out.read_text(encoding="utf-8")) if written else None)


def run(tmp_path, extra=(), lineups=4, pool=None):
    code, got = invoke(tmp_path, extra, lineups, pool)
    assert code == 0, got and got.get("unfilled_entry_ids")
    return got


def rosters(got) -> list[frozenset]:
    return [frozenset(lineup["roster"]) for lineup in got["lineups"]]


def test_entry_ids_are_assigned_in_template_order(tmp_path):
    """The 2026-09-20 defect: this key was emitted empty and filled by hand."""

    entries = make_entries(tmp_path, 4)
    got = run(tmp_path, ["--entries", str(entries)])
    assigned = got["assignments_by_entry_id"]
    assert len(assigned) == len(got["lineups"]) == 4
    assert list(assigned) == ["5263200000", "5263200001", "5263200002", "5263200003"]
    for eid, roster in assigned.items():
        assert len(roster) == 9
    assert got["unfilled_entry_ids"] == []


def test_without_entries_the_mapping_is_empty_and_that_is_explicit(tmp_path):
    got = run(tmp_path)
    assert got["assignments_by_entry_id"] == {}
    assert got["unfilled_entry_ids"] == []
    assert len(got["lineups"]) == 4


def test_too_few_reserved_entry_ids_is_refused_before_the_build(tmp_path, capsys):
    """Was `SystemExit` (exit 1) after the build; now the writer's exit 2, nothing written."""

    entries = make_entries(tmp_path, 2)
    code, got = invoke(tmp_path, ["--entries", str(entries)], lineups=4)
    assert (code, got) == (2, None)
    err = capsys.readouterr().err
    assert "REFUSED ENTRY_ID_SHORTFALL" in err and "nothing was written" in err


def test_same_seed_same_bytes(tmp_path):
    """Determinism: the builder draws randomly, so the seed is the contract."""

    a = run(tmp_path, ["--seed", "913"])
    b = run(tmp_path, ["--seed", "913"])
    assert a["lineups"] == b["lineups"]


def test_same_inputs_give_a_byte_identical_portfolio(tmp_path):
    pool = make_pool(tmp_path)
    entries = make_entries(tmp_path, 4)
    outs = [tmp_path / "a.json", tmp_path / "b.json"]
    for out in outs:
        assert invoke(tmp_path, ["--entries", str(entries)], pool=pool, out=out)[0] == 0
    assert outs[0].read_bytes() == outs[1].read_bytes()


def test_a_different_seed_moves_the_portfolio(tmp_path):
    a = run(tmp_path, ["--seed", "1"])
    b = run(tmp_path, ["--seed", "2"])
    assert a["lineups"] != b["lineups"]


def test_require_bringback_holds_on_every_lineup(tmp_path):
    """12 of 18 on 2026-09-20 because this was an 85% coin flip, not a rule."""

    got = run(tmp_path, ["--require-bringback"])
    assert got["lineups"]
    assert all(l["bringback"] for l in got["lineups"])


def test_min_salary_floor_is_respected(tmp_path):
    got = run(tmp_path, ["--min-salary", "30000"])
    assert got["lineups"]
    assert all(l["salary"] >= 30000 for l in got["lineups"])


def test_every_lineup_is_legal_and_anti_correlation_holds(tmp_path):
    got = run(tmp_path, ["--entries", str(make_entries(tmp_path, 4))])
    sal = {r.split(",")[3]: r.split(",") for r in
           (tmp_path / "sal.csv").read_text(encoding="utf-8").splitlines()[1:]}
    for lineup in got["lineups"]:
        roster = lineup["roster"]
        assert len(set(roster)) == 9
        positions = [sal[i][0] for i in roster]
        assert positions.count("QB") == 1
        assert positions.count("DST") == 1
        assert lineup["salary"] <= 50000
        games = {sal[i][6].split()[0] for i in roster}
        assert len(games) >= 2
        dst = [i for i in roster if sal[i][0] == "DST"][0]
        dst_game = sal[dst][6].split()[0]
        away, home = dst_game.split("@")
        foe = home if sal[dst][7] == away else away
        assert not [i for i in roster if sal[i][7] == foe and sal[i][0] != "DST"]


def test_slate_context_is_read_and_recorded(tmp_path):
    ctx = tmp_path / "ctx.json"
    ctx.write_text(json.dumps({
        "implied_team_totals": {"AAA": 28.0, "BBB": 18.0},
        "projected_ownership": {}, "role_boosts": {},
    }), encoding="utf-8")
    got = run(tmp_path, ["--slate-context", str(ctx)])
    assert got["construction"]["slate_context"] == str(ctx)


def test_no_slate_context_means_no_stale_week_one_tables(tmp_path):
    """Regression on the real defect: the builder used to carry literal
    2026-09-13 implied totals, ownership and role boosts as module constants."""

    source = SCRIPT.read_text(encoding="utf-8")
    for stale in ("Jahmyr Gibbs", "Brock Bowers", "Michael Mayer", "Kendre Miller"):
        assert stale not in source, f"{stale} is a hardcoded Week 1 value"
    got = run(tmp_path)
    assert got["construction"]["slate_context"] is None


def test_empty_pool_is_a_named_refusal(tmp_path, capsys):
    """Was `SystemExit` (exit 1); now exit 2 by name, nothing written."""

    sal, sc, st = make_pool(tmp_path)
    sc.write_text(json.dumps({"by_dk_id": {}}), encoding="utf-8")
    code, got = invoke(tmp_path, lineups=2, pool=(sal, sc, st))
    assert (code, got) == (2, None)
    assert "REFUSED EMPTY_POOL" in capsys.readouterr().err


def test_inactive_players_never_enter_the_pool(tmp_path):
    sal, sc, st = make_pool(tmp_path)
    scores = json.loads(sc.read_text(encoding="utf-8"))["by_dk_id"]
    benched = sorted(scores)[0]
    st.write_text(STATUS_HEADER + f"AAA,{benched},INACTIVE,,\n", encoding="utf-8")
    got = run(tmp_path, pool=(sal, sc, st))
    assert all(benched not in l["roster"] for l in got["lineups"])


# ------------------------------------------------------------------ shortfall
# The audit's D6: the builder printed a WARNING and exited 0 on a shortfall, so
# the chain could ship blank reserved rows with nothing saying which.

def test_a_shortfall_writes_the_partial_map_and_exits_three(tmp_path, capsys):
    """Four quarterbacks and an overlap cap of 0: at most four lineups exist."""

    entries = make_entries(tmp_path, 8)
    code, got = invoke(tmp_path, ["--entries", str(entries), "--max-overlap", "0",
                                  "--attempts", "5000"], lineups=None)
    assert code == 3
    ids = [entry_id(n) for n in range(8)]
    built = len(got["lineups"])
    assert 0 < built <= 4
    assert list(got["assignments_by_entry_id"]) == ids[:built]
    assert got["unfilled_entry_ids"] == ids[built:]
    assert got["shortfall"] == 8 - built
    err = capsys.readouterr().err
    assert "SHORTFALL" in err
    assert all(eid in err for eid in ids[built:])


def test_a_shortfall_without_entries_still_exits_three(tmp_path, capsys):
    code, got = invoke(tmp_path, ["--max-overlap", "0", "--attempts", "5000"], lineups=8)
    assert code == 3
    assert got["shortfall"] == 8 - len(got["lineups"]) > 0
    assert got["unfilled_entry_ids"] == []
    assert "SHORTFALL" in capsys.readouterr().err


def test_no_lineup_repeats_even_when_the_overlap_cap_allows_it(tmp_path):
    """R29. Before Session 02b, `--max-overlap 9` let this pool return five lineups,
    two of them distinct, with exit 0."""

    entries = make_entries(tmp_path, 5)
    code, got = invoke(tmp_path, ["--entries", str(entries), "--max-overlap", "9",
                                  "--max-exposure", "60", "--attempts", "2000"],
                       lineups=None, pool=make_tiny_pool(tmp_path))
    assert code == 3
    assert len(got["lineups"]) == 2
    assert len(set(rosters(got))) == 2
    assert got["unfilled_entry_ids"] == [entry_id(n) for n in range(2, 5)]


def test_the_ratchet_stops_at_its_ceiling(tmp_path, monkeypatch):
    """`min(EXP + 1, max(EXP + 1, 9))` was always `EXP + 1`: no ceiling at all."""

    monkeypatch.setattr(build, "RATCHET_EVERY", 50)
    # A floor the pool cannot reach, so every attempt fails and the ratchet runs
    # 39 times.
    code, got = invoke(tmp_path, ["--min-salary", "50000", "--max-exposure", "1",
                                  "--attempts", "2000"], lineups=3)
    assert code == 3 and got["lineups"] == []
    c = got["construction"]
    assert c["max_exposure_requested"] == 1
    assert c["max_exposure_landed"] == 3        # max(asked, N), not 1 + 39
    assert c["max_overlap_landed"] == 6
    assert c["ratchet_steps"] > 0


def test_the_ratchet_never_tightens_a_cap_the_operator_set(tmp_path, monkeypatch):
    """`min(OVL + 1, 6)` pulled `--max-overlap 9` down to 6 on the first step."""

    monkeypatch.setattr(build, "RATCHET_EVERY", 50)
    code, got = invoke(tmp_path, ["--min-salary", "50000", "--max-exposure", "12",
                                  "--max-overlap", "9", "--attempts", "400"], lineups=3)
    assert code == 3
    c = got["construction"]
    assert (c["max_exposure_landed"], c["max_overlap_landed"]) == (12, 9)


@pytest.mark.parametrize("asked, n, steps, landed", [
    ((6, 4, 14), 20, 1, (7, 5, 11)),
    ((6, 4, 14), 20, 9, (15, 6, 6)),
    ((1, 4, 2), 3, 9, (3, 6, 2)),
    ((12, 9, 2), 3, 3, (12, 9, 2)),
])
def test_next_rung_loosens_toward_a_ceiling_and_never_below_the_ask(asked, n, steps, landed):
    exp, ovl, bb = asked
    for _ in range(steps):
        exp, ovl, bb = build.next_rung(exp, ovl, bb, asked[0], asked[1], n)
    assert (exp, ovl, bb) == landed


# ------------------------------------------------------------------ output
# The builder opened `--out` with "w", so a rerun destroyed the earlier portfolio.

def test_an_existing_output_is_refused_and_left_alone(tmp_path, capsys):
    out = tmp_path / "earlier.json"
    out.write_text("earlier", encoding="utf-8")
    code, _ = invoke(tmp_path, out=out)
    assert code == 2
    assert out.read_text(encoding="utf-8") == "earlier"
    assert "REFUSED OUTPUT_EXISTS" in capsys.readouterr().err
    assert list(tmp_path.glob(".earlier.json.*")) == []


def test_an_output_that_is_an_input_is_refused(tmp_path, capsys):
    sal, sc, st = make_pool(tmp_path)
    before = sc.read_bytes()
    code, _ = invoke(tmp_path, pool=(sal, sc, st), out=sc)
    assert code == 2
    assert sc.read_bytes() == before
    assert "REFUSED OUTPUT_IS_AN_INPUT" in capsys.readouterr().err


def test_the_portfolio_is_written_through_a_temporary_file(tmp_path, monkeypatch):
    moves = []
    real = build.os.replace
    monkeypatch.setattr(build.os, "replace", lambda a, b: (moves.append((a, b)), real(a, b)))
    code, got = invoke(tmp_path, out=tmp_path / "p.json")
    assert code == 0 and got["lineups"]
    assert len(moves) == 1 and Path(moves[0][1]) == tmp_path / "p.json"
    assert list(tmp_path.glob(".p.json.*")) == []


# ------------------------------------------------------------------ pool filter
# `selection.py` writes scores.json before its exclusion set, so DraftKings
# OUT, IR and D rows reached the builder with positive scores (33 of them in the
# supplied Classic salary file).

def top_wr(team: str) -> str:
    """The DraftKings ID of `team`'s highest-scoring receiver in `make_pool`."""

    base = 1000 + list(TEAMS).index(team) * sum(COUNTS.values())
    return str(base + COUNTS["QB"] + COUNTS["RB"] + COUNTS["WR"])


@pytest.mark.parametrize("flag", ["OUT", "IR", "D"])
def test_draftkings_unavailable_rows_leave_the_pool(tmp_path, flag):
    flagged = top_wr("AAA")
    pool = make_pool(tmp_path, statuses={flagged: flag}, scores_override={flagged: 500.0})
    got = run(tmp_path, lineups=8, pool=pool)
    assert all(flagged not in l["roster"] for l in got["lineups"])
    assert got["construction"]["dk_status_dropped"] == {flag: 1}


def test_a_questionable_player_stays_in_the_pool(tmp_path):
    """`Q` is degraded, not unavailable: fading him is the operator's call."""

    flagged = top_wr("AAA")
    pool = make_pool(tmp_path, statuses={flagged: "Q"}, scores_override={flagged: 500.0})
    got = run(tmp_path, lineups=8, pool=pool)
    assert any(flagged in l["roster"] for l in got["lineups"])
    assert got["construction"]["dk_status_dropped"] == {}


def test_available_status_restores_a_doubtful_player_as_the_engine_does(tmp_path):
    flagged = top_wr("AAA")
    pool = make_pool(tmp_path, statuses={flagged: "D"}, scores_override={flagged: 500.0})
    got = run(tmp_path, ["--available-status", "d"], lineups=8, pool=pool)
    assert any(flagged in l["roster"] for l in got["lineups"])
    assert "D" not in got["construction"]["dk_unavailable_statuses"]


def test_a_salary_file_without_status_is_refused(tmp_path, capsys):
    code, got = invoke(tmp_path, pool=make_pool(tmp_path, status_column=False))
    assert (code, got) == (2, None)
    assert "REFUSED SALARY_COLUMNS_MISSING" in capsys.readouterr().err


def _truncate_scores(sal, sc, st):
    sc.write_bytes(sc.read_bytes()[:40])


def _repeat_an_id(sal, sc, st):
    lines = sal.read_text(encoding="utf-8").splitlines(keepends=True)
    sal.write_text("".join(lines + lines[1:2]), encoding="utf-8")


def _unreadable_salary(sal, sc, st):
    sal.write_text(sal.read_text(encoding="utf-8").replace(",3000,", ",3O00,", 1), encoding="utf-8")


def _showdown_rows(sal, sc, st):
    sal.write_text(sal.read_text(encoding="utf-8").replace(",QB,", ",CPT,", 1), encoding="utf-8")


def _status_without_columns(sal, sc, st):
    st.write_text("TEAM,ID,STATE\n", encoding="utf-8")


@pytest.mark.parametrize("mutate, code", [
    (_truncate_scores, "SCORES_UNREADABLE"),
    (_repeat_an_id, "SALARY_DUPLICATE_ID"),
    (_unreadable_salary, "SALARY_UNREADABLE"),
    (_showdown_rows, "NOT_A_CLASSIC_SALARY_FILE"),
    (_status_without_columns, "STATUS_COLUMNS_MISSING"),
])
def test_a_damaged_input_withholds_the_portfolio(tmp_path, capsys, mutate, code):
    """One changed input, one named refusal, no file: never a repaired portfolio."""

    pool = make_pool(tmp_path)
    mutate(*pool)
    got_code, got = invoke(tmp_path, pool=pool, out=tmp_path / "p.json")
    assert (got_code, got) == (2, None)
    assert not (tmp_path / "p.json").exists()
    assert f"REFUSED {code}" in capsys.readouterr().err


def test_the_builder_never_reads_points_per_game():
    assert "AvgPointsPerGame" not in SCRIPT.read_text(encoding="utf-8")


# ------------------------------------------------------------------ template rows
# `reserved_entry_ids` returned every row, so a prefilled row was assigned and
# the writer then refused the whole file.

def test_only_blank_rows_are_reserved_and_lineups_defaults_to_their_count(tmp_path):
    first = run(tmp_path, lineups=1)["lineups"][0]["roster"]
    entries = make_entries(tmp_path, 4, prefilled={1: first})
    assert build.reserved_entry_ids(entries) == [entry_id(0), entry_id(2), entry_id(3)]
    got = run(tmp_path, ["--entries", str(entries)], lineups=None)
    assert list(got["assignments_by_entry_id"]) == [entry_id(0), entry_id(2), entry_id(3)]
    assert got["construction"]["lineups"] == 3


def test_a_prefilled_roster_is_never_built_again(tmp_path):
    """Same seed, same pool: the first lineup drawn is the prefilled one, and R29
    covers the whole file, so it must be skipped. The writer refuses a repeat."""

    first = run(tmp_path, lineups=1)["lineups"][0]["roster"]
    cells = [f"Name {i} ({i})" for i in first]
    entries = make_entries(tmp_path, 3, prefilled={0: cells})
    got = run(tmp_path, ["--entries", str(entries)], lineups=None)
    assert frozenset(first) not in rosters(got)
    portfolio = tmp_path / "chain.json"
    portfolio.write_text(json.dumps(got), encoding="utf-8")
    out = tmp_path / "filled.csv"
    proc = subprocess.run([sys.executable, str(WRITER), str(portfolio), str(entries),
                           str(tmp_path / "sal.csv"), str(out)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_fewer_lineups_than_blank_rows_names_the_rest(tmp_path, capsys):
    entries = make_entries(tmp_path, 4)
    code, got = invoke(tmp_path, ["--entries", str(entries)], lineups=2)
    assert code == 3
    assert got["unfilled_entry_ids"] == [entry_id(2), entry_id(3)]
    assert entry_id(3) in capsys.readouterr().err


def test_a_template_with_no_blank_row_is_refused(tmp_path, capsys):
    first = run(tmp_path, lineups=1)["lineups"][0]["roster"]
    entries = make_entries(tmp_path, 1, prefilled={0: first})
    code, got = invoke(tmp_path, ["--entries", str(entries)], lineups=None)
    assert (code, got) == (2, None)
    assert "REFUSED NO_BLANK_ENTRY_ROWS" in capsys.readouterr().err


def test_a_showdown_template_is_refused(tmp_path, capsys):
    p = tmp_path / "sd.csv"
    p.write_text("Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions\n"
                 f"{entry_id(0)},Contest,1234,$1,,,,,,,,\n", encoding="utf-8")
    code, got = invoke(tmp_path, ["--entries", str(p)], lineups=None)
    assert (code, got) == (2, None)
    assert "REFUSED NOT_A_CLASSIC_TEMPLATE" in capsys.readouterr().err


# ------------------------------------------------------------------ the chain
# Builder, writer and Classic QA share one exit vocabulary; they must agree.

def fill_and_check(tmp_path, got, entries, salaries):
    portfolio = tmp_path / "chain.json"
    portfolio.write_text(json.dumps(got), encoding="utf-8")
    out = tmp_path / "filled.csv"
    proc = subprocess.run([sys.executable, str(WRITER), str(portfolio), str(entries),
                           str(salaries), str(out)], capture_output=True, text=True)
    qa = _load("qa_classic_portfolio", QA)
    verdict = qa.main(["--portfolio", str(portfolio), "--salaries", str(salaries),
                       "--template", str(entries), "--export", str(out)])
    return proc, verdict


def test_a_builder_shortfall_carries_through_the_writer_and_qa(tmp_path):
    entries = make_entries(tmp_path, 8, crlf=True)
    code, got = invoke(tmp_path, ["--entries", str(entries), "--max-overlap", "0",
                                  "--attempts", "5000"], lineups=None)
    assert code == 3
    proc, verdict = fill_and_check(tmp_path, got, entries, tmp_path / "sal.csv")
    assert proc.returncode == 3, proc.stderr
    assert all(eid in proc.stderr for eid in got["unfilled_entry_ids"])
    assert verdict == 3


def test_the_supplied_classic_files_build_fill_and_pass_qa(tmp_path):
    """The real 719-row salary file (33 rows OUT, IR or D) and 20-entry template,
    copied first. Scores are synthetic and positive for every row, so only the
    status filter can keep a flagged player out."""

    salaries = tmp_path / "DKSalaries.csv"
    entries = tmp_path / "DKEntries.csv"
    shutil.copyfile(SUPPLIED / "DKSalaries Salary CSV Classic.csv", salaries)
    shutil.copyfile(SUPPLIED / "DKEntries CSV 20 entries.csv", entries)
    import csv
    with salaries.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    flagged = {r["ID"] for r in rows if r["Status"].strip().upper() in {"OUT", "IR", "D"}}
    assert len(flagged) == 33
    scores = tmp_path / "scores.json"
    scores.write_text(json.dumps({"by_dk_id": {r["ID"]: 5.0 + int(r["ID"]) % 17 for r in rows}}),
                      encoding="utf-8")
    status = tmp_path / "status.csv"
    status.write_text(STATUS_HEADER, encoding="utf-8")
    code, got = invoke(tmp_path, ["--entries", str(entries)], lineups=None,
                       pool=(salaries, scores, status))
    assert code == 0, got and got["unfilled_entry_ids"]
    assert len(got["assignments_by_entry_id"]) == 20
    assert not flagged & set().union(*rosters(got))
    assert got["construction"]["dk_status_dropped"] == {"D": 1, "IR": 24, "OUT": 8}
    assert len(set(rosters(got))) == 20
    before = entries.read_bytes()
    proc, verdict = fill_and_check(tmp_path, got, entries, salaries)
    assert proc.returncode == 0, proc.stderr
    assert verdict == 0
    assert entries.read_bytes() == before
