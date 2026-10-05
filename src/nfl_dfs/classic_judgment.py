"""The Classic judgment pass inside the run (Session 61, R37, P9 part 2).

Until Session 61 the pass ran by hand after the engine (`docs/claude/working.md`
§ Classic judgment pass) and Week 4 needed three prompts from Ben to get there. This
module does the parts that need no judgment and hands the rest over as a short
report, one block per question Ben's rule asks:

- **Starters check.** Every depth-chart starting quarterback (the promoted backup of
  a DraftKings-unavailable starter included) is named with whether the pool scored
  him, and why not when it did not.
- **Injury rooms.** Each person DraftKings marks unavailable who held a share, who
  inherits it, the inheritors' prior points before and after Session 60's
  redistribution, and every salary. A person whose current role is unresolved never
  inherits (Session 60), so he is named separately: his prior still describes his old
  role.
- **Candidates.** A ranked list for the agent's research. It is never a selection and
  nothing here reads it back: the agent researches the names, and a person it decides
  to place goes in through the judgment input, which is a different, validated file.
- **Late-swap watch list.** Rostered people whose game locks after the earliest lock
  and for whom no official status row was supplied, with their DraftKings status.
  Official activity is not available for a later window at the early lock and late
  swap covers it (R37), so this is a list to re-check, not a blocker. It changes no
  `OFFICIAL_STATUS_*` code: certification still sees every one of them.

`classic_judgment_pass_v1` writes no model value and clears no gate. A candidate's
rank is the vacated room share and the salary-versus-prior gap, never a projection, and
`does_not_establish` says so in the report. The judgment input and its protected
placements (the second half of the session) live below the report functions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from .contracts import FrozenModel, SalaryPlayer, SlateContract
from .hashing import sha256_file
from .sources import PROHIBITED_HOSTS

JUDGMENT_PASS_VERSION = "classic_judgment_pass_v1"
DOES_NOT_ESTABLISH = (
    "THAT_ANY_LISTED_PERSON_IS_PLAYING_OR_STARTING",
    "OFFICIAL_ACTIVE_STATUS",
    "A_CURRENT_ROLE_FOR_ANY_CANDIDATE",
    "ANY_PROJECTION_EXPECTED_VALUE_OR_WIN_PROBABILITY",
    "THAT_A_RANK_IS_ANYTHING_BUT_THE_ORDER_TO_RESEARCH_IN",
)

# The shares a vacated room is measured in. A touch share is carries plus targets; it is a share the
# model already holds, never points, so the rank below writes no number.
TOUCH_FIELDS = ("carry_share", "target_share")

# Candidate sources, in the order they rank. The first is the one the engine cannot price: a
# vacancy exists in his room and his current role is unresolved, so Session 60 left his prior alone.
SOURCE_UNRESOLVED_IN_VACATED_ROOM = "UNRESOLVED_ROLE_IN_VACATED_ROOM"
SOURCE_UNRESOLVED_TRANSFER = "UNRESOLVED_TRANSFER_PRIOR"
SOURCE_ABSORBER = "ABSORBER_OF_A_VACATED_SHARE"
SOURCE_SALARY_ABOVE_PRIOR = "SALARY_RANK_ABOVE_PRIOR_RANK"
PRICED_ABOVE_PRIOR_LIMIT = 10
SOURCE_TIER = {
    SOURCE_UNRESOLVED_IN_VACATED_ROOM: 0,
    SOURCE_UNRESOLVED_TRANSFER: 1,
    SOURCE_ABSORBER: 2,
    SOURCE_SALARY_ABOVE_PRIOR: 3,
}
# What the run cannot read. Named, never guessed: the frozen depth chart is read for quarterbacks only
# and matching a name to a DraftKings row is a fuzzy join the engine never uses.
SOURCES_UNEVALUATED = {
    "DEPTH_RANK_ONE_AT_POSITION": (
        "the engine reads the frozen depth chart for quarterbacks only; a running back, receiver or tight end"
        " listed first at his position is a research step"
    ),
}

_ROLE_GATE_PREFIX = "OFFENSIVE_ROLE_GATE_EXCLUDED"


def _people(slate: SlateContract) -> dict[str, SalaryPlayer]:
    """The one DraftKings row of each person (Classic has exactly one)."""

    rows: dict[str, SalaryPlayer] = {}
    for player in slate.players:
        rows.setdefault(player.underlying_id, player)
    return rows


def _coverage_by_person(pool_coverage: Mapping[str, object] | None) -> dict[str, Mapping[str, object]]:
    return {
        str(row["person"]): row
        for row in (dict(pool_coverage or {}).get("people") or ())
        if isinstance(row, Mapping) and row.get("person")
    }


def _points(value: object) -> float | None:
    return round(float(value), 3) if isinstance(value, (int, float)) else None


def starters_check(
    slate: SlateContract,
    *,
    qb_depth_report: Mapping[str, object] | None,
    pool_coverage: Mapping[str, object] | None,
    prior_points: Mapping[str, float],
) -> dict[str, object]:
    """Name each team's effective starting quarterback and whether the pool scored him.

    `starters_by_team` is the depth resolver's effective starter (R25 has promoted over a
    DraftKings-unavailable one), so a promoted backup is the starter here and the unavailable
    published starter is not. A team the evidence does not order is `unevaluated`, never guessed.
    """

    report = qb_depth_report if isinstance(qb_depth_report, Mapping) else {}
    starters = report.get("starters_by_team")
    starters = starters if isinstance(starters, Mapping) else {}
    promotions = {
        str(item.get("team")): item
        for item in (report.get("effective_starter_promotions") or ())
        if isinstance(item, Mapping)
    }
    people, coverage = _people(slate), _coverage_by_person(pool_coverage)
    qb_teams = sorted({row.team for row in slate.players if row.position == "QB"})
    rows: list[dict[str, object]] = []
    unevaluated: list[str] = []
    for team in qb_teams:
        person = starters.get(team)
        if not isinstance(person, str) or person not in people:
            unevaluated.append(team)
            continue
        row, cover = people[person], coverage.get(person, {})
        reason = str(cover.get("reason") or "NOT_IN_POOL_COVERAGE")
        scored = person in prior_points
        promotion = promotions.get(team)
        rows.append({
            "team": team,
            "person": person,
            "name": row.name,
            "dk_id": row.dk_id,
            "salary": int(row.salary),
            "dk_status": str(cover.get("dk_status") or ""),
            "scored": scored,
            "selectable": reason == "SELECTABLE" and scored,
            "prior_points": _points(prior_points.get(person)),
            "reason": reason,
            "smallest_evidence_action": str(cover.get("smallest_evidence_action") or ""),
            "promoted_over": list(promotion.get("promoted_over") or ()) if promotion else [],
        })
    return {
        "evidence": "SUPPLIED" if starters or report.get("schema_version") else "NOT_SUPPLIED",
        "basis": "QB_DEPTH_EVIDENCE_EFFECTIVE_STARTERS_NOT_OFFICIAL_ACTIVE_STATUS",
        "starters": rows,
        "missing_from_scored_pool": [row for row in rows if not row["selectable"]],
        "unevaluated_teams": unevaluated,
        "does_not_establish": ["THAT_THE_STARTER_IS_PLAYING", "OFFICIAL_ACTIVE_STATUS"],
    }


def _findings_by_person(offensive_report: Mapping[str, object] | None) -> dict[str, Mapping[str, object]]:
    return {
        str(item["person"]): item
        for item in (dict(offensive_report or {}).get("findings") or ())
        if isinstance(item, Mapping) and item.get("person")
    }


def injury_rooms(
    slate: SlateContract,
    *,
    redistribution: Mapping[str, object] | None,
    prior_before: Mapping[str, float] | None,
    prior_after: Mapping[str, float],
    offensive_report: Mapping[str, object] | None,
    pool_coverage: Mapping[str, object] | None,
) -> dict[str, object]:
    """Each room a DraftKings-unavailable person left: who vacated, who inherits, before and after.

    `prior_before` is the pool scored from the model as it stood before Session 60's
    redistribution, by the same pipeline; None when the run could not compute it or nothing moved,
    in which case an inheritor's `prior_points_before` is None and the report says so.
    """

    redistribution = dict(redistribution or {})
    people, coverage = _people(slate), _coverage_by_person(pool_coverage)
    findings = _findings_by_person(offensive_report)
    before = dict(prior_before or {})

    def person_entry(person: str) -> dict[str, object]:
        row, cover, finding = people[person], coverage.get(person, {}), findings.get(person, {})
        return {
            "person": person,
            "name": row.name,
            "team": row.team,
            "position": row.position,
            "dk_id": row.dk_id,
            "salary": int(row.salary),
            "dk_status": str(cover.get("dk_status") or ""),
            "history_state": finding.get("history_state"),
            "role_state": finding.get("state"),
            "selection_action": finding.get("selection_action"),
        }

    rooms: dict[tuple[str, str], dict[str, object]] = {}

    def room(team: str, position: str) -> dict[str, object]:
        return rooms.setdefault((team, position), {
            "team": team,
            "position": position,
            "vacated": {},
            "vacated_total_by_field": defaultdict(float),
            "inheritors": {},
            "unallocated_by_field": defaultdict(float),
            "not_inheriting_unresolved_role": [],
        })

    for move in redistribution.get("moves") or ():
        target = room(str(move["team"]), str(move["position"]))
        field = str(move["field"])
        target["vacated_total_by_field"][field] += float(move.get("vacated_total") or 0.0)
        target["unallocated_by_field"][field] += float(move.get("unallocated") or 0.0)
        for vacated in move.get("vacated") or ():
            person = str(vacated["person"])
            if person not in people:
                continue
            slot = target["vacated"].setdefault(person, {
                **person_entry(person),
                "triggered_by": list(vacated.get("triggered_by") or ()),
                "share_by_field": {},
            })
            slot["share_by_field"][field] = round(float(vacated.get("share") or 0.0), 6)
        for absorbed in move.get("absorbed") or ():
            person = str(absorbed["person"])
            if person not in people:
                continue
            slot = target["inheritors"].setdefault(person, {
                **person_entry(person),
                "share_gained_by_field": {},
                "prior_points_before": _points(before.get(person)),
                "prior_points_after": _points(prior_after.get(person)),
            })
            slot["share_gained_by_field"][field] = round(float(absorbed.get("gained") or 0.0), 6)
            slot["superseded_by_declared_allocation"] = bool(move.get("superseded_by_declared_allocation"))
    for person in redistribution.get("not_absorbing_unresolved_current_role") or ():
        if person not in people:
            continue
        row = people[person]
        if (row.team, row.position) in rooms:
            rooms[(row.team, row.position)]["not_inheriting_unresolved_role"].append({
                **person_entry(person),
                "prior_points": _points(prior_after.get(person)),
                "why": "HIS_CURRENT_ROLE_IS_UNRESOLVED_SO_HIS_PRIOR_STILL_DESCRIBES_HIS_OLD_ROLE",
            })

    out: list[dict[str, object]] = []
    for key in sorted(rooms):
        item = rooms[key]
        inheritors = sorted(item["inheritors"].values(), key=lambda entry: (
            -sum(entry["share_gained_by_field"].values()), str(entry["name"])))
        for entry in inheritors:
            before_points, after_points = entry["prior_points_before"], entry["prior_points_after"]
            entry["repriced_by_redistribution"] = (
                before_points is not None and after_points is not None and after_points > before_points)
        out.append({
            "team": item["team"],
            "position": item["position"],
            "vacated": sorted(item["vacated"].values(), key=lambda entry: str(entry["name"])),
            "vacated_total_by_field": {
                field: round(value, 6) for field, value in sorted(item["vacated_total_by_field"].items())},
            "inheritors": inheritors,
            "not_inheriting_unresolved_role": sorted(
                item["not_inheriting_unresolved_role"], key=lambda entry: str(entry["name"])),
            "unallocated_by_field": {
                field: round(value, 6) for field, value in sorted(item["unallocated_by_field"].items())
                if value > 0},
        })
    return {
        "rule": redistribution.get("rule"),
        "transformation_version": redistribution.get("transformation_version"),
        "applied": bool(redistribution.get("applied")),
        "prior_points_before_basis": (
            "SAME_SCORING_PIPELINE_ON_THE_MODEL_BEFORE_THE_REDISTRIBUTION" if before
            else "NOT_COMPUTED_NOTHING_MOVED_OR_THE_COUNTERFACTUAL_COULD_NOT_RUN"),
        "rooms": out,
        "quarterbacks_left_to_the_depth_evidence": [
            dict(item) for item in redistribution.get("quarterbacks_left_to_the_depth_evidence") or ()],
        "does_not_establish": ["THAT_ANY_INHERITOR_RECEIVES_THE_WORKLOAD", "OFFICIAL_ACTIVE_STATUS",
                               "A_CURRENT_ROLE"],
    }


def candidates(
    slate: SlateContract,
    *,
    rooms: Mapping[str, object],
    offensive_report: Mapping[str, object] | None,
    divergence: Iterable[Mapping[str, object]],
    prior_before: Mapping[str, float] | None,
    prior_after: Mapping[str, float],
    pool_coverage: Mapping[str, object] | None,
    protected: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """People whose role may have changed today while their prior still describes the old one.

    Three sources, each a fact the run already holds (`SOURCE_TIER` is their order): a person
    Session 60 could not reprice because his current role is unresolved and a vacancy exists in his
    room; a transfer carried on his old team's share; and the absorbers of a vacated share, with
    the prior they now have. A person on several sources lists them all and ranks by his best, and
    one whom DraftKings also prices far above his prior carries that tag. Offensive people priced
    far above their prior with none of those facts are a short list of their own
    (`priced_above_prior_only`), not candidates. Within a tier the larger vacated room share
    comes first, then the larger salary-versus-prior gap, then salary, then name, so the order is
    deterministic and writes no number.

    Never a selection. A person DraftKings marks unavailable, an official inactive row or an operator
    exclusion is not listed: nothing can place him. A person the role gate left out is listed with
    the finding and `placeable` false, since the judgment input places people in the scored pool only.
    """

    people, coverage = _people(slate), _coverage_by_person(pool_coverage)
    findings = _findings_by_person(offensive_report)
    before = dict(prior_before or {})
    protected_people = set(dict(protected or {}))
    found: dict[str, dict[str, object]] = {}
    dropped: dict[str, str] = {}

    def entry(person: str) -> dict[str, object] | None:
        cover = coverage.get(person)
        if person not in people or cover is None:
            return None
        reason = str(cover.get("reason") or "")
        if reason != "SELECTABLE" and not reason.startswith(_ROLE_GATE_PREFIX):
            dropped[person] = reason
            return None
        if person not in found:
            row, finding = people[person], findings.get(person, {})
            in_pool = reason == "SELECTABLE"
            found[person] = {
                "person": person,
                "name": row.name,
                "team": row.team,
                "position": row.position,
                "dk_id": row.dk_id,
                "salary": int(row.salary),
                "dk_status": str(cover.get("dk_status") or ""),
                "sources": [],
                "history_state": finding.get("history_state"),
                "role_state": finding.get("state"),
                "selection_action": finding.get("selection_action"),
                "prior_points_before": _points(before.get(person)),
                "prior_points_after": _points(prior_after.get(person)),
                "repriced_by_redistribution": False,
                "room_vacated_touch_share": None,
                "room_vacated_names": [],
                "salary_rank_divergence_places": None,
                "placeable": in_pool,
                "placement": "IN_THE_SCORED_POOL" if in_pool else reason,
                "already_protected": person in protected_people,
            }
        return found[person]

    room_touch: dict[tuple[str, str], float] = {}
    room_names: dict[tuple[str, str], list[str]] = {}
    for item in rooms.get("rooms") or ():
        key = (str(item["team"]), str(item["position"]))
        totals = dict(item.get("vacated_total_by_field") or {})
        room_touch[key] = round(sum(float(totals.get(field, 0.0)) for field in TOUCH_FIELDS), 6)
        room_names[key] = [str(vacated["name"]) for vacated in item.get("vacated") or ()]
        for inheritor in item.get("inheritors") or ():
            slot = entry(str(inheritor["person"]))
            if slot is not None:
                slot["sources"].append(SOURCE_ABSORBER)
                slot["repriced_by_redistribution"] = bool(inheritor.get("repriced_by_redistribution"))
        for unresolved in item.get("not_inheriting_unresolved_role") or ():
            slot = entry(str(unresolved["person"]))
            if slot is not None:
                slot["sources"].append(SOURCE_UNRESOLVED_IN_VACATED_ROOM)
    for person, finding in sorted(findings.items()):
        if finding.get("state") == "TRANSFER_PRIOR_UNVERIFIED":
            slot = entry(person)
            if slot is not None:
                slot["sources"].append(SOURCE_UNRESOLVED_TRANSFER)
    # DraftKings pricing a person far above his prior is a tag on a candidate another source found, and a
    # short list of its own. On its own it is not a candidate: on a real slate it names dozens of people
    # (every expensive defense, every back whose prior is low), and a long list is not a research order.
    divergence_places: dict[str, int] = {}
    priced_above_prior: list[dict[str, object]] = []
    for item in divergence:
        person = str(item.get("person") or "")
        places = int(item.get("divergence_places") or 0)
        divergence_places[person] = places
        if person in found:
            found[person]["sources"].append(SOURCE_SALARY_ABOVE_PRIOR)
        elif (
            str(item.get("position")) in {"QB", "RB", "WR", "TE"}
            and str(coverage.get(person, {}).get("reason")) == "SELECTABLE"
        ):
            priced_above_prior.append({
                "person": person,
                "name": item.get("name"),
                "team": item.get("team"),
                "position": item.get("position"),
                "dk_id": item.get("dk_id"),
                "salary": item.get("salary"),
                "prior_points": item.get("prior_points"),
                "divergence_places": places,
                "history_state": item.get("history_state"),
            })
    priced_above_prior.sort(key=lambda row: (-int(row["divergence_places"]), -int(row["salary"] or 0), str(row["name"])))
    for person, slot in found.items():
        slot["sources"] = sorted(set(slot["sources"]), key=lambda source: SOURCE_TIER[source])
        key = (str(slot["team"]), str(slot["position"]))
        if key in room_touch:
            slot["room_vacated_touch_share"] = room_touch[key]
            slot["room_vacated_names"] = room_names[key]
        slot["salary_rank_divergence_places"] = divergence_places.get(person)

    def rank_key(slot: Mapping[str, object]):
        return (
            SOURCE_TIER[slot["sources"][0]],
            -(slot["room_vacated_touch_share"] or 0.0),
            -(slot["salary_rank_divergence_places"] or 0),
            -int(slot["salary"]),
            str(slot["name"]),
        )

    ranked = sorted((slot for slot in found.values() if slot["sources"]), key=rank_key)
    for position, slot in enumerate(ranked, start=1):
        slot["rank"] = position
        slot["research"] = _research_question(slot)
    return {
        "kind": "FOR_THE_AGENTS_RESEARCH_NOT_A_SELECTION",
        "ranked_by": "SOURCE_TIER_THEN_VACATED_ROOM_TOUCH_SHARE_THEN_SALARY_RANK_GAP_THEN_SALARY_THEN_NAME",
        "candidates": ranked,
        "priced_above_prior_only": priced_above_prior[:PRICED_ABOVE_PRIOR_LIMIT],
        "sources_unevaluated": dict(SOURCES_UNEVALUATED),
        "not_listed_because_nothing_can_place_them": dict(sorted(dropped.items())),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


def _research_question(slot: Mapping[str, object]) -> str:
    name, team, position = slot["name"], slot["team"], slot["position"]
    sources = set(slot["sources"])
    vacated = ", ".join(slot["room_vacated_names"]) or "a teammate"
    if SOURCE_UNRESOLVED_IN_VACATED_ROOM in sources:
        return (f"Does {name} take {vacated}'s {position} workload for {team}? The engine did not move it to him:"
                f" his role is unresolved ({slot['history_state']}), so his prior is still his old role's.")
    if SOURCE_UNRESOLVED_TRANSFER in sources:
        return (f"What is {name}'s role at {team}? His prior is his old team's share, carried and unverified"
                f" ({slot['history_state']}).")
    if SOURCE_ABSORBER in sources:
        return (f"Does {name} get the {position} workload {vacated} leaves at {team}? The engine moved it to him by"
                " rule; confirm the room before relying on the new prior.")
    return f"What changed for {name} at {team}? His prior and his salary disagree."


def late_swap_watch(
    slate: SlateContract,
    *,
    lineups: Sequence[object],
    pool_coverage: Mapping[str, object] | None,
    official_statuses: Mapping[str, str] | None,
) -> dict[str, object]:
    """Rostered people in a later window with no official status row, for late swap (R37).

    Additive only: the existing `OFFICIAL_STATUS_*` coverage and its certification effect are
    untouched. The window is the game's lock; "later" means after the earliest lock in the salary
    file. Each person carries his DraftKings status and how many rows he is in.
    """

    people, coverage = _people(slate), _coverage_by_person(pool_coverage)
    by_id = {row.dk_id: row for row in slate.players}
    statuses = dict(official_statuses or {})
    covered = {row.underlying_id for row in slate.players if row.dk_id in statuses}
    earliest = min((row.lock_at for row in slate.players), default=None)
    rows_by_person: dict[str, int] = defaultdict(int)
    for lineup in lineups:
        for person in {by_id[str(dk_id)].underlying_id for dk_id in getattr(lineup, "roster", ())}:
            rows_by_person[person] += 1
    watch: list[dict[str, object]] = []
    early_without_row: list[dict[str, object]] = []
    for person, count in rows_by_person.items():
        if person in covered:
            continue
        row = people[person]
        entry = {
            "person": person,
            "name": row.name,
            "team": row.team,
            "position": row.position,
            "dk_id": row.dk_id,
            "game_id": row.game_id,
            "lock_at": row.lock_at.isoformat(),
            "dk_status": str(coverage.get(person, {}).get("dk_status") or ""),
            "rows": count,
        }
        (watch if earliest is not None and row.lock_at > earliest else early_without_row).append(entry)

    def order(item):
        return (item["lock_at"], -int(item["rows"]), str(item["name"]))

    return {
        "kind": "LATE_SWAP_WATCH_LIST_NOT_A_BLOCKER",
        "earliest_lock_at": earliest.isoformat() if earliest is not None else None,
        "later_window_without_official_row": sorted(watch, key=order),
        "early_window_without_official_row": sorted(early_without_row, key=order),
        "note": (
            "A later window has no posted inactive list at the early lock; late swap re-checks these people once"
            " their window's inactives post. The early-window people without a row are the open gap: confirm"
            " them against the posted lists. OFFICIAL_STATUS_* still stops certification for every one of them."
        ),
        "does_not_establish": ["OFFICIAL_ACTIVE_STATUS", "THAT_ANY_LISTED_PERSON_IS_PLAYING"],
    }


def build_judgment_pass(
    slate: SlateContract,
    *,
    lineups: Sequence[object],
    selection: Mapping[str, object],
    prior_points: Mapping[str, float],
    redistribution: Mapping[str, object] | None,
    pool_coverage: Mapping[str, object] | None,
    official_statuses: Mapping[str, str] | None,
    protected: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """The whole report block, from what the run already holds. Writes no number, reads no gate."""

    offensive = selection.get("offensive_roles") if isinstance(selection.get("offensive_roles"), Mapping) else {}
    before = selection.get("prior_points_before_redistribution")
    before = before if isinstance(before, Mapping) else None
    rooms = injury_rooms(
        slate, redistribution=redistribution, prior_before=before, prior_after=prior_points,
        offensive_report=offensive, pool_coverage=pool_coverage)
    divergence = ((selection.get("salary_rank_divergence") or {}).get("findings") or ()
                  if isinstance(selection.get("salary_rank_divergence"), Mapping) else ())
    decision = selection.get("construction_judgment") if isinstance(selection.get("construction_judgment"), Mapping) else {}
    delivery = decision.get("delivery") if isinstance(decision.get("delivery"), Mapping) else {}
    delivered = dict(delivery.get("delivered_rows") or {})
    placed = [
        {
            "person": row["person"], "dk_id": row["dk_id"], "name": row["name"], "min_rows": row["min_rows"],
            "delivered_rows": list(delivered.get(row["person"], [])),
            "met": bool((delivery.get("met") or {}).get(row["person"], False)),
        }
        for row in decision.get("placements") or ()
        if row.get("decision") == "ACCEPTED"
    ]
    return {
        "version": JUDGMENT_PASS_VERSION,
        # The people a redeploy never removes (Session 62's `--protect`): what the run actually placed.
        "protected_people": placed,
        "starters_check": starters_check(
            slate, qb_depth_report=selection.get("qb_depth_roles"), pool_coverage=pool_coverage,
            prior_points=prior_points),
        "injury_rooms": rooms,
        "candidates": candidates(
            slate, rooms=rooms, offensive_report=offensive, divergence=divergence, prior_before=before,
            prior_after=prior_points, pool_coverage=pool_coverage, protected=protected),
        "late_swap_watch": late_swap_watch(
            slate, lineups=lineups, pool_coverage=pool_coverage, official_statuses=official_statuses),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


# ---------------------------------------------------------------------------
# The construction judgment input (Session 61, R37)
# ---------------------------------------------------------------------------
#
# `nfl_classic_construction_judgment_v1` is the Classic schema of the construction judgment Session
# 52 specified for Showdown (`nfl_construction_judgment_v1`, never built: Session 52 is Deferred, and
# its card says Classic needs its own schema version). One JSON names the people the thesis build
# must roster, by exact DraftKings ID, with a row minimum, a reason, sources and an author, bound to
# the salary file's SHA-256. It is a *construction* input: it writes no model value, it clears no
# gate, and it cannot override anything that says a person is not playing. The agent decides who to
# name after researching the candidate list above; the engine only places him, and says so.
#
# A malformed or mis-bound FILE is dropped by name and the run goes on (`CONSTRUCTION_JUDGMENT_DROPPED`,
# a `P` limitation): the minimum is a construction preference, the lock-clock ruling relaxes those,
# and the worst outcome is no lineup. A single PLACEMENT the run cannot honour is refused by name and
# the rest are applied.

CONSTRUCTION_JUDGMENT_VERSION = "nfl_classic_construction_judgment_v1"
MAX_PLACEMENTS = 12
MIN_REASON_CHARS = 12
# Free text in the file reaches hash-bound artifacts and a limitation string, so it is bounded and plain.
MAX_AUTHOR_CHARS = 80
MAX_REASON_CHARS = 600
MAX_NAME_CHARS = 120
MAX_URI_CHARS = 500
# `sources.PROHIBITED_HOSTS` names the exact hosts; research never uses them or any subdomain of them.
_PROHIBITED_DOMAINS = frozenset(host.removeprefix("www.") for host in PROHIBITED_HOSTS)
JUDGMENT_DOES_NOT_ESTABLISH = (
    "THAT_ANY_NAMED_PERSON_IS_PLAYING_OR_HAS_THE_ROLE_THE_REASON_GIVES",
    "A_CURRENT_ROLE_OR_ANY_MODEL_VALUE_FOR_A_NAMED_PERSON",
    "OFFICIAL_ACTIVE_STATUS",
    "THAT_PLACING_A_PERSON_RAISES_ANY_PAYOUT",
)
# Findings the judgment never overrides. Participation precedence is checked first (DraftKings status,
# an operator or official exclusion); these are the role gate's own.
NEVER_OVERRIDDEN_FINDINGS = frozenset({
    "OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE",
    "PARTICIPATION_PRECEDENCE",
})


class ConstructionJudgmentError(ValueError):
    """A named reason the judgment file as a whole cannot be used; the run drops it and goes on."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def _plain_text(value: str, *, label: str) -> str:
    """Text a person or an agent wrote, kept to one plain line: no control characters, whitespace collapsed."""

    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value.replace("\n", " ").replace("\t", " ")):
        raise ValueError(f"{label} holds a control character")
    return " ".join(value.split())


