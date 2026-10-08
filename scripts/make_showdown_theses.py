#!/usr/bin/env python3
"""Write Ben's R33 game theses for one Showdown as thesis files, by structure alone (Session 67).

R33 (Ben, 2026-09-24): each team wins big, each team wins close (high and low scoring sub-variants), a defensive
battle, an offensive shootout. On slate day a portfolio of theses used to mean hand-writing six JSON files; this writes
them from the salary bytes, one file per thesis, for `scripts/make_showdown_policy.py --thesis <file>` (repeatable).

    .venv\\Scripts\\python.exe scripts\\make_showdown_theses.py --salaries <DKSalaries.csv> --teams NE SEA --out-dir <dir>

STRUCTURE ONLY. A thesis names "a team's best players by salary at a position": FLEX rows, DraftKings `OUT` and `IR`
left out, highest salary first and the lower DraftKings ID on a tie. Nothing here reads a model value, a spread, a total,
a contest name or the points-per-game column, and nothing infers a favorite or a script. The output for `--teams NE SEA`
is exactly the list `tests/test_showdown_thesis_acceptance.py::r33_theses` builds (Session 23c's acceptance).

BEN'S INPUTS. The teams are his (`--teams`, exactly the slate's two), and so is the order: the first team named comes
first in every pair, and the files are numbered in the declared order, which `make_showdown_policy.py` reads as the
priority (it breaks allotment ties). Which theses reach a policy is his too: pass only the files he chose, in the order
he chose. `--variants` writes the close game's high and low scoring sub-variants for each team (eight files, not six).
No file carries a `row_weight` (equal shares); add one to a file to give a thesis more rows. A `D` (doubtful) player is
not left out, exactly as the acceptance does; `run-slate` treats `D` as unavailable by default, so read the Captain
sets this prints.

REFUSALS, by name, leaving nothing behind: THESES_SALARY_UNREADABLE, THESES_NOT_SHOWDOWN, THESES_TEAMS_NOT_TWO,
THESES_TEAM_NOT_ON_SLATE, THESES_EMPTY_CAPTAIN_SET:<NAME>, THESES_OUTPUT_EXISTS:<path> (every target is checked before
the first is written; nothing is ever overwritten), THESES_WRITE_FAILED:<path> (a write failed part way; the files this
run wrote are removed).

A thesis is a choice, not a forecast: nothing here calls one likely, and with no ownership input leverage is unmeasured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

UNAVAILABLE = frozenset({"OUT", "IR"})


class Refusal(Exception):
    """A named refusal: nothing is written."""


def _top(slate, team, position, count):
    rows = sorted((row for row in slate.players
                   if row.team == team and row.position == position and row.role == "FLEX"
                   and row.status_raw not in UNAVAILABLE),
                  key=lambda row: (-row.salary, row.dk_id))
    return [row.underlying_id for row in rows[:count]]


def r33_theses(slate, one: str, two: str, *, variants: bool) -> list[dict]:
    """Ben's R33 list for teams `one` and `two`, in that order, as structure."""

    def wins_big(team):
        return {"name": f"{team}_WINS_BIG", "teams": [team],
                "captain_set": [*_top(slate, team, "QB", 1), *_top(slate, team, "RB", 2), *_top(slate, team, "WR", 2),
                                *_top(slate, team, "DST", 1)],
                "team_bounds": [{"team": team, "minimum": 4, "maximum": 5}]}

    def close(team, other, *, high):
        if high:
            return {"name": f"{team}_WINS_CLOSE_HIGH", "teams": [team, other],
                    "captain_set": [*_top(slate, team, "QB", 1), *_top(slate, other, "QB", 1), *_top(slate, team, "WR", 2)],
                    "team_bounds": [{"team": team, "minimum": 3, "maximum": 4}],
                    "position_bounds": [{"position": "QB", "minimum": 1, "maximum": 2}]}
        return {"name": f"{team}_WINS_CLOSE_LOW" if variants else f"{team}_WINS_CLOSE", "teams": [team, other],
                "captain_set": [*_top(slate, team, "K", 1), *_top(slate, team, "DST", 1)],
                "team_bounds": [{"team": team, "minimum": 3, "maximum": 4}],
                "position_bounds": [{"position": "K", "minimum": 1, "maximum": 1},
                                    {"position": "DST", "minimum": 1, "maximum": 1},
                                    {"position": "WR", "minimum": 0, "maximum": 1}]}

    defensive = {"name": "DEFENSIVE_BATTLE", "teams": [one, two],
                 "captain_set": [*_top(slate, one, "K", 1), *_top(slate, two, "K", 1),
                                 *_top(slate, one, "DST", 1), *_top(slate, two, "DST", 1)],
                 "position_bounds": [{"position": "K", "minimum": 2, "maximum": 2},
                                     {"position": "DST", "minimum": 1, "maximum": 1},
                                     {"position": "QB", "minimum": 0, "maximum": 1},
                                     {"position": "WR", "minimum": 0, "maximum": 1}]}
    shootout = {"name": "OFFENSIVE_SHOOTOUT", "teams": [one, two],
                "captain_set": [*_top(slate, one, "QB", 1), *_top(slate, two, "QB", 1),
                                *_top(slate, one, "WR", 2), *_top(slate, two, "WR", 2)],
                "position_bounds": [{"position": "QB", "minimum": 2, "maximum": 2},
                                    {"position": "K", "minimum": 0, "maximum": 0},
                                    {"position": "DST", "minimum": 0, "maximum": 0}]}
    theses = [wins_big(one), wins_big(two)]
    if variants:
        theses += [close(one, two, high=True), close(one, two, high=False),
                   close(two, one, high=True), close(two, one, high=False)]
    else:
        theses += [close(one, two, high=False), close(two, one, high=False)]
    return [*theses, defensive, shootout]


