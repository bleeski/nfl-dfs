"""Each contest's entries, read together on their shot at that contest's first place (Session 75, R38).

`first_place_coverage_v1`. R38 (Ben, 2026-10-14) sets goal 1 contest by contest: the entries in one Contest ID are one
set of shots at its first place, so two near-copies there are one shot, not two. Session 50's contest step already
measures each contest's spread; this module reads it back per Contest ID where the operator decides (both QA scripts;
the readable review and the run's own record are Session 75b's) and joins each contest to the run's contest facts. It is a reading. It never gates, never
selects and never moves a lineup or a release truth.

Per Contest ID:

- two or more entries: `statistics` is exactly `contest_assignment.contest_statistics` over the contest's lineups, the
  same call `statistics_from_rosters` makes, so it equals the step's `contests_after` on the same rosters, people and
  thesis labels. `repeated_key_people` names each Captain (Showdown) or QB (Classic) held by more than one entry.
- one entry: the lineup's shape instead, since a single lineup has no pair to compare: the Captain and his salary
  (Showdown); the QB, the primary stack team, its depth and the bring-back (Classic); salary left in both. Beside it is
  `NO_TAIL_LINE`: nothing here ranks one lineup over another.
- the facts columns, from a bound `nfl_contest_facts_labels_v1` block (`SUPPLIED`, `NO_FACTS_ROW`, `FEE_DISAGREES`
  with the supplied numbers), else `NO_CONTEST_FACTS`. Every contest is read as a tournament until a payout ladder or
  Ben says it is flat (R38).

Every state here is a reading state, returned and never raised: `NO_CONTEST_FACTS`, `NO_CONTEST_IDS`,
`NO_CONTEST_ID_COLUMN`, `NOT_BOUND` and `NOT_COMPUTED` stop nothing and are not limitations.

People are keyed `team|position|name`, the run's `SalaryPlayer.underlying_id`, so a Captain row and his FLEX row are
one person. Standard library only, beside the two standard-library modules it reads.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from . import contest_assignment as ca
from . import contest_facts

FIRST_PLACE_COVERAGE_VERSION = "first_place_coverage_v1"
DOES_NOT_ESTABLISH = (
    "NOT_A_CHANCE_OF_FINISHING_FIRST",
    "NOT_A_SHARE_OF_ANY_PRIZE",
    "NOT_A_TAIL_STATISTIC",
    "NOT_OWNERSHIP_OR_DUPLICATION",
    "NOT_UPLOAD_CLEARANCE",
)
NO_TAIL_LINE = "no tail statistic exists before Session 24b: shape facts only, never a ranking"
READ_AS = "every contest is read as a tournament (R38) until a payout ladder or Ben says it is flat"
SALARY_CAP = 50_000
OFFENSE = frozenset({"QB", "RB", "WR", "TE"})

# Reading states.
READ = "READ"
NO_CONTEST_IDS = "NO_CONTEST_IDS"
NO_CONTEST_ID_COLUMN = "NO_CONTEST_ID_COLUMN"
NO_ROSTER_COLUMNS = "NO_ROSTER_COLUMNS"
NOT_COMPUTED = "NOT_COMPUTED"
NO_CONTEST_FACTS = "NO_CONTEST_FACTS"
FACTS_NOT_SUPPLIED = "NOT_SUPPLIED"
FACTS_BOUND = "BOUND"
FACTS_NO_ROWS = "NO_ROWS"
FACTS_NOT_BOUND = "NOT_BOUND"
UNREADABLE_FACTS = object()   # what `facts_from_file` returns for bytes that are not JSON

_FACTS_COLUMNS = ("field_size", "places_paid", "paid_fraction", "paid_fraction_decimal", "label")
_ROWED_STATUSES = (contest_facts.STATUS_APPLIED, contest_facts.STATUS_PARTIAL)
_LOCKED = "(LOCKED)"
_BARE_ID = re.compile(r"[0-9]+")
_TRAILING_ID = re.compile(r"\(([0-9]+)\)\s*$")
_FIRST_SLOT = {ca.MODE_SHOWDOWN: "CPT", ca.MODE_CLASSIC: "QB"}
_WIDTH = {ca.MODE_SHOWDOWN: 6, ca.MODE_CLASSIC: 9}


@dataclass(frozen=True)
class PlayerInfo:
    """One DraftKings ID, as the reading needs it."""

    key: str                 # team|position|name: identical across a Showdown CPT and FLEX ID
    name: str
    team: str
    position: str
    salary: int
    opponent: str | None


def _opponent(team: str, game_info: str) -> str | None:
    teams = game_info.split()[0].split("@") if game_info.split() else []
    return next((other for other in teams if other != team), None) if team in teams and len(teams) == 2 else None


def players_from_salary_csv(path: str | Path) -> dict[str, PlayerInfo]:
    """Every DraftKings ID in a salary file, keyed and trimmed exactly as `dk.parse_salaries` keys them."""

    players: dict[str, PlayerInfo] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            team, position, name = row["TeamAbbrev"].strip(), row["Position"].strip(), row["Name"].strip()
            players[row["ID"].strip()] = PlayerInfo(
                f"{team}|{position}|{name}", name, team, position, int(row["Salary"]),
                _opponent(team, row["Game Info"].strip()))
    return players


def players_from_slate(players) -> dict[str, PlayerInfo]:
    """The same map from a parsed slate's players (duck-typed on `SalaryPlayer`)."""

    return {
        p.dk_id: PlayerInfo(p.underlying_id, p.name, p.team, p.position, p.salary, p.opponent) for p in players
    }


