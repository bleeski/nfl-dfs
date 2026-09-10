"""SD2: exact current-team allocations, with source-bound numbers and unknowns.

The source capture validator is shared with SD1. No allocation can establish
official activity or model validation. Unchanged history is only a diagnostic.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .contracts import FrozenModel, SlateContract
from .hashing import sha256_file
from .kicker_roles import KickerRoleError, KickerRoleSource, _validate_source
from .opportunity import OpportunityModel
from .participation import ParticipationContract

VERSION = "nfl_offensive_role_evidence_v1"
TRANSFORM = "offensive_explicit_team_shares_v1"
FIELDS = ("qb_attempt_share", "carry_share", "target_share", "rushing_td_share", "receiving_td_share")
POSITIONS = {
    "qb_attempt_share": {"QB"}, "carry_share": {"QB", "RB", "WR", "TE"},
    "target_share": {"RB", "WR", "TE"}, "rushing_td_share": {"QB", "RB", "WR", "TE"},
    "receiving_td_share": {"RB", "WR", "TE"},
}
OFFENSE = {"QB", "RB", "WR", "TE"}
TOLERANCE = 1e-6


class OffensiveRoleError(ValueError):
    def __init__(self, message: str, report: dict[str, object] | None = None):
        super().__init__(message)
        self.report = report or {"evidence_state": "UNKNOWN", "blocker": message}


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("must be a finite nonnegative JSON number")
    return float(value)


class Shares(FrozenModel):
    qb_attempt_share: float = Field(ge=0, le=1)
    carry_share: float = Field(ge=0, le=1)
    target_share: float = Field(ge=0, le=1)
    rushing_td_share: float = Field(ge=0, le=1)
    receiving_td_share: float = Field(ge=0, le=1)

    @field_validator("*", mode="before")
    @classmethod
    def finite(cls, value: object) -> float:
        return _number(value)


class Efficiency(FrozenModel):
    catch_rate: float = Field(ge=0, le=1)
    yards_per_target: float = Field(ge=0, le=30)

    @field_validator("*", mode="before")
    @classmethod
    def finite(cls, value: object) -> float:
        return _number(value)


class PersonBinding(FrozenModel):
    underlying_id: str = Field(min_length=1)
    cpt_dk_id: str = Field(min_length=1)
    flex_dk_id: str = Field(min_length=1)


class Recipient(PersonBinding):
    shares: Shares
    receiving_efficiency: Efficiency | None = None


class RoleFact(PersonBinding):
    team: str
    game_id: str
    fact: Literal["NAMED_STARTER", "NAMED_BACKUP", "MATERIAL_ROLE_CHANGE", "EXPLICIT_NONPARTICIPATION"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TeamAllocation(FrozenModel):
    team: str
    game_id: str
    totals: Shares
    unallocated: Shares
    recipients: tuple[Recipient, ...] = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OffensiveSource(KickerRoleSource):
    # A declaration covers an entire offensive team, unlike SD1's few kickers.
    supporting_excerpt: str = Field(min_length=1, max_length=100000)
    support_kind: Literal["QUALITATIVE_FACT", "NUMERICAL_ALLOCATION"]
    transformation_version: Literal["offensive_explicit_team_shares_v1"]


class OffensiveEvidence(FrozenModel):
    schema_version: Literal["nfl_offensive_role_evidence_v1"]
    transformation_version: Literal["offensive_explicit_team_shares_v1"]
    salary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    game_id: str
    sources: tuple[OffensiveSource, ...] = Field(min_length=1)
    declarations: tuple[TeamAllocation, ...] = ()
    facts: tuple[RoleFact, ...] = ()


@dataclass(frozen=True)
class OffensiveResolution:
    model: OpportunityModel
    excluded_people: tuple[str, ...]
    report: dict[str, object]
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    source_hashes: dict[str, str] | None = None
    expires_at: datetime | None = None


def attach_history(model: OpportunityModel, path: str | Path, digest: str) -> OpportunityModel:
    """Read only the hash-bound producer's coverage, never an operator override."""
    if sha256_file(path) != digest:
        raise OffensiveRoleError("OFFENSIVE_HISTORY_SOURCE_HASH_MISMATCH")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    coverage = payload.get("metadata", {}).get("coverage", {})
    history = coverage.get("offensive_history_by_person", {})
    if not isinstance(history, dict):
        raise OffensiveRoleError("OFFENSIVE_HISTORY_SCHEMA_INVALID")
    expected = {p.underlying_id for p in model.players if p.position in OFFENSE}
    if set(history) != expected:
        raise OffensiveRoleError("OFFENSIVE_HISTORY_COVERAGE_REQUIRED:rebuild the prior package with SD2")
    for player in model.players:
        if player.underlying_id not in expected:
            continue
        basis = history[player.underlying_id]
        if not isinstance(basis, dict) or basis.get("state") not in {
            "OBSERVED_HISTORY", "OBSERVED_HISTORY_ZERO", "MISSING_HISTORY", "CURRENT_ROLE_UNKNOWN"
        } or basis.get("current_team", player.team) != player.team:
            raise OffensiveRoleError(f"OFFENSIVE_HISTORY_SCHEMA_INVALID:{player.underlying_id}")
    if sha256_file(path) != digest:
        raise OffensiveRoleError("OFFENSIVE_HISTORY_SOURCE_CHANGED_DURING_READ")
    return replace(model, offensive_history_by_person=history)


