"""Showdown game theses (Session 23b, chunk P8, R33 and R34): the single-thesis build.

A thesis is a script Ben names for how one game plays out, written as a structure
every lineup built under it follows: a required Captain set (a kicker or a DST
allowed), per-team and per-position person counts, and exclusions. It travels as
`controls.theses` in an `nfl_showdown_portfolio_policy_v3` policy, which
`portfolio_policy.py` validates; this module holds the thesis itself and the pure
functions every layer applies to it: the MILP rows, the excluded rows, the roster
check the SD4 audit recomputes, and the backup-quarterback pool rule.

A thesis is a construction preference Ben chooses, never a model value and never
an evidence claim: its name is a label, it moves no projection, and nothing calls
it likely, calibrated or +EV. Unlike a cap it is never loosened (brief principle
6). A thesis that cannot be built is dropped and named; the relaxation ladder
carries its fields byte-for-byte to every rung it builds and drops it, by name,
only with the whole policy at rung 4.

Backup quarterbacks (R33). Under a thesis, every quarterback the current depth
evidence (`qb_depth_roles.py`) places behind his team's starter, or declares
unlisted, is out of the pool unless the thesis names him (`named_backup_
quarterbacks`, or its Captain set). A team the evidence does not declare has no
quarterback excluded: missing evidence is never permission to guess, and the gap
is named instead.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Collection, Mapping, Protocol, Sequence

from .contracts import SlateContract

THESIS_BUILD_VERSION = "showdown_single_thesis_sd3_v1"
# Session 23c: a policy v4 carries several theses, each with a `row_weight`; the rows are allotted by `allot_rows`.
THESIS_PORTFOLIO_VERSION = "showdown_thesis_portfolio_sd3_v1"
ACTIVE = "ACTIVE"
DROPPED = "DROPPED"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
ROSTER_PEOPLE = 6
THESIS_FIELDS = (
    "name",
    "teams",
    "captain_set",
    "team_bounds",
    "position_bounds",
    "excluded_people",
    "named_backup_quarterbacks",
)
THESIS_FIELDS_V4 = (*THESIS_FIELDS, "row_weight")
# A row weight is an allotment preference (a higher weight is more rows and nothing more), never a probability.
MAX_ROW_WEIGHT = 100
DOES_NOT_ESTABLISH = (
    "THAT_THE_THESIS_WILL_HAPPEN",
    "EV_ROI_OR_WIN_PROBABILITY",
    "LEVERAGE_NO_OWNERSHIP_INPUT_SO_LEVERAGE_IS_UNMEASURED",
    "CALIBRATION",
    "UPLOAD_CLEARANCE",
)


class Person(Protocol):
    underlying_id: str
    cpt_dk_id: str
    flex_dk_id: str

    def as_mapping(self) -> dict[str, str]: ...


@dataclass(frozen=True)
class CountBound:
    key: str  # a team code or a position
    minimum: int
    maximum: int

    def as_mapping(self, label: str) -> dict[str, object]:
        return {label: self.key, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class ShowdownThesis:
    name: str
    teams: tuple[str, ...]
    captain_set: tuple[Person, ...]
    team_bounds: tuple[CountBound, ...] = ()
    position_bounds: tuple[CountBound, ...] = ()
    excluded_people: tuple[Person, ...] = ()
    named_backup_quarterbacks: tuple[Person, ...] = ()
    status: str = ACTIVE
    # Why a DROPPED thesis could not be built, and each unavailable Captain with its source.
    dropped_reason: str | None = None
    unavailable_captains: tuple[tuple[str, str], ...] = ()
    # Session 23c (policy v4 only). `row_weight` is None for a v3 thesis, which has no weight, no allotment and writes
    # none of these. `rows` is its allotment of the policy's entries (0 once dropped), `effective_bounds` the policy's
    # declared structural bounds widened by the least step for this thesis's rows alone (a `StructuralBounds`), and
    # `widened` what moved (named in the relaxation record, never serialized: the audit recomputes it).
    row_weight: int | None = None
    rows: int = 0
    effective_bounds: Any = None
    widened: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return self.status == ACTIVE

    @property
    def captain_people(self) -> frozenset[str]:
        return frozenset(person.underlying_id for person in self.captain_set)

    @property
    def excluded_ids(self) -> frozenset[str]:
        return frozenset(person.underlying_id for person in self.excluded_people)

    def source_mapping(self) -> dict[str, object]:
        """The thesis as a v3 policy declares it; the ladder copies exactly this."""

        return {
            "name": self.name,
            "teams": list(self.teams),
            "captain_set": [person.as_mapping() for person in self.captain_set],
            "team_bounds": [bound.as_mapping("team") for bound in self.team_bounds],
            "position_bounds": [bound.as_mapping("position") for bound in self.position_bounds],
            "excluded_people": [person.as_mapping() for person in self.excluded_people],
            "named_backup_quarterbacks": [person.as_mapping() for person in self.named_backup_quarterbacks],
            # v4 only: a v3 thesis's bytes (and every rung built from one) must not move.
            **({"row_weight": self.row_weight} if self.row_weight is not None else {}),
        }

    def as_mapping(self) -> dict[str, object]:
        return {
            **self.source_mapping(),
            "status": self.status,
            "dropped_reason": self.dropped_reason,
            "unavailable_captains": [
                {"underlying_id": person, "source": source} for person, source in self.unavailable_captains
            ],
            **({"rows": self.rows,
                "effective_bounds": self.effective_bounds.as_mapping() if self.effective_bounds is not None else None}
               if self.row_weight is not None else {}),
        }


def allot_rows(weights: Sequence[tuple[str, int]], rows: int) -> dict[str, int]:
    """Allot `rows` entries across theses by largest remainder (Session 23c, brief principle 1).

    `weights` is the active theses in declared order, each with its positive integer `row_weight`. A thesis
    gets the floor of its proportional share, and the rows left go to the largest remainders, a tie to the
    earlier thesis: the order Ben declared is the priority. Pure, integer-only and deterministic, so the
    audit recomputes it from the normalized bytes. With fewer rows than theses the rows go to the largest
    remainders (with equal weights, the earliest theses one each) and the rest get none (the policy drops those
    and names them); it never invents a favourite.
    """

    if rows < 0 or not weights:
        raise ValueError("allot_rows needs at least one thesis and a non-negative row count")
    total = sum(weight for _name, weight in weights)
    if total <= 0 or any(weight <= 0 for _name, weight in weights):
        raise ValueError("allot_rows needs positive weights")
    allotment = {name: (rows * weight) // total for name, weight in weights}
    left = rows - sum(allotment.values())
    # Largest remainder first; `index` makes a tie go to the earlier thesis.
    order = sorted(
        range(len(weights)), key=lambda index: (-((rows * weights[index][1]) % total), index))
    for index in order[:left]:
        allotment[weights[index][0]] += 1
    return allotment


def admitted_quarterbacks(slate: SlateContract, thesis: ShowdownThesis) -> frozenset[str]:
    """The quarterbacks the thesis names: its `named_backup_quarterbacks` and any Captain who is a QB."""

    quarterbacks = {row.underlying_id for row in slate.players if row.position == "QB"}
    named = {person.underlying_id for person in thesis.named_backup_quarterbacks}
    return frozenset(named | (thesis.captain_people & quarterbacks))


def backup_quarterbacks(
    slate: SlateContract,
    thesis: ShowdownThesis | None,
    qb_depth_report: Mapping[str, object] | None,
    *,
    admitted_people: Collection[str] = (),
) -> tuple[frozenset[str], tuple[str, ...]]:
    """(people out of the pool, teams with quarterbacks the evidence does not declare).

    Read from the depth evidence's own `starters_by_team`: every other quarterback
    of a declared team is out unless the thesis names him. A team with no
    declaration keeps every quarterback and is returned as unevaluated.

    With no thesis (Session 53, R36: the default of every Showdown run) nobody is
    named, so every backup of a declared team is out. `starters_by_team` is the
    resolver's effective starter: a published starter the salary bytes flag
    unavailable has already been promoted over (R25), and a starter the run
    cannot select for another reason is refused there. The resolver checks him
    against the participation contract only. The offensive role gate runs after
    it. Since Session 54 it selects a starter with no usable history
    (`MISSING_HISTORY`), but a hash-bound fact that he is a backup or has an
    unresolved role change keeps him out, and with his backups out too that team
    has no selectable quarterback.

    `admitted_people` (Session 61, Classic) are people a named choice keeps in: a Classic policy's
    minimum, a validated construction judgment. Like a thesis's Captain set, each stays out of the
    returned set even when the evidence lists him behind a starter.
    """

    report = qb_depth_report if isinstance(qb_depth_report, Mapping) else {}
    starters = report.get("starters_by_team")  # empty when no evidence was supplied
    starters = starters if isinstance(starters, Mapping) else {}
    admitted = (admitted_quarterbacks(slate, thesis) if thesis is not None else frozenset()) | frozenset(admitted_people)
    by_team: dict[str, set[str]] = {}
    for row in slate.players:
        if row.position == "QB":
            by_team.setdefault(row.team, set()).add(row.underlying_id)
    out: set[str] = set()
    unevaluated: list[str] = []
    for team, people in sorted(by_team.items()):
        starter = starters.get(team)
        if not isinstance(starter, str):
            unevaluated.append(team)
            continue
        out.update(person for person in people if person != starter and person not in admitted)
    return frozenset(out), tuple(unevaluated)


def _percentage(count: int, total: int) -> float:
    return round(100 * count / total, 3) if total else 0.0


def thesis_portfolio_measures(
    slate: SlateContract,
    entries: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    allotment: Mapping[str, int],
    followed: Mapping[str, Sequence[str]],
    broken: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    """The review's numbers for a portfolio of theses (R34), recomputed from the rosters it is handed.

    `entries` is each Entry ID with its roster (Captain first) and the thesis it fills (`None` when none is
    assigned). `followed` is, per Entry ID, every thesis its roster follows, and `broken` the rules it breaks
    under the thesis it fills; whoever calls this decides those with `thesis_roster_violations`, so this
    function counts and never judges. It reports, per Entry ID, the thesis and whether the lineup follows it;
    each Captain's count and the theses it serves; every person in more than half the rows; the most rows one
    player's bad night sinks and the most rows one thesis sinks (each thesis is a bet that loses when its game
    does not happen); and the pairs of rows that share five or more people, which is how one core with a
    rotating Captain shows up (the same bet placed twice). It names no favourite and moves no number: a thesis is
    a choice, and with no ownership input leverage is unmeasured.
    """

    by_id = {row.dk_id: row for row in slate.players}
    total = len(entries)
    per_entry: dict[str, dict[str, object]] = {}
    by_thesis: dict[str, dict[str, object]] = {
        name: {"rows": int(rows), "entries": [], "captains": {}} for name, rows in allotment.items()}
    people_by_entry: dict[str, frozenset[str]] = {}
    captain_by_entry: dict[str, str] = {}
    combined: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    captain_theses: dict[str, Counter[str]] = {}
    filled: Counter[str] = Counter()
    for entry, roster, thesis in entries:
        rows = [by_id[str(dk_id).strip()] for dk_id in roster]
        people = frozenset(row.underlying_id for row in rows)
        captain = rows[0].underlying_id
        people_by_entry[entry], captain_by_entry[entry] = people, captain
        combined.update(people)
        captains[captain] += 1
        captain_theses.setdefault(captain, Counter())[thesis or "UNASSIGNED"] += 1
        rules = list(broken.get(entry, ()))
        per_entry[entry] = {
            "thesis": thesis, "follows": thesis is not None and not rules,
            "followed_by": list(followed.get(entry, ())), "broken_rules": rules}
        if thesis is not None:
            filled[thesis] += 1
            slot = by_thesis.setdefault(thesis, {"rows": 0, "entries": [], "captains": {}})
            slot["entries"].append(entry)
            slot["captains"][captain] = slot["captains"].get(captain, 0) + 1
    for slot in by_thesis.values():
        slot["captains"] = dict(sorted(slot["captains"].items()))
    top = max(combined.values(), default=0)
    thesis_top = max(filled.values(), default=0)
    entry_ids = [entry for entry, _roster, _thesis in entries]
    pairs = []
    for left_index, left in enumerate(entry_ids):
        for right in entry_ids[left_index + 1:]:
            shared = len(people_by_entry[left] & people_by_entry[right])
            if shared >= 5:
                pairs.append({
                    "entry_id_a": left, "entry_id_b": right, "shared_people": shared,
                    "captain_rotation": (shared == ROSTER_PEOPLE and captain_by_entry[left] != captain_by_entry[right])})
    return {
        "entries": per_entry,
        "by_thesis": dict(sorted(by_thesis.items())),
        "captains": {
            person: {"count": count, "share_percentage": _percentage(count, total),
                     "theses": dict(sorted(captain_theses[person].items()))}
            for person, count in sorted(captains.items(), key=lambda item: (-item[1], item[0]))},
        "distinct_captains": len(captains),
        "max_captain_share_percentage": _percentage(max(captains.values(), default=0), total),
        "people_in_more_than_half": [
            {"person": person, "rows": count, "share_percentage": _percentage(count, total)}
            for person, count in sorted(combined.items(), key=lambda item: (-item[1], item[0])) if 2 * count > total],
        "most_rows_one_player_sinks": {
            "rows": top, "share_percentage": _percentage(top, total),
            "people": sorted(person for person, count in combined.items() if count == top)},
        "most_rows_one_thesis_sinks": {
            "rows": thesis_top, "theses": sorted(name for name, count in filled.items() if count == thesis_top)},
        "same_core_pairs": pairs,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


def thesis_excluded_dk_ids(
    slate: SlateContract, thesis: ShowdownThesis, backups: frozenset[str] = frozenset()
) -> tuple[str, ...]:
    """The rows a thesis keeps out of every lineup built under it.

    The CPT row of everyone outside the Captain set (so the Captain comes from the
    set), and both rows of a thesis exclusion or a backup quarterback.
    """

    captains = thesis.captain_people
    gone = thesis.excluded_ids | backups
    return tuple(sorted(
        row.dk_id for row in slate.players
        if row.underlying_id in gone or (row.role == "CPT" and row.underlying_id not in captains)
    ))


def apply_thesis_rows(optimizer, slate: SlateContract, thesis: ShowdownThesis) -> None:
    """Bind the thesis's team and position counts as MILP rows on `optimizer`.

    A person holds one row of a lineup (Captain or FLEX), so counting selected rows
    of a team or a position counts its people.
    """

    for bound in thesis.team_bounds:
        optimizer.add_selected_count_bounds(
            [row.dk_id for row in slate.players if row.team == bound.key],
            minimum=bound.minimum, maximum=bound.maximum)
    for bound in thesis.position_bounds:
        optimizer.add_selected_count_bounds(
            [row.dk_id for row in slate.players if row.position == bound.key],
            minimum=bound.minimum, maximum=bound.maximum)


def thesis_violations(
    slate: SlateContract,
    roster_ids: Sequence[str],
    thesis: ShowdownThesis,
    backups: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Which rules of `thesis` a roster breaks, recomputed from `slate.players` (Captain first)."""

    by_id = {row.dk_id: row for row in slate.players}
    rows = [by_id[str(dk_id).strip()] for dk_id in roster_ids]
    found: list[str] = []
    if not rows or rows[0].underlying_id not in thesis.captain_people:
        found.append("captain_set")
    for bound in thesis.team_bounds:
        count = sum(1 for row in rows if row.team == bound.key)
        if not bound.minimum <= count <= bound.maximum:
            found.append(f"team_bounds.{bound.key}")
    for bound in thesis.position_bounds:
        count = sum(1 for row in rows if row.position == bound.key)
        if not bound.minimum <= count <= bound.maximum:
            found.append(f"position_bounds.{bound.key}")
    people = {row.underlying_id for row in rows}
    if people & thesis.excluded_ids:
        found.append("excluded_people")
    if people & backups:
        found.append("backup_quarterback")
    return tuple(found)