def people(players: Mapping[str, PlayerInfo]) -> dict[str, ca.Person]:
    return {dk_id: ca.Person(key=info.key, team=info.team, position=info.position) for dk_id, info in players.items()}


def cell_dk_id(cell: str) -> str | None:
    """A roster cell's exact DraftKings ID: a bare ID, `Name (ID)`, or late swap's `Name (ID) (LOCKED)`.

    The same forms `entry_record._cell_id` reads (Session 72b): one trailing `(LOCKED)` is stripped, then
    `lineups.prefilled_cell_id`'s rule. A name alone, or anything else, names no ID.
    """

    value = cell.strip()
    if value.endswith(_LOCKED):
        value = value[: -len(_LOCKED)]
    value = value.strip()
    if _BARE_ID.fullmatch(value):
        return value
    match = _TRAILING_ID.search(value)
    return match.group(1) if match else None


def read_entries_file(
    path: str | Path, *, mode: str
) -> tuple[list[tuple[str, str, tuple[str, ...] | None]], str]:
    """`(entry_id, contest_id, roster or None)` for every entry row of a DraftKings entries file, and a reading state.

    A row's roster is None unless every roster cell names an ID. The header row must name `Entry ID` and `Contest ID`
    (`NO_CONTEST_ID_COLUMN`) and the mode's first roster slot (`NO_ROSTER_COLUMNS`).
    """

    table = list(csv.reader(io.StringIO(Path(path).read_bytes().decode("utf-8-sig", errors="replace"))))
    header = [cell.strip() for cell in table[0]] if table else []
    if "Entry ID" not in header or "Contest ID" not in header:
        return [], NO_CONTEST_ID_COLUMN
    if _FIRST_SLOT[mode] not in header:
        return [], NO_ROSTER_COLUMNS
    entry_at, contest_at = header.index("Entry ID"), header.index("Contest ID")
    first, width = header.index(_FIRST_SLOT[mode]), _WIDTH[mode]
    rows: list[tuple[str, str, tuple[str, ...] | None]] = []
    for line in table[1:]:
        if len(line) <= max(entry_at, contest_at) or not line[entry_at].strip().isdigit():
            continue
        ids = [cell_dk_id(cell) for cell in line[first:first + width]]
        roster = tuple(ids) if len(ids) == width and all(ids) else None
        rows.append((line[entry_at].strip(), line[contest_at].strip(), roster))
    return rows, READ


def facts_from_file(path: str | Path) -> object:
    """The parsed JSON of a run's `selection/contest_facts.json`, or `UNREADABLE_FACTS`."""

    try:
        return json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return UNREADABLE_FACTS


def _facts_rows(facts: object, contest_ids: set[str]) -> tuple[dict[str, Mapping[str, object]], dict[str, object]]:
    """Each contest's facts row and the binding: a block binds to this file or the table reads it as absent."""

    def binding(state: str, detail: str | None = None, status: object = None) -> dict[str, object]:
        return {"binding": state, "detail": detail, "facts_status": status}

    if facts is None:
        return {}, binding(FACTS_NOT_SUPPLIED)
    if facts is UNREADABLE_FACTS:
        return {}, binding(FACTS_NOT_BOUND, "UNREADABLE")
    if not isinstance(facts, Mapping) or not isinstance(facts.get("contests"), list) or not all(
            isinstance(row, Mapping) for row in facts["contests"]):
        return {}, binding(FACTS_NOT_BOUND, "NOT_AN_OBJECT")
    if facts.get("schema_version") != contest_facts.BLOCK_VERSION:
        return {}, binding(FACTS_NOT_BOUND, "SCHEMA_VERSION")
    status = facts.get("status")
    if status not in _ROWED_STATUSES:
        return {}, binding(FACTS_NO_ROWS, None, status)
    rows = {str(row.get("contest_id")): row for row in facts["contests"]}
    if set(rows) != contest_ids or len(rows) != len(facts["contests"]):
        return {}, binding(FACTS_NOT_BOUND, "CONTEST_SET")
    return rows, binding(FACTS_BOUND, None, status)


