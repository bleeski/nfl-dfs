"""One gated entry point for the prior-only Showdown and Classic review chain.

R02, the `cowork-run` half. `select` and `review-export` already exist and are
tested; what was missing was a single command that drives the whole chain, so a
session had to orchestrate six CLI calls by hand from a skill.

This module owns that orchestration and nothing else. It adds no economics, no
ownership, leverage, correlation or duplication model, and no new numerical
transformation. Every number still comes from `priors.py`, `projection.py` and
`prior_score.py`. Output is `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` on every path, including the success path.

Three gates are genuinely human and stay human:

1. Identity. `projection.py` accepts only `match_method="EXACT"`, so a package
   cannot be frozen on a guess. The one automatic acceptance is a unique
   league-wide name and position match for a person DraftKings has flagged `OUT`
   or `IR`: the availability contract makes those people unselectable, so an
   accepted-but-uncertain identity can never reach a lineup. Every auto-accept
   and its reason is recorded.
2. Weather. A game the schedule artifact cannot resolve on its own needs an
   operator capture with its URI and observation time. Since Session 09 (R28) a
   game without one is frozen `UNOBSERVED` and named, never blocked, and a state
   typed without a capture is never used.
3. Staleness. The team prior inherits `MARKET_LINE_MOVES_INTRADAY` from
   `games.csv`, which expires twelve hours after capture. A same-day re-run is
   the normal case. An expired package is rebuilt, never widened.
"""

from __future__ import annotations

from contextlib import nullcontext

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .contracts import (
    EngineMode,
    EvidenceState,
    SalaryPlayer,
    SlateContract,
    SourceFreshness,
    earliest_expiry,
    earliest_source_freshness,
)
from .classic_portfolio import (
    assignment_artifact_bytes,
    audit_classic_portfolio,
    exact_classic_assignments,
)
from .classic_portfolio_policy import NormalizedClassicPortfolioPolicy
from .classic_review import (
    SCORE_SNAPSHOT_VERSION,
    ClassicReviewPresentationError,
    create_classic_review_package,
)
from .dk import (
    PARSER_VERSION as DK_PARSER_VERSION,
    parse_entries,
    parse_salaries,
    reconcile_template,
)
from .entry_groups import plan_entries, subset_binding_problems, unbound_rows
from .evidence import parse_official_inactive_snapshot
from .hashing import sha256_bytes, sha256_file
from .kicker_roles import verify_kicker_role_resolution
from .opportunity import load_opportunity_model
from .offensive_roles import OffensiveRoleError, attach_history, verify_offensive_resolution
from .participation import (
    UNAVAILABLE_STATUSES,
    ParticipationContract,
    build_participation_contract,
    redistribute_opportunity,
)
from .prior_score import read_team_splits
from .priors import (
    ACCEPTED_DECISION,
    IDENTITY_MAP_FILENAME,
    IdentityProposal,
    PACKAGE_FILENAME,
    PLAYER_PRIOR_FILENAME,
    PROPOSAL_FILENAME,
    RAW_DIRNAME,
    REVIEW_COLUMNS,
    TEAM_PRIOR_FILENAME,
    freeze_prior_package,
    propose_prior_package,
)
from .projection import build_projection_package
from .deadline import BANK_SHARE, JOINT_SHARE, SOLVE_MINIMUM_SECONDS, Budget
from .portfolio_enforcement import (
    DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    audit_policy_assignments,
    exact_assignments_for_entries,
    scaled_candidate_seconds,
    scaled_selection_seconds,
)
from .portfolio_policy import NormalizedPortfolioPolicy
from .prelock_manifest import (
    PredictionArtifact,
    PrelockManifestError,
    build_prelock_manifest,
    write_prelock_manifest,
)
from .review_export import export_review_entries, write_assignments_csv, write_run_record
from .selection import SelectionError, assignments_for_entries, select_prior_lineups
from .sources import SourcePolicyError, validate_source_reference_policy
from .venues import home_team_of, resolve_blank_roof


PROFILE_VERSION = "cowork_prior_review_v1"
CLASSIC_PROFILE_VERSION = "cowork_classic_prior_review_c1_v1"
CLASSIC_PROFILE_VERSION_C2 = "cowork_classic_prior_review_c2_v1"
CLASSIC_PROFILE_VERSION_C3 = "cowork_classic_prior_review_c3_v1"
CLASSIC_SELECTION_SCHEMA = "nfl_classic_prior_review_selection_c1_v1"
CLASSIC_SELECTION_SCHEMA_C2 = "nfl_classic_prior_review_selection_c2_v1"
CLASSIC_COVERAGE_SCHEMA = "nfl_classic_slate_coverage_c1_v1"
CLASSIC_COVERAGE_SCHEMA_C2 = "nfl_classic_slate_coverage_c2_v1"

# nflverse roof values the frozen schedule artifact resolves without any
# operator input. `priors._ROOF_WEATHER` also maps "open", but a retractable
# roof left open is played in the weather, so this profile still names a
# missing capture (WEATHER_UNOBSERVED) rather than treating the schedule as the
# whole answer.
SCHEDULE_DERIVABLE_ROOFS = frozenset({"dome", "closed"})
ROOF_STATE_IS_SCHEDULE_AUTHORITATIVE = frozenset({"dome", "closed", "open"})

# The single automatic identity acceptance. `propose_identities` emits this
# method when exactly one league-wide roster row matches the person's normalized
# name and position, and that row sits on a different nflverse team than
# DraftKings lists.
AUTO_ACCEPT_MATCH_METHOD = "NAME_POSITION_OTHER_TEAM"

STAGES = ("PRIORS", "IDENTITY", "PROJECT", "SELECT", "EXPORT")


class PriorReviewError(ValueError):
    """A named fail-closed prior-review orchestration error."""


# --------------------------------------------------------------------------- #
# Slate-derived inputs that need no human
# --------------------------------------------------------------------------- #


def derive_season(lock_at: datetime) -> int:
    """The NFL season a kickoff belongs to, from the slate's own bytes.

    The league year rolls over in March, so a January playoff game belongs to the
    previous season. This is slate geometry read out of the DraftKings file, not
    a model value, and the derivation is recorded in the run report.
    """

    moment = lock_at.astimezone(timezone.utc)
    return moment.year if moment.month >= 3 else moment.year - 1


# --------------------------------------------------------------------------- #
# Frozen prior package resolution
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResolvedPriorPackage:
    package_dir: str
    team_source: str
    player_source: str
    identity_map: str
    hashes: dict[str, str]
    season: int
    prior_season: int
    salary_artifact_id: str
    frozen_sources: dict[str, str]
    expires_at: str
    expiry_basis: str
    expired: bool
    freshness_state: str
    proposal_dir: str

    def as_report(self) -> dict[str, object]:
        return {
            "package_dir": self.package_dir,
            "hashes": dict(sorted(self.hashes.items())),
            "season": self.season,
            "prior_season": self.prior_season,
            "salary_artifact_id": self.salary_artifact_id,
            "expires_at": self.expires_at,
            "expiry_basis": self.expiry_basis,
            "expired": self.expired,
            "freshness_state": self.freshness_state,
        }


