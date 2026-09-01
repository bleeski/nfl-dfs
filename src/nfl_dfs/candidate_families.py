from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .contracts import EngineMode, SlateContract
from .lineups import validate_lineup


@dataclass(frozen=True)
class CandidateFeatures:
    canonical_key: str
    family_labels: tuple[str, ...]
    salary_left: int
    details: dict[str, str | int | float]


@dataclass(frozen=True)
class CoverageReport:
    counts: dict[str, int]
    missing_registered_families: tuple[str, ...]
    pass_status: bool


CLASSIC_REGISTERED_FAMILIES = (
    "QB_SINGLE",
    "QB_DOUBLE",
    "ZERO_BRINGBACK",
    "ONE_BRINGBACK",
    "TWO_PLUS_BRINGBACK",
    "SECONDARY_CORRELATION",
    "NAKED_QB",
    "RB_DST",
)
SHOWDOWN_REGISTERED_FAMILIES = (
    "CPT_QB",
    "CPT_RB",
    "CPT_WR_TE",
    "CPT_K_DST",
    "TEAM_SPLIT_3_3",
    "TEAM_SPLIT_4_2",
    "TEAM_SPLIT_5_1",
    "K_DST_CONSTRUCTION",
    "FULL_SALARY",
    "SALARY_LEFT",
)


def classify_candidate(slate: SlateContract, roster: tuple[str, ...]) -> CandidateFeatures:
    validation = validate_lineup(slate, roster)
    if not validation.valid or validation.lineup is None:
        raise ValueError(f"cannot classify illegal lineup: {validation.errors}")
    by_id = {player.dk_id: player for player in slate.players}
    players = [by_id[dk_id] for dk_id in roster]
    labels: set[str] = set()
    details: dict[str, str | int | float] = {}
    if slate.mode is EngineMode.CLASSIC:
        qb = next(player for player in players if player.position == "QB")
        pass_catchers = [
            player
            for player in players
            if player.team == qb.team and player.position in {"WR", "TE"}
        ]
        bringbacks = [
            player
            for player in players
            if player.team == qb.opponent and player.position in {"RB", "WR", "TE"}
        ]
        labels.add("NAKED_QB" if not pass_catchers else "QB_SINGLE" if len(pass_catchers) == 1 else "QB_DOUBLE")
        labels.add(
            "ZERO_BRINGBACK"
            if not bringbacks
            else "ONE_BRINGBACK"
            if len(bringbacks) == 1
            else "TWO_PLUS_BRINGBACK"
        )
        dst_teams = {player.team for player in players if player.position == "DST"}
        if any(player.position == "RB" and player.team in dst_teams for player in players):
            labels.add("RB_DST")
        game_team_counts: dict[str, Counter[str]] = {}
        for player in players:
            if player.game_id == qb.game_id or player.position == "DST":
                continue
            game_team_counts.setdefault(player.game_id, Counter())[player.team] += 1
        if any(len(counts) >= 2 for counts in game_team_counts.values()):
            labels.add("SECONDARY_CORRELATION")
        details.update(
            {
                "qb": qb.dk_id,
                "qb_stack_size": len(pass_catchers),
                "bringback_size": len(bringbacks),
            }
        )
    else:
        captain = players[0]
        if captain.position == "QB":
            labels.add("CPT_QB")
        elif captain.position == "RB":
            labels.add("CPT_RB")
        elif captain.position in {"WR", "TE"}:
            labels.add("CPT_WR_TE")
        else:
            labels.add("CPT_K_DST")
        team_counts = Counter(player.team for player in players)
        split = sorted(team_counts.values(), reverse=True)
        labels.add(f"TEAM_SPLIT_{split[0]}_{split[1]}")
        if any(player.position in {"K", "DST"} for player in players):
            labels.add("K_DST_CONSTRUCTION")
        salary_left = slate.salary_cap - validation.lineup.salary
        labels.add("FULL_SALARY" if salary_left == 0 else "SALARY_LEFT")
        details.update({"captain_position": captain.position, "team_split": f"{split[0]}-{split[1]}"})
    return CandidateFeatures(
        canonical_key=validation.lineup.canonical_key,
        family_labels=tuple(sorted(labels)),
        salary_left=slate.salary_cap - validation.lineup.salary,
        details=details,
    )


def coverage_report(
    slate: SlateContract, rosters: Iterable[tuple[str, ...]]
) -> CoverageReport:
    counts: Counter[str] = Counter()
    for roster in rosters:
        counts.update(classify_candidate(slate, roster).family_labels)
    registered = (
        CLASSIC_REGISTERED_FAMILIES
        if slate.mode is EngineMode.CLASSIC
        else SHOWDOWN_REGISTERED_FAMILIES
    )
    missing = tuple(family for family in registered if counts[family] == 0)
    return CoverageReport(dict(sorted(counts.items())), missing, not missing)