def _read_slate(path: Path):
    from nfl_dfs.dk import parse_salaries
    from nfl_dfs.contracts import EngineMode

    try:
        slate = parse_salaries(path)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the one named refusal
        raise Refusal(f"THESES_SALARY_UNREADABLE: {path}: {type(exc).__name__}: {exc}") from exc
    if slate.mode is not EngineMode.SHOWDOWN:
        raise Refusal(f"THESES_NOT_SHOWDOWN: {path} is a {slate.mode.value} salary file")
    return slate


def _teams(slate, named: list[str]) -> tuple[str, str]:
    teams = [str(team).strip() for team in named]
    on_slate = sorted({row.team for row in slate.players})
    if len(teams) != 2 or teams[0] == teams[1]:
        raise Refusal(f"THESES_TEAMS_NOT_TWO: name the slate's two teams once each; got {teams}; slate {on_slate}")
    outside = [team for team in teams if team not in on_slate]
    if outside:
        raise Refusal(f"THESES_TEAM_NOT_ON_SLATE: {outside} not in the salary file; slate {on_slate}")
    return teams[0], teams[1]


def plan(salaries: Path, teams: list[str], out_dir: Path, *, variants: bool):
    """The slate, the files to write (path, thesis) in declared order, and the salary SHA-256; nothing written."""

    slate = _read_slate(salaries)
    one, two = _teams(slate, teams)
    theses = r33_theses(slate, one, two, variants=variants)
    empty = [item["name"] for item in theses if not item["captain_set"]]
    if empty:
        raise Refusal(f"THESES_EMPTY_CAPTAIN_SET:{empty[0]}: no FLEX player outside OUT and IR fills it"
                      f" (all empty: {empty})")
    targets = [(out_dir / f"{index:02d}_{item['name']}.json", item) for index, item in enumerate(theses, 1)]
    taken = [str(path) for path, _item in targets if path.exists()]
    if taken:
        raise Refusal(f"THESES_OUTPUT_EXISTS:{taken[0]}: never overwritten; choose an empty --out-dir (all: {taken})")
    return slate, targets, hashlib.sha256(salaries.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--salaries", required=True, type=Path, help="the DraftKings Showdown salary CSV")
    parser.add_argument("--teams", required=True, nargs="+",
                        help="the slate's two teams; the first named comes first in every pair (the priority)")
    parser.add_argument("--out-dir", required=True, type=Path, help="where the thesis files go (created if missing)")
    parser.add_argument("--variants", action="store_true",
                        help="the close game's high and low scoring sub-variants for each team (eight files)")
    args = parser.parse_args(argv)
    written: list[Path] = []
    try:
        slate, targets, digest = plan(args.salaries, args.teams, args.out_dir, variants=args.variants)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for path, item in targets:
            with path.open("x", encoding="utf-8", newline="\n") as handle:  # exclusive: never overwrite
                written.append(path)
                handle.write(json.dumps(item, indent=2) + "\n")
    except Refusal as refusal:
        print(str(refusal), file=sys.stderr)
        return 1
    except OSError as exc:
        # A file that appeared after the check, a full disk, a permission: remove only what this run wrote, so a
        # failed run leaves no partial set behind.
        for path in written:
            path.unlink(missing_ok=True)
        code = "THESES_OUTPUT_EXISTS" if isinstance(exc, FileExistsError) else "THESES_WRITE_FAILED"
        print(f"{code}:{exc.filename}: {type(exc).__name__}: nothing kept from this run", file=sys.stderr)
        return 1
    names = {row.underlying_id: f"{row.name} ({row.position}, {row.team})" for row in slate.players}
    print(f"salaries {args.salaries} sha256 {digest}")
    for path, item in targets:
        print(f"{path}: {item['name']}; Captain set: {', '.join(names[uid] for uid in item['captain_set'])}")
    print("make_showdown_policy.py flags, in the declared order (keep only the theses you chose):")
    print(" ".join(f'--thesis "{path}"' for path, _item in targets))
    print("A thesis is a choice, not a forecast; with no ownership input leverage is unmeasured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