def _read_json(path: Path, code: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriorReviewError(f"{code}:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise PriorReviewError(f"{code}:{path}:not a JSON object")
    return payload


def _parse_moment(value: object, *, label: str) -> datetime:
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PriorReviewError(f"{label}_NOT_A_TIMESTAMP:{value!r}") from exc
    if moment.tzinfo is None:
        raise PriorReviewError(f"{label}_NOT_TIMEZONE_AWARE:{value!r}")
    return moment.astimezone(timezone.utc)


def _freshness_record(
    *,
    label: str,
    basis: str,
    expires_at: datetime,
    declared_state: object,
    where: str,
) -> SourceFreshness:
    """One frozen artifact's freshness, on the shared contract."""

    state = EvidenceState.PASS
    if declared_state is not None:
        try:
            state = EvidenceState(str(declared_state))
        except ValueError as exc:
            raise PriorReviewError(
                f"PRIOR_ARTIFACT_EVIDENCE_STATE_UNKNOWN:{where}:{declared_state!r}"
            ) from exc
    try:
        return SourceFreshness(
            label=label, basis=basis, expires_at=expires_at, declared_state=state
        )
    except ValueError as exc:
        raise PriorReviewError(f"PRIOR_ARTIFACT_FRESHNESS_INVALID:{where}:{exc}") from exc


def resolve_prior_package(
    package_dir: str | Path, *, salary_sha256: str, as_of: datetime
) -> ResolvedPriorPackage:
    """Rehydrate a frozen prior package, hash-checked and expiry-checked.

    Every published artifact is re-hashed against `prior_package.json`. A
    mismatch is a hard stop, never a warning: a package whose bytes moved after
    publication is not the package that was reviewed.
    """

    root = Path(package_dir).resolve()
    if not root.is_dir():
        raise PriorReviewError(f"PRIOR_PACKAGE_DIR_MISSING:{root}")
    package = _read_json(root / PACKAGE_FILENAME, "PRIOR_PACKAGE_UNREADABLE")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise PriorReviewError(f"PRIOR_PACKAGE_HAS_NO_ARTIFACTS:{root}")

    hashes: dict[str, str] = {}
    for filename in (TEAM_PRIOR_FILENAME, PLAYER_PRIOR_FILENAME, IDENTITY_MAP_FILENAME):
        expected = str(artifacts.get(filename, "")).strip().lower()
        path = root / filename
        if not path.is_file():
            raise PriorReviewError(f"PRIOR_ARTIFACT_MISSING:{filename}:{path}")
        if len(expected) != 64:
            raise PriorReviewError(f"PRIOR_ARTIFACT_HASH_UNRECORDED:{filename}")
        actual = sha256_file(path)
        if actual != expected:
            raise PriorReviewError(
                f"PRIOR_ARTIFACT_HASH_MISMATCH:{filename}"
                f":expected={expected}:actual={actual}"
            )
        hashes[filename] = actual

    recorded_salary = str(package.get("salary_artifact_id", "")).strip().lower()
    if recorded_salary != salary_sha256.strip().lower():
        raise PriorReviewError(
            "PRIOR_PACKAGE_SALARY_MISMATCH:"
            f"package={recorded_salary}:slate={salary_sha256.strip().lower()}"
        )

    # R08: this used to be a second implementation of the freshness rule,
    # reading `expires_at` straight out of artifact metadata. It now composes
    # `SourceFreshness` records and lets the shared contract decide, so the
    # producer, the ledger validator and this resolver cannot drift apart.
    records: list[SourceFreshness] = []
    for filename in (TEAM_PRIOR_FILENAME, PLAYER_PRIOR_FILENAME, IDENTITY_MAP_FILENAME):
        payload = _read_json(root / filename, "PRIOR_ARTIFACT_UNREADABLE")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise PriorReviewError(f"PRIOR_ARTIFACT_METADATA_MISSING:{filename}")
        coverage = metadata.get("coverage")
        basis = ""
        if isinstance(coverage, dict):
            basis = str(coverage.get("expiry_basis", ""))
        records.append(
            _freshness_record(
                label=f"{filename}:{basis or 'UNRECORDED'}",
                basis=basis or "UNRECORDED",
                expires_at=_parse_moment(
                    metadata.get("expires_at"), label="PRIOR_ARTIFACT_EXPIRES_AT"
                ),
                declared_state=metadata.get("evidence_state"),
                where=filename,
            )
        )
        salary_artifact = payload.get("salary_artifact")
        if isinstance(salary_artifact, dict) and salary_artifact.get("expires_at"):
            records.append(
                _freshness_record(
                    label=f"{filename}:salary_artifact:GAME_LOCK_HORIZON",
                    basis="GAME_LOCK_HORIZON",
                    expires_at=_parse_moment(
                        salary_artifact["expires_at"],
                        label="SALARY_ARTIFACT_EXPIRES_AT",
                    ),
                    declared_state=salary_artifact.get("evidence_state"),
                    where=f"{filename}:salary_artifact",
                )
            )

    binding = earliest_source_freshness(records, at=as_of)
    state = binding.state_at(as_of)
    # The state comes from the worst source, the window from the earliest
    # expiry. They are the same record whenever every source is PASS, which is
    # the only shape `priors.freeze_prior_package` emits.
    earliest, basis = earliest_expiry(records), binding.label
    return ResolvedPriorPackage(
        package_dir=str(root),
        team_source=str(root / TEAM_PRIOR_FILENAME),
        player_source=str(root / PLAYER_PRIOR_FILENAME),
        identity_map=str(root / IDENTITY_MAP_FILENAME),
        hashes=hashes,
        season=int(package["season"]),
        prior_season=int(package["prior_season"]),
        salary_artifact_id=recorded_salary,
        frozen_sources={
            str(key): str(value)
            for key, value in dict(package.get("frozen_sources") or {}).items()
        },
        expires_at=earliest.isoformat(),
        expiry_basis=basis,
        expired=state is not EvidenceState.PASS,
        freshness_state=state.value,
        proposal_dir=str(package.get("package_dir") or ""),
    )


@dataclass(frozen=True)
class ResolvedFrozenArtifact:
    """One content-addressed frozen artifact and how it was found."""

    path: Path
    resolution: str
    searched: tuple[str, ...]

    def as_report(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "resolution": self.resolution,
            "searched": list(self.searched),
        }


def resolve_frozen_artifact(
    digest: str,
    *,
    package_dir: str | Path,
    fallback_roots: Sequence[Path] = (),
    label: str,
) -> ResolvedFrozenArtifact:
    """Find one content-addressed frozen artifact and re-verify its bytes.

    R08: this searched four candidate directories because a frozen package was
    not self-contained. A package archives its own raw sources under
    `raw/<sha256>.csv`, so the in-package lookup is the contract and the wider
    search is a recorded fallback for a package published before that was true.
    Which one answered is reported rather than hidden, because resolving out of
    a sibling directory means the package that gets copied is not the package
    that was reviewed.
    """

    expected = digest.strip().lower()
    if len(expected) != 64:
        raise PriorReviewError(f"FROZEN_ARTIFACT_HASH_UNRECORDED:{label}")

    def verified(candidate: Path) -> Path | None:
        if not candidate.is_file():
            return None
        actual = sha256_file(candidate)
        if actual != expected:
            raise PriorReviewError(
                f"FROZEN_ARTIFACT_HASH_MISMATCH:{label}"
                f":expected={expected}:actual={actual}:{candidate}"
            )
        return candidate.resolve()

    root = Path(package_dir)
    seen: list[str] = []
    for candidate in (root / RAW_DIRNAME / f"{expected}.csv", root / f"{expected}.csv"):
        seen.append(str(candidate))
        found = verified(candidate)
        if found is not None:
            return ResolvedFrozenArtifact(found, "IN_PACKAGE", tuple(seen))
    for fallback in fallback_roots:
        for candidate in (
            Path(fallback) / RAW_DIRNAME / f"{expected}.csv",
            Path(fallback) / f"{expected}.csv",
        ):
            seen.append(str(candidate))
            found = verified(candidate)
            if found is not None:
                return ResolvedFrozenArtifact(found, "FALLBACK_SEARCH", tuple(seen))
    raise PriorReviewError(
        f"FROZEN_ARTIFACT_UNRESOLVED:{label}:{expected}:searched={seen[:6]}"
    )


# --------------------------------------------------------------------------- #
# The two-phase identity gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IdentityDecision:
    dk_id: str
    dk_name: str
    dk_team: str
    dk_position: str
    dk_status: str
    match_method: str
    provider_player_id: str
    provider_name: str
    provider_team: str
    provider_status: str
    decision: str
    basis: str

    def as_payload(self) -> dict[str, object]:
        return {
            "dk_id": self.dk_id,
            "dk_name": self.dk_name,
            "dk_team": self.dk_team,
            "dk_position": self.dk_position,
            "dk_status": self.dk_status or "BLANK",
            "match_method": self.match_method,
            "provider_player_id": self.provider_player_id,
            "provider_name": self.provider_name,
            "provider_team": self.provider_team,
            "provider_status": self.provider_status,
            "decision": self.decision or "UNRESOLVED",
            "basis": self.basis,
        }


@dataclass(frozen=True)
class IdentityGateResult:
    decisions: tuple[IdentityDecision, ...]
    auto_accepted: tuple[IdentityDecision, ...]
    blocked: tuple[IdentityDecision, ...]
    blockers: tuple[str, ...]

    def as_report(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for item in self.decisions:
            counts[item.match_method] = counts.get(item.match_method, 0) + 1
        return {
            "gate_version": PROFILE_VERSION,
            "people": len(self.decisions),
            "auto_accepted": len(self.auto_accepted),
            "blocked": len(self.blocked),
            "match_methods": dict(sorted(counts.items())),
            "auto_accept_rule": (
                "unique league-wide normalized name and position match, accepted only"
                f" for a DraftKings status in {sorted(UNAVAILABLE_STATUSES)} because the"
                " availability contract makes those people unselectable"
            ),
            "auto_accept_detail": [item.as_payload() for item in self.auto_accepted],
            "blocked_detail": [item.as_payload() for item in self.blocked],
        }


def _proposals_from_payload(package_dir: Path) -> tuple[IdentityProposal, ...]:
    payload = _read_json(package_dir / PROPOSAL_FILENAME, "IDENTITY_PROPOSAL_UNREADABLE")
    rows = payload.get("proposals")
    if not isinstance(rows, list) or not rows:
        raise PriorReviewError(f"IDENTITY_PROPOSAL_EMPTY:{package_dir}")
    return tuple(
        IdentityProposal(
            dk_id=item["dk_id"],
            captain_dk_id=item["captain_dk_id"],
            dk_name=item["dk_name"],
            dk_team=item["dk_team"],
            dk_position=item["dk_position"],
            underlying_id=item["underlying_id"],
            nflverse_team=item["nflverse_team"],
            provider_player_id=item["provider_player_id"],
            provider_name=item["provider_name"],
            provider_pfr_id=item["provider_pfr_id"],
            provider_team=item.get("provider_team", ""),
            provider_status=item.get("provider_status", ""),
            match_method=item["match_method"],
            candidates=tuple(item.get("candidates") or ()),
        )
        for item in rows
    )


def apply_identity_gate(
    proposals: Sequence[IdentityProposal], status_by_dk_id: Mapping[str, str]
) -> IdentityGateResult:
    """Decide every proposed identity, or stop and say exactly which one failed.

    Nothing looser than the recorded rule is accepted. A row the proposal already
    resolved carries its own method. One unique league-wide name and position
    match is accepted for an `OUT` or `IR` person only. Everything else stops the
    run and reports the candidate provider ID, the conflicting nflverse team and
    the roster status, which is what a human needs to settle it.
    """

    decisions: list[IdentityDecision] = []
    auto: list[IdentityDecision] = []
    blocked: list[IdentityDecision] = []
    blockers: list[str] = []
    for proposal in proposals:
        status = (status_by_dk_id.get(proposal.dk_id, "") or "").strip().upper()
        unavailable = status in UNAVAILABLE_STATUSES
        if proposal.resolved:
            decision = IdentityDecision(
                dk_id=proposal.dk_id,
                dk_name=proposal.dk_name,
                dk_team=proposal.dk_team,
                dk_position=proposal.dk_position,
                dk_status=status,
                match_method=proposal.match_method,
                provider_player_id=proposal.provider_player_id,
                provider_name=proposal.provider_name,
                provider_team=proposal.provider_team,
                provider_status=proposal.provider_status,
                decision=ACCEPTED_DECISION,
                basis=f"PROPOSAL_RESOLVED:{proposal.match_method}",
            )
            decisions.append(decision)
            continue
        if (
            proposal.match_method == AUTO_ACCEPT_MATCH_METHOD
            and unavailable
            and proposal.provider_player_id
        ):
            decision = IdentityDecision(
                dk_id=proposal.dk_id,
                dk_name=proposal.dk_name,
                dk_team=proposal.dk_team,
                dk_position=proposal.dk_position,
                dk_status=status,
                match_method=proposal.match_method,
                provider_player_id=proposal.provider_player_id,
                provider_name=proposal.provider_name,
                provider_team=proposal.provider_team,
                provider_status=proposal.provider_status,
                decision=ACCEPTED_DECISION,
                basis=(
                    "AUTO_ACCEPT_UNIQUE_LEAGUE_NAME_POSITION"
                    f":dk_status={status}:nflverse_team={proposal.provider_team or 'NONE'}"
                    f":roster_status={proposal.provider_status or 'NONE'}"
                    ":unselectable_under_the_availability_contract"
                ),
            )
            decisions.append(decision)
            auto.append(decision)
            continue
        decision = IdentityDecision(
            dk_id=proposal.dk_id,
            dk_name=proposal.dk_name,
            dk_team=proposal.dk_team,
            dk_position=proposal.dk_position,
            dk_status=status,
            match_method=proposal.match_method,
            provider_player_id=proposal.provider_player_id,
            provider_name=proposal.provider_name,
            provider_team=proposal.provider_team,
            provider_status=proposal.provider_status,
            decision="",
            basis="UNRESOLVED",
        )
        decisions.append(decision)
        blocked.append(decision)
        code = (
            "IDENTITY_UNRESOLVED_AND_UNAVAILABLE"
            if unavailable
            else "IDENTITY_UNRESOLVED_AND_AVAILABLE"
        )
        blockers.append(
            f"{code}:{proposal.dk_id}:{proposal.dk_name}:{proposal.dk_position}"
            f":dk_team={proposal.dk_team}:dk_status={status or 'BLANK'}"
            f":match_method={proposal.match_method}"
            f":candidate_provider_id={proposal.provider_player_id or 'NONE'}"
            f":nflverse_team={proposal.provider_team or 'NONE'}"
            f":roster_status={proposal.provider_status or 'NONE'}"
            f":candidates={list(proposal.candidates[:4]) or 'NONE'}"
        )
    return IdentityGateResult(
        decisions=tuple(decisions),
        auto_accepted=tuple(auto),
        blocked=tuple(blocked),
        blockers=tuple(blockers),
    )


def write_reviewed_decisions(path: str | Path, result: IdentityGateResult) -> str:
    """Write the decision file `priors-freeze` reads, in its own column order."""

    import csv as _csv
    import io as _io

    buffer = _io.StringIO(newline="")
    writer = _csv.writer(buffer, lineterminator="\n")
    writer.writerow(REVIEW_COLUMNS)
    for item in result.decisions:
        writer.writerow(
            (
                item.dk_id,
                item.dk_name,
                item.dk_team,
                item.dk_position,
                item.provider_player_id,
                item.provider_name,
                item.provider_team,
                item.provider_status,
                item.match_method,
                item.decision,
                "",
            )
        )
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(buffer.getvalue().encode("utf-8"))
    temporary.replace(target)
    return sha256_file(target)


# --------------------------------------------------------------------------- #
# The weather gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WeatherDecision:
    roof: str
    freeze_weather_state: str | None
    freeze_source_uri: str | None
    freeze_observed_at: str | None
    basis: str
    # Since Session 09 (R28) missing weather is named here and never blocks.
    limitations: tuple[str, ...] = ()

    def as_report(self) -> dict[str, object]:
        return {
            "roof": self.roof or "BLANK",
            "basis": self.basis,
            "operator_state_passed_to_freeze": self.freeze_weather_state,
            "operator_source_uri": self.freeze_source_uri,
            "operator_observed_at": self.freeze_observed_at,
            "limitations": list(self.limitations),
        }


def decide_weather(
    roof: str,
    *,
    game_id: str | None = None,
    venue_roof_history: Mapping[str, Mapping[str, int]] | None = None,
    venue_roof_seasons: Sequence[int | str] | None = None,
    weather_state: str | None = None,
    weather_source_uri: str | None = None,
    weather_observed_at: str | None = None,
) -> WeatherDecision:
    """Resolve the weather enum from the schedule, or name the game nobody observed.

    A fixed or retracted-closed roof is decided by the frozen schedule artifact
    alone. Every other value, including a retractable roof left open, is
    observed only by an `api.weather.gov` capture with its URI and its
    `generatedAt`. Until Session 09 a game without one blocked the run
    (`WEATHER_CAPTURE_REQUIRED`, `WEATHER_STATE_REQUIRED`). Under R28 it is a
    named `WEATHER_UNOBSERVED` limitation instead: the freeze records the game as
    `UNOBSERVED` (an open roof stays schedule-derived `ROOF_OPEN`), and a state
    typed without a capture is never passed on, because it is not an observation.

    A blank cell used to fall in with "every other value", and on 2026-09-20 that
    cost two of five games on a live slate: nflverse writes `roof` only after the
    game, so an unplayed game at a retractable venue is always blank. Given
    `game_id` and that venue's counts from the frozen artifact, a blank resolves
    from the venue's own unanimous history instead. An attributed capture is
    still checked first and still wins, because an observation outranks a count.
    """

    normalized = (roof or "").strip().lower()
    state = (weather_state or "").strip().upper() or None
    uri = (weather_source_uri or "").strip() or None
    observed = (weather_observed_at or "").strip() or None
    attributed = bool(uri and observed)

    # A typed state with no capture is dropped below, so it does not keep a
    # blank from resolving here: the freeze resolves the same blank the same way.
    if not normalized and not attributed:
        resolved = resolve_blank_roof(
            home_team_of(game_id or ""),
            venue_roof_history,
            seasons=venue_roof_seasons,
        )
        if resolved is not None:
            venue_roof, venue_basis = resolved
            return WeatherDecision(
                roof=venue_roof,
                freeze_weather_state=None,
                freeze_source_uri=None,
                freeze_observed_at=None,
                basis=venue_basis,
            )

    # Nothing unattributed is passed on from here, not even for a game the
    # schedule resolves: the legacy freeze reads the first game's fields as
    # the scalar capture, and an unsourced state there would stop a multi-game
    # Classic freeze (CLASSIC_WEATHER_SCOPE_AMBIGUOUS) on a value nobody observed.
    if normalized in SCHEDULE_DERIVABLE_ROOFS:
        return WeatherDecision(
            roof=normalized,
            freeze_weather_state=state if attributed else None,
            freeze_source_uri=uri if attributed else None,
            freeze_observed_at=observed if attributed else None,
            basis=f"SCHEDULE_ROOF_IS_AUTHORITATIVE:{normalized}",
        )

    unobserved = (
        f"WEATHER_UNOBSERVED:roof={normalized or 'BLANK'}:no attributed api.weather.gov"
        " capture (URI and generatedAt) for this game"
        + (f"; the unattributed state {state} was not used" if state and not attributed else "")
    )
    if normalized in ROOF_STATE_IS_SCHEDULE_AUTHORITATIVE:
        # The schedule artifact already resolves this roof. The game is played
        # in the weather, so a missing capture is named, but the state itself
        # stays schedule-derived so the two cannot disagree.
        return WeatherDecision(
            roof=normalized,
            freeze_weather_state=None,
            freeze_source_uri=uri if attributed else None,
            freeze_observed_at=observed if attributed else None,
            basis=f"SCHEDULE_ROOF_IS_AUTHORITATIVE_CAPTURE_REPORTED_ONLY:{normalized}",
            limitations=() if attributed else (unobserved,),
        )
    if not attributed or state is None:
        return WeatherDecision(
            roof=normalized,
            freeze_weather_state=None,
            freeze_source_uri=None,
            freeze_observed_at=None,
            basis=f"WEATHER_UNOBSERVED:{normalized or 'BLANK'}",
            limitations=(
                unobserved
                if not attributed
                else f"WEATHER_UNOBSERVED:roof={normalized or 'BLANK'}:the capture carries"
                " no weather state",
            ),
        )
    return WeatherDecision(
        roof=normalized,
        freeze_weather_state=state,
        freeze_source_uri=uri,
        freeze_observed_at=observed,
        basis=f"OPERATOR_CAPTURE_REQUIRED:{normalized or 'BLANK'}",
    )


# --------------------------------------------------------------------------- #
# The orchestrated run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PriorReviewOutcome:
    profile_version: str
    stage: str
    blocked: bool
    blockers: tuple[str, ...]
    stages: tuple[dict[str, object], ...]
    artifacts: dict[str, str]
    hashes: dict[str, str]
    reports: dict[str, object] = field(default_factory=dict)
    export: dict[str, object] | None = None
    error: str | None = None

    @property
    def file_valid(self) -> bool:
        return bool(self.export and self.export.get("FILE_VALID"))

    def as_report(self) -> dict[str, object]:
        return {
            "profile": "prior_review",
            "profile_version": self.profile_version,
            "prior_review_stage": self.stage,
            "prior_review_stages": list(self.stages),
            "prior_review_artifacts": dict(sorted(self.artifacts.items())),
            "prior_review_hashes": dict(sorted(self.hashes.items())),
            "prior_review_reports": dict(self.reports),
            "prior_review_error": self.error,
            "bulk_entry_csv": (
                self.export.get("bulk_entry_csv") if self.file_valid else None
            ),
            "bulk_entry_sha256": (
                self.export.get("bulk_entry_sha256") if self.file_valid else None
            ),
            "export": self.export,
        }


def _stage(name: str, status: str, **detail: object) -> dict[str, object]:
    return {"stage": name, "status": status, **detail}


# `select_prior_lineups`' own per-solve default for sequential (C1) selection,
# which the run's budget shortens and never raises (Session 07).
SEQUENTIAL_PER_SOLVE_SECONDS = 10.0
# Where each filled row's lineup came from (Session 11b): the policy's joint
# solve, or the sequential fill of the rows it leaves unbound (or of every row,
# with no policy).
ROW_SOURCE_POLICY = "POLICY"
ROW_SOURCE_C1 = "C1"
ROW_SOURCE_SHOWDOWN_SEQUENTIAL = "SHOWDOWN_SEQUENTIAL"


def _classic_declared_search_seconds(policy: NormalizedClassicPortfolioPolicy) -> float:
    """A C2 policy's hash-bound bank and joint-solve limits, in seconds."""

    limits = policy.search_limits
    return (limits.candidate_total_milliseconds + limits.selection_milliseconds) / 1000.0


def _fill_solve_seconds(
    budget: Budget | None, rows: int, *, declared_search_seconds: float | None = None
) -> float | None:
    """The per-solve limit for a subset policy's unbound fill (Session 11b).

    The fill runs after the bank and joint solve. An SD3 policy's take their
    shares of the window; a C2 policy's are its declared limits (Session 11c).
    The fill gets what they leave, split across its solves, never above the
    sequential default and never under the solver's minimum.
    """

    if budget is None or rows < 1:
        return None
    window = 0.0 if budget.passed_at_start else max(0.0, budget.improvement_remaining())
    if declared_search_seconds is None:
        left = max(0.0, 1.0 - BANK_SHARE - JOINT_SHARE) * window
    else:
        left = max(0.0, window - declared_search_seconds)
    return max(SOLVE_MINIMUM_SECONDS, min(SEQUENTIAL_PER_SOLVE_SECONDS, left / (rows + 1)))


def row_sources(
    entry_ids: Sequence[str], bound: Sequence[str], mode: EngineMode
) -> dict[str, str]:
    """Each filled row's source, in template order: `POLICY`, `C1` or `SHOWDOWN_SEQUENTIAL`."""

    fill = ROW_SOURCE_C1 if mode is EngineMode.CLASSIC else ROW_SOURCE_SHOWDOWN_SEQUENTIAL
    taken = set(bound)
    return {entry_id: (ROW_SOURCE_POLICY if entry_id in taken else fill) for entry_id in entry_ids}


def _deadline_selection_limits(
    budget: Budget, *, count: int, portfolio_policy: object
) -> tuple[dict[str, float], str | None]:
    """`select_prior_lineups` keyword limits from the budget, or the text that stops selection.

    C1 gets a per-solve limit that fits its solves in the window; an SD3 policy a
    bank and joint-solve budget; a Classic C2 policy's limits are hash-bound in
    the policy, so they either fit the window or stop the review.
    """

    if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        declared = _classic_declared_search_seconds(portfolio_policy)
        return {}, budget.fits_declared_search(declared_seconds=declared)
    if isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        entries = portfolio_policy.entry_count
        seconds, stopped = budget.policy_search_seconds(
            bank_default=scaled_candidate_seconds(entries),
            joint_default=scaled_selection_seconds(entries),
            per_solve_default=DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
        )
        if seconds is None:
            return {}, stopped
        bank, per_solve, joint = seconds
        return {"policy_candidate_seconds": bank, "policy_candidate_per_solve_seconds": per_solve,
                "policy_selection_seconds": joint}, None
    per_solve, stopped = budget.sequential_solve_seconds(
        count=count, default=SEQUENTIAL_PER_SOLVE_SECONDS)
    return ({"time_limit_seconds": per_solve} if per_solve is not None else {}), stopped


def _safe_label(label: str) -> str:
    """Make an operator label safe for a filename without changing the run id.

    The export used the raw label, so `--label 'ne/sea wk1'` created a
    subdirectory and a name with spaces, and a label containing `..` could place
    the CSV outside the review folder. Same character policy as `cli._run_id`.
    """

    cleaned = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in str(label)
    )
    return cleaned[:60] or "slate"


def _write_canonical_json(path: str | Path, value: Mapping[str, object]) -> str:
    """Write stable run-ID-independent machine bytes for deterministic replay."""

    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return sha256_file(target)


def _official_status_coverage(
    slate: SlateContract, lineups: Sequence[object], official_report: object
) -> dict[str, object] | None:
    """Which selected people the supplied official status file actually covers.

    A supplied file used to clear `OFFICIAL_STATUS_REQUIRED` from the reported
    blockers on presence alone, while the rows were used only to exclude
    INACTIVE people. The gap this closes is a selected person with no row at
    all: nothing named them, and the run read as if activity were covered.
    """

    if not isinstance(official_report, Mapping):
        return None
    statuses = official_report.get("statuses")
    if not isinstance(statuses, Mapping):
        return None
    covered_people = {
        player.underlying_id for player in slate.players if player.dk_id in statuses
    }
    by_id = {player.dk_id: player for player in slate.players}
    selected_people: set[str] = set()
    for lineup in lineups:
        for dk_id in getattr(lineup, "roster", ()):
            player = by_id.get(str(dk_id))
            if player is not None:
                selected_people.add(player.underlying_id)
    without_row = sorted(person for person in selected_people if person not in covered_people)
    return {
        "scope": "SUPPLIED_ROWS_ONLY_NOT_FULL_POOL_ACTIVITY_CERTIFICATION",
        "selected_people": len(selected_people),
        "selected_with_row": len(selected_people) - len(without_row),
        "selected_without_row": without_row,
    }


def _weather_from_frozen_package(team_source: str | Path) -> dict[str, object] | None:
    """Recover the weather basis a reused frozen package was built with.

    On a `--build-priors` run the weather decision is reported directly. On a
    reuse run it used to be absent from every review surface even though the
    frozen team prior carries its basis and its six-hour expiry still binds.
    """

    try:
        payload = json.loads(Path(team_source).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    coverage = metadata.get("coverage") if isinstance(metadata, dict) else None
    basis = coverage.get("weather_basis") if isinstance(coverage, dict) else None
    if not basis:
        return None
    observed = None
    source_uri = None
    for part in str(basis).split("|"):
        if part.startswith("OPERATOR_CAPTURE:"):
            capture = part[len("OPERATOR_CAPTURE:"):]
            marker = ":observed_at="
            if marker in capture:
                source_uri, observed = capture.split(marker, 1)
            else:
                source_uri = capture
    states = {
        str(record.get("weather_state"))
        for record in (payload.get("records") or [])
        if isinstance(record, dict) and record.get("weather_state")
    }
    return {
        "basis": f"INHERITED_FROM_FROZEN_PACKAGE:{basis}",
        "weather_state": sorted(states)[0] if len(states) == 1 else (sorted(states) or None),
        "source_uri": source_uri,
        "observed_at": observed,
        "expires_at": metadata.get("expires_at") if isinstance(metadata, dict) else None,
    }


def _unobserved_weather(team_source: str | Path) -> list[str]:
    """Each game the frozen package holds no weather observation for (R28, Session 09).

    Read from the package itself, so a rebuilt and a reused package name the
    same games: one frozen `UNOBSERVED`, and one under an open roof whose
    weather nobody captured. Each code is a `P` limitation `run-slate` names; a
    package frozen before Session 09 could hold neither.
    """

    try:
        payload = json.loads(Path(team_source).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    coverage = metadata.get("coverage") if isinstance(metadata, dict) else None
    basis_by_game = coverage.get("weather_basis_by_game") if isinstance(coverage, dict) else None
    records = payload.get("records") if isinstance(payload, dict) else None
    recorded = {
        str(record.get("game_id"))
        for record in records or ()
        if isinstance(record, dict) and record.get("weather_state") == "UNOBSERVED"
    }
    limitations: list[str] = []
    for game_id, basis in sorted(dict(basis_by_game or {}).items()):
        text = str(basis)
        if text.startswith("WEATHER_UNOBSERVED") or game_id in recorded:
            recorded.discard(game_id)
            limitations.append(
                f"WEATHER_UNOBSERVED:{game_id}:{text}:frozen as UNOBSERVED, never as an"
                " observation; weather moves no number, and a fresh attributed capture clears it"
            )
        elif text.startswith("DERIVED_FROM_SCHEDULE_ROOF:open") and "OPERATOR_CAPTURE:" not in text:
            limitations.append(
                f"WEATHER_UNOBSERVED:{game_id}:{text}:the roof is open and nobody captured the"
                " weather the game is played in"
            )
        elif text.endswith("OPERATOR_SUPPLIED_UNATTRIBUTED"):
            # A package frozen outside run-slate with a typed state and no source.
            limitations.append(
                f"WEATHER_UNOBSERVED:{game_id}:{text}:the state was typed without a captured"
                " source, so it is not an observation"
            )
    limitations.extend(
        f"WEATHER_UNOBSERVED:{game_id}:the frozen team prior records this game as UNOBSERVED"
        for game_id in sorted(recorded)
    )
    return limitations


def pool_coverage_summary(
    slate: SlateContract,
    contract: ParticipationContract,
    *,
    official_inactive_dk_ids: Sequence[str],
    operator_excluded_dk_ids: Sequence[str],
    offense_excluded_people: Sequence[str],
    kicker_zero_share_people: Sequence[str],
    unallocated_by_team: Mapping[str, Mapping[str, float]],
    offense_excluded_by_finding: Mapping[str, Sequence[str]] | None = None,
    offense_findings: Sequence[Mapping[str, object]] = (),
    official_statuses: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Say who was selectable, who was not, why, and what it cost in salary.

    R17 asked for this next to the lineups: the count and salary of everyone the
    run could not use, by reason, so pool coverage is visible without reading
    the offensive-roles report. Exclusion sources are kept distinct because a
    DraftKings OUT flag, an official INACTIVE row, an operator fade and a role
    gate are four different facts with four different next actions.
    """

    by_person: dict[str, list[SalaryPlayer]] = {}
    for player in slate.players:
        by_person.setdefault(player.underlying_id, []).append(player)
    official_people = {
        player.underlying_id
        for player in slate.players
        if player.dk_id in set(official_inactive_dk_ids)
    }
    operator_people = {
        player.underlying_id
        for player in slate.players
        if player.dk_id in set(operator_excluded_dk_ids)
    }
    unavailable = set(contract.unavailable_people)
    offense_excluded = set(offense_excluded_people)
    kicker_excluded = set(kicker_zero_share_people)
    finding_by_person = {
        str(person): str(finding)
        for finding, members in dict(offense_excluded_by_finding or {}).items()
        for person in members
    }
    next_action_by_person = {
        str(item.get("person")): str(item.get("next_evidence_action") or "")
        for item in offense_findings
        if item.get("person")
    }
    official_by_person: dict[str, str] = {}
    for player in slate.players:
        status = (official_statuses or {}).get(player.dk_id)
        if status:
            official_by_person[player.underlying_id] = str(status)

    def reason_for(person: str) -> str:
        if person in unavailable:
            return f"DK_STATUS_UNAVAILABLE:{contract.status_by_person.get(person, '')}"
        if person in official_people:
            return "OFFICIAL_INACTIVE"
        if person in operator_people:
            return "OPERATOR_EXCLUDED"
        if person in offense_excluded:
            finding = finding_by_person.get(person)
            return f"OFFENSIVE_ROLE_GATE_EXCLUDED:{finding}" if finding else "OFFENSIVE_ROLE_GATE_EXCLUDED"
        if person in kicker_excluded:
            return "KICKER_ROLE_ZERO_SHARE"
        return "SELECTABLE"

    rows: list[dict[str, object]] = []
    totals: dict[str, dict[str, object]] = {}
    for person, players in sorted(by_person.items()):
        flex_salary = sum(
            player.salary for player in players if player.role in {None, "FLEX"}
        )
        cpt_salary = sum(player.salary for player in players if player.role == "CPT")
        reason = reason_for(person)
        bucket = reason.split(":", 1)[0]
        first = players[0]
        rows.append(
            {
                "person": person,
                "name": first.name,
                "team": first.team,
                "position": first.position,
                "game_id": first.game_id,
                "lock_at": first.lock_at.isoformat(),
                "dk_ids": sorted((player.dk_id for player in players), key=int),
                "dk_status": contract.status_by_person.get(person, ""),
                "official_activity": official_by_person.get(person, "UNKNOWN"),
                "reason": reason,
                "smallest_evidence_action": next_action_by_person.get(person, ""),
                "salary": flex_salary,
                "flex_salary": flex_salary,
                "cpt_salary": cpt_salary,
            }
        )
        entry = totals.setdefault(
            bucket, {"people": 0, "flex_salary": 0, "cpt_salary": 0, "names": []}
        )
        entry["people"] = int(entry["people"]) + 1
        entry["flex_salary"] = int(entry["flex_salary"]) + int(flex_salary)
        entry["cpt_salary"] = int(entry["cpt_salary"]) + int(cpt_salary)
        names = entry["names"]
        assert isinstance(names, list)
        names.append(f"{first.name} ({first.position}, {first.team})")
    selectable_positions: dict[str, dict[str, int]] = {}
    for row in rows:
        team = str(row["team"])
        position = str(row["position"])
        slot = selectable_positions.setdefault(team, {})
        key = f"{position}_selectable"
        pool_key = f"{position}_in_pool"
        slot[pool_key] = slot.get(pool_key, 0) + 1
        if row["reason"] == "SELECTABLE":
            slot[key] = slot.get(key, 0) + 1
    return {
        "people_in_pool": len(rows),
        # Selectable here means selectable by the solver: participation-eligible
        # AND not removed by a role gate. The participation-only count is kept
        # beside it so the two are never confused again.
        "selectable_people": sum(1 for row in rows if row["reason"] == "SELECTABLE"),
        "participation_selectable_people": len(contract.selectable_people),
        "by_reason": dict(sorted(totals.items())),
        "by_team_position": dict(sorted(selectable_positions.items())),
        "unallocated_by_team": {
            team: {field: round(float(value), 4) for field, value in sorted(dict(fields).items())}
            for team, fields in sorted(dict(unallocated_by_team).items())
        },
        "people": rows,
        "note": (
            "Unallocated shares are prior-season volume held by people who cannot"
            " be selected; it is not reassigned. Salary totals are DraftKings FLEX"
            " and, for Showdown, CPT prices of the excluded people, a coverage measure, not a"
            " projection or an edge claim."
        ),
    }


#: The frozen model artifacts a prior-only run produces, and the schema version
#: each one declares. Together these *are* the prediction: the projections the
#: portfolio was selected from, plus the provenance ledger binding them to their
#: approved sources. Anything listed here becomes a prediction the settlement
#: request must bind, so the list stays exactly what the run actually froze.
_PRELOCK_PREDICTION_VERSIONS = {
    "team_projections": "nfl_team_projections_csv_v1",
    "player_opportunities": "nfl_player_opportunities_csv_v1",
    "source_ledger": "nfl_source_ledger_v2",
}
TEAM_PROJECTIONS_CSV_V2 = "nfl_team_projections_csv_v2"


def team_projections_csv_version(weather_states: Iterable[str]) -> str:
    """v2 (Session 09) is v1 plus the weather state UNOBSERVED, declared only
    when a row carries it, so every other team CSV is still exactly v1."""

    if "UNOBSERVED" in {str(state).strip().upper() for state in weather_states}:
        return TEAM_PROJECTIONS_CSV_V2
    return _PRELOCK_PREDICTION_VERSIONS["team_projections"]


def _team_csv_weather_states(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [row.get("WEATHER_STATE") or "" for row in csv.DictReader(handle)]
    except (OSError, UnicodeError, csv.Error):
        return []


def _declared_schema_version(path: Path) -> str | None:
    """The schema version a JSON artifact declares about itself, if any.

    `None` for a CSV, which carries no such declaration and which settlement
    therefore does not version-check.
    """
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    declared = payload.get("schema_version") or payload.get("artifact_version")
    return str(declared) if declared else None


def _emit_prelock_manifest(
    *,
    run_dir: Path,
    as_of: datetime,
    slate: SlateContract,
    template: object,
    salary_digest: str,
    assignments: Mapping[str, tuple[str, ...]],
    assignments_path: Path,
    assignments_hash: str,
    projection: object,
    export_report: Mapping[str, object],
    artifacts: dict[str, str],
    hashes: dict[str, str],
) -> dict[str, object]:
    """Freeze this run's prediction as `nfl_prelock_run_manifest_v1`.

    Emitted at the end of the run, which is still before lock: the whole point is
    that the record predates the outcome, and the run does. It is emitted for a
    `DO_NOT_UPLOAD` run on purpose — those are the review lineups Ben actually
    enters by hand, so those are the ones worth settling later. Emitting one
    changes no release truth and unlocks nothing.

    Never fails the run. A slate this cannot describe truthfully produces a named
    `SKIPPED` stage and no file, because a run that produced a portfolio is still
    a good run even when its manifest cannot be written.
    """

    contests = {entry.contest_id for entry in template.authorizations}
    fees = {entry.entry_fee for entry in template.authorizations}
    if len(contests) != 1 or len(fees) != 1:
        # `settlement.require_single_contest` refuses a multi-contest template
        # outright, so a manifest naming one of several contests would bind a
        # portfolio to a contest it only partly belongs to. 16 of Ben's 18
        # entered contests are in exactly this state.
        return _stage(
            "PRELOCK_MANIFEST",
            "SKIPPED",
            reason="MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED",
            contest_ids=sorted(contests),
            entry_fees=sorted(fees),
        )
    if not assignments or not assignments_hash:
        return _stage(
            "PRELOCK_MANIFEST", "SKIPPED", reason="NO_ASSIGNMENT_TO_FREEZE"
        )

    predictions: list[PredictionArtifact] = []
    missing: list[str] = []
    versions = dict(_PRELOCK_PREDICTION_VERSIONS)
    team_csv = artifacts.get("team_projections")
    if team_csv:
        versions["team_projections"] = team_projections_csv_version(
            _team_csv_weather_states(Path(team_csv))
        )
    for name, version in sorted(versions.items()):
        digest = projection.hashes.get(name) if projection is not None else None
        path = artifacts.get(name)
        if not digest or not path:
            missing.append(name)
            continue
        # Settlement re-reads every JSON prediction and compares the version the
        # request declares against the one the file itself carries. Checking that
        # here turns a confusing capture-time refusal days later into an obvious
        # one now, and stops the manifest asserting a version that has moved on.
        declared = _declared_schema_version(Path(path))
        if declared is not None and declared != version:
            return _stage(
                "PRELOCK_MANIFEST",
                "SKIPPED",
                reason="PREDICTION_VERSION_UNEXPECTED",
                artifact=name,
                expected=version,
                declared=declared,
            )
        predictions.append(
            PredictionArtifact(
                name=name, path=str(path), sha256=str(digest), artifact_version=version
            )
        )
    if missing:
        return _stage(
            "PRELOCK_MANIFEST", "SKIPPED", reason="PREDICTION_ARTIFACT_ABSENT",
            absent=sorted(missing),
        )

    truths = {
        key: export_report.get(key)
        for key in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")
    }
    if any(value is None for value in truths.values()):
        return _stage(
            "PRELOCK_MANIFEST", "SKIPPED", reason="RELEASE_TRUTHS_INCOMPLETE",
            observed=sorted(k for k, v in truths.items() if v is not None),
        )

    try:
        relative_assignments = Path(assignments_path)
        try:
            relative_assignments = relative_assignments.relative_to(run_dir)
        except ValueError:
            relative_assignments = Path(relative_assignments.name)
        manifest = build_prelock_manifest(
            run_id=run_dir.name,
            # The run's own clock, not `now()`: a run replayed at a pinned
            # `as_of` must produce byte-identical bytes, and a wall-clock stamp
            # here would be the one thing that could not.
            created_at=as_of,
            mode=slate.mode,
            contest_id=sorted(contests)[0],
            draft_group=slate.draft_group,
            entry_fee=sorted(fees)[0],
            salary_sha256=salary_digest,
            entries_sha256=template.raw_hash,
            assignments_path=relative_assignments.as_posix(),
            assignments_sha256=assignments_hash,
            predictions=predictions,
            release_truths=truths,
            selected_entry_ids=sorted(assignments),
            evidence={
                "official_status_csv_sha256": hashes.get("official_status_csv"),
                "weather_evidence_json_sha256": hashes.get("weather_evidence_json"),
                "role_evidence_json_sha256": hashes.get("role_evidence_json"),
                "offensive_role_evidence_json_sha256": hashes.get(
                    "offensive_role_evidence_json"
                ),
            },
        )
    except PrelockManifestError as exc:
        return _stage("PRELOCK_MANIFEST", "SKIPPED", reason=str(exc))

    manifest_path = run_dir / "prelock_manifest.json"
    manifest_hash = write_prelock_manifest(manifest_path, manifest)
    artifacts["prelock_manifest"] = str(manifest_path)
    hashes["prelock_manifest"] = manifest_hash
    return _stage(
        "PRELOCK_MANIFEST",
        "OK",
        path=str(manifest_path),
        sha256=manifest_hash,
        prediction_artifacts=[item.name for item in predictions],
        selected_entries=len(assignments),
    )


def run_prior_review(
    *,
    salary_csv: str | Path,
    entry_csv: str | Path,
    label: str,
    as_of: datetime | None,
    run_root: str | Path,
    output_root: str | Path,
    season: int | None = None,
    prior_season: int | None = None,
    prior_package_dir: str | Path | None = None,
    build_priors: bool = False,
    weather_state: str | None = None,
    weather_source_uri: str | None = None,
    weather_observed_at: str | None = None,
    weather_evidence_json: str | Path | None = None,
    lineup_count: int | None = None,
    max_person_overlap: int | None = 4,
    allow_repeat_captain: bool = False,
    operator_excluded_dk_ids: Sequence[str] = (),
    extra_unavailable_statuses: Sequence[str] = (),
    extra_available_statuses: Sequence[str] = (),
    official_status_csv: str | Path | None = None,
    role_evidence_json: str | Path | None = None,
    offensive_role_evidence_json: str | Path | None = None,
    qb_depth_role_evidence_json: str | Path | None = None,
    portfolio_policy: NormalizedPortfolioPolicy | NormalizedClassicPortfolioPolicy | None = None,
    portfolio_policy_source_path: str | Path | None = None,
    portfolio_policy_source_sha256: str | None = None,
    portfolio_policy_normalized_path: str | Path | None = None,
    portfolio_policy_normalized_sha256: str | None = None,
    propose: Callable[..., dict[str, object]] = propose_prior_package,
    freeze: Callable[..., dict[str, object]] = freeze_prior_package,
    project: Callable[..., object] = build_projection_package,
    budget: Budget | None = None,
    showdown_candidate_limit: int | None = None,
) -> PriorReviewOutcome:
    """Drive priors, identity, projection, selection and export as one gate.

    Returns a blocked outcome with named blockers wherever a human decision is
    genuinely required, and never writes an export on any blocked or failed path.
    `budget` (Session 07) sets selection's time limits from the run's window and
    stops the review before selection when the window cannot hold it.
    `showdown_candidate_limit` (Session 10) is the relaxation controller's SD3
    bank size, in place of `max(32, 4 x entries)`.
    """

    run_dir = Path(run_root).resolve()
    out_dir = Path(output_root).resolve()
    live_run = as_of is None
    as_of = as_of or datetime.now(timezone.utc)
    stages: list[dict[str, object]] = []
    artifacts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    reports: dict[str, object] = {}

    salary_path = Path(salary_csv).resolve()
    entry_path = Path(entry_csv).resolve()
    try:
        slate = parse_salaries(salary_path)
        template = parse_entries(entry_path)
        reconcile_template(template, slate)
        # Per-row authority (Session 11) replaces the whole-file refusal: prefilled
        # rows are preserved and seed distinctness, partly filled rows, unresolved
        # prefilled rosters and unstated groups are named, and only the plan's
        # fillable blank rows are ever assigned.
        entry_plan = plan_entries(template, slate)
        if not entry_plan.fillable:
            raise PriorReviewError(
                "ENTRY_BLANK_CELL_AUTHORITY_REQUIRED:"
                f"fillable_entries=[]:rows={list(entry_plan.order)}:prior_review may assign only "
                "exact reserved Entry IDs whose roster cells are all blank, and the template has none"
            )
    except (OSError, ValueError) as exc:
        return PriorReviewOutcome(
            profile_version=PROFILE_VERSION,
            stage="INTAKE",
            blocked=True,
            blockers=(f"INTAKE_FAILED:{type(exc).__name__}:{exc}",),
            stages=(_stage("INTAKE", "FAILED", error=str(exc)),),
            artifacts={},
            hashes={},
            error=str(exc),
        )
    profile_version = (
        PROFILE_VERSION
        if slate.mode is EngineMode.SHOWDOWN
        else (
            CLASSIC_PROFILE_VERSION_C3
            if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
            else CLASSIC_PROFILE_VERSION
        )
    )
    salary_digest = sha256_file(salary_path)
    hashes["salary_csv"] = salary_digest
    hashes["entry_csv"] = sha256_file(entry_path)
    # The run already hashed both; recording where they are too is what lets a
    # settlement request bind the exact bytes the pre-lock manifest names.
    artifacts["salary_csv"] = str(salary_path)
    artifacts["entry_csv"] = str(entry_path)
    reports["intake"] = {
        "schema_version": "nfl_prior_review_intake_c1_v1",
        "mode": slate.mode.value,
        "salary_sha256": salary_digest,
        "entry_sha256": hashes["entry_csv"],
        "draft_group": slate.draft_group,
        "games": [
            {
                "game_id": game.game_id,
                "away_team": game.away_team,
                "home_team": game.home_team,
                "lock_at": game.lock_at.isoformat(),
            }
            for game in slate.games
        ],
        "salary_cap": slate.salary_cap,
        "salary_parser_version": DK_PARSER_VERSION,
        "entry_parser_version": DK_PARSER_VERSION,
        "scoring_version": slate.scoring_version,
        "entry_ids": [entry.entry_id for entry in template.authorizations],
        "contest_ids": sorted({entry.contest_id for entry in template.authorizations}),
        "contest_names": sorted({entry.contest_name for entry in template.authorizations}),
        "entry_fees": sorted({entry.entry_fee for entry in template.authorizations}),
        "blank_cell_authority": "PASS",
        "entry_rows": entry_plan.slate_summary(),
        "entry_findings": [
            {"code": code, "entry_ids": list(ids), "detail": detail}
            for code, ids, detail in entry_plan.findings
        ],
        "appg_policy": "PRESENT_ONLY_IN_HASHED_UNTOUCHED_RAW_SALARY_BYTES",
    }
    stages.append(
        _stage(
            "INTAKE",
            "OK",
            mode=slate.mode.value,
            games=len(slate.games),
            entries=len(template.authorizations),
        )
    )
    weather_evidence_by_game: dict[str, dict[str, object]] = {}
    if weather_evidence_json is not None:
        try:
            weather_path = Path(weather_evidence_json).resolve()
            weather_hash = sha256_file(weather_path)
            weather_payload = _read_json(
                weather_path, "WEATHER_EVIDENCE_JSON_INVALID"
            )
            if weather_payload.get("schema_version") != "nfl_classic_weather_evidence_c1_v1":
                raise PriorReviewError("WEATHER_EVIDENCE_SCHEMA_UNSUPPORTED")
            if weather_payload.get("salary_sha256") != salary_digest:
                raise PriorReviewError("WEATHER_EVIDENCE_SALARY_HASH_MISMATCH")
            games_payload = weather_payload.get("games")
            if not isinstance(games_payload, Mapping):
                raise PriorReviewError("WEATHER_EVIDENCE_GAMES_REQUIRED")
            expected_games = {game.game_id for game in slate.games}
            if set(map(str, games_payload)) != expected_games:
                raise PriorReviewError(
                    "WEATHER_EVIDENCE_GAME_COVERAGE_MISMATCH:"
                    f"expected={sorted(expected_games)}:actual={sorted(map(str, games_payload))}"
                )
            for game_id, raw in games_payload.items():
                if not isinstance(raw, Mapping):
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_GAME_INVALID:{game_id}"
                    )
                game_evidence = dict(raw)
                source_relative = Path(str(game_evidence.get("path") or ""))
                expected_source_hash = str(game_evidence.get("sha256") or "").lower()
                if (
                    not source_relative.parts
                    or source_relative.is_absolute()
                    or ".." in source_relative.parts
                    or len(expected_source_hash) != 64
                    or any(character not in "0123456789abcdef" for character in expected_source_hash)
                ):
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_SOURCE_BINDING_INVALID:{game_id}"
                    )
                source_path = (weather_path.parent / source_relative).resolve()
                if (
                    not source_path.is_relative_to(weather_path.parent)
                    or source_path.is_symlink()
                    or not source_path.is_file()
                    or not source_path.name.startswith(expected_source_hash)
                ):
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_SOURCE_PATH_INVALID:{game_id}"
                    )
                if sha256_file(source_path) != expected_source_hash:
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_SOURCE_HASH_MISMATCH:{game_id}"
                    )
                try:
                    validate_source_reference_policy(
                        str(game_evidence.get("source_uri") or ""),
                        license_decision=str(
                            game_evidence.get("license_decision") or ""
                        ),
                        parser_version=str(game_evidence.get("parser_version") or ""),
                    )
                except SourcePolicyError as exc:
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_SOURCE_POLICY:{game_id}:{exc}"
                    ) from exc
                observed = _parse_moment(
                    game_evidence.get("observed_at"),
                    label=f"WEATHER_OBSERVED_AT:{game_id}",
                )
                captured = _parse_moment(
                    game_evidence.get("captured_at"),
                    label=f"WEATHER_CAPTURED_AT:{game_id}",
                )
                expires = _parse_moment(
                    game_evidence.get("expires_at"),
                    label=f"WEATHER_EXPIRES_AT:{game_id}",
                )
                if observed > captured or captured > as_of or as_of > expires:
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_TIME_INVALID_OR_STALE:{game_id}"
                    )
                if sha256_file(source_path) != expected_source_hash:
                    raise PriorReviewError(
                        f"WEATHER_EVIDENCE_SOURCE_CHANGED_DURING_READ:{game_id}"
                    )
                artifacts[f"weather_source:{game_id}"] = str(source_path)
                hashes[f"weather_source:{game_id}"] = expected_source_hash
                weather_evidence_by_game[str(game_id)] = game_evidence
            if sha256_file(weather_path) != weather_hash:
                raise PriorReviewError("WEATHER_EVIDENCE_CHANGED_DURING_READ")
            artifacts["weather_evidence_json"] = str(weather_path)
            hashes["weather_evidence_json"] = weather_hash
        except (OSError, ValueError) as exc:
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="WEATHER",
                blocked=True,
                blockers=(str(exc),),
                stages=tuple(stages) + (
                    _stage("WEATHER", "FAILED", error=str(exc)),
                ),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                error=str(exc),
            )
    policy_source_path: Path | None = None
    policy_normalized_path: Path | None = None
    if portfolio_policy is not None:
        if (
            portfolio_policy_source_path is None
            or portfolio_policy_source_sha256 is None
            or portfolio_policy_normalized_path is None
            or portfolio_policy_normalized_sha256 is None
        ):
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="PORTFOLIO_POLICY",
                blocked=True,
                blockers=(
                    "PORTFOLIO_POLICY_ARTIFACT_BINDING_INCOMPLETE: source and normalized "
                    "policy paths and hashes are required for governed enforcement",
                ),
                stages=(_stage("PORTFOLIO_POLICY", "FAILED_BINDING"),),
                artifacts=artifacts,
                hashes=hashes,
            )
        policy_source_path = Path(portfolio_policy_source_path).resolve()
        policy_normalized_path = Path(portfolio_policy_normalized_path).resolve()
        artifacts["portfolio_policy_source"] = str(policy_source_path)
        artifacts["portfolio_policy_normalized"] = str(policy_normalized_path)
        hashes["portfolio_policy_source"] = str(portfolio_policy_source_sha256)
        hashes["portfolio_policy_normalized"] = str(portfolio_policy_normalized_sha256)

    # A supplied current report must affect generation, including both salary
    # roles of an inactive person. Absence remains a release blocker; partial
    # ACTIVE coverage here never claims that the rest of the pool is active.
    official_exclusions: tuple[str, ...] = ()
    if official_status_csv is not None:
        try:
            status_path = Path(official_status_csv).resolve()
            status_hash = sha256_file(status_path)
            snapshot = parse_official_inactive_snapshot(status_path, slate.players)
            if snapshot.problems:
                raise PriorReviewError("OFFICIAL_STATUS_INVALID:" + ";".join(snapshot.problems))
            if not snapshot.statuses:
                raise PriorReviewError("OFFICIAL_STATUS_EMPTY")
            for dk_id, observed in snapshot.observed_at_by_id.items():
                if observed > as_of + timedelta(minutes=5):
                    raise PriorReviewError(f"OFFICIAL_STATUS_FUTURE:{dk_id}")
                if as_of > observed + timedelta(hours=3):
                    raise PriorReviewError(f"OFFICIAL_STATUS_STALE:{dk_id}")
            if sha256_file(status_path) != status_hash:
                raise PriorReviewError("OFFICIAL_STATUS_CHANGED_DURING_READ")
            official_exclusions = tuple(
                dk_id for dk_id, status in snapshot.statuses.items() if status == "INACTIVE"
            )
            hashes["official_status_csv"] = status_hash
            artifacts["official_status_csv"] = str(status_path)
            reports["official_status"] = {
                "scope": "SUPPLIED_ROWS_ONLY_NOT_FULL_POOL_ACTIVITY_CERTIFICATION",
                "rows": len(snapshot.statuses), "inactive_dk_ids": list(official_exclusions),
                "statuses": dict(sorted(snapshot.statuses.items())),
                "source_urls": dict(sorted(snapshot.source_url_by_id.items())),
                "observed_at": {
                    dk_id: observed.astimezone(timezone.utc).isoformat()
                    for dk_id, observed in sorted(snapshot.observed_at_by_id.items())
                },
            }
        except (OSError, ValueError) as exc:
            return PriorReviewOutcome(
                profile_version=profile_version, stage="ACTIVITY", blocked=True,
                blockers=(str(exc),), stages=(_stage("ACTIVITY", "FAILED", error=str(exc)),),
                artifacts=artifacts, hashes=hashes, reports=reports, error=str(exc),
            )

    lock_at = slate.games[0].lock_at
    resolved_season = int(season) if season is not None else derive_season(lock_at)
    resolved_prior_season = (
        int(prior_season) if prior_season is not None else resolved_season - 1
    )
    reports["seasons"] = {
        "season": resolved_season,
        "prior_season": resolved_prior_season,
        "basis": (
            "OPERATOR_SUPPLIED"
            if season is not None
            else f"DERIVED_FROM_DK_LOCK_AT:{lock_at.isoformat()}"
        ),
    }

    # ----------------------------------------------------------------- PRIORS
    package: ResolvedPriorPackage | None = None
    reuse_detail: dict[str, object] = {}
    if prior_package_dir not in (None, ""):
        try:
            package = resolve_prior_package(
                prior_package_dir, salary_sha256=salary_digest, as_of=as_of
            )
        except PriorReviewError as exc:
            if build_priors and str(exc).startswith("PRIOR_PACKAGE_SALARY_MISMATCH:"):
                # A fresh DraftKings download (one status flag is enough) no
                # longer matches the package's bound salary bytes. With rebuild
                # authorized, that is a reason to re-propose against the current
                # snapshot, exactly like an expiry; without it, it stays a named
                # stop. A hash mismatch inside the package is never rebuilt over.
                stages.append(
                    _stage(
                        "PRIORS",
                        "REBUILDING_SALARY_MISMATCHED_PACKAGE",
                        package_dir=str(prior_package_dir),
                        error=str(exc),
                    )
                )
                reports["superseded_package"] = {
                    "package_dir": str(prior_package_dir),
                    "reason": str(exc),
                }
                package = None
            else:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="PRIORS",
                    blocked=True,
                    blockers=(str(exc),),
                    stages=(_stage("PRIORS", "FAILED", error=str(exc)),),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                    error=str(exc),
                )
        if package is not None:
            reuse_detail = package.as_report()
        if package is not None and package.expired:
            if not build_priors:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="PRIORS",
                    blocked=True,
                    blockers=(
                        "PRIOR_PACKAGE_EXPIRED:"
                        f"expires_at={package.expires_at}:as_of={as_of.isoformat()}"
                        f":basis={package.expiry_basis}"
                        ":authorize a rebuild with build_priors; an expiry is never widened",
                    ),
                    stages=(_stage("PRIORS", "BLOCKED_EXPIRED", **reuse_detail),),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports={**reports, "prior_package": reuse_detail},
                )
            # An expiry is a reason to re-fetch, never a reason to widen a
            # window. The stale package is recorded and then discarded.
            stages.append(_stage("PRIORS", "REBUILDING_EXPIRED_PACKAGE", **reuse_detail))
            reports["expired_package"] = reuse_detail
            package = None
    elif not build_priors:
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="PRIORS",
            blocked=True,
            blockers=(
                "PRIOR_PACKAGE_REQUIRED:supply prior_package_dir pointing at a frozen"
                " team_prior.json, player_prior.json and identity_map.json, or set"
                " build_priors to authorize fetching and freezing approved nflverse"
                " artifacts for this slate",
            ),
            stages=(_stage("PRIORS", "BLOCKED"),),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
        )

    proposal_dir: Path | None = None
    if package is not None:
        inherited_weather = _weather_from_frozen_package(package.team_source)
        if inherited_weather is not None:
            reports["weather"] = inherited_weather
    if package is None:
        proposal_dir = run_dir / "priors" / "proposal"
        try:
            proposed = propose(
                salaries=str(salary_path),
                salary_sha256=salary_digest,
                season=resolved_season,
                prior_season=resolved_prior_season,
                as_of=as_of.isoformat(),
                output_dir=str(proposal_dir),
            )
        except Exception as exc:  # noqa: BLE001 - named, never swallowed
            error = f"{type(exc).__name__}:{exc}"
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="PRIORS",
                blocked=True,
                blockers=(f"PRIORS_PROPOSE_FAILED:{error}",),
                stages=tuple(stages) + (_stage("PRIORS", "FAILED", error=error),),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                error=error,
            )
        artifacts["identity_proposals"] = str(proposed.get("identity_proposals", ""))
        artifacts["source_manifest"] = str(proposed.get("source_manifest", ""))
        for name, digest in dict(proposed.get("hashes") or {}).items():
            hashes[f"proposal:{name}"] = str(digest)
        reports["propose"] = {
            "package_dir": proposed.get("package_dir"),
            "people": proposed.get("people"),
            "salary_rows": proposed.get("salary_rows"),
            "match_methods": proposed.get("match_methods"),
            "market": proposed.get("market"),
            "markets": proposed.get("markets"),
            "nflverse_game_id": proposed.get("nflverse_game_id"),
            "nflverse_game_ids": proposed.get("nflverse_game_ids"),
        }
        if live_run:
            as_of = datetime.now(timezone.utc)
        proposed_markets = dict(proposed.get("markets") or {})
        if not proposed_markets and proposed.get("market"):
            proposed_markets = {
                slate.games[0].game_id: dict(proposed.get("market") or {})
            }
        weather_decisions: dict[str, WeatherDecision] = {}
        for game_id, raw_market in sorted(proposed_markets.items()):
            market = dict(raw_market or {})
            supplied = dict(weather_evidence_by_game.get(game_id) or {})
            weather_decisions[game_id] = decide_weather(
                str(market.get("roof", "")),
                game_id=game_id,
                venue_roof_history={
                    home_team_of(game_id): {
                        str(roof): int(count)
                        for roof, count in dict(
                            market.get("venue_roof_history") or {}
                        ).items()
                    }
                },
                venue_roof_seasons=list(
                    market.get("venue_roof_history_seasons") or []
                )
                or None,
                weather_state=(
                    str(supplied.get("weather_state") or "") or None
                    if weather_evidence_by_game
                    else weather_state
                ),
                weather_source_uri=(
                    str(supplied.get("source_uri") or "") or None
                    if weather_evidence_by_game
                    else weather_source_uri
                ),
                weather_observed_at=(
                    str(supplied.get("observed_at") or "") or None
                    if weather_evidence_by_game
                    else weather_observed_at
                ),
            )
        reports["weather"] = {
            "scope": "COMPLETE_GAME_SET",
            "games": {
                game_id: decision.as_report()
                for game_id, decision in sorted(weather_decisions.items())
            },
        }

        # --------------------------------------------------------- IDENTITY
        status_by_dk_id = {
            player.dk_id: (player.status_raw or "") for player in slate.players
        }
        proposals = _proposals_from_payload(proposal_dir)
        gate = apply_identity_gate(proposals, status_by_dk_id)
        reports["identity"] = gate.as_report()
        reviewed_path = run_dir / "priors" / "identity_reviewed.csv"
        reviewed_hash = write_reviewed_decisions(reviewed_path, gate)
        artifacts["identity_reviewed"] = str(reviewed_path)
        hashes["identity_reviewed"] = reviewed_hash
        write_run_record(run_dir / "priors" / "identity_decisions.json", gate.as_report())

        # R28 (Session 09): weather never blocks here. A game nobody observed is
        # frozen as UNOBSERVED and named from the frozen package below.
        unobserved_games = sorted(
            game_id for game_id, decision in weather_decisions.items() if decision.limitations
        )
        stages.append(
            _stage(
                "PRIORS",
                "PROPOSED",
                package_dir=str(proposal_dir),
                people=len(proposals),
            )
        )
        stages.append(
            _stage(
                "WEATHER",
                "UNOBSERVED_GAMES_NAMED" if unobserved_games else "OK",
                games=reports["weather"]["games"],
            )
        )
        stages.append(
            _stage(
                "IDENTITY",
                "BLOCKED" if gate.blockers else "OK",
                people=len(gate.decisions),
                auto_accepted=len(gate.auto_accepted),
                blocked=len(gate.blocked),
            )
        )
        if gate.blockers:
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="IDENTITY",
                blocked=True,
                blockers=gate.blockers,
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
            )

        frozen_dir = run_dir / "priors" / "frozen"
        try:
            legacy_weather = weather_decisions[slate.games[0].game_id]
            frozen = freeze(
                package_dir=str(proposal_dir),
                reviewed=str(reviewed_path),
                reviewed_sha256=reviewed_hash,
                salaries=str(salary_path),
                salary_sha256=salary_digest,
                as_of=as_of.isoformat(),
                output_dir=str(frozen_dir),
                weather_state=(
                    None
                    if weather_evidence_by_game
                    else legacy_weather.freeze_weather_state
                ),
                salary_observed_at=None,
                weather_source_uri=(
                    None
                    if weather_evidence_by_game
                    else legacy_weather.freeze_source_uri
                ),
                weather_observed_at=(
                    None
                    if weather_evidence_by_game
                    else legacy_weather.freeze_observed_at
                ),
                weather_evidence_by_game=(
                    weather_evidence_by_game or None
                ),
            )
        except Exception as exc:  # noqa: BLE001 - named, never swallowed
            error = f"{type(exc).__name__}:{exc}"
            stages.append(_stage("PRIORS", "FAILED", error=error))
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="PRIORS",
                blocked=True,
                blockers=(f"PRIORS_FREEZE_FAILED:{error}",),
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                error=error,
            )
        reports["freeze"] = {
            "output_dir": frozen.get("output_dir"),
            "teams": frozen.get("teams"),
            "people": frozen.get("people"),
            "weather_state": frozen.get("weather_state"),
            "weather_basis": frozen.get("weather_basis"),
        }
        if live_run:
            as_of = datetime.now(timezone.utc)
        try:
            package = resolve_prior_package(
                frozen_dir, salary_sha256=salary_digest, as_of=as_of
            )
        except PriorReviewError as exc:
            stages.append(_stage("PRIORS", "FAILED", error=str(exc)))
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="PRIORS",
                blocked=True,
                blockers=(str(exc),),
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                error=str(exc),
            )
        reuse_detail = package.as_report()
        stages.append(_stage("PRIORS", "BUILT", **reuse_detail))
    else:
        stages.append(_stage("PRIORS", "REUSED", **reuse_detail))
        stages.append(_stage("IDENTITY", "INHERITED_FROM_FROZEN_PACKAGE"))

    reports["prior_package"] = package.as_report()
    reports["weather_unobserved"] = _unobserved_weather(package.team_source)
    artifacts["team_source"] = package.team_source
    artifacts["player_source"] = package.player_source
    artifacts["identity_map"] = package.identity_map
    for name, digest in package.hashes.items():
        hashes[f"prior:{name}"] = digest

    # ---------------------------------------------------------------- PROJECT
    projected_dir = run_dir / "projected"
    if live_run:
        as_of = datetime.now(timezone.utc)
    try:
        projection = project(
            salaries=str(salary_path),
            salary_sha256=salary_digest,
            team_source=package.team_source,
            team_source_sha256=package.hashes[TEAM_PRIOR_FILENAME],
            player_source=package.player_source,
            player_source_sha256=package.hashes[PLAYER_PRIOR_FILENAME],
            identity_map=package.identity_map,
            identity_map_sha256=package.hashes[IDENTITY_MAP_FILENAME],
            as_of=as_of.isoformat(),
            output_dir=str(projected_dir),
        )
    except Exception as exc:  # noqa: BLE001 - named, never swallowed
        error = f"{type(exc).__name__}:{exc}"
        stages.append(_stage("PROJECT", "FAILED", error=error))
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="PROJECT",
            blocked=True,
            blockers=(f"PROJECTION_FAILED:{error}",),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=error,
        )
    artifacts["team_projections"] = str(projection.team_projections)
    artifacts["player_opportunities"] = str(projection.player_opportunities)
    artifacts["source_ledger"] = str(projection.source_ledger)
    for name, digest in dict(projection.hashes).items():
        hashes[f"projected:{name}"] = str(digest)
    # The produced package carries its own expiry across this boundary now, so
    # the run record states when these model inputs stop being usable instead
    # of leaving a later consumer to infer it from a hash match. That expiry is
    # re-evaluated here, before selection, against this run's clock: a run that
    # crosses an expiry between freezing and selecting has stale inputs, and no
    # expiry is widened to let it through. Certification re-evaluates the same
    # expiry again at the live release clock through
    # `evidence.source_ledger_evidence`, which is the boundary that can refuse
    # an upload; this profile ends `DO_NOT_UPLOAD` on every path regardless.
    projection_freshness = _freshness_record(
        label=f"projected:{projection.ledger_schema_version}",
        basis=str(projection.expiry_basis),
        expires_at=_parse_moment(
            projection.expires_at, label="PROJECTION_PACKAGE_EXPIRES_AT"
        ),
        declared_state=None,
        where="projected",
    )
    projection_state = projection_freshness.state_at(as_of)
    reports["projection"] = {
        "output_dir": str(projection.output_dir),
        "ledger_schema_version": str(projection.ledger_schema_version),
        "expires_at": str(projection.expires_at),
        "expiry_basis": str(projection.expiry_basis),
        "archived_sources": dict(sorted(dict(projection.archived_sources).items())),
        "replay_clock": as_of.isoformat(),
        "freshness_state": projection_state.value,
    }
    if projection_state is not EvidenceState.PASS:
        blocker = (
            f"PROJECTION_PACKAGE_NOT_FRESH:{projection_state.value}"
            f":expires_at={projection.expires_at}:as_of={as_of.isoformat()}"
            f":basis={projection.expiry_basis}"
            ":refresh the sources and rebuild; an expiry is never widened"
        )
        stages.append(_stage("PROJECT", "BLOCKED_NOT_FRESH", **reports["projection"]))
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="PROJECT",
            blocked=True,
            blockers=(blocker,),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
        )
    stages.append(
        _stage("PROJECT", "OK", output_dir=str(projection.output_dir))
    )

    # ----------------------------------------------------------------- SELECT
    try:
        resolved_splits = resolve_frozen_artifact(
            package.frozen_sources.get("team_stats", ""),
            package_dir=package.package_dir,
            fallback_roots=[
                Path(package.package_dir).parent,
                Path(package.package_dir).parent.parent,
                *([proposal_dir] if proposal_dir is not None else []),
            ],
            label="team_stats",
        )
        splits_path = resolved_splits.path
    except PriorReviewError as exc:
        stages.append(_stage("SELECT", "FAILED", error=str(exc)))
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="SELECT",
            blocked=True,
            blockers=(str(exc),),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=str(exc),
        )
    artifacts["team_splits"] = str(splits_path)
    hashes["frozen:team_stats"] = package.frozen_sources.get("team_stats", "")
    reports["team_splits"] = resolved_splits.as_report()

    template = parse_entries(entry_path)
    entry_ids = list(entry_plan.fillable)
    requested_count = int(lineup_count) if lineup_count else len(entry_ids)
    # Session 11b (C2 since 11c): a policy binds the fillable rows or a subset
    # of them in template order; after its joint solve C1 or sequential
    # Showdown fills the rest, with every policy lineup and prefilled roster as
    # a no-good.
    bound_ids = list(portfolio_policy.entry_ids) if portfolio_policy is not None else []
    unbound_ids = list(unbound_rows(bound_ids, entry_ids)) if portfolio_policy is not None else []
    if portfolio_policy is None and requested_count < len(entry_ids):
        # Fewer lineups than reserved entries can only be filled by repeating a
        # roster across entries. The export would then carry duplicate lineups
        # into a bulk-entry file, which the display reconciliation rejects one
        # stage later, after the CSV is already on disk. Refuse here instead.
        message = (
            "LINEUP_COUNT_BELOW_RESERVED_ENTRIES:"
            f"lineup_count={requested_count}:reserved_entries={len(entry_ids)}"
            ":every reserved entry needs its own distinct lineup; omit lineup_count"
            " or set it to at least the reserved-entry count"
        )
        stages.append(_stage("SELECT", "FAILED", error=message))
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="SELECT",
            blocked=True,
            blockers=(message,),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=message,
        )
    selection_limits: dict[str, float] = {}
    if budget is not None:
        selection_limits, deadline_stop = _deadline_selection_limits(
            budget, count=requested_count, portfolio_policy=portfolio_policy)
        if deadline_stop is not None:
            stages.append(_stage("SELECT", "STOPPED_FOR_DEADLINE", error=deadline_stop))
            reports["selection_failure"] = {
                "status": deadline_stop.split(":", 1)[0], "origin": "DEADLINE",
                "facts": {"improvement_remaining_seconds": round(budget.improvement_remaining(), 3)},
                "error": deadline_stop,
            }
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="SELECT",
                blocked=True,
                blockers=(deadline_stop,),
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                error=deadline_stop,
            )
    if showdown_candidate_limit is not None and isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        selection_limits = {**selection_limits, "policy_candidate_limit": int(showdown_candidate_limit)}
    try:
        if slate.mode is EngineMode.CLASSIC:
            if sha256_file(salary_path) != salary_digest:
                raise PriorReviewError("SALARY_INPUT_CHANGED_BEFORE_SELECTION")
            if sha256_file(entry_path) != hashes["entry_csv"]:
                raise PriorReviewError("ENTRY_INPUT_CHANGED_BEFORE_SELECTION")
            for source_path, expected_hash, label_name in (
                (package.team_source, package.hashes[TEAM_PRIOR_FILENAME], "TEAM_PRIOR"),
                (package.player_source, package.hashes[PLAYER_PRIOR_FILENAME], "PLAYER_PRIOR"),
                (package.identity_map, package.hashes[IDENTITY_MAP_FILENAME], "IDENTITY_MAP"),
                (projection.team_projections, projection.hashes["team_projections"], "TEAM_PROJECTIONS"),
                (projection.player_opportunities, projection.hashes["player_opportunities"], "PLAYER_OPPORTUNITIES"),
                (projection.source_ledger, projection.hashes["source_ledger"], "SOURCE_LEDGER"),
            ):
                if sha256_file(source_path) != expected_hash:
                    raise PriorReviewError(f"{label_name}_CHANGED_BEFORE_SELECTION")
        if portfolio_policy is not None:
            assert policy_source_path is not None
            assert policy_normalized_path is not None
            assert portfolio_policy_source_sha256 is not None
            assert portfolio_policy_normalized_sha256 is not None
            binding = subset_binding_problems(bound_ids, entry_ids)
            if binding:
                raise PriorReviewError(
                    "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH:" + "; ".join(binding))
            if requested_count != len(entry_ids):
                raise SelectionError(
                    "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
                    f"lineup_count={requested_count}:fillable_rows={len(entry_ids)}")
            if sha256_file(salary_path) != portfolio_policy.salary_sha256:
                raise PriorReviewError("PORTFOLIO_POLICY_SALARY_CHANGED_BEFORE_SELECTION")
            if sha256_file(entry_path) != hashes["entry_csv"]:
                raise PriorReviewError("PORTFOLIO_POLICY_ENTRY_BYTES_CHANGED_BEFORE_SELECTION")
            if (
                isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                and portfolio_policy.entry_sha256 != hashes["entry_csv"]
            ):
                raise PriorReviewError("CLASSIC_PORTFOLIO_POLICY_ENTRY_HASH_MISMATCH")
            if sha256_file(policy_source_path) != portfolio_policy_source_sha256:
                raise PriorReviewError("PORTFOLIO_POLICY_SOURCE_CHANGED_BEFORE_SELECTION")
            if sha256_file(policy_normalized_path) != portfolio_policy_normalized_sha256:
                raise PriorReviewError("PORTFOLIO_POLICY_NORMALIZED_CHANGED_BEFORE_SELECTION")
            if policy_normalized_path.read_bytes() != portfolio_policy.canonical_bytes():
                raise PriorReviewError("PORTFOLIO_POLICY_NORMALIZED_BYTES_NOT_CONSUMED_POLICY")
        model = load_opportunity_model(
            slate, str(projection.team_projections), str(projection.player_opportunities),
            allow_empty_groups=True,
        )
        model = attach_history(model, package.player_source, package.hashes[PLAYER_PRIOR_FILENAME])
        contract = build_participation_contract(
            slate,
            operator_excluded_dk_ids=tuple(operator_excluded_dk_ids) + official_exclusions,
            extra_unavailable_statuses=tuple(extra_unavailable_statuses),
            extra_available_statuses=tuple(extra_available_statuses),
        )
        _reduced, redistribution = redistribute_opportunity(model, contract, redistribute=False)
        if sha256_file(package.identity_map) != package.hashes[IDENTITY_MAP_FILENAME]:
            raise PriorReviewError("TEAM_SPLIT_IDENTITY_MAP_CHANGED")
        identity_payload = json.loads(Path(package.identity_map).read_text(encoding="utf-8"))
        team_binding = {}
        for mapping in identity_payload.get("team_mappings", []):
            parts = mapping["provider_team_id"].split(":")
            if len(parts) != 3 or parts[0] != "nflverse" or parts[2] != str(package.season):
                raise PriorReviewError("TEAM_SPLIT_PROVIDER_TEAM_ID_UNSUPPORTED")
            if mapping["team"] in team_binding:
                raise PriorReviewError("TEAM_SPLIT_IDENTITY_MAP_DUPLICATE")
            team_binding[mapping["team"]] = parts[1]
        reports["team_splits"]["provider_team_by_team"] = team_binding
        splits = read_team_splits(
            splits_path,
            prior_season=package.prior_season,
            teams=sorted({player.team for player in slate.players}),
            provider_team_by_team=team_binding or None,
        )
        measured = budget.stage("selection") if budget is not None else nullcontext()
        with measured:
            lineups, scores, selection = select_prior_lineups(
                slate,
                model,
                splits,
                contract,
                count=(portfolio_policy.entry_count if portfolio_policy is not None else requested_count),
                fill_count=len(unbound_ids),
                fill_time_limit_seconds=_fill_solve_seconds(
                    budget, len(unbound_ids),
                    declared_search_seconds=(
                        _classic_declared_search_seconds(portfolio_policy)
                        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy) else None)),
                differentiate_captain=not allow_repeat_captain,
                max_person_overlap=max_person_overlap,
                role_evidence_json=role_evidence_json,
                offensive_role_evidence_json=offensive_role_evidence_json,
                qb_depth_role_evidence_json=qb_depth_role_evidence_json,
                as_of=as_of,
                portfolio_policy=portfolio_policy,
                forbidden_rosters=entry_plan.forbidden_rosters,
                **selection_limits,
            )
        policy_rosters = [lineup.roster for lineup in lineups[: len(bound_ids)]]
        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
            bound_assignments = dict(
                exact_classic_assignments(portfolio_policy.entry_ids, policy_rosters)
            )
        elif portfolio_policy is not None:
            bound_assignments = exact_assignments_for_entries(
                portfolio_policy.entry_ids, policy_rosters
            )
        if portfolio_policy is not None:
            # Every fillable row once, in template order: the policy's rows from
            # its joint solve, the rest from the fill, never cycled.
            filled = [lineup.roster for lineup in lineups[len(bound_ids):]]
            unbound_assignments = (
                exact_assignments_for_entries(unbound_ids, filled) if unbound_ids or filled else {}
            )
            assignments = {
                entry_id: (bound_assignments[entry_id] if entry_id in bound_assignments
                           else unbound_assignments[entry_id])
                for entry_id in entry_ids
            }
        else:
            assignments = assignments_for_entries(entry_ids, lineups)
    except Exception as exc:  # noqa: BLE001 - named, never swallowed
        error = f"{type(exc).__name__}:{exc}"
        stages.append(_stage("SELECT", "FAILED", error=error))
        if isinstance(exc, OffensiveRoleError):
            reports["offensive_roles"] = exc.report
        if isinstance(exc, SelectionError) and exc.status:
            # Structured (Session 10): the relaxation controller reads this, not the text.
            reports["selection_failure"] = exc.as_report(error=error)
        return PriorReviewOutcome(
            profile_version=profile_version,
            stage="SELECT",
            blocked=True,
            blockers=(f"SELECTION_FAILED:{error}",),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=error,
        )

    names = {
        player.dk_id: f"{player.name} ({player.position}, {player.team})"
        for player in slate.players
    }
    selection_dir = run_dir / "selection"
    role_resolution = scores.kicker_role_resolution
    offensive_resolution = scores.offensive_role_resolution
    selected_ids = {
        dk_id for lineup in lineups for dk_id in lineup.roster
    }
    by_dk_id = {player.dk_id: player for player in slate.players}
    selected_people = {
        by_dk_id[dk_id].underlying_id for dk_id in selected_ids
    }
    selected_unavailable = sorted(
        selected_people.intersection(contract.unavailable_people)
    )
    activity_coverage = _official_status_coverage(
        slate, lineups, reports.get("official_status")
    )
    selected_evidence_gaps: list[dict[str, object]] = []
    if slate.mode is EngineMode.CLASSIC:
        if offensive_resolution.report.get("synthetic_sources"):
            selected_evidence_gaps.append(
                {
                    "person": "SELECTED_OFFENSE",
                    "evidence": "CURRENT_OFFENSIVE_ROLE",
                    "state": "SYNTHETIC_TEST_EVIDENCE",
                    "smallest_evidence_action": (
                        "Replace synthetic role sources with fresh approved captured sources."
                    ),
                }
            )
        if selected_unavailable:
            selected_evidence_gaps.extend(
                {
                    "person": person,
                    "evidence": "PARTICIPATION",
                    "smallest_evidence_action": "Remove the unavailable person and rerun selection.",
                }
                for person in selected_unavailable
            )
        # R28 (Session 09): a selected person with no exact-ID activity row is a
        # named limitation, as Showdown already treats it, not a stop. It stops
        # certification: the release truths stay DO_NOT_UPLOAD, and `run-slate`
        # names OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED for a file that omits him,
        # or OFFICIAL_STATUS_REQUIRED when no file was supplied. An INACTIVE row
        # took him out of the pool before selection; an invalid, stale, future or
        # changed file still stops the run above and below.
        missing_activity = (
            sorted(selected_people)
            if activity_coverage is None
            else list(activity_coverage["selected_without_row"])
        )
        activity_gaps = [
            {
                "person": person,
                "evidence": "OFFICIAL_ACTIVITY",
                "state": (
                    "NO_OFFICIAL_STATUS_FILE"
                    if activity_coverage is None
                    else "NO_EXACT_ID_ROW_IN_SUPPLIED_FILE"
                ),
                "limitation": (
                    "OFFICIAL_STATUS_REQUIRED"
                    if activity_coverage is None
                    else "OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED"
                ),
                "smallest_evidence_action": (
                    "Capture a fresh exact-ID ACTIVE or INACTIVE row from the approved "
                    "official status source and rerun."
                ),
            }
            for person in missing_activity
        ]
        finding_by_person = {
            str(item.get("person")): item
            for item in offensive_resolution.report.get("findings", [])
            if isinstance(item, Mapping) and item.get("person")
        }
        # R17 extended to Classic, 2026-09-12, on Ben's explicit ruling. The
        # resolver is the single authority on whether a role is good enough to
        # select: it BLOCKS an unresolved or declared-changed role before any
        # selection happens, and EXCLUDES a person with no prior-season row, so
        # anyone who survives into a lineup already carries a SELECT or
        # DIAGNOSTIC action. Classic previously demanded
        # `SOURCE_SUPPORTED_ADJUSTMENT` here, which only a captured numerical
        # team allocation produces and no approved host publishes before a game,
        # so a live Classic slate could never publish while the identical
        # Showdown pool could. This gate is now exactly as strict as Showdown
        # and no stricter; every state that is not source-supported is named in
        # `selected_role_observations` rather than passing silently.
        selected_role_observations: list[dict[str, object]] = []
        for person in sorted(selected_people):
            selected_player = next(
                player
                for player in slate.players
                if player.underlying_id == person
            )
            if selected_player.position not in {"QB", "RB", "WR", "TE"}:
                continue
            finding = finding_by_person.get(person)
            selection_action = (
                str(finding.get("selection_action") or "") if finding else ""
            )
            if not finding or selection_action not in {"SELECT", "DIAGNOSTIC"}:
                selected_evidence_gaps.append(
                    {
                        "person": person,
                        "evidence": "CURRENT_OFFENSIVE_ROLE",
                        "state": finding.get("state") if finding else "MISSING",
                        "selection_action": selection_action or "MISSING",
                        "smallest_evidence_action": (
                            finding.get("next_evidence_action")
                            if finding
                            else "Capture a fresh exact-ID numerical current-team allocation."
                        ),
                    }
                )
                continue
            selected_role_observations.append(
                {
                    "person": person,
                    "dk_id": selected_player.dk_id,
                    "team": selected_player.team,
                    "position": selected_player.position,
                    "state": finding.get("state"),
                    "selection_action": selection_action,
                    "finding": finding.get("finding"),
                    "next_evidence_action": finding.get("next_evidence_action"),
                }
            )
        unverified_role_people = sorted(
            str(item["person"])
            for item in selected_role_observations
            if item.get("state") != "SOURCE_SUPPORTED_ADJUSTMENT"
        )
        reports["selected_evidence_gate"] = {
            "schema_version": "nfl_classic_selected_evidence_gate_c1_v3",
            "selected_people": sorted(selected_people),
            "gaps": selected_evidence_gaps,
            "activity_gaps": activity_gaps,
            "selected_role_observations": selected_role_observations,
            "unverified_role_people": unverified_role_people,
            "role_basis": (
                "HISTORY_DERIVED_PRIOR_IS_NOT_A_CURRENT_ROLE"
                if unverified_role_people
                else "EVERY_SELECTED_ROLE_IS_SOURCE_SUPPORTED"
            ),
            "status": (
                "BLOCKED"
                if selected_evidence_gaps
                else "PASS_WITH_NAMED_LIMITATIONS" if activity_gaps else "PASS"
            ),
        }
        if selected_evidence_gaps:
            blocker = (
                "SELECTED_CURRENT_EVIDENCE_REQUIRED:"
                + ";".join(
                    f"{item['evidence']}:{item['person']}:{item['smallest_evidence_action']}"
                    for item in selected_evidence_gaps
                )
            )
            stages.append(
                _stage(
                    "SELECT",
                    "BLOCKED_SELECTED_EVIDENCE",
                    gaps=len(selected_evidence_gaps),
                )
            )
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="SELECT",
                blocked=True,
                blockers=(blocker,),
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
            )
    if offensive_resolution.evidence_path:
        artifacts["offensive_role_evidence_json"] = offensive_resolution.evidence_path
        hashes["offensive_role_evidence_json"] = str(offensive_resolution.evidence_sha256)
        for index, (path, digest) in enumerate(sorted((offensive_resolution.source_hashes or {}).items()), start=1):
            artifacts[f"offensive_role_source:{index}"] = path
            hashes[f"offensive_role_source:{index}"] = digest
    qb_depth_report = selection.get("qb_depth_roles") or {}
    if qb_depth_report.get("evidence_path"):
        artifacts["qb_depth_role_evidence_json"] = str(qb_depth_report["evidence_path"])
        hashes["qb_depth_role_evidence_json"] = str(qb_depth_report["evidence_sha256"])
        for index, (path, digest) in enumerate(
            sorted((qb_depth_report.get("source_hashes") or {}).items()), start=1
        ):
            artifacts[f"qb_depth_source:{index}"] = path
            hashes[f"qb_depth_source:{index}"] = digest
    if role_resolution.evidence_path is not None:
        artifacts["role_evidence_json"] = role_resolution.evidence_path
        hashes["role_evidence_json"] = str(role_resolution.evidence_sha256)
        for index, source_path in enumerate(role_resolution.source_paths, start=1):
            artifacts[f"role_evidence_source:{index}"] = source_path
            hashes[f"role_evidence_source:{index}"] = str(
                (role_resolution.source_hashes or {})[source_path]
            )
    assignments_path = selection_dir / "assignments.csv"
    assignments_hash = ""
    if slate.mode is EngineMode.SHOWDOWN:
        assignments_hash = write_assignments_csv(
            assignments_path,
            assignments,
            entry_order=tuple(entry_ids) if portfolio_policy is not None else None,
        )
        artifacts["assignments"] = str(assignments_path)
        hashes["assignments"] = assignments_hash
    else:
        # Classic previously left its selection only as `classic_assignment.json`,
        # which `lineups.read_assignment_csv` cannot read, so a Classic run could
        # not bind an assignment into a pre-lock manifest at all. This is the same
        # nine-slot geometry `certify` and `settle` already accept; it is an
        # additional record of the same selection, and changes none of the C2/C3
        # artifacts that remain authoritative for the audit.
        assignments_hash = write_assignments_csv(
            assignments_path,
            assignments,
            entry_order=(
                tuple(entry_ids)
                if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                else None
            ),
            mode=EngineMode.CLASSIC,
        )
        artifacts["assignments"] = str(assignments_path)
        hashes["assignments"] = assignments_hash

    def freeze_prelock(export_report: Mapping[str, object]) -> dict[str, object]:
        """Freeze this run's prediction, whichever success path it exits by.

        Showdown, Classic C1/C2 and Classic C3 each return from their own place,
        and a manifest emitted on only one of them would silently make the other
        two unsettleable — which is exactly the failure Q1B found. Bound here,
        once, so every exit carries the same record.
        """
        return _emit_prelock_manifest(
            run_dir=run_dir,
            as_of=as_of,
            slate=slate,
            template=template,
            salary_digest=salary_digest,
            assignments=assignments,
            assignments_path=assignments_path,
            assignments_hash=assignments_hash,
            projection=projection,
            export_report=export_report,
            artifacts=artifacts,
            hashes=hashes,
        )

    selection_report = {
        "status": "DO_NOT_UPLOAD",
        "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "assignments": str(assignments_path) if slate.mode is EngineMode.SHOWDOWN else None,
        "assignments_sha256": assignments_hash or None,
        "reserved_entries": entry_ids,
        # Session 11b: which source filled each row (the policy, or the fill).
        "row_sources": row_sources(
            list(assignments), bound_ids if portfolio_policy is not None else (), slate.mode),
        "lineups": [lineup.as_payload(names) for lineup in lineups],
        "selected_prior_points_by_dk_id": {
            dk_id: scores.by_dk_id[dk_id]
            for dk_id in sorted({dk_id for lineup in lineups for dk_id in lineup.roster})
        },
        "participation": contract.as_report(),
        "participation_detail": {
            "unavailable_people": list(contract.unavailable_people),
            "degraded_people": list(contract.degraded_people),
            "operator_excluded_people": list(contract.operator_excluded_people),
            "status_by_person": dict(sorted(contract.status_by_person.items())),
        },
        "redistribution": redistribution,
        "pool_coverage": pool_coverage_summary(
            slate,
            contract,
            official_inactive_dk_ids=official_exclusions,
            operator_excluded_dk_ids=tuple(operator_excluded_dk_ids),
            offense_excluded_people=scores.offensive_role_resolution.excluded_people,
            kicker_zero_share_people=scores.kicker_role_resolution.zero_share_people,
            unallocated_by_team=dict(
                scores.offensive_role_resolution.report.get("unallocated_by_team") or {}
            ),
            offense_excluded_by_finding=dict(
                scores.offensive_role_resolution.report.get("excluded_by_finding") or {}
            ),
            offense_findings=tuple(
                scores.offensive_role_resolution.report.get("findings") or ()
            ),
            official_statuses=dict(
                (reports.get("official_status") or {}).get("statuses") or {}
            ),
        ),
        "official_status_coverage": activity_coverage,
        "assignment_summary": {
            "lineups_generated": len(lineups),
            "reserved_entries": len(entry_ids),
            "unassigned_lineups": max(0, len(lineups) - len(entry_ids)),
            "note": (
                "Lineups beyond the reserved-entry count are retained in this report"
                " for review and are not written to any entry."
                if len(lineups) > len(entry_ids)
                else "Every reserved entry received its own lineup."
            ),
        },
        "selection": selection,
        "prior_scores": scores.as_report(),
        "warning": (
            "Prior-only selection maximizing a central estimate. Not a ceiling, not"
            " ownership aware, and not EV, ROI, win probability or edge."
        ),
    }
    if slate.mode is EngineMode.CLASSIC:
        # Publish only after re-reading every immutable input and current-evidence
        # artifact.  The JSON is deliberately not a DraftKings-shaped template;
        # C3 owns review/export redesign and this C1 output cannot be uploaded.
        mutation_checks = (
            (salary_path, salary_digest, "SALARY"),
            (entry_path, hashes["entry_csv"], "ENTRY"),
            (package.team_source, package.hashes[TEAM_PRIOR_FILENAME], "TEAM_PRIOR"),
            (package.player_source, package.hashes[PLAYER_PRIOR_FILENAME], "PLAYER_PRIOR"),
            (package.identity_map, package.hashes[IDENTITY_MAP_FILENAME], "IDENTITY_MAP"),
            (projection.team_projections, projection.hashes["team_projections"], "TEAM_PROJECTIONS"),
            (projection.player_opportunities, projection.hashes["player_opportunities"], "PLAYER_OPPORTUNITIES"),
            (projection.source_ledger, projection.hashes["source_ledger"], "SOURCE_LEDGER"),
        )
        for source_path, expected_hash, label_name in mutation_checks:
            if sha256_file(source_path) != expected_hash:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="SELECT",
                    blocked=True,
                    blockers=(f"{label_name}_CHANGED_BEFORE_ARTIFACT_PUBLISH",),
                    stages=tuple(stages) + (
                        _stage("SELECT", "BLOCKED_INPUT_MUTATION", input=label_name),
                    ),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                )
        if weather_evidence_json is not None and sha256_file(weather_evidence_json) != hashes.get(
            "weather_evidence_json"
        ):
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="SELECT",
                blocked=True,
                blockers=("WEATHER_EVIDENCE_CHANGED_BEFORE_ARTIFACT_PUBLISH",),
                stages=tuple(stages) + (
                    _stage("SELECT", "BLOCKED_INPUT_MUTATION", input="WEATHER_EVIDENCE"),
                ),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
            )
        for key, expected_hash in sorted(hashes.items()):
            if not key.startswith("weather_source:"):
                continue
            if sha256_file(artifacts[key]) != expected_hash:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="SELECT",
                    blocked=True,
                    blockers=(f"WEATHER_SOURCE_CHANGED_BEFORE_ARTIFACT_PUBLISH:{key}",),
                    stages=tuple(stages) + (
                        _stage("SELECT", "BLOCKED_INPUT_MUTATION", input=key),
                    ),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                )
        if official_status_csv is not None and sha256_file(official_status_csv) != hashes.get(
            "official_status_csv"
        ):
            return PriorReviewOutcome(
                profile_version=profile_version,
                stage="SELECT",
                blocked=True,
                blockers=("OFFICIAL_STATUS_CHANGED_BEFORE_ARTIFACT_PUBLISH",),
                stages=tuple(stages) + (
                    _stage("SELECT", "BLOCKED_INPUT_MUTATION", input="OFFICIAL_STATUS"),
                ),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
            )
        verify_offensive_resolution(offensive_resolution, at=as_of)
        official_statuses = dict(
            (reports.get("official_status") or {}).get("statuses") or {}
        )
        overall_evidence_state = (
            "PASS"
            if set(official_statuses) == {player.dk_id for player in slate.players}
            and offensive_resolution.report.get("evidence_state") == "PASS"
            and not offensive_resolution.report.get("synthetic_sources")
            and not reports.get("weather_unobserved")
            else "UNKNOWN"
        )
        classic_policy_report: dict[str, object] | None = None
        classic_audit_report: dict[str, object] | None = None
        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
            def blocked_classic_portfolio(message: str) -> PriorReviewOutcome:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="SELECT",
                    blocked=True,
                    blockers=(message,),
                    stages=tuple(stages)
                    + (_stage("SELECT", "BLOCKED_CLASSIC_PORTFOLIO"),),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                    error=message,
                )

            assert policy_source_path is not None
            assert policy_normalized_path is not None
            assert portfolio_policy_source_sha256 is not None
            assert portfolio_policy_normalized_sha256 is not None
            raw_policy_report = selection.get("portfolio_policy")
            if not isinstance(raw_policy_report, Mapping):
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="SELECT",
                    blocked=True,
                    blockers=("CLASSIC_PORTFOLIO_SELECTION_REPORT_MISSING",),
                    stages=tuple(stages) + (_stage("SELECT", "BLOCKED_POLICY_REPORT"),),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                )
            classic_policy_report = dict(raw_policy_report)
            candidate_json = classic_policy_report.get(
                "candidate_bank_canonical_json"
            )
            if not isinstance(candidate_json, str):
                return blocked_classic_portfolio(
                    "CLASSIC_CANDIDATE_BANK_CANONICAL_BYTES_MISSING"
                )
            candidate_bytes = candidate_json.encode("utf-8")
            expected_candidate_hash = str(
                classic_policy_report.get("candidate_bank_sha256") or ""
            )
            if sha256_file(policy_source_path) != portfolio_policy_source_sha256:
                return blocked_classic_portfolio(
                    "CLASSIC_POLICY_SOURCE_CHANGED_BEFORE_BANK_PUBLISH"
                )
            if sha256_file(policy_normalized_path) != portfolio_policy_normalized_sha256:
                return blocked_classic_portfolio(
                    "CLASSIC_POLICY_NORMALIZED_CHANGED_BEFORE_BANK_PUBLISH"
                )
            if sha256_bytes(candidate_bytes) != expected_candidate_hash:
                return blocked_classic_portfolio(
                    "CLASSIC_CANDIDATE_BANK_IN_MEMORY_HASH_MISMATCH"
                )
            selection_dir.mkdir(parents=True, exist_ok=True)
            candidate_path = selection_dir / "classic_candidate_bank.json"
            candidate_temporary = candidate_path.with_suffix(".json.tmp")
            candidate_temporary.write_bytes(candidate_bytes)
            candidate_temporary.replace(candidate_path)
            if sha256_file(candidate_path) != expected_candidate_hash:
                return blocked_classic_portfolio(
                    "CLASSIC_CANDIDATE_BANK_POST_WRITE_HASH_MISMATCH"
                )
            artifacts["classic_candidate_bank"] = str(candidate_path)
            hashes["classic_candidate_bank"] = expected_candidate_hash

            ordered_assignments = exact_classic_assignments(
                portfolio_policy.entry_ids,
                [assignments[entry_id] for entry_id in portfolio_policy.entry_ids],
            )
            assignment_bytes = assignment_artifact_bytes(
                portfolio_policy,
                ordered_assignments,
                candidate_bank_sha256=expected_candidate_hash,
            )
            assignment_hash = sha256_bytes(assignment_bytes)
            assignment_json_path = selection_dir / "classic_assignment.json"
            assignment_temporary = assignment_json_path.with_suffix(".json.tmp")
            assignment_temporary.write_bytes(assignment_bytes)
            assignment_temporary.replace(assignment_json_path)
            if sha256_file(assignment_json_path) != assignment_hash:
                return blocked_classic_portfolio(
                    "CLASSIC_ASSIGNMENT_POST_WRITE_HASH_MISMATCH"
                )
            artifacts["classic_assignment"] = str(assignment_json_path)
            hashes["classic_assignment"] = assignment_hash

            bound_artifacts: dict[str, tuple[bytes, str]] = {
                "team_prior_sha256": (
                    Path(package.team_source).read_bytes(),
                    package.hashes[TEAM_PRIOR_FILENAME],
                ),
                "player_prior_sha256": (
                    Path(package.player_source).read_bytes(),
                    package.hashes[PLAYER_PRIOR_FILENAME],
                ),
                "identity_map_sha256": (
                    Path(package.identity_map).read_bytes(),
                    package.hashes[IDENTITY_MAP_FILENAME],
                ),
                "team_projections_sha256": (
                    Path(projection.team_projections).read_bytes(),
                    projection.hashes["team_projections"],
                ),
                "player_opportunities_sha256": (
                    Path(projection.player_opportunities).read_bytes(),
                    projection.hashes["player_opportunities"],
                ),
                "source_ledger_sha256": (
                    Path(projection.source_ledger).read_bytes(),
                    projection.hashes["source_ledger"],
                ),
                "team_splits_sha256": (
                    Path(splits_path).read_bytes(),
                    hashes["frozen:team_stats"],
                ),
            }
            for artifact_key, expected_hash in sorted(hashes.items()):
                if artifact_key in {
                    "official_status_csv",
                    "offensive_role_evidence_json",
                    "qb_depth_role_evidence_json",
                    "role_evidence_json",
                    "weather_evidence_json",
                } or artifact_key.startswith(
                    (
                        "offensive_role_source:",
                        "qb_depth_source:",
                        "role_evidence_source:",
                        "weather_source:",
                    )
                ):
                    artifact_path = artifacts.get(artifact_key)
                    if artifact_path is not None:
                        bound_artifacts[f"{artifact_key}_sha256"] = (
                            Path(artifact_path).read_bytes(),
                            expected_hash,
                        )
            audit = audit_classic_portfolio(
                slate=slate,
                normalized_policy_bytes=policy_normalized_path.read_bytes(),
                expected_normalized_policy_sha256=portfolio_policy_normalized_sha256,
                source_policy_bytes=policy_source_path.read_bytes(),
                expected_source_policy_sha256=portfolio_policy_source_sha256,
                salary_bytes=salary_path.read_bytes(),
                expected_salary_sha256=salary_digest,
                entry_bytes=entry_path.read_bytes(),
                expected_entry_sha256=hashes["entry_csv"],
                bound_artifacts=bound_artifacts,
                candidate_bytes=candidate_path.read_bytes(),
                expected_candidate_sha256=expected_candidate_hash,
                assignment_bytes=assignment_json_path.read_bytes(),
                expected_assignment_sha256=assignment_hash,
            )
            classic_audit_report = audit.as_report()
            reports["classic_portfolio_audit"] = classic_audit_report
            audit_path = selection_dir / "classic_portfolio_audit.json"
            audit_hash = _write_canonical_json(audit_path, classic_audit_report)
            artifacts["classic_portfolio_audit"] = str(audit_path)
            hashes["classic_portfolio_audit"] = audit_hash
            if not audit.passed:
                return PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="SELECT",
                    blocked=True,
                    blockers=(
                        "CLASSIC_PORTFOLIO_INDEPENDENT_AUDIT_FAILED:"
                        + ";".join(audit.problems),
                    ),
                    stages=tuple(stages)
                    + (_stage("SELECT", "BLOCKED_INDEPENDENT_AUDIT"),),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                )
            post_audit_checks: list[tuple[str | Path, str, str]] = [
                (salary_path, salary_digest, "salary_csv"),
                (entry_path, hashes["entry_csv"], "entry_csv"),
                (package.team_source, package.hashes[TEAM_PRIOR_FILENAME], "team_source"),
                (package.player_source, package.hashes[PLAYER_PRIOR_FILENAME], "player_source"),
                (package.identity_map, package.hashes[IDENTITY_MAP_FILENAME], "identity_map"),
                (projection.team_projections, projection.hashes["team_projections"], "team_projections"),
                (projection.player_opportunities, projection.hashes["player_opportunities"], "player_opportunities"),
                (projection.source_ledger, projection.hashes["source_ledger"], "source_ledger"),
                (splits_path, hashes["frozen:team_stats"], "team_splits"),
                (policy_source_path, portfolio_policy_source_sha256, "portfolio_policy_source"),
                (policy_normalized_path, portfolio_policy_normalized_sha256, "portfolio_policy_normalized"),
                (candidate_path, expected_candidate_hash, "classic_candidate_bank"),
                (assignment_json_path, assignment_hash, "classic_assignment"),
                (audit_path, audit_hash, "classic_portfolio_audit"),
            ]
            for artifact_key, expected_hash in sorted(hashes.items()):
                if artifact_key in {
                    "official_status_csv",
                    "offensive_role_evidence_json",
                    "qb_depth_role_evidence_json",
                    "role_evidence_json",
                    "weather_evidence_json",
                } or artifact_key.startswith(
                    (
                        "offensive_role_source:",
                        "qb_depth_source:",
                        "role_evidence_source:",
                        "weather_source:",
                    )
                ):
                    artifact_path = artifacts.get(artifact_key)
                    if artifact_path is not None:
                        post_audit_checks.append(
                            (artifact_path, expected_hash, artifact_key)
                        )
            for artifact_path, expected_hash, artifact_key in post_audit_checks:
                if sha256_file(artifact_path) != expected_hash:
                    return PriorReviewOutcome(
                        profile_version=profile_version,
                        stage="SELECT",
                        blocked=True,
                        blockers=(
                            f"CLASSIC_PORTFOLIO_ARTIFACT_MUTATED_AFTER_AUDIT:{artifact_key}",
                        ),
                        stages=tuple(stages)
                        + (_stage("SELECT", "BLOCKED_POST_AUDIT_MUTATION"),),
                        artifacts=artifacts,
                        hashes=hashes,
                        reports=reports,
                    )
        immutable_bindings = {
            "salary_sha256": salary_digest,
            "entry_sha256": hashes["entry_csv"],
            "team_prior_sha256": package.hashes[TEAM_PRIOR_FILENAME],
            "player_prior_sha256": package.hashes[PLAYER_PRIOR_FILENAME],
            "identity_map_sha256": package.hashes[IDENTITY_MAP_FILENAME],
            "team_projections_sha256": projection.hashes["team_projections"],
            "player_opportunities_sha256": projection.hashes["player_opportunities"],
            "source_ledger_sha256": projection.hashes["source_ledger"],
            "official_status_sha256": hashes.get("official_status_csv"),
            "offensive_role_evidence_sha256": hashes.get("offensive_role_evidence_json"),
            "qb_depth_role_evidence_sha256": hashes.get("qb_depth_role_evidence_json"),
            "weather_evidence_sha256": hashes.get("weather_evidence_json"),
            "weather_source_sha256_by_game": {
                key.removeprefix("weather_source:"): value
                for key, value in sorted(hashes.items())
                if key.startswith("weather_source:")
            },
        }
        stable_lineups = [
            {
                "index": lineup.index,
                "roster": list(lineup.roster),
                "salary": lineup.salary,
                "prior_points": round(lineup.prior_points, 6),
                "canonical_key": (
                    lineup.canonical_key
                    if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                    else list(lineup.canonical_key)
                ),
                "solver_status": lineup.solver_status,
            }
            for lineup in lineups
        ]
        stable_selection = {
            "schema_version": (
                CLASSIC_SELECTION_SCHEMA_C2
                if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                else CLASSIC_SELECTION_SCHEMA
            ),
            "artifact_class": "REVIEW_ONLY_NOT_DRAFTKINGS_UPLOAD",
            "FILE_VALID": True,
            "EVIDENCE_STATE": overall_evidence_state,
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
            "mode": slate.mode.value,
            "draft_group": slate.draft_group,
            "scoring_version": slate.scoring_version,
            "immutable_bindings": immutable_bindings,
            "assignments_by_entry_id": {
                entry_id: list(roster)
                for entry_id, roster in sorted(assignments.items())
            },
            "lineups": stable_lineups,
            "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "limitations": [
                "NOT_CALIBRATED_EV_ROI_WIN_OR_CASH_PROBABILITY",
                "NO_OWNERSHIP_FIELD_DUPLICATION_PAYOUT_OR_PORTFOLIO_ECONOMICS",
                "NOT_UPLOAD_READY",
            ],
        }
        stable_coverage = {
            "schema_version": (
                CLASSIC_COVERAGE_SCHEMA_C2
                if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                else CLASSIC_COVERAGE_SCHEMA
            ),
            "artifact_class": "COMPLETE_SLATE_REVIEW_COVERAGE",
            "FILE_VALID": True,
            "EVIDENCE_STATE": overall_evidence_state,
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
            "mode": slate.mode.value,
            "immutable_bindings": immutable_bindings,
            "games": reports["intake"]["games"],
            "official_status_coverage": activity_coverage,
            "selected_evidence_gate": reports.get("selected_evidence_gate"),
            "pool_coverage": selection_report["pool_coverage"],
            "conservation": {
                "declared_totals_by_team": offensive_resolution.report.get(
                    "declared_totals", {}
                ),
                "declared_unallocated_by_team": offensive_resolution.report.get(
                    "declared_unallocated", {}
                ),
                "basis": (
                    "For each team and registered opportunity field, explicit "
                    "recipient shares plus unallocated share equal one."
                ),
            },
        }
        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
            immutable_bindings.update(
                {
                    "source_policy_sha256": hashes["portfolio_policy_source"],
                    "normalized_policy_sha256": hashes[
                        "portfolio_policy_normalized"
                    ],
                    "candidate_bank_sha256": hashes["classic_candidate_bank"],
                    "assignment_sha256": hashes["classic_assignment"],
                    "classic_portfolio_audit_sha256": hashes[
                        "classic_portfolio_audit"
                    ],
                }
            )
            stable_selection.update(
                {
                    "entry_assignments": [
                        {
                            "entry_id": entry_id,
                            "roster": list(assignments[entry_id]),
                        }
                        for entry_id in portfolio_policy.entry_ids
                    ],
                    "portfolio_policy": {
                        "source_policy_sha256": portfolio_policy_source_sha256,
                        "normalized_policy_sha256": portfolio_policy_normalized_sha256,
                        "candidate_bank_sha256": hashes["classic_candidate_bank"],
                        "assignment_sha256": hashes["classic_assignment"],
                        "audit_sha256": hashes["classic_portfolio_audit"],
                        "enforcement": {
                            "status": "ENFORCED_AND_INDEPENDENTLY_AUDITED",
                            "candidate_bank_status": dict(
                                (classic_policy_report or {}).get(
                                    "candidate_bank_artifact", {}
                                )
                            ).get("status"),
                            "joint_selection_status": dict(
                                (classic_policy_report or {}).get("solve", {})
                            ).get("status"),
                            # Scoped only for a proven optimum (Session 08).
                            "optimality_scope": dict(
                                (classic_policy_report or {}).get("solve", {})
                            ).get("optimality_scope"),
                        },
                        "independent_audit": classic_audit_report,
                    },
                }
            )
            stable_coverage["policy_coverage"] = {
                "candidate_bank": (
                    classic_policy_report.get("candidate_bank_artifact")
                    if classic_policy_report
                    else None
                ),
                "independent_audit": classic_audit_report,
            }
        selection_report_path = selection_dir / "classic_selection.json"
        coverage_report_path = selection_dir / "classic_complete_slate_coverage.json"
        selection_report_hash = _write_canonical_json(
            selection_report_path, stable_selection
        )
        coverage_report_hash = _write_canonical_json(
            coverage_report_path, stable_coverage
        )
        artifacts["selection_report"] = str(selection_report_path)
        artifacts["complete_slate_coverage"] = str(coverage_report_path)
        hashes["selection_report"] = selection_report_hash
        hashes["complete_slate_coverage"] = coverage_report_hash
    else:
        selection_report_path = selection_dir / "selection_report.json"
        selection_report_hash = write_run_record(selection_report_path, selection_report)
        artifacts["selection_report"] = str(selection_report_path)
        hashes["selection_report"] = selection_report_hash
    reports["selection"] = selection_report
    stages.append(
        _stage(
            "SELECT",
            "OK",
            lineups=len(lineups),
            reserved_entries=len(entry_ids),
            selectable_people=len(contract.selectable_people),
            unavailable_people=len(contract.unavailable_people),
        )
    )

    # ----------------------------------------------------------------- EXPORT
    if slate.mode is EngineMode.CLASSIC:
        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
            selected_score_ids = sorted(
                {dk_id for roster in assignments.values() for dk_id in roster}, key=int
            )
            score_snapshot_path = selection_dir / "classic_selected_scores.json"
            score_snapshot_hash = _write_canonical_json(
                score_snapshot_path,
                {
                    "schema_version": SCORE_SNAPSHOT_VERSION,
                    "salary_sha256": salary_digest,
                    "assignment_sha256": hashes["classic_assignment"],
                    "scores_by_dk_id": {
                        dk_id: scores.by_dk_id[dk_id] for dk_id in selected_score_ids
                    },
                    "metric": "DRAFTKINGS_POINTS_OF_THE_EXPECTED_STAT_LINE",
                    "not_a_claim_of": (
                        "CEILING_LEVERAGE_EV_ROI_WIN_PROBABILITY_CASH_PROBABILITY_"
                        "CALIBRATED_OWNERSHIP_OR_VALIDATED_PERFORMANCE"
                    ),
                },
            )
            artifacts["classic_selected_scores"] = str(score_snapshot_path)
            hashes["classic_selected_scores"] = score_snapshot_hash
            package_root = (
                run_dir.parent
                if run_dir.parent == out_dir.parent
                else Path.cwd().resolve()
            )
            review_dir = out_dir / "review"
            # R28 (Session 05): a readable-review failure after the export and its
            # audit passed keeps both, so they are listed here; run-slate
            # classifies the failure and publishes or withholds the CSV.
            readable_failure: ClassicReviewPresentationError | None = None
            try:
                classic_review = create_classic_review_package(
                    salary_path=salary_path,
                    entry_path=entry_path,
                    artifacts=artifacts,
                    expected_hashes=hashes,
                    audit_at=(datetime.now(timezone.utc) if live_run else as_of),
                    output_path=review_dir / f"DK_REVIEW_ENTRY_{_safe_label(label)}.csv",
                    output_dir=review_dir,
                    package_root=package_root,
                )
            except ClassicReviewPresentationError as exc:
                classic_review = None
                readable_failure = exc
            except (OSError, ValueError) as exc:
                error = f"{type(exc).__name__}:{exc}"
                stages.append(_stage("EXPORT", "FAILED_C3_DOWNSTREAM_AUDIT", error=error))
                outcome = PriorReviewOutcome(
                    profile_version=profile_version,
                    stage="EXPORT",
                    blocked=True,
                    blockers=(f"CLASSIC_C3_REVIEW_EXPORT_FAILED:{error}",),
                    stages=tuple(stages),
                    artifacts=artifacts,
                    hashes=hashes,
                    reports=reports,
                    error=error,
                )
                write_run_record(run_dir / "prior_review.json", outcome.as_report())
                return outcome
            kept = classic_review if classic_review is not None else readable_failure
            assert kept is not None
            artifacts.update(
                {"classic_export_audit": kept.audit_path, "bulk_entry_csv": kept.export_path}
            )
            hashes.update(
                {"classic_export_audit": kept.audit_sha256, "bulk_entry_csv": kept.export_sha256}
            )
            reports["classic_export_audit"] = kept.audit
            if classic_review is not None:
                artifacts.update(
                    {
                        "readable_review_json": classic_review.json_path,
                        "readable_review_html": classic_review.html_path,
                    }
                )
                hashes.update(
                    {
                        "readable_review_json": classic_review.json_sha256,
                        "readable_review_html": classic_review.html_sha256,
                    }
                )
                reports["readable_review"] = classic_review.data
            export_report = {
                "FILE_VALID": True,
                "EVIDENCE_STATE": overall_evidence_state,
                "MODEL_STATUS": "PRIOR_ONLY",
                "RELEASE_DECISION": "DO_NOT_UPLOAD",
                "file_kind": "EXACT_TEMPLATE_REVIEW_CSV_NOT_UPLOAD_CERTIFICATION",
                "bulk_entry_csv": kept.export_path,
                "bulk_entry_sha256": kept.export_sha256,
                "downstream_audit": kept.audit_path,
                "downstream_audit_sha256": kept.audit_sha256,
                "readable_review_json": classic_review.json_path if classic_review else None,
                "readable_review_json_sha256": (
                    classic_review.json_sha256 if classic_review else None
                ),
                "readable_review_html": classic_review.html_path if classic_review else None,
                "readable_review_html_sha256": (
                    classic_review.html_sha256 if classic_review else None
                ),
                "certification_basis": "NOT_CERTIFIED_CLASSIC_C3_REVIEW_ONLY",
                "warning": (
                    "Exact-template and independently audited review bytes only. "
                    "This remains PRIOR_ONLY / DO_NOT_UPLOAD."
                ),
            }
            if readable_failure is not None:
                export_report["readable_review_failure"] = str(readable_failure)
            stages.append(
                _stage(
                    "EXPORT",
                    "C3_INDEPENDENT_AUDIT_AND_REVIEW_PASS"
                    if readable_failure is None
                    else "C3_INDEPENDENT_AUDIT_PASS_READABLE_REVIEW_FAILED",
                    file_valid=True,
                    release_decision="DO_NOT_UPLOAD",
                    **({"error": str(readable_failure)} if readable_failure is not None else {}),
                )
            )
            stages.append(freeze_prelock(export_report))
            outcome = PriorReviewOutcome(
                profile_version=profile_version,
                stage="EXPORT",
                blocked=False,
                blockers=(
                    (f"CLASSIC_C3_READABLE_REVIEW_FAILED:{readable_failure}",)
                    if readable_failure is not None
                    else ()
                ),
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
                export=export_report,
            )
            write_run_record(run_dir / "prior_review.json", outcome.as_report())
            return outcome
        export_report = {
            "FILE_VALID": True,
            "EVIDENCE_STATE": overall_evidence_state,
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
            "file_kind": "VERSIONED_MACHINE_READABLE_REVIEW_ARTIFACTS",
            "bulk_entry_csv": None,
            "bulk_entry_sha256": None,
            "selection_artifact": artifacts["selection_report"],
            "selection_sha256": hashes["selection_report"],
            "coverage_artifact": artifacts["complete_slate_coverage"],
            "coverage_sha256": hashes["complete_slate_coverage"],
            "note": (
                "Classic C2 emits no DraftKings-shaped CSV. FILE_VALID describes the "
                "bound machine-readable JSON artifacts only; C3 owns readable review, "
                "independent export audit, and exact-template export."
                if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
                else "Classic C1 emits no DraftKings-shaped CSV. FILE_VALID describes the "
                "two bound review JSON artifacts only; C3 owns export redesign."
            ),
        }
        if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
            export_report.update(
                {
                    "candidate_bank_artifact": artifacts["classic_candidate_bank"],
                    "candidate_bank_sha256": hashes["classic_candidate_bank"],
                    "assignment_artifact": artifacts["classic_assignment"],
                    "assignment_sha256": hashes["classic_assignment"],
                    "independent_audit_artifact": artifacts[
                        "classic_portfolio_audit"
                    ],
                    "independent_audit_sha256": hashes[
                        "classic_portfolio_audit"
                    ],
                }
            )
        stages.append(
            _stage(
                "EXPORT",
                "NOT_APPLICABLE_REVIEW_JSON_ONLY",
                file_valid=True,
                release_decision="DO_NOT_UPLOAD",
            )
        )
        stages.append(freeze_prelock(export_report))
        outcome = PriorReviewOutcome(
            profile_version=profile_version,
            stage="EXPORT",
            blocked=False,
            blockers=(),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            export=export_report,
        )
        write_run_record(run_dir / "prior_review.json", outcome.as_report())
        return outcome

    review_dir = out_dir / "review"
    try:
        export_clock = datetime.now(timezone.utc) if live_run else as_of
        if projection_freshness.state_at(export_clock) is not EvidenceState.PASS:
            raise PriorReviewError("PROJECTION_EXPIRED_DURING_SELECTION:refresh and rerun")
        if official_status_csv is not None:
            if sha256_file(official_status_csv) != hashes["official_status_csv"]:
                raise PriorReviewError("OFFICIAL_STATUS_CHANGED_DURING_SELECTION")
            if any(export_clock > observed + timedelta(hours=3)
                   for observed in snapshot.observed_at_by_id.values()):
                raise PriorReviewError("OFFICIAL_STATUS_STALE_DURING_SELECTION")
        verify_kicker_role_resolution(role_resolution, at=export_clock)
        verify_offensive_resolution(offensive_resolution, at=export_clock)
        if sha256_file(package.player_source) != package.hashes[PLAYER_PRIOR_FILENAME]:
            raise OffensiveRoleError("OFFENSIVE_HISTORY_CHANGED_DURING_SELECTION")
        if sha256_file(package.identity_map) != package.hashes[IDENTITY_MAP_FILENAME]:
            raise PriorReviewError("TEAM_SPLIT_IDENTITY_MAP_CHANGED_DURING_SELECTION")
        if portfolio_policy is not None:
            assert policy_source_path is not None
            assert policy_normalized_path is not None
            assert portfolio_policy_source_sha256 is not None
            assert portfolio_policy_normalized_sha256 is not None
            audit = audit_policy_assignments(
                slate=slate,
                policy=portfolio_policy,
                # The policy's rows only (Session 11b); the readable review
                # checks the rows the fill wrote.
                assignments=[(entry_id, assignments[entry_id]) for entry_id in portfolio_policy.entry_ids],
                unbound_entry_ids=unbound_ids,
                salary_bytes=salary_path.read_bytes(),
                entry_bytes=entry_path.read_bytes(),
                expected_entry_sha256=hashes["entry_csv"],
                source_policy_bytes=policy_source_path.read_bytes(),
                expected_source_policy_sha256=portfolio_policy_source_sha256,
                normalized_policy_bytes=policy_normalized_path.read_bytes(),
                expected_normalized_policy_sha256=portfolio_policy_normalized_sha256,
                assignment_artifact_bytes=assignments_path.read_bytes(),
                expected_assignment_artifact_sha256=assignments_hash,
                selector_summary=selection,
            )
            audit_report = audit.as_report()
            reports["portfolio_policy_audit"] = audit_report
            audit_path = selection_dir / "portfolio_policy_audit.json"
            audit_record_hash = write_run_record(audit_path, audit_report)
            artifacts["portfolio_policy_audit"] = str(audit_path)
            hashes["portfolio_policy_audit"] = audit_record_hash
            if not audit.passed:
                raise PriorReviewError(
                    "PORTFOLIO_POLICY_INDEPENDENT_AUDIT_FAILED:"
                    + ";".join(audit.problems)
                )
            if (
                sha256_file(salary_path) != portfolio_policy.salary_sha256
                or sha256_file(entry_path) != hashes["entry_csv"]
                or sha256_file(policy_source_path) != portfolio_policy_source_sha256
                or sha256_file(policy_normalized_path)
                != portfolio_policy_normalized_sha256
                or sha256_file(assignments_path) != assignments_hash
            ):
                raise PriorReviewError(
                    "PORTFOLIO_POLICY_INPUT_MUTATED_AFTER_AUDIT: rerun from stable immutable artifacts"
                )
        export = export_review_entries(
            slate=slate,
            template=template,
            assignments=assignments,
            output_path=review_dir / f"DK_REVIEW_ENTRY_{_safe_label(label)}.csv",
        )
    except Exception as exc:  # noqa: BLE001 - named, never swallowed
        error = f"{type(exc).__name__}:{exc}"
        stages.append(_stage("EXPORT", "FAILED", error=error))
        return PriorReviewOutcome(
            profile_version=PROFILE_VERSION,
            stage="EXPORT",
            blocked=True,
            blockers=(f"REVIEW_EXPORT_FAILED:{error}",),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=error,
        )
    export_report = export.as_report(
        {
            "salaries_sha256": salary_digest,
            "entries_sha256": template.raw_hash,
            "assignments_sha256": assignments_hash,
            "portfolio_policy_enforcement": (
                selection.get("portfolio_policy") if portfolio_policy is not None else None
            ),
            "portfolio_policy_audit": (
                reports.get("portfolio_policy_audit") if portfolio_policy is not None else None
            ),
            "contest_ids": sorted({e.contest_id for e in template.authorizations}),
            "entry_fees": sorted({e.entry_fee for e in template.authorizations}),
        }
    )
    write_run_record(review_dir / "review_export_report.json", export_report)
    if export.file_valid:
        artifacts["bulk_entry_csv"] = export.output_path
        hashes["bulk_entry_csv"] = export.output_sha256
    stages.append(
        _stage(
            "EXPORT",
            "OK" if export.file_valid else "BLOCKED",
            file_valid=export.file_valid,
            problems=list(export.problems),
        )
    )
    stages.append(freeze_prelock(export_report))
    outcome = PriorReviewOutcome(
        profile_version=profile_version,
        stage="EXPORT",
        blocked=not export.file_valid,
        blockers=tuple(f"REVIEW_EXPORT:{problem}" for problem in export.problems),
        stages=tuple(stages),
        artifacts=artifacts,
        hashes=hashes,
        reports=reports,
        export=export_report,
    )
    write_run_record(run_dir / "prior_review.json", outcome.as_report())
    return outcome
