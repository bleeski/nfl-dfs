"""Session 76: `within_contest_diversity_v2` on the committed PHI@CHI and MIN@NO files, against an exact floor.

The card's acceptance: no contest repeats a Captain when an arrangement avoids it, decided by an independent exact check on
the file, never by the search's own output. `_floor` below is that check. It knows nothing of the search: it reads only how
many lineups each key person has, how many movable rows each contest has and which key people its filled rows already hold.

- (a) The fewest contests holding a repeated key person: every set of multi-entry contests, largest first, is tested for
  whether its contests can all be clean at once.
- (b) and (b') Over every such largest set, the fewest lost key people and then same-key pairs: a min-cost flow whose unit
  costs are convex in a contest's count of one key person, so it is exact.
- The floor is itself checked against brute force over every arrangement on small instances with filled rows and one-entry
  contests. It covers one pool of movable rows, as every committed file and the offline wrapper have; the pools' own rule
  (lineups never cross pools) is pinned in `tests/test_contest_assignment.py`.

The lineup multiset, each person's exposure and the four portfolio washout proxies never move. Labels come from the slates'
own records: MIN@NO's `theses_by_entry.json` labels the file the v7 contest pass read, so labels follow that pass's mapping;
PHI@CHI's `theses_v3.json` follows `assignment_v4.json`'s mapping. Readings print beside each other with `-s`.
"""

from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import first_place_coverage as fpc

ROOT = Path(__file__).resolve().parents[1] / "data" / "inbox" / "slates"
PHI = ROOT / "phi-chi-sd-2026-09-28"
MIN = ROOT / "min-no-sd-2026-10-11"
FILES = {
    "phi-chi-v1": (PHI / "bdc34f2b-DKSalaries_119.csv", PHI / "5ed750e7-DKEntries_97.csv",
                   PHI / "DK_REVIEW_ENTRY_phi-chi-sd-v1.csv"),
    "phi-chi-v4": (PHI / "bdc34f2b-DKSalaries_119.csv", PHI / "5ed750e7-DKEntries_97.csv",
                   PHI / "DK_REVIEW_ENTRY_phi-chi-sd-v4.csv"),
    "min-no-v10": (MIN / "input" / "DKSalaries_169.csv", MIN / "input" / "DKEntries_141.csv",
                   MIN / "construction" / "DK_REVIEW_ENTRY_min-no-sd_final_v10.csv"),
}
POOL = "template"
V1, V2 = ca.CONTEST_ASSIGNMENT_VERSION_V1, ca.CONTEST_ASSIGNMENT_VERSION_V2


# ---------------------------------------------------------------- the independent floor


def _min_cost_flow(supply: dict[str, int], capacity: dict[str, int], edge_costs) -> int | None:
    """Route every unit of supply (keys) to capacity (contests); `edge_costs(key, contest)` lists each unit's cost in
    order (convex: never falling). Successive shortest paths on a small graph; None when not every unit fits."""

    keys, contests = sorted(supply), sorted(capacity)
    source, sink = 0, 1 + len(keys) + len(contests)
    graph: list[list[list[int]]] = [[] for _ in range(sink + 1)]

    def add(u: int, v: int, cap: int, cost: int) -> None:
        graph[u].append([v, cap, cost, len(graph[v])])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1])

    for i, key in enumerate(keys):
        add(source, 1 + i, supply[key], 0)
        for j, contest in enumerate(contests):
            for cost in edge_costs(key, contest):
                add(1 + i, 1 + len(keys) + j, 1, cost)
    for j, contest in enumerate(contests):
        add(1 + len(keys) + j, sink, capacity[contest], 0)
    total, units = 0, sum(supply.values())
    for _ in range(units):
        dist, prev = [None] * (sink + 1), [None] * (sink + 1)
        dist[source] = 0
        for _round in range(sink + 1):
            changed = False
            for u in range(sink + 1):
                if dist[u] is None:
                    continue
                for index, (v, cap, cost, _rev) in enumerate(graph[u]):
                    if cap > 0 and (dist[v] is None or dist[u] + cost < dist[v]):
                        dist[v], prev[v], changed = dist[u] + cost, (u, index), True
            if not changed:
                break
        if dist[sink] is None:
            return None
        v = sink
        while v != source:
            u, index = prev[v]
            graph[u][index][1] -= 1
            graph[v][graph[u][index][3]][1] += 1
            v = u
        total += dist[sink]
    return total