def _people(slate: SlateContract) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for p in slate.players:
        if p.position not in OFFENSE:
            continue
        rows = result.setdefault(p.underlying_id, {})
        if p.role in rows:
            raise OffensiveRoleError(f"OFFENSIVE_ROLE_DUPLICATE_ID:{p.underlying_id}")
        rows[p.role] = p
    for person, rows in result.items():
        if set(rows) != {"CPT", "FLEX"} or len({(p.team, p.position, p.game_id) for p in rows.values()}) != 1:
            raise OffensiveRoleError(f"OFFENSIVE_ROLE_IDENTITY_CONFLICT:{person}")
    return result


def _bind(binding: PersonBinding, team: str, game: str, people: dict) -> None:
    rows = people.get(binding.underlying_id)
    if rows is None or rows["CPT"].dk_id != binding.cpt_dk_id or rows["FLEX"].dk_id != binding.flex_dk_id:
        raise OffensiveRoleError(f"OFFENSIVE_ROLE_EXACT_ID_MISMATCH:{binding.underlying_id}")
    if rows["FLEX"].team != team or rows["FLEX"].game_id != game:
        raise OffensiveRoleError(f"OFFENSIVE_ROLE_TEAM_GAME_MISMATCH:{binding.underlying_id}")


def _load(path: str | Path, slate: SlateContract, when: datetime):
    manifest = Path(path).resolve()
    try:
        digest = sha256_file(manifest)
        evidence = OffensiveEvidence.model_validate_json(manifest.read_text(encoding="utf-8"))
        if sha256_file(manifest) != digest:
            raise OffensiveRoleError("OFFENSIVE_ROLE_MANIFEST_CHANGED_DURING_READ")
        if evidence.salary_sha256 != slate.salary_hash:
            raise OffensiveRoleError("OFFENSIVE_ROLE_SALARY_HASH_MISMATCH")
        if {g.game_id for g in slate.games} != {evidence.game_id}:
            raise OffensiveRoleError("OFFENSIVE_ROLE_GAME_MISMATCH")
        sources, hashes = {}, {}
        for source in evidence.sources:
            if source.sha256 in sources:
                raise OffensiveRoleError("OFFENSIVE_ROLE_DUPLICATE_SOURCE")
            captured, source_digest = _validate_source(source, manifest_path=manifest, as_of=when)
            sources[source.sha256] = source
            hashes[str(captured)] = source_digest
        return evidence, sources, hashes, str(manifest), digest
    except KickerRoleError as exc:
        raise OffensiveRoleError(str(exc).replace("KICKER_ROLE", "OFFENSIVE_ROLE")) from exc
    except (OSError, ValueError) as exc:
        if isinstance(exc, OffensiveRoleError):
            raise
        raise OffensiveRoleError(f"OFFENSIVE_ROLE_EVIDENCE_INVALID:{exc}") from exc


