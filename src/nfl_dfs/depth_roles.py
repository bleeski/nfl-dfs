"""P7: effective depth rank, for every skill position, from a published order.

The problem this exists to solve, measured on the 2026-09-20 Week 2 slate. A
depth chart is published about twice a day; the last snapshot before that
Sunday's 13:00 ET lock was 12:14:30Z, which is 08:14 ET. Official inactives
publish about 11:30 ET. **No depth chart is ever published between the inactive
announcement and lock**, so a rule that answers "who starts" out of the
published `pos_rank` alone is answering with a chart that predates the only news
that matters.

`qb_depth_roles.py` refused with `QB_DEPTH_STARTER_NOT_SELECTABLE` in exactly
that case and told the operator to refresh the chart. Ben ruled that refusal a
defect on 2026-09-20 (`R25`), because its stated remedy does not exist inside the
window where it is needed, and a gate no real source can ever clear is a defect
rather than a constraint.

What an effective rank is. The published order with everyone the **bound salary
bytes** flag unavailable removed from above, and the survivors renumbered from
1 in the same relative order. Nothing else. It is still an ordering, not a
measurement: it says who holds the role once the people ahead of him are known
not to be playing, and it says nothing about how much work the role gets.

Three bounds, carried from `R25` and binding rather than advisory:

- Availability is re-derived from the bound salary bytes on every call. The
  caller passes the people the salary file itself flags unavailable, so a
  supplied depth package can never widen the set; see the refusal
  `DEPTH_PROMOTION_OVER_AVAILABLE_PERSON`.
- Nobody becomes selectable who was not already. A promotion changes which
  available person holds a role; it never adds a person to the pool. This module
  returns ranks and never touches a candidate pool at all.
- Every promotion is reported, so a portfolio built on one says so.

Why the key is `(person, position)` and never the person alone. The published
file gives a person one row per position he appears at, and the return lines are
positions: `KR` and `PR` carry their own `pos_rank`. Measured on the
2026-09-20T12:14:30Z snapshot, Brian Robinson Jr. (ATL) is `KR` rank 1 and `RB`
rank 2, and Devin Duvernay (ARI) is `KR` 1, `PR` 1 and `WR` 6. Keying by person
and taking his best row would make Robinson Atlanta's lead back and Duvernay a
Cardinals WR1, on the strength of a kick-return line. This module reads only the
four skill positions and keys every rank by the position it was published at, so
a return line can never become an offensive role.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# The offensive skill positions this module ranks. `KR`, `PR`, `PK`, `P`, `LS`
# and every defensive and offensive-line abbreviation in the published
# vocabulary are deliberately absent: a rank at one of them is not a claim about
# who runs, catches or throws. The salary file's own position is what a rank is
# matched against downstream.
SKILL_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")
EFFECTIVE_RANK_VERSION = "effective_depth_rank_v1"
TRANSFORMATION_VERSION = "depth_chart_effective_rank_v1"
STARTER_RANK = 1


class DepthRoleError(ValueError):
    """A named fail-closed effective-depth-rank error."""

    def __init__(self, message: str, report: Mapping[str, object] | None = None):
        super().__init__(message)
        self.report = dict(report or {"evidence_state": "UNKNOWN", "blocker": message})


@dataclass(frozen=True)
class DepthRow:
    """One published depth-chart row, already bound to a slate person."""

    person: str
    team: str
    position: str
    published_rank: int
    player_name: str


@dataclass(frozen=True)
class EffectiveRank:
    """Where a person actually sits at one position, and why."""

    person: str
    team: str
    position: str
    published_rank: int
    effective_rank: int
    player_name: str
    promoted_over: tuple[str, ...]

    @property
    def promoted(self) -> bool:
        return self.effective_rank != self.published_rank

    def as_report(self) -> dict[str, object]:
        return {
            "person": self.person,
            "team": self.team,
            "position": self.position,
            "player_name": self.player_name,
            "published_rank": self.published_rank,
            "effective_rank": self.effective_rank,
            "promoted_over": list(self.promoted_over),
        }


def _validated_rows(rows: Iterable[DepthRow]) -> tuple[DepthRow, ...]:
    kept: list[DepthRow] = []
    seen: set[tuple[str, str, int]] = set()
    people: set[tuple[str, str]] = set()
    for row in rows:
        position = row.position.strip().upper()
        if position not in SKILL_POSITIONS:
            continue
        if row.published_rank < STARTER_RANK:
            raise DepthRoleError(
                f"DEPTH_PUBLISHED_RANK_INVALID:{row.person}:{position}:"
                f"{row.published_rank}"
            )
        team = row.team.strip().upper()
        key = (team, position, row.published_rank)
        if key in seen:
            raise DepthRoleError(
                f"DEPTH_DUPLICATE_PUBLISHED_RANK:team={team}:position={position}:"
                f"rank={row.published_rank}"
            )
        seen.add(key)
        person_key = (row.person, position)
        if person_key in people:
            raise DepthRoleError(
                f"DEPTH_PERSON_RANKED_TWICE:{row.person}:{position}"
            )
        people.add(person_key)
        kept.append(
            DepthRow(
                person=row.person,
                team=team,
                position=position,
                published_rank=row.published_rank,
                player_name=row.player_name,
            )
        )
    return tuple(kept)


def effective_depth_ranks(
    rows: Iterable[DepthRow],
    *,
    unavailable_people: Iterable[str],
) -> dict[tuple[str, str], EffectiveRank]:
    """Renumber each `(team, position)` order with the unavailable removed.

    `unavailable_people` is re-derived from the bound salary bytes by the
    caller. It is the only thing that may move a rank, and it can only ever
    remove someone from above: a person the salary file still shows as available
    is never stepped over.
    """

    unavailable = set(unavailable_people)
    ordered = _validated_rows(rows)
    grouped: dict[tuple[str, str], list[DepthRow]] = {}
    for row in ordered:
        grouped.setdefault((row.team, row.position), []).append(row)

    resolved: dict[tuple[str, str], EffectiveRank] = {}
    for key, group in grouped.items():
        group.sort(key=lambda row: row.published_rank)
        survivors = [row for row in group if row.person not in unavailable]
        removed_above: list[str] = []
        rank = 0
        for row in group:
            if row.person in unavailable:
                removed_above.append(row.person)
                continue
            rank += 1
            resolved[(row.person, row.position)] = EffectiveRank(
                person=row.person,
                team=row.team,
                position=row.position,
                published_rank=row.published_rank,
                effective_rank=rank,
                player_name=row.player_name,
                promoted_over=tuple(removed_above),
            )
        if survivors and rank != len(survivors):  # pragma: no cover - arithmetic guard
            raise DepthRoleError(
                f"DEPTH_RENUMBERING_LOST_A_PERSON:team={key[0]}:position={key[1]}"
            )
    return resolved


def effective_starter(
    ranks: Mapping[tuple[str, str], EffectiveRank],
    *,
    team: str,
    position: str,
) -> EffectiveRank | None:
    """The person holding rank 1 at one `(team, position)`, if anyone does."""

    team = team.strip().upper()
    position = position.strip().upper()
    for rank in ranks.values():
        if rank.team == team and rank.position == position and rank.effective_rank == STARTER_RANK:
            return rank
    return None


def promote_to_effective_starter(
    order: Sequence[tuple[int, str]],
    *,
    unavailable_people: Iterable[str],
    selectable_people: Iterable[str],
    team: str,
) -> tuple[str, tuple[str, ...]]:
    """Resolve one published order to the person who actually holds the role.

    `order` is `(published_rank, person)` pairs. Two separate sets, and the
    difference between them is the whole of `R25`'s first bound:

    - `unavailable_people` comes from the salary file's own Status bytes. Only
      these may be stepped over.
    - `selectable_people` is the participation contract's selectable set, which
      is the available people minus anything the *operator* excluded by hand.

    A rank-1 person the salary bytes still show as available is never promoted
    past, even when an operator exclusion has made him unselectable. Promotion is
    a fact about who is playing; an exclusion is a preference, and a preference
    must not be able to hand someone else the job. That case keeps a named
    refusal.
    """

    unavailable = set(unavailable_people)
    selectable = set(selectable_people)
    ranked = sorted(order)
    if not ranked:
        raise DepthRoleError(f"DEPTH_ORDER_EMPTY:{team}")
    stepped_over: list[str] = []
    for _rank, person in ranked:
        if person in selectable:
            return person, tuple(stepped_over)
        if person not in unavailable:
            raise DepthRoleError(
                f"DEPTH_PROMOTION_OVER_AVAILABLE_PERSON:team={team}:person={person}:"
                "the salary bytes still show this person as available, so nobody"
                " below him inherits the role; an operator exclusion is a"
                " preference and never promotes a backup"
            )
        stepped_over.append(person)
    raise DepthRoleError(
        f"DEPTH_NO_SELECTABLE_PERSON_AT_POSITION:team={team}:"
        f"order={[person for _rank, person in ranked]}:"
        "every person the published order names is unavailable or excluded"
    )