def _floor(movable_keys: list[str], slots: dict[str, int], fixed: dict[str, Counter]) -> tuple[int, int, int]:
    """(contests with a repeated key person, lost key people, same-key pairs): the fewest, in that order.

    `movable_keys` holds each movable lineup's key person; `slots` each contest's movable rows; `fixed` each contest's
    key people already in rows that never move."""

    supply = Counter(movable_keys)
    contests = sorted(set(slots) | set(fixed))
    sizes = {c: slots.get(c, 0) + sum(fixed.get(c, Counter()).values()) for c in contests}
    multi = [c for c in contests if sizes[c] > 1]
    big = (sum(sizes.values()) + 1) ** 2
    base_lost = sum(n - 1 for c in contests for n in fixed.get(c, Counter()).values() if n > 1)
    base_pairs = sum(n * (n - 1) // 2 for c in contests for n in fixed.get(c, Counter()).values())
    for clean_count in range(len(multi), -1, -1):
        best = None
        for clean in itertools.combinations(multi, clean_count):
            clean = set(clean)
            if any(n > 1 for c in clean for n in fixed.get(c, Counter()).values()):
                continue

            def costs(key: str, contest: str) -> list[int]:
                held = fixed.get(contest, Counter())[key]
                if contest in clean:
                    return [] if held else [0]
                units = min(supply[key], slots.get(contest, 0))
                return [big * (1 if t + held >= 1 else 0) + (t + held) for t in range(units)]

            cost = _min_cost_flow(dict(supply), {c: slots.get(c, 0) for c in contests}, costs)
            if cost is not None and (best is None or cost < best):
                best = cost
        if best is not None:
            return len(multi) - clean_count, base_lost + best // big, base_pairs + best % big
    raise AssertionError("no arrangement places every lineup")


def _measured(placed: dict[str, list[str]]) -> tuple[int, int, int]:
    dirty = lost = pairs = 0
    for keys in placed.values():
        counts = Counter(keys)
        dirty += any(n > 1 for n in counts.values())
        lost += sum(n - 1 for n in counts.values())
        pairs += sum(n * (n - 1) // 2 for n in counts.values())
    return dirty, lost, pairs


@pytest.mark.parametrize("seed", range(40))
def test_the_floor_equals_brute_force_over_every_arrangement(seed):
    rng = random.Random(seed)
    contests = [f"c{i}" for i in range(rng.randint(2, 4))]
    slots = {c: rng.randint(0, 3) for c in contests}
    # Up to two filled rows a contest, so a contest whose filled rows already repeat a key person is covered.
    fixed = {c: Counter(rng.choice("ABC") for _ in range(rng.randint(0, 2))) for c in contests}
    keys = [rng.choice("ABCD") for _ in range(sum(slots.values()))]
    order = [c for c in contests for _ in range(slots[c])]
    best = min(
        _measured({c: [k for slot, k in zip(order, perm) if slot == c] + list(fixed[c].elements()) for c in contests})
        for perm in set(itertools.permutations(keys)))
    assert _floor(keys, slots, fixed) == best


def test_the_floor_reads_the_perverse_case_with_a_clean_small_contest():
    # Contests of 2 and 6, Captains A x5, B, C, D: one contest dirty, 3 lost, 6 pairs (the plan's decision 2).
    assert _floor(list("AAAAABCD"), {"small": 2, "big": 6}, {}) == (1, 3, 6)


# ---------------------------------------------------------------- the committed files


def _read(name):
    salaries, template, entries = FILES[name]
    players = fpc.players_from_salary_csv(salaries)
    template_rows, state = fpc.read_entries_file(template, mode=ca.MODE_SHOWDOWN)
    assert state == fpc.READ
    filled = {entry_id for entry_id, _contest, roster in template_rows if roster is not None}
    rows, state = fpc.read_entries_file(entries, mode=ca.MODE_SHOWDOWN)
    assert state == fpc.READ and [r[0] for r in rows] == [r[0] for r in template_rows]
    entry_rows = [ca.EntryRow(e, c, tuple(r), None if e in filled else POOL) for e, c, r in rows]
    return players, entry_rows


def _labels(name, rows):
    """Each row's thesis, through the record of the contest pass that last moved lineups between Entry IDs."""

    if name == "min-no-v10":
        mapping = json.loads((MIN / "construction" / "contest_diversify_record_v7.json").read_text("utf-8"))
        theses = json.loads((MIN / "construction" / "theses_by_entry.json").read_text("utf-8"))
    else:
        mapping = json.loads((PHI / "assignment_v4.json").read_text("utf-8"))
        theses = json.loads((PHI / "theses_v3.json").read_text("utf-8"))
    by_entry = {entry: theses[source] for entry, source in mapping["mapping_entry_to_source_entry"].items()}
    assert set(by_entry) == {row.entry_id for row in rows}
    return {row.roster: by_entry[row.entry_id] for row in rows}


def _run(name, *, version=V2, restarts=None, labels=False):
    players, rows = _read(name)
    thesis_by_roster = _labels(name, rows) if labels else None
    out = ca.diversify(rows, mode=ca.MODE_SHOWDOWN, people=fpc.people(players), thesis_by_roster=thesis_by_roster,
                       restarts=restarts, time_limit_seconds=None, version=version)
    return players, rows, out


@pytest.fixture(scope="module")
def runs():
    cache = {}

    def get(name, *, version=V2, restarts=None, labels=False):
        if restarts is None:
            rows = _read(name)[1]
            restarts = ca.restarts_for([ca.Slot(r.entry_id, r.contest_id, r.pool) for r in rows])
        key = (name, version, restarts, labels)
        if key not in cache:
            cache[key] = _run(name, version=version, restarts=restarts, labels=labels)
        return cache[key]

    return get


def _placed_keys(players, rows, assignment):
    placed: dict[str, list[str]] = {}
    for row in rows:
        roster = assignment.get(row.entry_id, row.roster)
        placed.setdefault(row.contest_id, []).append(players[roster[0]].key)
    return placed


def _file_floor(players, rows):
    movable = [players[row.roster[0]].key for row in rows if row.pool is not None]
    slots = Counter(row.contest_id for row in rows if row.pool is not None)
    fixed = {}
    for row in rows:
        if row.pool is None:
            fixed.setdefault(row.contest_id, Counter())[players[row.roster[0]].key] += 1
    return _floor(movable, dict(slots), fixed)


def _washout(players, rosters):
    """The portfolio-wide washout proxies: max exposure, the top three's union, mean pairwise overlap, distinct people."""

    people = [frozenset(players[dk_id].key for dk_id in roster) for roster in rosters]
    uses = Counter(person for lineup in people for person in lineup)
    top = {person for person, _count in sorted(uses.items(), key=lambda item: (-item[1], item[0]))[:3]}
    pairs = list(itertools.combinations(people, 2))
    return (max(uses.values()), sum(1 for lineup in people if lineup & top),
            sum(len(a & b) for a, b in pairs) / len(pairs), len(uses))


@pytest.mark.parametrize("name", sorted(FILES))
@pytest.mark.parametrize("restarts", [None, ca.DEFAULT_RESTARTS], ids=["sized", "300"])
def test_v2_reaches_the_exact_floor_on_the_committed_files(runs, name, restarts):
    players, rows, out = runs(name, restarts=restarts)
    reached = _measured(_placed_keys(players, rows, out.assignments))
    assert reached == _file_floor(players, rows), name
    after = out.report["objective_after"]
    assert (after["contests_with_a_repeated_key_person"], after["lost_key_people"],
            after["same_key_person_pairs"]) == reached


def test_the_files_are_what_the_card_describes(runs):
    # PHI@CHI v1 repeated a Captain in all three seven-entry contests; v4 and every contest of v2's PHI@CHI are clean.
    # MIN@NO's 20-entry contest must repeat (20 entries, 9 Captains); every other contest can be clean.
    for name, floor, before in (("phi-chi-v1", (0, 0, 0), (3, 5, 6)), ("phi-chi-v4", (0, 0, 0), (0, 0, 0)),
                                ("min-no-v10", (1, 11, 14), (1, 12, 18))):
        players, rows, _out = runs(name)
        assert _file_floor(players, rows) == floor
        assert _measured(_placed_keys(players, rows, {})) == before, name


@pytest.mark.parametrize("name", sorted(FILES))
def test_v2_moves_only_which_entry_holds_which_lineup(runs, name):
    players, rows, out = runs(name)
    before = [row.roster for row in rows]
    after = [out.assignments.get(row.entry_id, row.roster) for row in rows]
    assert Counter(before) == Counter(after)
    exposure = lambda rosters: Counter(players[dk_id].key for roster in rosters for dk_id in roster)  # noqa: E731
    assert exposure(before) == exposure(after)
    assert _washout(players, before) == _washout(players, after)
    assert out.report["contest_assignment_version"] == V2


@pytest.mark.parametrize("name", sorted(FILES))
def test_v2_replays_byte_for_byte(runs, name):
    _players, _rows, first = runs(name)
    _players, _rows, second = _run(name)
    assert first.assignments == second.assignments
    strip = lambda report: json.dumps({k: v for k, v in report.items() if k != "seconds"}, sort_keys=True)  # noqa: E731
    assert strip(first.report) == strip(second.report)


def test_the_labels_bind_to_the_files_through_the_records():
    players, rows = _read("min-no-v10")
    names = {json.loads(p.read_text("utf-8"))["name"]: set(json.loads(p.read_text("utf-8"))["captain_set"])
             for p in (MIN / "construction" / "theses").glob("*.json")}
    labels = _labels("min-no-v10", rows)
    assert all(players[row.roster[0]].key in names[labels[row.roster]] for row in rows)
    # By Entry ID alone, without the v7 mapping, the labels would not fit the file.
    by_entry = json.loads((MIN / "construction" / "theses_by_entry.json").read_text("utf-8"))
    assert sum(players[row.roster[0]].key not in names[by_entry[row.entry_id]] for row in rows) == 15
    phi_players, phi_rows = _read("phi-chi-v4")
    assert len(_labels("phi-chi-v4", phi_rows)) == 36


@pytest.mark.parametrize("name", ["phi-chi-v4", "min-no-v10"])
def test_v1_and_v2_read_side_by_side(runs, name, capsys):
    players, rows, v1 = runs(name, version=V1)
    _players, _rows, v2 = runs(name)
    _players, _rows, v1_labelled = runs(name, version=V1, labels=True)
    _players, _rows, labelled = runs(name, labels=True)
    labels = _labels(name, rows)
    readings, objectives = {}, {}
    variants = (("v1", v1), ("v2", v2), ("v1 labels", v1_labelled), ("v2 labels", labelled))
    for label, out in variants:
        triples = [(r.entry_id, r.contest_id, tuple(out.assignments.get(r.entry_id, r.roster))) for r in rows]
        # Every reading is taken with the record's labels, so the three placements are compared on one measure.
        reading = fpc.reading(triples, mode=ca.MODE_SHOWDOWN, players=players,
                              thesis_by_entry={e: labels[r] for e, _c, r in triples})
        readings[label] = {row["contest_id"]: row for row in reading["contests"] if "statistics" in row}
        objectives[label] = ca.objective_total(ca.objectives_from_rosters(
            triples, mode=ca.MODE_SHOWDOWN, people=fpc.people(players), thesis_by_roster=labels))
    with capsys.disabled():
        print(f"\n[S76 {name}] per contest, both with the record's labels: entries, distinct Captains, repeated "
              "Captains, worst pair, mean shared")
        for contest in sorted(readings["v1"]):
            cells = []
            for label in ("v1 labels", "v2 labels"):
                row = readings[label][contest]
                stats = row["statistics"]
                repeats = "+".join(str(item["entries"]) for item in row["repeated_key_people"]) or "0"
                cells.append(f"{label}: {stats['distinct_key_people']} CPT, rep {repeats}, worst "
                             f"{stats['worst_pair_shared_people']}, mean {stats['mean_shared_people']}")
            print(f"  {contest} ({readings['v1'][contest]['entries']}): " + " | ".join(cells))
        for label, objective in objectives.items():
            print(f"  objective with the record's labels, {label}: {objective}")
    v1_keys = _measured(_placed_keys(players, rows, v1.assignments))
    v2_keys = _measured(_placed_keys(players, rows, v2.assignments))
    assert v2_keys <= v1_keys
    assert _measured(_placed_keys(players, rows, labelled.assignments)) == v2_keys
    assert v2_keys <= _measured(_placed_keys(players, rows, v1_labelled.assignments))
    assert objectives["v2 labels"]["same_thesis_pairs"] <= objectives["v1 labels"]["same_thesis_pairs"]
