"""One gated entry point for the prior-only Showdown review chain.

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
2. Weather. The enum has no `UNKNOWN` member and `api.weather.gov` is
   unreachable from a session, so a game the schedule artifact cannot resolve on
   its own blocks for an operator capture with its URI and observation time.
3. Staleness. The team prior inherits `MARKET_LINE_MOVES_INTRADAY` from
   `games.csv`, which expires twelve hours after capture. A same-day re-run is
   the normal case. An expired package is rebuilt, never widened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .contracts import (
    EngineMode,
    EvidenceState,
    SalaryPlayer,
    SlateContract,
    SourceFreshness,
    earliest_expiry,
    earliest_source_freshness,
)
from .dk import parse_entries, parse_salaries
from .evidence import parse_official_inactive_snapshot
from .hashing import sha256_file
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
from .portfolio_enforcement import (
    audit_policy_assignments,
    exact_assignments_for_entries,
)
from .portfolio_policy import NormalizedPortfolioPolicy
from .review_export import export_review_entries, write_assignments_csv, write_run_record
from .selection import assignments_for_entries, select_prior_lineups


PROFILE_VERSION = "cowork_prior_review_v1"

# nflverse roof values the frozen schedule artifact resolves without any
# operator input. `priors._ROOF_WEATHER` also maps "open", but a retractable
# roof left open is played in the weather, so this profile still asks for the
# capture rather than treating the schedule as the whole answer.
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
    blockers: tuple[str, ...]

    def as_report(self) -> dict[str, object]:
        return {
            "roof": self.roof or "BLANK",
            "basis": self.basis,
            "operator_state_passed_to_freeze": self.freeze_weather_state,
            "operator_source_uri": self.freeze_source_uri,
            "operator_observed_at": self.freeze_observed_at,
        }


def decide_weather(
    roof: str,
    *,
    weather_state: str | None = None,
    weather_source_uri: str | None = None,
    weather_observed_at: str | None = None,
) -> WeatherDecision:
    """Resolve the weather enum from the schedule, or name what a human must send.

    The enum has no `UNKNOWN` member, so nothing here defaults it. A fixed or
    retracted-closed roof is decided by the frozen schedule artifact alone. Every
    other value, including a retractable roof left open and a blank cell, needs
    an `api.weather.gov` capture with its URI and its `generatedAt`.
    """

    normalized = (roof or "").strip().lower()
    state = (weather_state or "").strip().upper() or None
    uri = (weather_source_uri or "").strip() or None
    observed = (weather_observed_at or "").strip() or None
    attributed = bool(uri and observed)

    if normalized in SCHEDULE_DERIVABLE_ROOFS:
        return WeatherDecision(
            roof=normalized,
            freeze_weather_state=state,
            freeze_source_uri=uri,
            freeze_observed_at=observed,
            basis=f"SCHEDULE_ROOF_IS_AUTHORITATIVE:{normalized}",
            blockers=(),
        )

    blockers: list[str] = []
    if not attributed:
        blockers.append(
            f"WEATHER_CAPTURE_REQUIRED:roof={normalized or 'BLANK'}"
            ":supply the api.weather.gov gridpoint forecast URI and its generatedAt"
            " observation time; api.weather.gov is unreachable from a session and the"
            " weather enum has no UNKNOWN member, so nothing is defaulted"
        )
    if normalized in ROOF_STATE_IS_SCHEDULE_AUTHORITATIVE:
        # The schedule artifact already resolves this roof. The capture is
        # required because the game is played in the weather, but the state
        # itself stays schedule-derived so the two cannot disagree.
        return WeatherDecision(
            roof=normalized,
            freeze_weather_state=None,
            freeze_source_uri=uri,
            freeze_observed_at=observed,
            basis=f"SCHEDULE_ROOF_IS_AUTHORITATIVE_CAPTURE_REPORTED_ONLY:{normalized}",
            blockers=tuple(blockers),
        )
    if state is None:
        blockers.append(
            f"WEATHER_STATE_REQUIRED:roof={normalized or 'BLANK'}"
            ":the schedule artifact cannot resolve this roof; supply one of"
            " CLEAR, INDOOR_OR_CLEAR, MIXED, RAIN, SNOW, WIND"
        )
    return WeatherDecision(
        roof=normalized,
        freeze_weather_state=state,
        freeze_source_uri=uri,
        freeze_observed_at=observed,
        basis=f"OPERATOR_CAPTURE_REQUIRED:{normalized or 'BLANK'}",
        blockers=tuple(blockers),
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
        flex_salary = sum(player.salary for player in players if player.role == "FLEX")
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
                "dk_status": contract.status_by_person.get(person, ""),
                "reason": reason,
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
            " and CPT prices of the excluded people, a coverage measure, not a"
            " projection or an edge claim."
        ),
    }


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
    lineup_count: int | None = None,
    max_person_overlap: int | None = 4,
    allow_repeat_captain: bool = False,
    operator_excluded_dk_ids: Sequence[str] = (),
    extra_unavailable_statuses: Sequence[str] = (),
    extra_available_statuses: Sequence[str] = (),
    official_status_csv: str | Path | None = None,
    role_evidence_json: str | Path | None = None,
    offensive_role_evidence_json: str | Path | None = None,
    portfolio_policy: NormalizedPortfolioPolicy | None = None,
    portfolio_policy_source_path: str | Path | None = None,
    portfolio_policy_source_sha256: str | None = None,
    portfolio_policy_normalized_path: str | Path | None = None,
    portfolio_policy_normalized_sha256: str | None = None,
    propose: Callable[..., dict[str, object]] = propose_prior_package,
    freeze: Callable[..., dict[str, object]] = freeze_prior_package,
    project: Callable[..., object] = build_projection_package,
) -> PriorReviewOutcome:
    """Drive priors, identity, projection, selection and export as one gate.

    Returns a blocked outcome with named blockers wherever a human decision is
    genuinely required, and never writes an export on any blocked or failed path.
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
    slate = parse_salaries(salary_path)
    if slate.mode is not EngineMode.SHOWDOWN:
        return PriorReviewOutcome(
            profile_version=PROFILE_VERSION,
            stage="PRIORS",
            blocked=True,
            blockers=(
                f"PROFILE_MODE_NOT_SUPPORTED:{slate.mode.value}"
                ":the prior_review profile is Showdown only; Classic selection is DL6",
            ),
            stages=(_stage("PRIORS", "BLOCKED", mode=slate.mode.value),),
            artifacts={},
            hashes={},
        )
    salary_digest = sha256_file(salary_path)
    hashes["salary_csv"] = salary_digest
    hashes["entry_csv"] = sha256_file(entry_path)
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
                profile_version=PROFILE_VERSION,
                stage="PORTFOLIO_POLICY",
                blocked=True,
                blockers=(
                    "PORTFOLIO_POLICY_ARTIFACT_BINDING_INCOMPLETE: source and normalized "
                    "policy paths and hashes are required for SD4 enforcement",
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
                profile_version=PROFILE_VERSION, stage="ACTIVITY", blocked=True,
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
                    profile_version=PROFILE_VERSION,
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
                    profile_version=PROFILE_VERSION,
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
            profile_version=PROFILE_VERSION,
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
                profile_version=PROFILE_VERSION,
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
            "nflverse_game_id": proposed.get("nflverse_game_id"),
        }
        market = dict(proposed.get("market") or {})
        if live_run:
            as_of = datetime.now(timezone.utc)
        weather = decide_weather(
            str(market.get("roof", "")),
            weather_state=weather_state,
            weather_source_uri=weather_source_uri,
            weather_observed_at=weather_observed_at,
        )
        reports["weather"] = weather.as_report()

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

        blockers = tuple(weather.blockers) + gate.blockers
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
                "BLOCKED" if weather.blockers else "OK",
                **weather.as_report(),
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
        if blockers:
            return PriorReviewOutcome(
                profile_version=PROFILE_VERSION,
                stage="IDENTITY" if gate.blockers else "WEATHER",
                blocked=True,
                blockers=blockers,
                stages=tuple(stages),
                artifacts=artifacts,
                hashes=hashes,
                reports=reports,
            )

        frozen_dir = run_dir / "priors" / "frozen"
        try:
            frozen = freeze(
                package_dir=str(proposal_dir),
                reviewed=str(reviewed_path),
                reviewed_sha256=reviewed_hash,
                salaries=str(salary_path),
                salary_sha256=salary_digest,
                as_of=as_of.isoformat(),
                output_dir=str(frozen_dir),
                weather_state=weather.freeze_weather_state,
                salary_observed_at=None,
                weather_source_uri=weather.freeze_source_uri,
                weather_observed_at=weather.freeze_observed_at,
            )
        except Exception as exc:  # noqa: BLE001 - named, never swallowed
            error = f"{type(exc).__name__}:{exc}"
            stages.append(_stage("PRIORS", "FAILED", error=error))
            return PriorReviewOutcome(
                profile_version=PROFILE_VERSION,
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
                profile_version=PROFILE_VERSION,
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
            profile_version=PROFILE_VERSION,
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
            profile_version=PROFILE_VERSION,
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
            profile_version=PROFILE_VERSION,
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
    entry_ids = [entry.entry_id for entry in template.authorizations]
    requested_count = int(lineup_count) if lineup_count else len(entry_ids)
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
            profile_version=PROFILE_VERSION,
            stage="SELECT",
            blocked=True,
            blockers=(message,),
            stages=tuple(stages),
            artifacts=artifacts,
            hashes=hashes,
            reports=reports,
            error=message,
        )
    try:
        if portfolio_policy is not None:
            assert policy_source_path is not None
            assert policy_normalized_path is not None
            assert portfolio_policy_source_sha256 is not None
            assert portfolio_policy_normalized_sha256 is not None
            if sha256_file(salary_path) != portfolio_policy.salary_sha256:
                raise PriorReviewError("PORTFOLIO_POLICY_SALARY_CHANGED_BEFORE_SELECTION")
            if sha256_file(entry_path) != hashes["entry_csv"]:
                raise PriorReviewError("PORTFOLIO_POLICY_ENTRY_BYTES_CHANGED_BEFORE_SELECTION")
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
        lineups, scores, selection = select_prior_lineups(
            slate,
            model,
            splits,
            contract,
            count=requested_count,
            differentiate_captain=not allow_repeat_captain,
            max_person_overlap=max_person_overlap,
            role_evidence_json=role_evidence_json,
            offensive_role_evidence_json=offensive_role_evidence_json,
            as_of=as_of,
            portfolio_policy=portfolio_policy,
        )
        assignments = (
            exact_assignments_for_entries(
                portfolio_policy.entry_ids,
                [lineup.roster for lineup in lineups],
            )
            if portfolio_policy is not None
            else assignments_for_entries(entry_ids, lineups)
        )
    except Exception as exc:  # noqa: BLE001 - named, never swallowed
        error = f"{type(exc).__name__}:{exc}"
        stages.append(_stage("SELECT", "FAILED", error=error))
        if isinstance(exc, OffensiveRoleError):
            reports["offensive_roles"] = exc.report
        return PriorReviewOutcome(
            profile_version=PROFILE_VERSION,
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
    if offensive_resolution.evidence_path:
        artifacts["offensive_role_evidence_json"] = offensive_resolution.evidence_path
        hashes["offensive_role_evidence_json"] = str(offensive_resolution.evidence_sha256)
        for index, (path, digest) in enumerate(sorted((offensive_resolution.source_hashes or {}).items()), start=1):
            artifacts[f"offensive_role_source:{index}"] = path
            hashes[f"offensive_role_source:{index}"] = digest
    if role_resolution.evidence_path is not None:
        artifacts["role_evidence_json"] = role_resolution.evidence_path
        hashes["role_evidence_json"] = str(role_resolution.evidence_sha256)
        for index, source_path in enumerate(role_resolution.source_paths, start=1):
            artifacts[f"role_evidence_source:{index}"] = source_path
            hashes[f"role_evidence_source:{index}"] = str(
                (role_resolution.source_hashes or {})[source_path]
            )
    assignments_path = selection_dir / "assignments.csv"
    assignments_hash = write_assignments_csv(
        assignments_path,
        assignments,
        entry_order=portfolio_policy.entry_ids if portfolio_policy is not None else None,
    )
    artifacts["assignments"] = str(assignments_path)
    hashes["assignments"] = assignments_hash
    selection_report = {
        "status": "DO_NOT_UPLOAD",
        "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "assignments": str(assignments_path),
        "assignments_sha256": assignments_hash,
        "reserved_entries": entry_ids,
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
        ),
        "official_status_coverage": _official_status_coverage(
            slate, lineups, reports.get("official_status")
        ),
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
                assignments=list(assignments.items()),
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
    outcome = PriorReviewOutcome(
        profile_version=PROFILE_VERSION,
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