def _shape(roster: Sequence[str], *, mode: str, players: Mapping[str, PlayerInfo]) -> dict[str, object]:
    salary_left = SALARY_CAP - sum(players[dk_id].salary for dk_id in roster)
    if mode == ca.MODE_SHOWDOWN:
        captain = players[roster[0]]
        return {"captain": captain.key, "captain_salary": captain.salary, "salary_left": salary_left}
    offense = [players[dk_id] for dk_id in roster if players[dk_id].position in OFFENSE]
    quarterback = next((info for info in offense if info.position == "QB"), None)
    stack = ca.primary_stack_team(roster, people({dk_id: players[dk_id] for dk_id in roster}))
    anchor = next((info for info in offense if info.team == stack), quarterback)
    opponent = anchor.opponent if anchor is not None else None
    return {
        "quarterback": quarterback.key if quarterback is not None else None,
        "stack_team": stack,
        "stack_depth": sum(1 for info in offense if info.team == stack) if stack else 0,
        "bring_back": sum(1 for info in offense if opponent is not None and info.team == opponent),
        "salary_left": salary_left,
    }


def _skeleton(mode: str, state: str, detail: str | None, source: str | None) -> dict[str, object]:
    return {
        "first_place_coverage_version": FIRST_PLACE_COVERAGE_VERSION,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
        "status": state,
        "detail": detail,
        "mode": mode,
        "key_person": "CAPTAIN" if mode == ca.MODE_SHOWDOWN else "QUARTERBACK",
        "source": source,
        "read_as": READ_AS,
        "thesis_labels": "NONE",
        "facts": {"binding": FACTS_NOT_SUPPLIED, "detail": None, "facts_status": None},
        "duplicate_entry_ids": [],
        "contest_count": 0,
        "one_entry_contest_count": 0,
        "contests": [],
    }


def unread(mode: str, state: str, detail: str | None = None, *, source: str | None = None) -> dict[str, object]:
    """The reading when no contest could be read: the state named, no contest rows."""

    return _skeleton(mode, state, detail, source)


def reading(
    rows: Sequence[tuple[str, str, Sequence[str] | None]],
    *,
    mode: str,
    players: Mapping[str, PlayerInfo],
    thesis_by_entry: Mapping[str, str] | None = None,
    facts: object = None,
    source: str | None = None,
) -> dict[str, object]:
    """The reading over `(entry_id, contest_id, roster or None)` rows, one per entry, in file order.

    A row with no roster is listed in `rows_without_roster`; one naming an ID the players lack in `rows_unscored`
    (the run leaves such a row unscored, `contest_assignment.plan_rows`). Neither is scored. `thesis_by_entry`
    labels an entry's lineup with its thesis, as the step labels its roster.
    """

    out = _skeleton(mode, READ, None, source)
    by_contest: dict[str, list[tuple[str, tuple[str, ...] | None]]] = {}
    for entry_id, contest_id, roster in rows:
        by_contest.setdefault(contest_id, []).append((entry_id, None if roster is None else tuple(roster)))
    facts_rows, out["facts"] = _facts_rows(facts, set(by_contest))
    out["thesis_labels"] = "SUPPLIED" if thesis_by_entry else "NONE"
    counts = Counter(entry_id for entry_id, _contest, _roster in rows)
    out["duplicate_entry_ids"] = sorted(entry_id for entry_id, count in counts.items() if count > 1)
    known = people(players)
    contests: list[dict[str, object]] = []
    for contest_id in sorted(by_contest):
        scored = [(entry_id, roster) for entry_id, roster in by_contest[contest_id]
                  if roster is not None and all(dk_id in players for dk_id in roster)]
        row: dict[str, object] = {
            "contest_id": contest_id,
            "entry_ids": [entry_id for entry_id, _roster in scored],
            "entries": len(scored),
            "rows_without_roster": [entry_id for entry_id, roster in by_contest[contest_id] if roster is None],
            "rows_unscored": [entry_id for entry_id, roster in by_contest[contest_id]
                              if roster is not None and not all(dk_id in players for dk_id in roster)],
        }
        supplied = facts_rows.get(contest_id)
        row["facts_state"] = NO_CONTEST_FACTS if supplied is None else supplied.get("facts_state")
        row.update({column: None if supplied is None else supplied.get(column) for column in _FACTS_COLUMNS})
        if len(scored) >= 2:
            placed = [ca.lineup_facts(roster, mode=mode, people=known, thesis=(thesis_by_entry or {}).get(entry_id))
                      for entry_id, roster in scored]
            row["statistics"] = ca.contest_statistics(placed)
            held = Counter(lineup.key_person for lineup in placed if lineup.key_person is not None)
            row["repeated_key_people"] = [
                {"person": person, "entries": count}
                for person, count in sorted(held.items(), key=lambda item: (-item[1], item[0])) if count > 1
            ]
        elif len(scored) == 1:
            row["shape"] = _shape(scored[0][1], mode=mode, players=players)
            row["no_tail_statistic"] = NO_TAIL_LINE
        contests.append(row)
    out["contests"] = contests
    out["contest_count"] = len(contests)
    out["one_entry_contest_count"] = sum(1 for row in contests if row["entries"] == 1)
    return out