def resolve_offensive_roles(
    slate: SlateContract, model: OpportunityModel, contract: ParticipationContract,
    *, evidence_path: str | Path | None = None, as_of: datetime | None = None,
) -> OffensiveResolution:
    when = as_of or datetime.now(timezone.utc)
    if when.tzinfo is None:
        raise OffensiveRoleError("OFFENSIVE_ROLE_CLOCK_REQUIRES_TIMEZONE")
    people = _people(slate)
    eligible = set(contract.selectable_people)
    before = {p.underlying_id: p for p in model.players}
    updated = dict(before)
    facts, allocations, used = {}, {}, set()
    hashes, manifest, digest, expiry, synthetic = {}, None, None, None, []
    if evidence_path:
        evidence, sources, hashes, manifest, digest = _load(evidence_path, slate, when)
        expiry = min(s.expires_at for s in sources.values())
        synthetic = sorted(s.sha256 for s in sources.values() if s.synthetic)
        for fact in evidence.facts:
            _bind(fact, fact.team, fact.game_id, people)
            if fact.underlying_id in facts:
                raise OffensiveRoleError(f"OFFENSIVE_ROLE_DUPLICATE_FACT:{fact.underlying_id}")
            source = sources.get(fact.source_sha256)
            if source is None or source.support_kind != "QUALITATIVE_FACT":
                raise OffensiveRoleError("OFFENSIVE_ROLE_FACT_SOURCE_INVALID")
            name = people[fact.underlying_id]["FLEX"].name
            phrases = {"NAMED_STARTER": "is the starter", "NAMED_BACKUP": "is the backup",
                       "MATERIAL_ROLE_CHANGE": "has an unresolved role change",
                       "EXPLICIT_NONPARTICIPATION": "will not participate"}
            expected = f"{name} {phrases[fact.fact]} for {fact.team} in {fact.game_id}."
            if source.supporting_excerpt != expected:
                raise OffensiveRoleError("OFFENSIVE_ROLE_FACT_NOT_SUPPORTED")
            facts[fact.underlying_id] = fact.fact
            used.add(fact.source_sha256)
        nonparticipants = {p for p, f in facts.items() if f == "EXPLICIT_NONPARTICIPATION"}
        for declaration in evidence.declarations:
            if declaration.team in allocations:
                raise OffensiveRoleError(f"OFFENSIVE_ROLE_DUPLICATE_TEAM:{declaration.team}")
            if declaration.team not in {p.team for p in slate.players} or declaration.game_id != evidence.game_id:
                raise OffensiveRoleError("OFFENSIVE_ROLE_TEAM_GAME_MISMATCH")
            source = sources.get(declaration.source_sha256)
            if source is None or source.support_kind != "NUMERICAL_ALLOCATION":
                raise OffensiveRoleError("OFFENSIVE_ROLE_NUMERICAL_SOURCE_REQUIRED")
            expected = declaration.model_dump(mode="json", exclude={"source_sha256"})
            # A registered identity transformation: source JSON must explicitly
            # contain these numbers and exact identities. Prose supplies none.
            try:
                observed = json.loads(source.supporting_excerpt)
                supported = TeamAllocation.model_validate({**observed, "source_sha256": declaration.source_sha256})
            except (ValueError, TypeError) as exc:
                raise OffensiveRoleError("OFFENSIVE_ROLE_NUMERICAL_SUPPORT_INVALID") from exc
            if supported.model_dump(mode="json", exclude={"source_sha256"}) != expected:
                raise OffensiveRoleError("OFFENSIVE_ROLE_NUMERICAL_SUPPORT_MISMATCH")
            recipients = set()
            for recipient in declaration.recipients:
                person = recipient.underlying_id
                _bind(recipient, declaration.team, declaration.game_id, people)
                if person in recipients:
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_DUPLICATE_PERSON:{person}")
                recipients.add(person)
                shares = recipient.shares.model_dump()
                if person not in eligible or person in nonparticipants:
                    if any(shares.values()):
                        raise OffensiveRoleError(f"OFFENSIVE_ROLE_RECIPIENT_EXCLUDED:{person}:refresh allocation")
                position = people[person]["FLEX"].position
                if any(value and position not in POSITIONS[field] for field, value in shares.items()):
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_POSITION_CONFLICT:{person}")
                if person not in before:
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_PRIOR_ROW_MISSING:{person}:rebuild complete prior package")
                efficiency = recipient.receiving_efficiency
                history = model.offensive_history_by_person.get(person, {})
                efficiency_unknown = history.get("state") == "MISSING_HISTORY" or history.get("receiving_efficiency_observed") is False or (
                    before[person].target_share == 0 and before[person].yards_per_target == 0
                )
                if shares["target_share"] > 0 and efficiency_unknown and efficiency is None:
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_RECEIVING_EFFICIENCY_REQUIRED:{person}")
                if efficiency is not None and position not in {"RB", "WR", "TE"}:
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_POSITION_EFFICIENCY_CONFLICT:{person}")
                updated[person] = replace(before[person], **shares, **(efficiency.model_dump() if efficiency else {}))
            expected_people = {p for p in eligible if p in people and people[p]["FLEX"].team == declaration.team} - nonparticipants
            if not expected_people.issubset(recipients):
                raise OffensiveRoleError(f"OFFENSIVE_ROLE_ALLOCATION_COVERAGE_MISSING:{sorted(expected_people - recipients)}")
            for field in FIELDS:
                total = getattr(declaration.totals, field)
                allocated = sum(getattr(r.shares, field) for r in declaration.recipients)
                if total != 1 or not math.isclose(allocated + getattr(declaration.unallocated, field), total, abs_tol=TOLERANCE, rel_tol=0):
                    raise OffensiveRoleError(f"OFFENSIVE_ROLE_INVALID_TOTAL:{declaration.team}:{field}")
            allocations[declaration.team] = declaration
            used.add(declaration.source_sha256)
        if used != set(sources):
            raise OffensiveRoleError("OFFENSIVE_ROLE_UNUSED_SOURCE")

    findings, blocked, excluded = [], [], set(before) - eligible
    for person, rows in sorted(people.items()):
        original = before.get(person)
        player = updated.get(person)
        history = model.offensive_history_by_person.get(person, {})
        historical_state = history.get("state", "UNSPECIFIED_PRIOR_BASIS")
        action, reason, next_action = "DIAGNOSTIC", "HISTORICAL_ROLE_UNCONFIRMED", "Capture current role evidence if this role has changed."
        state = "CURRENT_ROLE_UNKNOWN"
        if person not in eligible or facts.get(person) == "EXPLICIT_NONPARTICIPATION":
            state, action, reason, next_action = "EXPLICIT_NONPARTICIPATION", "EXCLUDE", "PARTICIPATION_PRECEDENCE", "Refresh official status or operator exclusion before reconsideration."
        elif rows["FLEX"].team in allocations:
            state, action, reason, next_action = "SOURCE_SUPPORTED_ADJUSTMENT", "SELECT", "EXPLICIT_TEAM_ALLOCATION", "Refresh allocation when a recipient or source changes."
            if player is None or not any(getattr(player, field) for field in FIELDS):
                action = "EXCLUDE"
        elif original is None:
            state, action, reason = "MISSING_HISTORY", "BLOCK", "OFFENSIVE_PRIOR_ROW_MISSING"
            next_action = "Rebuild the complete prior package; this person has no prior record at all."
        elif historical_state == "MISSING_HISTORY":
            # No prior-season row anywhere (a rookie, or a person who never
            # recorded a stat). There is no source-bound number to carry, so the
            # honest share is zero: the person is excluded, named here and in
            # the pool-coverage report with salary, rather than stopping the run
            # for an operator `--exclude` that produces the identical result.
            # A rookie prior from approved draft/combine artifacts is the open
            # follow-up (R17); until it exists this stays an exclusion.
            state, action, reason = "MISSING_HISTORY", "EXCLUDE", "OFFENSIVE_MISSING_HISTORY"
            next_action = (
                "Excluded with zero share: no prior-season rows. Capture a numerical"
                " current-team allocation, or a registered rookie prior, to select this person."
            )
        elif (
            historical_state == "CURRENT_ROLE_UNKNOWN"
            and history.get("incompatible_transfer")
            and isinstance(history.get("transfer_prior"), dict)
            and person not in facts
        ):
            prior = history["transfer_prior"]
            if prior.get("basis") == "OWN_OLD_TEAM_SHARE" and any(getattr(original, f) for f in FIELDS):
                # The producer carried the person's own prior-team share into the
                # current team's normalization. It is a cold-start prior with
                # EVIDENCE_STATE=UNKNOWN, kept and reported, never a role fact.
                state, action, reason = "TRANSFER_PRIOR_UNVERIFIED", "DIAGNOSTIC", "OFFENSIVE_TRANSFER_PRIOR_UNVERIFIED"
                next_action = (
                    "Prior-team share carried as an unverified cold-start prior"
                    f" (old team {','.join(str(t) for t in prior.get('old_teams', []))});"
                    " capture an explicit numerical current-team allocation to replace it."
                )
            else:
                state, action, reason = "TRANSFER_PRIOR_ZERO", "EXCLUDE", "OFFENSIVE_TRANSFER_PRIOR_ZERO"
                next_action = (
                    "Excluded with zero share: the person's own prior-team share was zero."
                    " Capture current opportunity evidence before selecting."
                )
        elif historical_state == "CURRENT_ROLE_UNKNOWN" or person in facts or original.evidence_state != "PASS":
            state, action = "CURRENT_ROLE_UNKNOWN", "BLOCK"
            reason = "OFFENSIVE_TRANSFER_REQUIRES_CURRENT_TEAM_ROLE" if history.get("incompatible_transfer") else "OFFENSIVE_CURRENT_ROLE_UNRESOLVED"
            next_action = "Capture an explicit numerical current-team allocation for this changed role."
        elif historical_state == "OBSERVED_HISTORY_ZERO":
            state, action, reason = "OBSERVED_HISTORY_ZERO", "EXCLUDE", "OFFENSIVE_OBSERVED_HISTORY_ZERO"
            next_action = "Capture current opportunity evidence before selecting this historically zero person."
        elif not any(getattr(original, field) for field in FIELDS):
            action, reason, next_action = "BLOCK", "OFFENSIVE_ZERO_BASIS_UNRESOLVED", "Rebuild history coverage to distinguish missing from observed zero."
        if action == "EXCLUDE":
            excluded.add(person)
        if action == "BLOCK":
            excluded.add(person)
            blocked.append(f"{reason}:{person}:{next_action}")
        findings.append({"person": person, "team": rows["FLEX"].team, "cpt_dk_id": rows["CPT"].dk_id,
                         "flex_dk_id": rows["FLEX"].dk_id, "state": state, "history_state": historical_state,
                         "history_basis": history, "declared_fact": facts.get(person), "selection_action": action,
                         "finding": reason, "next_evidence_action": next_action,
                         "before": {f: getattr(original, f) for f in FIELDS} if original else None,
                         "after": None if action == "BLOCK" else {
                             f: getattr(player, f) if player and action != "EXCLUDE" else 0 for f in FIELDS
                         }})
    survivors = tuple(p for person, p in updated.items() if person not in excluded)
    transfer_priors = {
        f["person"]: {
            "team": f["team"],
            "old_teams": (f["history_basis"].get("transfer_prior") or {}).get("old_teams"),
            "own_old_share": (f["history_basis"].get("transfer_prior") or {}).get("own_old_share"),
            "pool_share_after_normalization": f["before"],
        }
        for f in findings
        if f["state"] == "TRANSFER_PRIOR_UNVERIFIED"
    }
    unallocated = {}
    for team in sorted({p.team for p in model.players}):
        unallocated[team] = {f: max(0.0, 1.0 - sum(getattr(p, f) for p in survivors if p.team == team)) for f in FIELDS}
    report = {"schema_version": VERSION, "transformation_version": TRANSFORM, "findings": findings,
              "evidence_state": "UNKNOWN" if not manifest or blocked or synthetic or any(f["selection_action"] == "DIAGNOSTIC" for f in findings) else "PASS",
              "coverage": {"offensive_people": len(people), "findings": len(findings), "blocked_people": len(blocked)},
              "assumptions": ["HISTORY_IS_UNCONFIRMED; VACATED_VOLUME_REMAINS_UNALLOCATED", "ROLE_CAPACITY_IS_NOT_A_CEILING",
                              *(["TRANSFER_PRIOR_IS_OWN_OLD_TEAM_SHARE_NOT_A_CURRENT_ROLE"] if transfer_priors else []),
                              *(["MISSING_HISTORY_PEOPLE_EXCLUDED_WITH_ZERO_SHARE"] if any(f["finding"] == "OFFENSIVE_MISSING_HISTORY" for f in findings) else [])],
              "transfer_priors": transfer_priors,
              "excluded_by_finding": {
                  reason: sorted(f["person"] for f in findings if f["selection_action"] == "EXCLUDE" and f["finding"] == reason)
                  for reason in sorted({f["finding"] for f in findings if f["selection_action"] == "EXCLUDE"})
              },
              "unallocated_by_team": unallocated,
              "declared_totals": {t: a.totals.model_dump() for t, a in allocations.items()},
              "declared_unallocated": {t: a.unallocated.model_dump() for t, a in allocations.items()},
              "evidence_path": manifest, "evidence_sha256": digest, "source_hashes": hashes,
              "expires_at": expiry.isoformat() if expiry else None,
              "sources": [s.model_dump(mode="json") for s in sources.values()] if manifest else [],
              "synthetic_sources": synthetic, "synthetic_note": "TEST_ONLY_SYNTHETIC_EVIDENCE" if synthetic else None,
              "does_not_establish": ["OFFICIAL_ACTIVE_STATUS", "MODEL_VALIDATION"], "blockers": blocked}
    if blocked:
        raise OffensiveRoleError(";".join(blocked), report)
    return OffensiveResolution(replace(model, players=survivors), tuple(sorted(excluded)), report, manifest, digest, hashes, expiry)


def verify_offensive_resolution(resolution: OffensiveResolution, *, at: datetime) -> None:
    if at.tzinfo is None:
        raise OffensiveRoleError("OFFENSIVE_ROLE_CLOCK_REQUIRES_TIMEZONE")
    try:
        if resolution.evidence_path and sha256_file(resolution.evidence_path) != resolution.evidence_sha256:
            raise OffensiveRoleError("OFFENSIVE_ROLE_MANIFEST_CHANGED_DURING_SELECTION")
        for path, digest in (resolution.source_hashes or {}).items():
            if sha256_file(path) != digest:
                raise OffensiveRoleError("OFFENSIVE_ROLE_SOURCE_CHANGED_DURING_SELECTION")
        if resolution.expires_at and at > resolution.expires_at:
            raise OffensiveRoleError("OFFENSIVE_ROLE_SOURCE_EXPIRED_DURING_SELECTION:refresh allocation")
    except OSError as exc:
        raise OffensiveRoleError("OFFENSIVE_ROLE_ARTIFACT_MISSING_DURING_SELECTION") from exc
