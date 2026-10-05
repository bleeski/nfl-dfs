"""Prior-only NFL lineup selection for Showdown and Classic.

R02, selection side. This is the step that turns a frozen prior package into
assignments, and it is deliberately narrow: it calls the MILP in `optimizer.py`
against the prior score in `prior_score.py`, over the pool the participation
contract permits. It never imports `field.py`, `economics.py` or the portfolio
objective, because those carry the R05, R06 and R07 defects and a prior-only
profile must not touch them.

Two consequences the caller has to carry forward. The objective maximizes a
central estimate, so the first lineup is close to the chalkiest legal lineup;
there is no ownership model here and therefore no leverage. And a portfolio of
more than one entry is differentiated structurally, by forbidding a repeat
captain, which is uniqueness rather than a claim about correlated equity.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .classic_judgment import ConstructionJudgment, judge_placements
from .contracts import EngineMode, SlateContract
from .classic_portfolio import (
    ENFORCEMENT_VERSION as CLASSIC_ENFORCEMENT_VERSION,
    build_classic_candidate_bank,
    candidate_bank_bytes,
    solve_classic_portfolio,
)
from .classic_portfolio_policy import NormalizedClassicPortfolioPolicy
from .hashing import sha256_bytes
from .kicker_roles import resolve_kicker_roles
from .lineups import roster_canonical_key, validate_lineup
from .opportunity import OpportunityModel
from .offensive_roles import resolve_offensive_roles, verify_offensive_resolution
from .qb_depth_roles import resolve_qb_depth_roles, verify_qb_depth_resolution
from .optimizer import LineupOptimizer
from .participation import ParticipationContract, excluded_dk_ids, selectable_pool_problems
from .portfolio_enforcement import (
    DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    ENFORCEMENT_VERSION,
    build_policy_candidate_bank,
    scaled_candidate_limit,
    scaled_candidate_seconds,
    scaled_selection_seconds,
    solve_policy_portfolio,
)
from .portfolio_policy import NormalizedPortfolioPolicy
from .prior_score import PriorScores, TeamSplits, score_pool
from .showdown_theses import (
    DOES_NOT_ESTABLISH as THESIS_DOES_NOT_ESTABLISH,
    THESIS_BUILD_VERSION,
    ShowdownThesis,
    apply_thesis_rows,
    backup_quarterbacks,
    thesis_excluded_dk_ids,
)
from .classic_theses import select_thesis_lineups
from .relaxation import own_exclusion_dk_ids


PROFILE_VERSION = "prior_only_showdown_selection_v1"
# v2 (Session 39): C1 and the unbound fill carry the Classic person-overlap cap. v1 (exact
# roster cuts only) is what earlier runs' selection reports name; nothing reads the string.
CLASSIC_PROFILE_VERSION = "prior_only_classic_selection_c1_v2"

# Session 39 (review S3): the Classic person-overlap cap on C1 and on the rows a
# subset policy leaves unbound. A nine-player lineup that shares at most six
# people with every earlier one is a construction preference, not a gate: when
# no distinct lineup fits under it the cap steps up one person at a time to
# `CLASSIC_MAX_USEFUL_OVERLAP` (distinct rosters never share nine people, so
# eight is the exact-roster cut alone), each step reported. Distinctness (R29)
# is never on that walk. `None` keeps the earlier exact-roster-only behaviour
# for diagnostics. It is separate from `max_person_overlap`, whose default is
# Showdown's six-slot scale.
CLASSIC_PERSON_OVERLAP = 6
CLASSIC_MAX_USEFUL_OVERLAP = 8

# Session 49: Classic rung 4 built as several stack theses under one person share cap.
THESIS_CONSTRUCTION = "THESES"


class SelectionError(ValueError):
    """A named fail-closed selection error.

    `status` and `facts` (Session 10) carry the failure structured, so the
    relaxation controller reads the status a bank or joint solve reported
    instead of parsing the message.
    """

    def __init__(self, message: str, *, status: str | None = None,
                 facts: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.facts = dict(facts or {})

    def as_report(self, *, error: str) -> dict[str, object]:
        return {"status": self.status, "origin": "SELECTION", "facts": dict(self.facts), "error": error}


@dataclass(frozen=True)
class SelectedLineup:
    index: int
    roster: tuple[str, ...]
    captain_dk_id: str
    salary: int
    prior_points: float
    canonical_key: str
    solver_status: str
    solver_seconds: float

    def as_payload(self, names: Mapping[str, str]) -> dict[str, object]:
        return {
            "index": self.index,
            "roster": list(self.roster),
            "captain": (
                names.get(self.captain_dk_id, self.captain_dk_id)
                if self.captain_dk_id
                else None
            ),
            "captain_dk_id": self.captain_dk_id or None,
            "salary": self.salary,
            "salary_remaining": 50_000 - self.salary,
            "prior_points": round(self.prior_points, 3),
            "canonical_key": self.canonical_key,
            "solver_status": self.solver_status,
            "solver_seconds": round(self.solver_seconds, 3),
            "players": [names.get(dk_id, dk_id) for dk_id in self.roster],
        }


POOL_SCORES_SCHEMA = "nfl_prior_pool_scores_v1"

# Environment fallback for the two entry points that cannot yet take a keyword:
# `cowork-run --profile prior_review` and the `select` subcommand both reach
# selection through fixed request plumbing. Backlog P1-4 replaces this whole
# function with a first-class, hash-bound artifact emitted by the engine and
# removes both the variable and the parameter; until then this is the documented
# way to get the gated scores out, and `scripts/build_classic_portfolio.py`
# consumes exactly this schema.
POOL_SCORES_PATH_ENV = "NFL_DFS_DUMP_SCORES"


def resolve_pool_scores_path(explicit: str | Path | None) -> Path | None:
    """Where to write the scored pool, or None when nobody asked for it."""

    raw = explicit if explicit is not None else os.environ.get(POOL_SCORES_PATH_ENV) or None
    if raw is None:
        return None
    path = Path(raw).expanduser()
    if path.is_dir():
        raise SelectionError(f"POOL_SCORES_PATH_IS_A_DIRECTORY:{path}")
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.is_dir():
        raise SelectionError(f"POOL_SCORES_PARENT_MISSING:{parent}")
    return path


def write_pool_scores(
    scores: PriorScores,
    path: str | Path,
    *,
    excluded_dk_ids: Iterable[str] = (),
) -> Path:
    """Write the gated per-player scores as a schema-versioned JSON document.

    This is a diagnostic export, not a release artifact: it binds no hashes and
    carries no evidence decision, so nothing downstream may treat its presence
    as authorization. It exists because on 2026-09-13 the engine's own scores
    were the one artifact that reached the shipped portfolio, and they left
    through an unnamed environment variable read in the middle of the scoring
    path.

    `excluded_dk_ids` (2026-09-27) names every dk_id the run's own role gates
    already excluded -- official status, kicker zero-share, offensive role and
    material-role-change findings alike -- the same set `select_prior_lineups`
    passes to its own objective. On 2026-09-27, 65 role-gated people were still
    scored above zero in this dump because it was written before that set was
    computed, and a downstream filter had to re-derive the same exclusions from
    a different report by hand. Carrying the set here means a consumer of this
    file never has to.
    """

    target = Path(path).expanduser()
    payload = {
        "schema_version": POOL_SCORES_SCHEMA,
        "score_version": scores.score_version,
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "by_dk_id": dict(sorted(scores.by_dk_id.items())),
        "by_person": dict(sorted(scores.by_person.items())),
        "threshold_sensitive": sorted(scores.threshold_sensitive),
        "omissions": sorted(scores.omissions),
        "excluded_dk_ids": sorted({str(dk_id) for dk_id in excluded_dk_ids}),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str), encoding="utf-8"
    )
    return target


def _prior_before_redistribution(model, pre_model, score_chain):
    """(prior points by person before the injury-room move, note) for the people the move changed.

    Scored by the same chain as the run, on the model before `redistribute_vacated_workload`. Nothing
    here selects or gates: a model the move left alone, or a counterfactual that cannot run, gives
    `None` and says which, so the judgment pass never reports a "before" it did not compute.
    """

    if pre_model is None:
        return None, "NOT_REQUESTED"
    if pre_model is model:
        return None, "NOTHING_MOVED"
    earlier = {player.underlying_id: player for player in pre_model.players}
    moved = sorted(
        player.underlying_id for player in model.players if earlier.get(player.underlying_id) != player)
    if not moved:
        return None, "NOTHING_MOVED"
    try:
        scored = score_chain(pre_model)[2]
    except Exception as exc:  # noqa: BLE001 - a diagnostic counterfactual never stops a run
        return None, f"COUNTERFACTUAL_COULD_NOT_RUN:{type(exc).__name__}:{' '.join(str(exc).split())[:160]}"
    return {person: round(float(scored.by_person[person]), 6) for person in moved if person in scored.by_person}, "SCORED"


def select_prior_lineups(
    slate: SlateContract,
    model: OpportunityModel,
    splits: Mapping[str, TeamSplits],
    contract: ParticipationContract,
    *,
    count: int,
    differentiate_captain: bool = True,
    max_person_overlap: int | None = 4,
    classic_person_overlap: int | None = CLASSIC_PERSON_OVERLAP,
    time_limit_seconds: float = 10.0,
    role_evidence_json: str | Path | None = None,
    offensive_role_evidence_json: str | Path | None = None,
    qb_depth_role_evidence_json: str | Path | None = None,
    as_of: datetime | None = None,
    portfolio_policy: NormalizedPortfolioPolicy | NormalizedClassicPortfolioPolicy | None = None,
    policy_candidate_limit: int | None = None,
    policy_candidate_seconds: float | None = None,
    policy_candidate_per_solve_seconds: float = DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    policy_selection_seconds: float | None = None,
    pool_scores_path: str | Path | None = None,
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    fill_count: int = 0,
    fill_time_limit_seconds: float | None = None,
    classic_construction: str | None = None,
    pre_redistribution_model: OpportunityModel | None = None,
    construction_judgment: ConstructionJudgment | None = None,
) -> tuple[tuple[SelectedLineup, ...], PriorScores, dict[str, object]]:
    """Solve for `count` distinct legal lineups over the permitted pool.

    The `policy_*` bounds default to `None`, meaning "scale with the policy's
    entry count" (`max(32, 4 * entries)` candidates, `max(30s, 2s * entries)`
    of bank generation, `max(10s, 1s * entries)` for the joint solve). An
    explicit value is used as given, so tests and diagnostics can pin small
    bounds. `forbidden_rosters` (Session 11) are the entry template's prefilled
    rosters: C1 and sequential Showdown cut each from every solve, and the C2
    and SD3 banks never hold one, so no selected lineup repeats one (R29).

    `fill_count` (Session 11b, C2 since Session 11c) is the fillable rows a
    subset policy leaves unbound. After the joint solve, sequential Showdown
    (SD3) or C1 (C2) fills them: every policy lineup and every forbidden roster is a no-good, and only
    the run's own exclusions apply (request, status, official, role), never the
    policy's. The fill's lineups follow the policy's in the returned tuple and
    its report is the policy report's `unbound_fill`. A fill that runs out of
    distinct lineups at row k (Session 39b, R29) returns the k rows it built and
    reports `unfilled_rows` and `stopped` beside them, so the caller names the
    Entry IDs left blank; the bound rows are never discarded and no lineup is
    repeated. C1 and sequential Showdown with no policy still raise.

    `classic_construction="THESES"` (Session 49) replaces C1's single repeated
    construction with `classic_theses.select_thesis_lineups`: several stack
    theses under one person share cap. It is Classic with no policy only (rung 4
    of the ladder, or a run that supplied none); it reports `construction`,
    and a run that runs out of distinct lineups or time at row k returns the k
    rows with `unfilled_rows` and `stopped`, like the fill, and raises only when
    it built none. `None` is C1 as it was.

    `pre_redistribution_model` (Session 61) is the model as it stood before Session 60's
    injury-room redistribution. When it differs from `model`, the pool is scored again from it by
    the same pipeline and the report carries each affected person's prior points before the move
    (`prior_points_before_redistribution`), a diagnostic the Classic judgment pass reads. It never
    selects, and a failure to compute it is named in the report and stops nothing.

    `construction_judgment` (Session 61) is a validated `nfl_classic_construction_judgment_v1`:
    people the thesis build must roster in at least a minimum of rows. It applies only to the thesis
    construction (no policy); each placement is accepted for a person in the scored pool and refused
    by name otherwise (`classic_judgment.judge_placements`), and an accepted person is also kept in
    when the backup-quarterback default would have removed him. It writes no number.

    `classic_person_overlap` (Session 39) is the most people a Classic C1 or
    fill row may share with an earlier row (default 6; `None` is no cap). It
    steps up one person at a time when no distinct lineup fits and each step is
    reported; `max_person_overlap` is Showdown's and Classic never reads it.
    """

    if slate.mode not in {EngineMode.SHOWDOWN, EngineMode.CLASSIC}:
        raise SelectionError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    if classic_construction not in {None, THESIS_CONSTRUCTION}:
        raise SelectionError(f"MODE_NOT_SUPPORTED:classic_construction={classic_construction!r}")
    if classic_construction is not None and (slate.mode is not EngineMode.CLASSIC or portfolio_policy is not None):
        raise SelectionError(
            f"MODE_NOT_SUPPORTED:{slate.mode.value}:the thesis construction is Classic rung 4 (no policy) only")
    forbidden_rosters = tuple(tuple(map(str, roster)) for roster in forbidden_rosters)
    forbidden_keys = {roster_canonical_key(slate, roster) for roster in forbidden_rosters}
    if count < 1:
        raise SelectionError(f"LINEUP_COUNT_INVALID:{count}")
    if portfolio_policy is not None and count != portfolio_policy.entry_count:
        raise SelectionError(
            "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
            f"count={count}:policy_entries={portfolio_policy.entry_count}"
        )
    if fill_count < 0 or (fill_count and portfolio_policy is None):
        raise SelectionError(
            "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
            f"fill_count={fill_count}:an unbound fill needs a subset policy"
        )
    if (
        isinstance(portfolio_policy, NormalizedPortfolioPolicy)
        and slate.mode is not EngineMode.SHOWDOWN
    ):
        raise SelectionError(
            "PORTFOLIO_POLICY_MODE_UNSUPPORTED_C1:Classic policy, candidate-bank, "
            "and joint portfolio selection belong to C2"
        )
    if (
        isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
        and slate.mode is not EngineMode.CLASSIC
    ):
        raise SelectionError(
            "CLASSIC_PORTFOLIO_POLICY_MODE_MISMATCH:Classic C2 policy requires Classic"
        )
    problems = selectable_pool_problems(slate, contract)
    if problems:
        raise SelectionError("SELECTABLE_POOL_INFEASIBLE:" + ";".join(problems))

    kicker_roles = resolve_kicker_roles(
        slate,
        contract,
        evidence_path=role_evidence_json,
        as_of=as_of,
    )

    def score_chain(scored_model: OpportunityModel):
        # The depth chart moves quarterback attempts onto the named starter before
        # anything reads a share, so a backup cannot carry his prior-season split
        # into the projection and then be removed by a policy exclusion that lands
        # after scoring. It touches `qb_attempt_share` and nothing else.
        depth = resolve_qb_depth_roles(
            slate, scored_model, contract, evidence_path=qb_depth_role_evidence_json, as_of=as_of,
        )
        # Session 54 (R36): the effective starters the depth evidence names are selectable even with no
        # history. `starters_by_team` is already past R25's promotion over a DraftKings-unavailable starter.
        roles = resolve_offensive_roles(
            slate,
            depth.model,
            contract,
            evidence_path=offensive_role_evidence_json,
            as_of=as_of,
            declared_starters=frozenset((depth.report.get("starters_by_team") or {}).values()),
            depth_evidence_sha256=depth.evidence_sha256,
        )
        return depth, roles, score_pool(slate, roles.model, splits, kicker_roles=kicker_roles, offensive_roles=roles)

    qb_depth, offense, scores = score_chain(model)
    # Scoring may leave out an unresolved role change (R28); its resolution is
    # the one every exclusion and report below reads.
    offense = scores.offensive_role_resolution
    pool_scores_target = resolve_pool_scores_path(pool_scores_path)
    zero_share_people = set(kicker_roles.zero_share_people)
    excluded_set = (
            sorted(
                set(excluded_dk_ids(slate, contract))
                | {
                player.dk_id
                for player in slate.players
                    if player.underlying_id in zero_share_people or player.underlying_id in offense.excluded_people
                }
            )
    )
    # Session 53 (R36, Ben 2026-10-01: "apply to every showdown"): every quarterback the depth
    # evidence puts behind a declared starter is out of every Showdown row, a plain policy or no
    # policy included, unless a thesis names him for its own rows. A team the evidence does not
    # declare keeps every quarterback and is named; nobody is guessed out. The starter the report
    # names is the resolver's effective one (R25 promotes over a DraftKings-unavailable starter and
    # refuses any other unavailable one). The offensive role gate runs after the resolver; since Session
    # 54 it selects a declared starter with no history, but a hash-bound fact that he is a backup, or an
    # allocation or participation rule, can still leave his team with no selectable quarterback.
    qb_depth_report = qb_depth.report
    # Session 61 (R37). Classic gets the same default: a quarterback the depth evidence puts behind a
    # declared starter is out of every Classic row (Week 4's first build rostered Nick Mullens, who was
    # not on his team's depth chart). A Classic policy that names a person with a minimum is a choice
    # made on purpose, so that person stays in; so does anyone a validated judgment names (Part B).
    # Classic supplies its own depth package (`run-slate` auto-captures for Showdown only), so a team the
    # evidence does not order is named and nobody is guessed out.
    judgment_decision = None
    if construction_judgment is not None:
        if slate.mode is not EngineMode.CLASSIC:
            raise SelectionError(f"MODE_NOT_SUPPORTED:{slate.mode.value}:a Classic construction judgment")
        thesis_build = classic_construction == THESIS_CONSTRUCTION and portfolio_policy is None
        judgment_decision = judge_placements(
            construction_judgment, slate, contract=contract, offensive_report=offense.report,
            offense_excluded_people=offense.excluded_people,
            kicker_zero_share_people=kicker_roles.zero_share_people, scored_people=scores.by_person,
            count=count, applies=thesis_build,
            why_not_applied=(
                "A_PORTFOLIO_POLICY_IS_IN_FORCE" if portfolio_policy is not None
                else "THE_RUN_DOES_NOT_USE_THE_THESIS_CONSTRUCTION"),
        )
    named_backups = frozenset(
        bound.entity_id
        for bound in (
            portfolio_policy.player_bounds if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy) else ()
        )
        if bound.minimum_entries > 0
    ) | frozenset(judgment_decision.accepted if judgment_decision is not None else ())
    default_backups, default_unevaluated = backup_quarterbacks(
        slate, None, qb_depth_report, admitted_people=named_backups)
    default_backup_ids = {player.dk_id for player in slate.players if player.underlying_id in default_backups}
    # The run's own exclusions bind every row; a policy's own exclusions and zero
    # caps (below) bind only the rows it binds, so the unbound fill uses these. The default
    # backups bind every row, the unbound fill included.
    run_excluded = tuple(sorted(set(excluded_set) | default_backup_ids))
    # Session 23b (R33): under an active thesis, the quarterbacks the depth evidence puts
    # behind a starter leave the pool unless the thesis names them. Bound rows only: the thesis's
    # own rows may hold the backups it names, so for them `row_backups` is the thesis's set and
    # not the default; `run_excluded` above (the unbound fill) keeps every backup out.
    thesis = portfolio_policy.active_thesis if isinstance(portfolio_policy, NormalizedPortfolioPolicy) else None
    backups, unevaluated_teams = (
        backup_quarterbacks(slate, thesis, qb_depth_report) if thesis is not None else (frozenset(), ()))
    row_backups = backups if thesis is not None else default_backups
    excluded_set.extend(player.dk_id for player in slate.players if player.underlying_id in row_backups)
    if isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        for limit in portfolio_policy.effective_limits:
            if limit.combined_max_entries == 0:
                excluded_set.extend((limit.person.cpt_dk_id, limit.person.flex_dk_id))
    elif isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        by_person = {player.underlying_id: player for player in slate.players}
        for limit in portfolio_policy.player_bounds:
            if limit.maximum_entries == 0:
                excluded_set.append(by_person[limit.entity_id].dk_id)
    excluded = tuple(sorted(set(excluded_set)))
    showdown = slate.mode is EngineMode.SHOWDOWN
    backup_default_report = {
        "rule": "SHOWDOWN_BACKUP_QUARTERBACKS_OUT_OF_EVERY_ROW_R36",
        "applies": showdown,
        "excluded_people": sorted(default_backups) if showdown else [],
        "unevaluated_teams": list(default_unevaluated) if showdown else [],
        "thesis_named_backups_readmitted_for_bound_rows": sorted(default_backups - backups) if thesis is not None else [],
        "does_not_establish": ["THAT_THE_DECLARED_STARTER_IS_PLAYING", "OFFICIAL_ACTIVE_STATUS"],
    }
    classic_backup_default_report = {
        "rule": "CLASSIC_BACKUP_QUARTERBACKS_OUT_OF_EVERY_ROW_R36_R37",
        "applies": not showdown,
        "excluded_people": [] if showdown else sorted(default_backups),
        "unevaluated_teams": [] if showdown else list(default_unevaluated),
        # Only a person the depth evidence would have removed counts as readmitted.
        "readmitted_by_a_named_choice": [] if showdown else sorted(
            named_backups & backup_quarterbacks(slate, None, qb_depth_report)[0]),
        "does_not_establish": ["THAT_THE_DECLARED_STARTER_IS_PLAYING", "OFFICIAL_ACTIVE_STATUS"],
    }
    # Session 61: the prior of each person the injury-room redistribution moved, as it stood before it.
    judgment_inputs: dict[str, object] = {}
    if not showdown:
        before_points, before_note = _prior_before_redistribution(model, pre_redistribution_model, score_chain)
        judgment_inputs = {
            "prior_points_before_redistribution": before_points,
            "prior_points_before_redistribution_note": before_note,
            **({"construction_judgment": judgment_decision.report} if judgment_decision is not None else {}),
        }
    if pool_scores_target is not None:
        write_pool_scores(scores, pool_scores_target, excluded_dk_ids=excluded)
    objective = _objective(slate, scores, excluded)

    # The fill's rows are bound by the run's own exclusions and, since Session 39
    # (review S6), by the policy's own exact exclusions and zero caps: an
    # exclusion is a fact about a person, not about the rows a policy binds.
    # The policy's other bounds still never cover them.
    fill_excluded = _fill_exclusions(run_excluded, portfolio_policy)

    def fill(policy_lineups: list[SelectedLineup]) -> tuple[list[SelectedLineup], dict[str, object]]:
        return _fill_unbound(
            slate, _objective(slate, scores, fill_excluded), fill_excluded, contract,
            policy_lineups=policy_lineups, forbidden_rosters=forbidden_rosters, count=fill_count,
            differentiate_captain=differentiate_captain, max_person_overlap=max_person_overlap,
            classic_person_overlap=classic_person_overlap,
            time_limit_seconds=(time_limit_seconds if fill_time_limit_seconds is None
                                else fill_time_limit_seconds),
        )

    by_id = {player.dk_id: player for player in slate.players}
    selected: list[SelectedLineup] = []
    if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        bank = build_classic_candidate_bank(
            slate,
            objective,
            portfolio_policy,
            excluded_ids=excluded,
            forbidden_rosters=forbidden_rosters,
        )
        if bank.blocking:
            raise SelectionError(
                f"{bank.status}:model_status={bank.terminal_model_status}:"
                f"candidates={len(bank.candidates)}:requested={bank.requested_candidates}",
                status=bank.status,
                facts={"stage": "CANDIDATE_BANK", "candidates": len(bank.candidates),
                       "requested_candidates": bank.requested_candidates,
                       "model_status": bank.terminal_model_status, "exhaustive": bank.exhaustive,
                       "elapsed_seconds": round(bank.elapsed_seconds, 3)},
            )
        portfolio_solve = solve_classic_portfolio(portfolio_policy, bank)
        if not portfolio_solve.passed:
            raise SelectionError(
                f"{portfolio_solve.status}:model_status={portfolio_solve.model_status}:"
                f"candidate_bank={len(bank.candidates)}:scope={portfolio_solve.infeasibility_scope}",
                status=portfolio_solve.status,
                facts={"stage": "JOINT_SELECTION", "candidates": len(bank.candidates),
                       "requested_candidates": bank.requested_candidates,
                       "model_status": portfolio_solve.model_status, "exhaustive": bank.exhaustive,
                       "scope": portfolio_solve.infeasibility_scope},
            )
        for index, candidate_index in enumerate(
            portfolio_solve.selected_candidate_indexes, start=1
        ):
            candidate = bank.candidates[candidate_index]
            validation = validate_lineup(slate, candidate.roster)
            if validation.lineup is None:
                raise SelectionError(
                    f"CLASSIC_PORTFOLIO_SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:"
                    f"{validation.errors}"
                )
            selected.append(
                SelectedLineup(
                    index=index,
                    roster=candidate.roster,
                    captain_dk_id="",
                    salary=validation.lineup.salary,
                    prior_points=candidate.prior_points,
                    canonical_key=validation.lineup.canonical_key,
                    solver_status=portfolio_solve.status,
                    solver_seconds=portfolio_solve.elapsed_seconds,
                )
            )
        exposure: Counter[str] = Counter()
        team_exposure: Counter[str] = Counter()
        game_exposure: Counter[str] = Counter()
        people_by_lineup: list[frozenset[str]] = []
        for lineup in selected:
            rows = [by_id[dk_id] for dk_id in lineup.roster]
            people = frozenset(row.underlying_id for row in rows)
            people_by_lineup.append(people)
            exposure.update(people)
            team_exposure.update({row.team for row in rows})
            game_exposure.update({row.game_id for row in rows})
        overlaps = [
            {
                "entry_id_a": portfolio_policy.entry_ids[left],
                "entry_id_b": portfolio_policy.entry_ids[right],
                "people": len(people_by_lineup[left] & people_by_lineup[right]),
            }
            for left in range(len(selected))
            for right in range(left + 1, len(selected))
        ]
        bank_raw = candidate_bank_bytes(portfolio_policy, bank)
        report = {
            "profile_version": "prior_only_classic_selection_c2_v1",
            "mode": slate.mode.value,
            "score_version": scores.score_version,
            "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "objective_version": portfolio_policy.objective_version,
            "objective_limits": [
                "CENTRAL_ESTIMATE_NOT_A_CEILING",
                "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
                "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
                # A limit incumbent is never called optimal (Session 08).
                "OPTIMAL_ONLY_OVER_ACTUAL_CANDIDATE_BANK"
                if portfolio_solve.proven_optimal
                else "LIMIT_INCUMBENT_NOT_PROVEN_OPTIMAL_OVER_ACTUAL_CANDIDATE_BANK",
            ],
            "lineups": len(selected),
            "selected_lineup_count": len(selected),
            "excluded_rows": len(excluded),
            "kicker_role_excluded_people": sorted(zero_share_people),
            "kicker_roles": kicker_roles.as_report(),
            "offensive_roles": offense.report,
            "qb_depth_roles": qb_depth_report,
            "showdown_backup_qb_default": backup_default_report,
            "classic_backup_qb_default": classic_backup_default_report,
            **judgment_inputs,
            "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
            "selectable_people": len(contract.selectable_people),
            "person_exposure": dict(sorted(exposure.items())),
            "team_exposure": dict(sorted(team_exposure.items())),
            "game_exposure": dict(sorted(game_exposure.items())),
            "pairwise_person_overlap": overlaps,
            "threshold_sensitive": list(scores.threshold_sensitive),
            "score_omissions": list(scores.omissions),
            "portfolio_policy": {
                "enforcement_version": CLASSIC_ENFORCEMENT_VERSION,
                "enforcement_status": "PASS",
                "normalized_policy_sha256": portfolio_policy.normalized_sha256,
                "entry_ids": list(portfolio_policy.entry_ids),
                "candidate_bank": bank.as_report(),
                "candidate_bank_artifact": json.loads(bank_raw.decode("utf-8")),
                "candidate_bank_canonical_json": bank_raw.decode("utf-8"),
                "candidate_bank_sha256": sha256_bytes(bank_raw),
                "solve": portfolio_solve.as_report(),
            },
            "never_calls": [
                "field.py",
                "ownership.py",
                "economics.py",
                "portfolio.py",
                "review_export.py",
                "readable_review.py",
            ],
        }
        # Session 11c: C1 fills the rows a subset leaves unbound, after the joint
        # solve, with every C2 lineup and prefilled roster a no-good. The
        # exposure and overlap above are the policy's rows, as SD3's are.
        if fill_count:
            selected, report["unbound_fill"] = fill(selected)
        verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
        verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
        _refuse_prefilled_repeats(selected, forbidden_keys)
        return tuple(selected), scores, report

    if isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        if thesis is not None:
            _refuse_unbuildable_thesis(slate, objective, excluded, thesis, backups, time_limit_seconds)
        entry_count = portfolio_policy.entry_count
        candidate_limit = (
            scaled_candidate_limit(entry_count)
            if policy_candidate_limit is None
            else policy_candidate_limit
        )
        candidate_seconds = (
            scaled_candidate_seconds(entry_count)
            if policy_candidate_seconds is None
            else policy_candidate_seconds
        )
        selection_seconds = (
            scaled_selection_seconds(entry_count)
            if policy_selection_seconds is None
            else policy_selection_seconds
        )
        bank = build_policy_candidate_bank(
            slate,
            objective,
            excluded_ids=excluded,
            candidate_limit=candidate_limit,
            total_time_limit_seconds=candidate_seconds,
            per_solve_time_limit_seconds=policy_candidate_per_solve_seconds,
            policy=portfolio_policy,
            forbidden_rosters=forbidden_rosters,
        )
        if bank.blocking:
            raise SelectionError(
                f"{bank.status}:model_status={bank.terminal_model_status}:"
                f"candidates={len(bank.candidates)}:budget={bank.total_time_limit_seconds}",
                status=bank.status,
                facts={"stage": "CANDIDATE_BANK", "candidates": len(bank.candidates),
                       "requested_candidates": bank.candidate_limit,
                       "model_status": bank.terminal_model_status, "complete": bank.complete,
                       "budget_seconds": bank.total_time_limit_seconds},
            )
        portfolio_solve = solve_policy_portfolio(
            portfolio_policy,
            bank,
            time_limit_seconds=selection_seconds,
        )
        if not portfolio_solve.passed:
            raise SelectionError(
                f"{portfolio_solve.status}:model_status={portfolio_solve.model_status}:"
                f"candidate_bank={len(bank.candidates)}:complete={bank.complete}",
                status=portfolio_solve.status,
                facts={"stage": "JOINT_SELECTION", "candidates": len(bank.candidates),
                       "requested_candidates": bank.candidate_limit,
                       "model_status": portfolio_solve.model_status, "complete": bank.complete},
            )
        for index, candidate_index in enumerate(
            portfolio_solve.selected_candidate_indexes, start=1
        ):
            candidate = bank.candidates[candidate_index]
            validation = validate_lineup(slate, candidate.roster)
            if validation.lineup is None:
                raise SelectionError(
                    f"PORTFOLIO_SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:"
                    f"{validation.errors}"
                )
            selected.append(
                SelectedLineup(
                    index=index,
                    roster=candidate.roster,
                    captain_dk_id=candidate.roster[0],
                    salary=validation.lineup.salary,
                    prior_points=candidate.prior_points,
                    canonical_key=validation.lineup.canonical_key,
                    solver_status=portfolio_solve.status,
                    solver_seconds=portfolio_solve.elapsed_seconds,
                )
            )
        exposure: dict[str, int] = {}
        captain_exposure: dict[str, int] = {}
        people_by_lineup: list[frozenset[str]] = []
        for lineup in selected:
            people = frozenset(by_id[dk_id].underlying_id for dk_id in lineup.roster)
            people_by_lineup.append(people)
            for person in people:
                exposure[person] = exposure.get(person, 0) + 1
            captain = by_id[lineup.captain_dk_id].underlying_id
            captain_exposure[captain] = captain_exposure.get(captain, 0) + 1
        overlaps = [
            {
                "entry_id_a": portfolio_policy.entry_ids[left],
                "entry_id_b": portfolio_policy.entry_ids[right],
                "people": len(people_by_lineup[left] & people_by_lineup[right]),
            }
            for left in range(len(selected))
            for right in range(left + 1, len(selected))
        ]
        report = {
            "profile_version": PROFILE_VERSION,
            "score_version": scores.score_version,
            "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "objective_limits": [
                "CENTRAL_ESTIMATE_NOT_A_CEILING",
                "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
                "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
            ],
            "differentiation": {
                "captain": "EXPLICIT_POLICY_MAXIMUM",
                "max_person_overlap": portfolio_policy.effective_pairwise_person_overlap,
                "basis": "EXACT_NORMALIZED_USER_POLICY_NOT_A_CORRELATED_EQUITY_CLAIM",
            },
            "lineups": len(selected),
            "selected_lineup_count": len(selected),
            "excluded_rows": len(excluded),
            "kicker_role_excluded_people": sorted(zero_share_people),
            "kicker_roles": kicker_roles.as_report(),
            "offensive_roles": offense.report,
            "qb_depth_roles": qb_depth_report,
            "showdown_backup_qb_default": backup_default_report,
            "classic_backup_qb_default": classic_backup_default_report,
            **judgment_inputs,
            "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
            "selectable_people": len(contract.selectable_people),
            "person_exposure": dict(sorted(exposure.items())),
            "captain_exposure": dict(sorted(captain_exposure.items())),
            "pairwise_person_overlap": overlaps,
            "forbidden_captain_rows": [],
            "threshold_sensitive": list(scores.threshold_sensitive),
            "score_omissions": list(scores.omissions),
            "portfolio_policy": {
                "enforcement_version": ENFORCEMENT_VERSION,
                "enforcement_status": "PASS",
                "normalized_policy_sha256": portfolio_policy.normalized_sha256,
                "entry_ids": list(portfolio_policy.entry_ids),
                "candidate_bank": bank.as_report(),
                "solve": portfolio_solve.as_report(),
                **({"theses": _thesis_report(portfolio_policy, len(selected), backups, unevaluated_teams)}
                   if portfolio_policy.theses else {}),
            },
            "never_calls": ["field.py", "economics.py", "portfolio economics"],
        }
        if fill_count:
            selected, report["unbound_fill"] = fill(selected)
        verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
        verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
        _refuse_prefilled_repeats(selected, forbidden_keys)
        return tuple(selected), scores, report

    selection_profile_version = (
        PROFILE_VERSION
        if slate.mode is EngineMode.SHOWDOWN
        else CLASSIC_PROFILE_VERSION
    )
    if classic_construction == THESIS_CONSTRUCTION:
        run = select_thesis_lineups(
            slate, objective, excluded, contract, count=count, forbidden_rosters=forbidden_rosters,
            time_limit_seconds=time_limit_seconds, classic_person_overlap=classic_person_overlap,
            protected=dict(judgment_decision.accepted) if judgment_decision is not None else None,
        )
        if judgment_decision is not None:
            # What the rows actually hold, recounted by the builder from the delivered rosters.
            judgment_decision.report["delivery"] = (run.construction or {}).get("placements")
    else:
        run = _sequential_lineups(
            slate, objective, excluded, contract, count=count, first_index=1,
            forbidden_rosters=forbidden_rosters, differentiate_captain=differentiate_captain,
            max_person_overlap=max_person_overlap, classic_person_overlap=classic_person_overlap,
            time_limit_seconds=time_limit_seconds,
        )
    selected = run.selected
    report = {
        "profile_version": selection_profile_version,
        "mode": slate.mode.value,
        "score_version": scores.score_version,
        "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
        "objective_limits": [
            "CENTRAL_ESTIMATE_NOT_A_CEILING",
            "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
            "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
        ],
        "differentiation": run.differentiation(slate),
        "lineups": len(selected),
        "excluded_rows": len(excluded),
        "kicker_role_excluded_people": sorted(zero_share_people),
        "kicker_roles": kicker_roles.as_report(),
        "offensive_roles": offense.report,
        "qb_depth_roles": qb_depth_report,
        "showdown_backup_qb_default": backup_default_report,
        "classic_backup_qb_default": classic_backup_default_report,
        **judgment_inputs,
        "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
        "selectable_people": len(contract.selectable_people),
        "person_exposure": run.person_exposure(slate),
        "forbidden_captain_rows": run.forbidden_captains,
        "non_optimal_lineups": [
            lineup.index for lineup in selected if lineup.solver_status != "OPTIMAL"
        ],
        "threshold_sensitive": list(scores.threshold_sensitive),
        "score_omissions": list(scores.omissions),
        "never_calls": ["field.py", "economics.py", "portfolio economics"],
    }
    if run.construction is not None:
        report["construction"] = run.construction
        report["unfilled_rows"] = count - len(selected)
        report["stopped"] = run.stopped
    verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
    verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
    _refuse_prefilled_repeats(selected, forbidden_keys)
    return tuple(selected), scores, report


def _refuse_unbuildable_thesis(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    thesis: ShowdownThesis,
    backups: frozenset[str],
    time_limit_seconds: float,
) -> None:
    """Raise `THESIS_UNBUILDABLE` when no single lineup can follow the thesis (Session 23b).

    One solve under the thesis and this run's exclusions alone, before any bank: no
    cap, overlap or structural bound, since those loosen and the thesis does not. Only
    a proved infeasibility drops it; a solve a limit stopped proves nothing.
    """

    optimizer = LineupOptimizer(
        slate, excluded_ids=tuple(sorted({*excluded, *thesis_excluded_dk_ids(slate, thesis, backups)})),
        time_limit_seconds=time_limit_seconds)
    apply_thesis_rows(optimizer, slate, thesis)
    if optimizer.solve(objective).status != "INFEASIBLE":
        return
    gone = set(excluded) | set(thesis_excluded_dk_ids(slate, thesis, backups))
    captains = sorted(person.underlying_id for person in thesis.captain_set if person.cpt_dk_id in gone)
    reason = ("every required Captain is out of this run's pool: " + ", ".join(captains)
              if len(captains) == len(thesis.captain_set)
              else "no legal lineup follows it under this run's exclusions")
    raise SelectionError(
        f"THESIS_UNBUILDABLE:thesis={thesis.name}:{reason}",
        status="THESIS_UNBUILDABLE",
        facts={"stage": "THESIS", "thesis": thesis.name, "reason": reason, "unavailable_captains": captains},
    )


def _thesis_report(
    policy: NormalizedPortfolioPolicy, rows: int, backups: frozenset[str], unevaluated: Sequence[str]
) -> dict[str, object]:
    """Each bound row's thesis and every declared thesis's state; a name is a label, not a number."""

    active = policy.active_thesis
    return {
        "build_version": THESIS_BUILD_VERSION,
        "theses": [{"name": thesis.name, "teams": list(thesis.teams), "status": thesis.status,
                    "dropped_reason": thesis.dropped_reason,
                    "captain_set": sorted(thesis.captain_people)} for thesis in policy.theses],
        "entries": {entry: (active.name if active is not None else None) for entry in policy.entry_ids[:rows]},
        "backup_quarterbacks_excluded": sorted(backups),
        # Teams whose quarterbacks no depth evidence orders: none of them was excluded.
        "backup_quarterbacks_unevaluated_teams": list(unevaluated) if active is not None else [],
        "does_not_establish": list(THESIS_DOES_NOT_ESTABLISH),
    }


@dataclass
class _Sequential:
    """One run of sequential selection: C1, or Showdown's captain-differentiated chain."""

    selected: list[SelectedLineup]
    forbidden_captains: list[str]
    captain_repeats_from_index: int | None
    differentiate_captain: bool
    effective_overlap: int | None
    requested_overlap: int | None = None
    overlap_relaxations: list[dict[str, object]] = field(default_factory=list)
    # Session 39b: the row an unbound fill stopped at (`index`, solver `status`), or None
    # when every requested row was built. Only the fill stops short; C1 and sequential
    # Showdown still raise.
    stopped: dict[str, object] | None = None
    # Session 49: the thesis construction's report block when rung 4 built the rows.
    construction: dict[str, object] | None = None

    def differentiation(self, slate: SlateContract) -> dict[str, object]:
        by_id = {player.dk_id: player for player in slate.players}
        return {
            "captain": (
                "NOT_APPLICABLE_CLASSIC"
                if slate.mode is EngineMode.CLASSIC
                else (
                    "DISTINCT_UNTIL_POOL_EXHAUSTED_THEN_REPEATED"
                    if self.captain_repeats_from_index is not None
                    else (
                        "DISTINCT_PER_ENTRY"
                        if self.differentiate_captain
                        else "UNCONSTRAINED"
                    )
                )
            ),
            "captain_repeats_from_index": self.captain_repeats_from_index,
            "captain_exposure": dict(
                sorted(
                    Counter(
                        by_id[lineup.captain_dk_id].underlying_id
                        for lineup in self.selected
                        if lineup.captain_dk_id
                    ).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            "max_person_overlap": self.effective_overlap,
            "requested_person_overlap": self.requested_overlap,
            "overlap_relaxations": list(self.overlap_relaxations),
            "basis": (
                (
                    "THESIS_SEQUENTIAL_EXACT_LINEUP_NO_GOODS_AND_PERSON_OVERLAP_CAP_NOT_A_PORTFOLIO_POLICY"
                    if self.construction is not None
                    else "SEQUENTIAL_EXACT_LINEUP_NO_GOODS_ONLY_C1_NOT_A_PORTFOLIO_POLICY"
                    if self.requested_overlap is None
                    else "SEQUENTIAL_EXACT_LINEUP_NO_GOODS_AND_PERSON_OVERLAP_CAP_C1_NOT_A_PORTFOLIO_POLICY"
                )
                if slate.mode is EngineMode.CLASSIC
                else "STRUCTURAL_UNIQUENESS_NOT_A_CORRELATED_EQUITY_CLAIM"
            ),
        }

    def person_exposure(self, slate: SlateContract) -> dict[str, int]:
        by_id = {player.dk_id: player for player in slate.players}
        exposure: dict[str, int] = {}
        for lineup in self.selected:
            for dk_id in lineup.roster:
                person = by_id[dk_id].underlying_id
                exposure[person] = exposure.get(person, 0) + 1
        return dict(sorted(exposure.items(), key=lambda item: (-item[1], item[0])))


def _sequential_lineups(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    contract: ParticipationContract,
    *,
    count: int,
    first_index: int,
    forbidden_rosters: Sequence[tuple[str, ...]],
    differentiate_captain: bool,
    max_person_overlap: int | None,
    time_limit_seconds: float,
    classic_person_overlap: int | None = CLASSIC_PERSON_OVERLAP,
    overlap_anchors: Sequence[tuple[str, ...]] = (),
    stage: str = "SEQUENTIAL",
) -> _Sequential:
    """`count` distinct lineups, one solve each, none equal to a forbidden roster.

    C1 and sequential Showdown raise `SOLVER_RETURNED_NO_LINEUP` when a row has no
    lineup. The unbound fill (`stage="UNBOUND_FILL"`, Session 39b) stops there
    instead and returns the rows before it with `stopped` set.

    C1 (Classic) and sequential Showdown, and since Session 11b the fill of the
    rows a subset policy leaves unbound. Lineups are numbered from `first_index`.

    Classic rows (Session 39) are also capped at `classic_person_overlap` shared
    people with every earlier row and with every `overlap_anchors` roster (the
    policy's own lineups, for a fill). A row no distinct lineup fits under that
    cap, proven infeasible, is solved again one person looser, up to
    `CLASSIC_MAX_USEFUL_OVERLAP`, and the step is recorded; the looser cap then
    holds for the rows that follow, so the walk costs at most a handful of model
    rebuilds however many rows there are. Distinctness is never on that walk.
    """

    by_id = {player.dk_id: player for player in slate.players}
    classic = slate.mode is EngineMode.CLASSIC
    requested_overlap = classic_person_overlap if classic else max_person_overlap
    anchors = tuple(tuple(map(str, roster)) for roster in overlap_anchors)

    def binds(cap: int | None) -> bool:
        # Classic rosters are distinct people, so a cap at the roster size less
        # one is the exact-roster cut alone and adds no row.
        return cap is not None and (not classic or cap < CLASSIC_MAX_USEFUL_OVERLAP)

    def cut(model: LineupOptimizer, roster: Sequence[str], cap: int | None) -> None:
        model.add_no_good(roster)
        if binds(cap):
            model.add_person_overlap_limit(roster, cap)

    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
    )
    for roster in forbidden_rosters:
        optimizer.add_no_good(roster)
    if binds(requested_overlap):
        for roster in anchors:
            optimizer.add_person_overlap_limit(roster, requested_overlap)
    current_overlap = requested_overlap  # the cap the model in `optimizer` holds
    selected: list[SelectedLineup] = []
    row_caps: list[int | None] = []
    overlap_relaxations: list[dict[str, object]] = []
    forbidden_captains: list[str] = []
    captain_repeats_from: int | None = None  # position in this run, 1-based
    stopped: dict[str, object] | None = None
    for position in range(1, count + 1):
        index = first_index + position - 1
        result = optimizer.solve(objective)
        if (
            result.roster is None
            and result.status == "INFEASIBLE"
            and classic
            and binds(current_overlap)
            and (selected or anchors)
        ):
            # The cap is what makes the next lineup impossible: the model is proven
            # infeasible, so this is not a time limit and not a pool with no
            # distinct lineup left. The cap is a construction preference, so it
            # steps up one person at a time on a model rebuilt with every earlier
            # row and anchor under the looser cap, and stays there for the rows
            # that follow (a ratchet: at most `CLASSIC_MAX_USEFUL_OVERLAP` minus
            # the requested cap rebuilds in a run, whatever the count, which the
            # deadline's per-solve sizing can afford). A solve that ended on a
            # time limit without a roster is not relaxed; it falls to the raise.
            first_status, before = result.status, current_overlap
            while result.roster is None and binds(current_overlap):
                current_overlap += 1
                optimizer = LineupOptimizer(
                    slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
                )
                for roster in forbidden_rosters:
                    optimizer.add_no_good(roster)
                for roster in anchors:
                    if binds(current_overlap):
                        optimizer.add_person_overlap_limit(roster, current_overlap)
                for earlier in selected:
                    cut(optimizer, earlier.roster, current_overlap)
                result = optimizer.solve(objective)
            if result.roster is not None:
                overlap_relaxations.append({
                    "index": index, "requested": requested_overlap, "from": before,
                    "used": current_overlap, "trigger_status": first_status,
                    "reason": "NO_DISTINCT_LINEUP_UNDER_THE_REQUESTED_OVERLAP_CAP",
                })
        row_cap = current_overlap
        if (
            result.roster is None
            and slate.mode is EngineMode.SHOWDOWN
            and differentiate_captain
            and selected
        ):
            # Every selectable person has already captained one lineup, so the
            # distinct-captain rule alone makes the next solve infeasible. That
            # is a structural limit of the pool, not a reason to hand back
            # nothing: rebuild the model without the captain no-goods, keep
            # every exact-roster and overlap cut, and continue with captain
            # repetition permitted. The index where repetition began is
            # reported so the review can see it.
            optimizer = LineupOptimizer(
                slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
            )
            for roster in forbidden_rosters:
                optimizer.add_no_good(roster)
            for earlier in selected:
                cut(optimizer, earlier.roster, current_overlap)
            differentiate_captain = False
            captain_repeats_from = position
            result = optimizer.solve(objective)
        if result.roster is None and stage == "UNBOUND_FILL":
            # Session 39b (R29): no distinct lineup is left for this row, or the solve
            # ended without one. The rows already built are delivered and the rest are
            # named by the caller; a lineup is never repeated to fill the gap.
            stopped = {"index": index, "status": result.status,
                       "proved_exhausted": result.status == "INFEASIBLE"}
            break
        if result.roster is None:
            raise SelectionError(
                f"SOLVER_RETURNED_NO_LINEUP:index={index}:status={result.status}"
                f":selectable_people={len(contract.selectable_people)}",
                status="SOLVER_RETURNED_NO_LINEUP",
                facts={"stage": stage, "index": index, "selected": len(selected),
                       "requested": count, "selectable_people": len(contract.selectable_people)},
            )
        roster = tuple(result.roster)
        validation = validate_lineup(slate, roster)
        if validation.lineup is None:
            raise SelectionError(
                f"SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:{validation.errors}"
            )
        blocked = set(excluded) & set(roster)
        if blocked:
            raise SelectionError(
                f"SOLVER_SELECTED_AN_EXCLUDED_ROW:index={index}:{sorted(blocked)}"
            )
        captain = roster[0] if slate.mode is EngineMode.SHOWDOWN else ""
        selected.append(
            SelectedLineup(
                index=index,
                roster=roster,
                captain_dk_id=captain,
                salary=validation.lineup.salary,
                prior_points=sum(objective[dk_id] for dk_id in roster),
                canonical_key=validation.lineup.canonical_key,
                solver_status=result.status,
                solver_seconds=result.elapsed_seconds,
            )
        )
        row_caps.append(row_cap)
        if position == count:
            break
        # Forbid this exact roster, cap how much personnel may carry over, and
        # optionally forbid a repeat captain. Without the overlap cap the next
        # solve returns the same six people with a rotated captain.
        cut(optimizer, roster, current_overlap)
        if differentiate_captain and slate.mode is EngineMode.SHOWDOWN:
            optimizer.add_no_good([captain])
            forbidden_captains.append(captain)

    keys = [lineup.canonical_key for lineup in selected]
    if len(set(keys)) != len(keys):
        raise SelectionError("DUPLICATE_LINEUP_SELECTED")
    distinct_captain_span = (
        selected[: captain_repeats_from - 1]
        if captain_repeats_from is not None
        else selected
    )
    if slate.mode is EngineMode.SHOWDOWN and (
        differentiate_captain or captain_repeats_from is not None
    ):
        captains = [lineup.captain_dk_id for lineup in distinct_captain_span]
        if len(set(captains)) != len(captains):
            raise SelectionError("DUPLICATE_CAPTAIN_SELECTED")

    # The backstop: every row shares at most the cap it was solved under with
    # every earlier row (and, for a fill, with every anchor).
    people = [{by_id[dk].underlying_id for dk in lineup.roster} for lineup in selected]
    anchor_people = [{by_id[dk].underlying_id for dk in roster} for roster in anchors]
    for later, cap in enumerate(row_caps):
        if not binds(cap):
            continue
        for earlier in range(later):
            shared = len(people[earlier] & people[later])
            if shared > cap:
                raise SelectionError(
                    f"OVERLAP_LIMIT_BREACHED:{earlier + 1}v{later + 1}:{shared}>{cap}"
                )
        for position, held in enumerate(anchor_people, start=1):
            shared = len(held & people[later])
            if shared > cap:
                raise SelectionError(
                    f"OVERLAP_LIMIT_BREACHED:anchor{position}v{later + 1}:{shared}>{cap}"
                )
    used = [cap for cap in row_caps if cap is not None]
    return _Sequential(
        selected=selected,
        forbidden_captains=forbidden_captains,
        captain_repeats_from_index=(
            None if captain_repeats_from is None else first_index + captain_repeats_from - 1
        ),
        differentiate_captain=differentiate_captain,
        effective_overlap=(max(used) if used else None) if requested_overlap is not None else None,
        requested_overlap=requested_overlap,
        overlap_relaxations=overlap_relaxations,
        stopped=stopped,
    )


def _fill_exclusions(
    run_excluded: Sequence[str],
    portfolio_policy: NormalizedPortfolioPolicy | NormalizedClassicPortfolioPolicy | None,
) -> tuple[str, ...]:
    """The rows an unbound fill may never use (Session 39, review S6).

    The run's own exclusions, plus every exact DraftKings ID the policy itself
    removes (an exact exclusion, a person it caps at zero, and in Classic a team
    or game it caps at zero): the same set rung 4 carries as operator exclusions.
    """

    return tuple(sorted(set(map(str, run_excluded)) | set(own_exclusion_dk_ids(portfolio_policy))))


def _objective(slate: SlateContract, scores: PriorScores, excluded: Sequence[str]) -> dict[str, float]:
    """Prior points by DraftKings ID, zero for every excluded row.

    Every row of an unavailable person is scoreless as well as excluded, so a
    solver bug that ignored the exclusion could not profit from it either.
    """

    blocked = set(excluded)
    objective = {
        dk_id: (0.0 if dk_id in blocked else value)
        for dk_id, value in scores.by_dk_id.items()
    }
    for player in slate.players:
        objective.setdefault(player.dk_id, 0.0)
    return objective


def _fill_unbound(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    contract: ParticipationContract,
    *,
    policy_lineups: list[SelectedLineup],
    forbidden_rosters: Sequence[tuple[str, ...]],
    count: int,
    differentiate_captain: bool,
    max_person_overlap: int | None,
    time_limit_seconds: float,
    classic_person_overlap: int | None = CLASSIC_PERSON_OVERLAP,
) -> tuple[list[SelectedLineup], dict[str, object]]:
    """The rows a subset policy leaves unbound, filled after its joint solve (Session 11b).

    C1 (Classic) or sequential Showdown, under the run's own exclusions and the
    policy's exact ones (Session 39), with every policy lineup and every prefilled
    roster as a no-good (R29).

    A fill that runs out of distinct lineups at row k (Session 39b) returns the k
    rows it built, none repeated, and says so in its report: `requested`,
    `lineups` (k), `unfilled_rows` and `stopped` (the row, the solver's status and
    whether it was proven that none was left). The caller names the unfilled Entry
    IDs; nothing here cycles a lineup into them.
    """

    run = _sequential_lineups(
        slate, objective, excluded, contract, count=count, first_index=len(policy_lineups) + 1,
        forbidden_rosters=(*forbidden_rosters, *(lineup.roster for lineup in policy_lineups)),
        differentiate_captain=differentiate_captain, max_person_overlap=max_person_overlap,
        classic_person_overlap=classic_person_overlap,
        # The fill's rows are also capped against the policy's own lineups, so they are
        # not near copies of a bound row (Session 39); the exact-roster cut above stays.
        overlap_anchors=(
            tuple(lineup.roster for lineup in policy_lineups)
            if slate.mode is EngineMode.CLASSIC else ()
        ),
        time_limit_seconds=time_limit_seconds, stage="UNBOUND_FILL",
    )
    policy_keys = {lineup.canonical_key for lineup in policy_lineups}
    repeated = [lineup.index for lineup in run.selected if lineup.canonical_key in policy_keys]
    if repeated:
        raise SelectionError(
            f"DUPLICATE_LINEUP_SELECTED:unbound fill indexes {repeated} repeat a policy lineup")
    classic = slate.mode is EngineMode.CLASSIC
    report = {
        "source": "C1" if classic else "SHOWDOWN_SEQUENTIAL",
        "profile_version": CLASSIC_PROFILE_VERSION if classic else PROFILE_VERSION,
        "requested": count,
        "lineups": len(run.selected),
        "unfilled_rows": count - len(run.selected),
        "stopped": run.stopped,
        "lineup_indexes": [lineup.index for lineup in run.selected],
        "no_good_rosters": {"policy_lineups": len(policy_lineups),
                            "prefilled_rosters": len(forbidden_rosters)},
        "exclusions": "THE_RUN_S_OWN_AND_THE_POLICY_S_EXACT_EXCLUSIONS",
        "excluded_rows": len(excluded),
        "differentiation": run.differentiation(slate),
        "person_exposure": run.person_exposure(slate),
        "forbidden_captain_rows": run.forbidden_captains,
        "non_optimal_lineups": [
            lineup.index for lineup in run.selected if lineup.solver_status != "OPTIMAL"
        ],
    }
    return [*policy_lineups, *run.selected], report


def _refuse_prefilled_repeats(selected: Sequence[SelectedLineup], forbidden_keys: set[str]) -> None:
    """The backstop (Session 11): no selected lineup is a prefilled roster (R29)."""

    repeated = [lineup.index for lineup in selected if lineup.canonical_key in forbidden_keys]
    if repeated:
        raise SelectionError(f"ENTRY_PREFILLED_LINEUP_REPEATED:selection_indexes={repeated}")


def assignments_for_entries(
    entry_ids: Sequence[str], lineups: Sequence[SelectedLineup]
) -> dict[str, tuple[str, ...]]:
    """Map reserved entries onto lineups, cycling if there are fewer lineups.

    Cycling is explicit rather than silent: asking for two lineups across five
    entries means three entries repeat, and the caller reports that.
    """

    if not entry_ids:
        raise SelectionError("NO_RESERVED_ENTRIES")
    if not lineups:
        raise SelectionError("NO_LINEUPS_TO_ASSIGN")
    return {
        entry_id: lineups[index % len(lineups)].roster
        for index, entry_id in enumerate(entry_ids)
    }