def _count(count: object, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def text_lines(data: Mapping[str, object]) -> list[str]:
    """The reading as plain text, the section `qa_classic_portfolio.py` prints after Tier 2."""

    rule = "=" * 62
    lines = ["", rule, f"FIRST PLACE, CONTEST BY CONTEST  ({FIRST_PLACE_COVERAGE_VERSION}: a reading, never a gate)", rule]
    one, key = ("Captain", "Captains") if data.get("key_person") == "CAPTAIN" else ("QB", "QBs")
    if data.get("status") != READ:
        lines.append(f"  {data.get('status')}: {data.get('detail')}")
    else:
        facts = data.get("facts") or {}
        binding = str(facts.get("binding"))
        if facts.get("detail"):
            binding += f" ({facts.get('detail')})"
        elif facts.get("facts_status"):
            binding += f" ({facts.get('facts_status')})"
        lines.append(f"  {_count(data.get('contest_count'), 'contest', 'contests')}, {data.get('one_entry_contest_count')} with one "
                     f"entry; facts {binding}; thesis labels {data.get('thesis_labels')}")
        lines.append(f"  {READ_AS}")
        for row in data.get("contests") or []:
            state = str(row.get("facts_state"))
            if row.get("field_size") is not None:
                numbers = [f"field {row.get('field_size')}", f"paid {row.get('places_paid')}"]
                numbers += [str(row[column]) for column in ("paid_fraction", "label") if row.get(column)]
                state += f" ({', '.join(numbers)})"
            lines.append(f"  contest {row.get('contest_id')}: {_count(row.get('entries'), 'entry', 'entries')}; facts {state}")
            stats = row.get("statistics")
            if isinstance(stats, Mapping):
                lines.append(
                    f"    worst pair shares {_count(stats.get('worst_pair_shared_people'), 'person', 'people')}, mean "
                    f"{stats.get('mean_shared_people')}; {_count(stats.get('distinct_key_people'), 'distinct ' + one, 'distinct ' + key)}, "
                    f"{_count(stats.get('distinct_stack_teams'), 'stack team', 'stack teams')}, "
                    f"{_count(stats.get('distinct_theses'), 'thesis', 'theses')}")
                repeats = ", ".join(f"{item['person']} x{item['entries']}" for item in row.get("repeated_key_people") or [])
                lines.append(f"    repeated {key}: {repeats or 'none'}")
                lines.append(f"    in every lineup: {', '.join(stats.get('people_in_every_lineup') or []) or 'none'}")
            shape = row.get("shape")
            if isinstance(shape, Mapping):
                if data.get("key_person") == "CAPTAIN":
                    lines.append(f"    shape: Captain {shape.get('captain')} at {shape.get('captain_salary')}, "
                                 f"salary left {shape.get('salary_left')}")
                else:
                    stack = f"stack {shape.get('stack_team')} x{shape.get('stack_depth')}" if shape.get("stack_team") \
                        else "stack none"
                    lines.append(f"    shape: QB {shape.get('quarterback')}, {stack}, bring-back "
                                 f"{shape.get('bring_back')}, salary left {shape.get('salary_left')}")
                lines.append(f"    {row.get('no_tail_statistic')}")
            for label, field in (("rows without a roster", "rows_without_roster"),
                                 ("rows not scored (an ID the salary file lacks)", "rows_unscored")):
                if row.get(field):
                    lines.append(f"    {label}: {', '.join(row[field])}")
        if data.get("duplicate_entry_ids"):
            lines.append(f"  Entry IDs read twice: {', '.join(data['duplicate_entry_ids'])}")
    lines.append(f"  does not establish: {', '.join(data.get('does_not_establish') or [])}")
    return lines