class JudgmentSource(FrozenModel):
    uri: str = Field(min_length=1, max_length=MAX_URI_CHARS)
    observed_at: datetime

    @field_validator("uri")
    @classmethod
    def https_on_an_allowed_host(cls, value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None:
            raise ValueError("a source is an HTTPS URI without credentials")
        if any(host == banned or host.endswith("." + banned) for banned in _PROHIBITED_DOMAINS):
            raise ValueError(f"{host} is a host the engine prohibits; research never uses it")
        return value

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class JudgmentPlacement(FrozenModel):
    dk_id: str = Field(pattern=r"^[0-9]+$")
    name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    min_rows: int = Field(ge=1, le=500)
    reason: str
    sources: tuple[JudgmentSource, ...] = Field(min_length=1, max_length=8)

    @field_validator("reason")
    @classmethod
    def a_stated_reason(cls, value: str) -> str:
        text = _plain_text(value, label="a reason")
        if not MIN_REASON_CHARS <= len(text) <= MAX_REASON_CHARS:
            raise ValueError(f"a reason is {MIN_REASON_CHARS} to {MAX_REASON_CHARS} characters of plain text")
        return text

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()


class ConstructionJudgmentFile(FrozenModel):
    schema_version: Literal["nfl_classic_construction_judgment_v1"]
    salary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    author: str = Field(min_length=1, max_length=MAX_AUTHOR_CHARS)
    authored_at: datetime
    placements: tuple[JudgmentPlacement, ...] = Field(min_length=1, max_length=MAX_PLACEMENTS)

    @field_validator("author")
    @classmethod
    def a_plain_author(cls, value: str) -> str:
        text = _plain_text(value, label="an author")
        if not text:
            raise ValueError("an author is named")
        return text

    @field_validator("authored_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("authored_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def distinct_people(self) -> "ConstructionJudgmentFile":
        ids = [placement.dk_id for placement in self.placements]
        if len(set(ids)) != len(ids):
            raise ValueError("a DraftKings ID is named once")
        return self


@dataclass(frozen=True)
class ConstructionJudgment:
    """A validated file: its bytes' hash, its document, and the slate rows its IDs bind to."""

    path: str
    sha256: str
    document: ConstructionJudgmentFile
    person_by_dk_id: Mapping[str, str]

    def as_report(self) -> dict[str, object]:
        # The base name and the hash, never the path: the report lands in hash-bound artifacts that are
        # run-ID independent, and a run-slate snapshot lives under `data/runs/<run_id>/inputs`.
        return {
            "file_name": Path(self.path).name,
            "sha256": self.sha256,
            "schema_version": self.document.schema_version,
            "salary_sha256": self.document.salary_sha256,
            "author": self.document.author,
            "authored_at": self.document.authored_at.isoformat(),
            "placements_named": len(self.document.placements),
        }


def load_construction_judgment(
    path: str | Path, slate: SlateContract, *, as_of: datetime
) -> ConstructionJudgment:
    """Read, validate and bind a judgment file; any failure is a `ConstructionJudgmentError`.

    Bound to the slate: the file names the salary SHA-256 it was written for, and each ID must be
    that salary file's own row, with the name the file echoes (a mistyped ID names another person,
    and the echo is what catches it). The file's bytes are hashed before and after the read.
    """

    if as_of.tzinfo is None:
        raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_CLOCK_REQUIRES_TIMEZONE")
    target = Path(path)
    try:
        before = sha256_file(target)
        text = target.read_text(encoding="utf-8")
        again = sha256_file(target)
    except (OSError, UnicodeError) as exc:
        raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_UNREADABLE", str(exc)[:200]) from exc
    if before != again:
        raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_CHANGED_DURING_READ")
    try:
        document = ConstructionJudgmentFile.model_validate_json(text)
    except ValueError as exc:
        raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_INVALID", " ".join(str(exc).split())[:400]) from exc
    if document.salary_sha256 != slate.salary_hash:
        raise ConstructionJudgmentError(
            "CONSTRUCTION_JUDGMENT_SALARY_HASH_MISMATCH",
            f"the file was written for {document.salary_sha256}, this slate is {slate.salary_hash}")
    now = as_of.astimezone(timezone.utc)
    if document.authored_at > now:
        raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_FROM_THE_FUTURE", document.authored_at.isoformat())
    for placement in document.placements:
        for source in placement.sources:
            if source.observed_at > now:
                raise ConstructionJudgmentError(
                    "CONSTRUCTION_JUDGMENT_SOURCE_FROM_THE_FUTURE", f"{placement.dk_id}:{source.uri}")
    earliest = min((row.lock_at for row in slate.players), default=None)
    if earliest is not None and now >= earliest:
        raise ConstructionJudgmentError(
            "CONSTRUCTION_JUDGMENT_EXPIRED_AT_LOCK", f"the earliest lock was {earliest.isoformat()}")
    rows = {row.dk_id: row for row in slate.players}
    people: dict[str, str] = {}
    for placement in document.placements:
        row = rows.get(placement.dk_id)
        if row is None:
            raise ConstructionJudgmentError("CONSTRUCTION_JUDGMENT_ID_NOT_IN_THE_SALARY_FILE", placement.dk_id)
        if row.name != placement.name:
            raise ConstructionJudgmentError(
                "CONSTRUCTION_JUDGMENT_NAME_IS_NOT_THE_ROW",
                f"{placement.dk_id} is {row.name!r} in the salary file, the judgment says {placement.name!r}")
        people[placement.dk_id] = row.underlying_id
    return ConstructionJudgment(str(target), before, document, people)


@dataclass(frozen=True)
class JudgmentDecision:
    """What the run does with each named person: place him, or refuse him by name."""

    status: str  # APPLIED, NOT_APPLIED, or NO_PLACEMENT_ACCEPTED
    accepted: Mapping[str, int]  # person -> minimum rows
    rows: tuple[dict[str, object], ...]  # one record per named person, in the file's order
    report: dict[str, object]


def judge_placements(
    judgment: ConstructionJudgment,
    slate: SlateContract,
    *,
    contract,
    offensive_report: Mapping[str, object] | None,
    offense_excluded_people: Iterable[str],
    kicker_zero_share_people: Iterable[str],
    scored_people: Iterable[str],
    count: int,
    applies: bool,
    why_not_applied: str = "",
) -> JudgmentDecision:
    """Decide each placement. Nothing here writes a number or reads a gate back into a pass.

    A placement is accepted only for a person in the scored pool. Refused by name, first match wins:
    his minimum is more than the rows the run builds; DraftKings marks him unavailable; an operator
    or an official inactive row excludes him (`NEVER_OVERRIDDEN`, as is a role-gate `BLOCK` or an
    unresolved material role change); or the role gate left him out for another reason, which this
    version does not readmit (`NOT_IN_THE_SCORED_POOL`: readmitting a person the gate left out is
    Session 52's, and belongs to a person with a source that can still clear the gate). With a
    portfolio policy in force the thesis build does not run, so every placement is `NOT_APPLIED`.
    """

    people = _people(slate)
    status_by_person = dict(getattr(contract, "status_by_person", {}))
    unavailable_people = set(getattr(contract, "unavailable_people", ()))
    operator_excluded = set(getattr(contract, "operator_excluded_people", ()))
    scored = set(scored_people)
    gate_excluded = set(offense_excluded_people)
    kicker_zero = set(kicker_zero_share_people)
    findings = _findings_by_person(offensive_report)
    accepted: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    for placement in judgment.document.placements:
        person = judgment.person_by_dk_id[placement.dk_id]
        row = people[person]
        record: dict[str, object] = {
            "dk_id": placement.dk_id, "person": person, "name": row.name, "position": row.position,
            "team": row.team, "salary": int(row.salary), "min_rows": placement.min_rows,
            "reason": placement.reason,
            "sources": [{"uri": source.uri, "observed_at": source.observed_at.isoformat()}
                        for source in placement.sources],
            "decision": "REFUSED", "refusal": None,
        }
        finding = findings.get(person, {})
        never = finding.get("material_role_change") or finding.get("finding")
        if not applies:
            record["decision"], record["refusal"] = "NOT_APPLIED", why_not_applied
        elif placement.min_rows > count:
            record["refusal"] = f"MIN_ROWS_EXCEEDS_THE_ENTRIES:{placement.min_rows}>{count}"
        elif person in unavailable_people:
            record["refusal"] = f"NEVER_OVERRIDDEN:DK_STATUS_UNAVAILABLE:{status_by_person.get(person, '')}"
        elif person in operator_excluded:
            record["refusal"] = "NEVER_OVERRIDDEN:OPERATOR_OR_OFFICIAL_INACTIVE_EXCLUSION"
        elif finding.get("selection_action") == "BLOCK" or never in NEVER_OVERRIDDEN_FINDINGS:
            record["refusal"] = f"NEVER_OVERRIDDEN:{never}"
        elif person in gate_excluded:
            record["refusal"] = f"NOT_IN_THE_SCORED_POOL:{finding.get('finding') or 'OFFENSIVE_ROLE_GATE_EXCLUDED'}"
        elif person in kicker_zero:
            record["refusal"] = "NOT_IN_THE_SCORED_POOL:KICKER_ROLE_ZERO_SHARE"
        elif person not in scored:
            record["refusal"] = "NOT_IN_THE_SCORED_POOL:NO_PRIOR_ROW"
        else:
            record["decision"], record["refusal"] = "ACCEPTED", None
            accepted[person] = placement.min_rows
        rows.append(record)
    status = "NOT_APPLIED" if not applies else ("APPLIED" if accepted else "NO_PLACEMENT_ACCEPTED")
    report = {
        "version": CONSTRUCTION_JUDGMENT_VERSION,
        "status": status,
        "number_written": "NONE",
        "file": judgment.as_report(),
        "applies_to": "CLASSIC_THESIS_CONSTRUCTION_WITH_NO_PORTFOLIO_POLICY",
        "not_applied_reason": why_not_applied if not applies else None,
        "placements": rows,
        "accepted": dict(accepted),
        "refused": [
            {"dk_id": r["dk_id"], "name": r["name"], "refusal": r["refusal"]}
            for r in rows if r["decision"] == "REFUSED"
        ],
        "does_not_establish": list(JUDGMENT_DOES_NOT_ESTABLISH),
    }
    return JudgmentDecision(status, accepted, tuple(rows), report)


def render_judgment_pass_text(
    block: Mapping[str, object], decision: Mapping[str, object] | None = None
) -> str:
    """The pass as the plain text the handoff carries. A pure view: it reads the report and adds nothing."""

    if block.get("status") == "FAILED":
        return f"Classic judgment pass did not run: {block.get('error')}\n"

    def rows(value: object) -> list[Mapping[str, object]]:
        return [item for item in value or () if isinstance(item, Mapping)] if isinstance(value, (list, tuple)) else []

    out = [f"# Classic judgment pass ({block.get('version')})",
           "A report for research. It writes no model value, clears no gate and selects nobody.", ""]
    starters = block.get("starters_check") if isinstance(block.get("starters_check"), Mapping) else {}
    out.append("## Starting quarterbacks")
    for row in rows(starters.get("starters")):
        flag = "scored" if row.get("selectable") else f"NOT IN THE SCORED POOL ({row.get('reason')})"
        promoted = f", promoted over {', '.join(map(str, row['promoted_over']))}" if row.get("promoted_over") else ""
        out.append(f"- {row.get('team')}: {row.get('name')} ${row.get('salary')} status {row.get('dk_status') or '-'}"
                   f" prior {row.get('prior_points')}: {flag}{promoted}")
    if starters.get("unevaluated_teams"):
        out.append(f"- the depth evidence does not order {', '.join(map(str, starters['unevaluated_teams']))};"
                   " nobody was guessed (supply --qb-depth-role-evidence-json)")
    out += ["", "## Injury rooms"]
    rooms = block.get("injury_rooms") if isinstance(block.get("injury_rooms"), Mapping) else {}
    for room in rows(rooms.get("rooms")):
        vacated = "; ".join(f"{v.get('name')} ({v.get('dk_status') or 'official INACTIVE'}, ${v.get('salary')})"
                            for v in rows(room.get("vacated")))
        out.append(f"- {room.get('team')} {room.get('position')}: vacated {vacated}")
        for heir in rows(room.get("inheritors")):
            tag = "repriced" if heir.get("repriced_by_redistribution") else "not repriced"
            out.append(f"    inherits: {heir.get('name')} ${heir.get('salary')} prior {heir.get('prior_points_before')}"
                       f" to {heir.get('prior_points_after')} ({tag}, {heir.get('history_state')})")
        for stuck in rows(room.get("not_inheriting_unresolved_role")):
            out.append(f"    does not inherit, role unresolved: {stuck.get('name')} ${stuck.get('salary')}"
                       f" prior {stuck.get('prior_points')} ({stuck.get('history_state')})")
    out += ["", "## Candidates to research (not a selection)"]
    candidates = block.get("candidates") if isinstance(block.get("candidates"), Mapping) else {}
    for row in rows(candidates.get("candidates")):
        placeable = "placeable" if row.get("placeable") else f"not placeable: {row.get('placement')}"
        out.append(f"{row.get('rank')}. {row.get('name')} {row.get('position')} {row.get('team')} ${row.get('salary')}"
                   f" [{', '.join(map(str, row.get('sources') or ()))}] prior {row.get('prior_points_before')} to"
                   f" {row.get('prior_points_after')}; {placeable}")
        out.append(f"    {row.get('research')}")
    for row in rows(candidates.get("priced_above_prior_only")):
        out.append(f"- priced above prior, no other signal: {row.get('name')} {row.get('position')} {row.get('team')}"
                   f" ${row.get('salary')} ({row.get('divergence_places')} places)")
    for key, why in sorted((candidates.get("sources_unevaluated") or {}).items()):
        out.append(f"- not evaluated, {key}: {why}")
    decision = decision if isinstance(decision, Mapping) else {}
    if decision:
        out += ["", f"## Construction judgment ({decision.get('status')}; no number written)"]
        delivery = decision.get("delivery") if isinstance(decision.get("delivery"), Mapping) else {}
        for row in rows(decision.get("placements")):
            if row.get("decision") == "ACCEPTED":
                held = (delivery.get("delivered_rows") or {}).get(row.get("person"), [])
                out.append(f"- placed: {row.get('name')} at least {row.get('min_rows')} rows; in {len(held)}")
            else:
                out.append(f"- {str(row.get('decision')).lower()}: {row.get('name')} ({row.get('dk_id')}): {row.get('refusal')}")
        for person, short in sorted((delivery.get("shortfall") or {}).items()):
            out.append(f"- SHORT: {person} by {short} rows")
    out += ["", "## Late-swap watch list (not a blocker)"]
    watch = block.get("late_swap_watch") if isinstance(block.get("late_swap_watch"), Mapping) else {}
    for row in rows(watch.get("later_window_without_official_row")):
        out.append(f"- {row.get('name')} {row.get('position')} {row.get('team')} locks {row.get('lock_at')}"
                   f" status {row.get('dk_status') or '-'} in {row.get('rows')} rows")
    if rows(watch.get("early_window_without_official_row")):
        out.append("Early window, no official row yet (confirm against the posted inactives): "
                   + ", ".join(str(row.get("name")) for row in rows(watch.get("early_window_without_official_row"))))
    return "\n".join(out) + "\n"
