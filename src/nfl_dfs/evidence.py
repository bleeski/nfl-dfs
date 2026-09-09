from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

from pydantic import ValidationError

from .contracts import (
    SOURCE_LEDGER_V1,
    EvidenceRecord,
    EvidenceState,
    LateSwapEligibility,
    SalaryPlayer,
    SlateContract,
    SourceLedger,
    TeamInactiveReportBundle,
    earliest_source_freshness,
    source_freshness_evidence,
)
from .hashing import sha256_bytes, sha256_file
from .sources import SourcePolicyError, validate_source_reference_policy


class EvidenceError(ValueError):
    pass


def release_clock() -> datetime:
    """The live clock every release-time freshness check uses.

    R08 requires historical replay time and the live release clock to stay
    separate. A replay passes its recorded `as_of` explicitly; anything that
    omits a clock is asking about right now, which is what a release is.
    """

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class InactiveStatusSnapshot:
    statuses: dict[str, str]
    observed_at_by_id: dict[str, datetime]
    source_url_by_id: dict[str, str]
    problems: tuple[str, ...]


def evaluate_hard_gates(
    evidence: Iterable[EvidenceRecord],
    now: datetime | None = None,
    *,
    final_release: bool = False,
) -> tuple[bool, tuple[str, ...]]:
    when = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    for record in evidence:
        if not record.hard_gate:
            continue
        state = record.state_at(when)
        if state is EvidenceState.NOT_APPLICABLE:
            continue
        if state is EvidenceState.NOT_YET_DUE and not final_release:
            continue
        if state is not EvidenceState.PASS:
            blockers.append(f"{record.subject}.{record.field}:{state.value}:{record.reason}")
    return not blockers, tuple(blockers)


def _valid_https_source(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def late_swap_eligibility_evidence(
    path: str | Path | None,
    *,
    contest_id: str,
    as_of: datetime,
) -> EvidenceRecord:
    if as_of.tzinfo is None:
        raise EvidenceError("late-swap as_of must be timezone-aware")
    if not path:
        return EvidenceRecord(
            subject=contest_id,
            field="contest_late_swap_eligibility",
            hard_gate=True,
            state=EvidenceState.UNKNOWN,
            reason="contest-bound late-swap eligibility evidence was not supplied",
        )
    evidence_path = Path(path)
    try:
        raw = evidence_path.read_bytes()
        digest = sha256_bytes(raw)
        contract = LateSwapEligibility.model_validate(json.loads(raw.decode("utf-8-sig")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        return EvidenceRecord(
            subject=contest_id,
            field="contest_late_swap_eligibility",
            hard_gate=True,
            state=EvidenceState.CONFLICTED,
            reason=f"invalid eligibility contract: {exc}",
        )
    problems: list[str] = []
    if sha256_file(evidence_path) != digest:
        problems.append("eligibility evidence changed while it was being validated")
    if contract.contest_id != contest_id:
        problems.append(
            f"eligibility Contest ID {contract.contest_id} does not match {contest_id}"
        )
    if not _valid_https_source(contract.source_url):
        problems.append("eligibility evidence requires a valid HTTPS source URL")
    observed_at = contract.observed_at.astimezone(timezone.utc)
    expires_at = contract.expires_at.astimezone(timezone.utc)
    when = as_of.astimezone(timezone.utc)
    if observed_at > when:
        problems.append("eligibility observation is in the future")
    if problems:
        state = EvidenceState.CONFLICTED
        reason = "; ".join(problems)
    elif contract.evidence_state is not EvidenceState.PASS:
        state = contract.evidence_state
        reason = f"eligibility evidence state is {state.value}"
    elif when > expires_at:
        state = EvidenceState.STALE
        reason = "contest late-swap eligibility evidence is stale"
    elif not contract.bulk_late_swap_eligible:
        state = EvidenceState.FAIL
        reason = "the exact contest is not eligible for bulk late swap"
    else:
        state = EvidenceState.PASS
        reason = "the exact Contest ID is source-bound as bulk-late-swap eligible"
    return EvidenceRecord(
        subject=contest_id,
        field="contest_late_swap_eligibility",
        value={
            "bulk_late_swap_eligible": contract.bulk_late_swap_eligible,
            "schema_version": contract.schema_version,
        },
        source_artifact_id=digest,
        source_url=contract.source_url,
        observed_at=observed_at,
        expires_at=expires_at,
        hard_gate=True,
        state=state,
        reason=reason,
    )


def team_inactive_report_evidence(
    path: str | Path | None,
    *,
    slate: SlateContract,
    selected_dk_ids: Iterable[str],
    as_of: datetime,
    release_before_lock: timedelta = timedelta(minutes=90),
) -> EvidenceRecord:
    if as_of.tzinfo is None:
        raise EvidenceError("late-swap as_of must be timezone-aware")
    selected = set(selected_dk_ids)
    by_id = {player.dk_id: player for player in slate.players}
    selected_teams = {by_id[dk_id].team for dk_id in selected if dk_id in by_id}
    if not selected:
        return EvidenceRecord(
            subject="selected_unlocked_portfolio",
            field="official_inactive_status",
            hard_gate=True,
            state=EvidenceState.NOT_APPLICABLE,
            reason="all selected cells are locked and exactly match the certified prior",
        )
    if not path:
        return EvidenceRecord(
            subject="selected_unlocked_portfolio",
            field="official_inactive_status",
            hard_gate=True,
            state=EvidenceState.UNKNOWN,
            reason="team-scoped official inactive reports were not supplied",
        )
    report_path = Path(path)
    try:
        raw = report_path.read_bytes()
        digest = sha256_bytes(raw)
        bundle = TeamInactiveReportBundle.model_validate(
            json.loads(raw.decode("utf-8-sig"))
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        return EvidenceRecord(
            subject="selected_unlocked_portfolio",
            field="official_inactive_status",
            hard_gate=True,
            state=EvidenceState.CONFLICTED,
            reason=f"invalid team inactive-report contract: {exc}",
        )

    problems: list[str] = []
    if sha256_file(report_path) != digest:
        problems.append("inactive-report evidence changed while it was being validated")
    teams = {player.team for player in slate.players}
    games_by_team = {
        team: game
        for game in slate.games
        for team in (game.away_team, game.home_team)
    }
    reports_by_team = {}
    for report in bundle.reports:
        if report.team in reports_by_team:
            problems.append(f"duplicate or conflicting report for team {report.team}")
            continue
        reports_by_team[report.team] = report
        if report.team not in teams:
            problems.append(f"unknown report team {report.team}")
            continue
        game = games_by_team.get(report.team)
        if game is None or report.game_id != game.game_id:
            problems.append(f"team/game conflict for report team {report.team}")
        if not _valid_https_source(report.source_url):
            problems.append(f"invalid HTTPS source URL for team {report.team}")
        observed = report.observed_at.astimezone(timezone.utc)
        when = as_of.astimezone(timezone.utc)
        if observed > when:
            problems.append(f"future inactive-report observation for team {report.team}")
        if game is not None and observed > game.lock_at.astimezone(timezone.utc):
            problems.append(f"inactive report follows game lock for team {report.team}")
        for dk_id in report.inactive_dk_ids:
            player = by_id.get(dk_id)
            if player is None:
                problems.append(f"unknown inactive exact DK ID {dk_id}")
            elif player.team != report.team:
                problems.append(
                    f"inactive player/team conflict for {dk_id}: "
                    f"{player.team} != {report.team}"
                )

    observations: list[datetime] = []
    expirations: list[datetime] = []
    missing_due: list[str] = []
    not_yet_due: list[str] = []
    stale_teams: list[str] = []
    nonpass: dict[str, EvidenceState] = {}
    inactive_selected: list[str] = []
    values: dict[str, object] = {}
    when = as_of.astimezone(timezone.utc)
    for team in sorted(selected_teams):
        game = games_by_team[team]
        due_at = game.lock_at.astimezone(timezone.utc) - release_before_lock
        report = reports_by_team.get(team)
        if report is None:
            (not_yet_due if when < due_at else missing_due).append(team)
            continue
        observed = report.observed_at.astimezone(timezone.utc)
        observations.append(observed)
        expirations.append(game.lock_at.astimezone(timezone.utc))
        values[team] = {
            "game_id": report.game_id,
            "inactive_dk_ids": list(report.inactive_dk_ids),
        }
        if report.evidence_state is not EvidenceState.PASS:
            nonpass[team] = report.evidence_state
            continue
        if when < due_at:
            not_yet_due.append(team)
            continue
        if observed < due_at:
            stale_teams.append(team)
            continue
        inactive = set(report.inactive_dk_ids)
        inactive_selected.extend(
            dk_id for dk_id in selected if by_id.get(dk_id) and dk_id in inactive
        )

    if set(selected).difference(by_id):
        problems.append(
            f"selected exact IDs are absent from the salary pool: {sorted(set(selected).difference(by_id))}"
        )
    if problems:
        state = EvidenceState.CONFLICTED
        reason = "; ".join(problems)
    elif inactive_selected:
        state = EvidenceState.FAIL
        reason = f"selected unlocked players are officially inactive: {sorted(inactive_selected)}"
    elif any(value is EvidenceState.CONFLICTED for value in nonpass.values()):
        state = EvidenceState.CONFLICTED
        reason = f"team inactive reports are conflicted: {nonpass}"
    elif any(value is EvidenceState.FAIL for value in nonpass.values()):
        state = EvidenceState.FAIL
        reason = f"team inactive reports failed verification: {nonpass}"
    elif stale_teams or any(value is EvidenceState.STALE for value in nonpass.values()):
        state = EvidenceState.STALE
        reason = f"team inactive reports are stale: {sorted(stale_teams or nonpass)}"
    elif missing_due or any(value is EvidenceState.UNKNOWN for value in nonpass.values()):
        state = EvidenceState.UNKNOWN
        reason = f"required team inactive reports are missing or unverified: {sorted(missing_due or nonpass)}"
    elif not_yet_due or any(
        value is EvidenceState.NOT_YET_DUE for value in nonpass.values()
    ):
        state = EvidenceState.NOT_YET_DUE
        reason = f"official team inactive reports are not yet due: {sorted(not_yet_due or nonpass)}"
    else:
        state = EvidenceState.PASS
        reason = (
            "every selected unlocked player is absent from a current, verified "
            "team-scoped official inactive negative list"
        )
    return EvidenceRecord(
        subject="selected_unlocked_portfolio",
        field="official_inactive_status",
        value=values,
        source_artifact_id=digest,
        observed_at=min(observations) if observations else None,
        expires_at=min(expirations) if expirations else None,
        hard_gate=True,
        state=state,
        reason=reason,
    )


def validate_source_ledger(
    path: str | Path,
    *,
    expected_outputs: Mapping[str, str],
    now: datetime | None = None,
) -> SourceLedger:
    ledger_path = Path(path).resolve()
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger = SourceLedger.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise EvidenceError(f"invalid source ledger contract: {exc}") from exc

    expected = dict(expected_outputs)
    if set(ledger.derived) != set(expected):
        raise EvidenceError(
            "source ledger derived outputs must be exactly "
            f"{sorted(expected)}; received {sorted(ledger.derived)}"
        )
    for name, digest in expected.items():
        if ledger.derived[name] != digest:
            raise EvidenceError(
                f"source ledger derived hash mismatch for {name}: expected {digest}"
            )

    checked_at = now or release_clock()
    future_limit = checked_at + timedelta(minutes=5)
    for entry in ledger.entries:
        try:
            validate_source_reference_policy(
                entry.source_uri,
                license_decision=entry.license_decision,
                parser_version=entry.parser_version,
            )
        except SourcePolicyError as exc:
            raise EvidenceError(
                f"source ledger URI is not approved: {entry.source_uri}: {exc}"
            ) from exc
        captured_at = entry.captured_at.astimezone(timezone.utc)
        if captured_at > future_limit:
            raise EvidenceError(f"source ledger captured_at is in the future: {entry.path}")
        if entry.observed_at is not None:
            observed_at = entry.observed_at.astimezone(timezone.utc)
            if observed_at > future_limit:
                raise EvidenceError(
                    f"source ledger observed_at is in the future: {entry.path}"
                )
            if observed_at > captured_at + timedelta(minutes=5):
                raise EvidenceError(
                    f"source ledger observed_at follows captured_at: {entry.path}"
                )
        artifact = Path(entry.path)
        if not artifact.is_absolute():
            artifact = ledger_path.parent / artifact
        try:
            artifact = artifact.resolve(strict=True)
        except OSError as exc:
            raise EvidenceError(f"source ledger artifact is missing: {entry.path}") from exc
        if not artifact.is_file():
            raise EvidenceError(f"source ledger artifact is missing: {entry.path}")
        if sha256_file(artifact) != entry.artifact_id:
            raise EvidenceError(
                f"source ledger artifact hash mismatch: {entry.path}"
            )
        # R08: a hash match is integrity, not freshness. The entry carries its
        # own expiry and evidence state, and both are re-evaluated at the clock
        # this validation is being performed at. `checked_at` is the caller's
        # replay clock when one was supplied and the live release clock when it
        # was not, so a package that was valid at creation goes stale at its
        # real expiry no matter who copies it.
        freshness = entry.freshness()
        if freshness is None:
            continue
        state = freshness.state_at(checked_at)
        if state is EvidenceState.STALE:
            raise EvidenceError(
                f"source ledger entry is stale: {entry.path}: "
                f"expires_at={freshness.expires_at.astimezone(timezone.utc).isoformat()}: "
                f"checked_at={checked_at.astimezone(timezone.utc).isoformat()}: "
                f"basis={freshness.basis}"
            )
        if state is not EvidenceState.PASS:
            raise EvidenceError(
                f"source ledger entry evidence state is {state.value}: {entry.path}"
            )
    return ledger


def source_ledger_evidence(
    path: str | Path,
    *,
    expected_outputs: Mapping[str, str],
    as_of: datetime | None = None,
) -> EvidenceRecord:
    """Bind a produced package's per-source expiry into the hard-gate set.

    Selection and certification both need the same question answered at their
    own clock rather than at the clock the package was built on. The returned
    record carries the binding expiry, so `evaluate_hard_gates` re-derives
    `STALE` later without re-reading a single source byte. A legacy
    `nfl_source_ledger_v1` package preserves no expiry at all, so it reports
    `UNKNOWN` and cannot clear the gate.
    """

    when = as_of or release_clock()
    ledger_path = Path(path)
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        parsed = SourceLedger.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        return EvidenceRecord(
            subject="source_ledger",
            field="source_freshness",
            hard_gate=True,
            state=EvidenceState.CONFLICTED,
            reason=f"invalid source ledger contract: {exc}",
        )
    try:
        ledger = validate_source_ledger(
            ledger_path, expected_outputs=expected_outputs, now=when
        )
    except EvidenceError as exc:
        # An expired package is `STALE`, not `CONFLICTED`: the release truth
        # model distinguishes them and both are hard blockers, so nothing is
        # weakened by naming the condition correctly. Staleness is claimed only
        # once the same ledger is shown to pass every other check at its own
        # expiry, so a package that is both expired and tampered with stays
        # `CONFLICTED`.
        state = EvidenceState.CONFLICTED
        expires: datetime | None = None
        observed: datetime | None = None
        freshness_records = parsed.freshness()
        if freshness_records:
            binding = earliest_source_freshness(freshness_records, at=when)
            expires, observed = binding.expires_at, binding.observed_at
            if binding.state_at(when) is EvidenceState.STALE:
                try:
                    validate_source_ledger(
                        ledger_path,
                        expected_outputs=expected_outputs,
                        now=binding.expires_at,
                    )
                except EvidenceError:
                    pass
                else:
                    state = EvidenceState.STALE
        return EvidenceRecord(
            subject="source_ledger",
            field="source_freshness",
            source_artifact_id=sha256_file(ledger_path),
            observed_at=observed,
            expires_at=expires,
            hard_gate=True,
            state=state,
            reason=str(exc),
        )
    records = ledger.freshness()
    if not records:
        return EvidenceRecord(
            subject="source_ledger",
            field="source_freshness",
            value={"schema_version": ledger.schema_version},
            hard_gate=True,
            state=EvidenceState.UNKNOWN,
            reason=(
                f"{SOURCE_LEDGER_V1} preserves no per-source expiry, so freshness"
                " cannot be re-evaluated at the release clock; rebuild the package"
                " with the project command to emit the versioned consumed contract"
            ),
        )
    return source_freshness_evidence(
        records,
        subject="source_ledger",
        field="source_freshness",
        at=when,
        source_artifact_id=sha256_file(ledger_path),
        value={
            "schema_version": ledger.schema_version,
            "entries": len(ledger.entries),
            "scopes": sorted(
                entry.evidence_scope.value
                for entry in ledger.entries
                if entry.evidence_scope is not None
            ),
        },
    )


def parse_official_inactive_snapshot(
    path: str | Path,
    players: Iterable[SalaryPlayer],
) -> InactiveStatusSnapshot:
    active_pool = list(players)
    by_id = {player.dk_id: player for player in active_pool}
    teams = {player.team for player in active_pool}
    statuses: dict[str, str] = {}
    observations: dict[str, datetime] = {}
    source_urls: dict[str, str] = {}
    problems: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        exact = ("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT")
        if tuple(reader.fieldnames or ()) != exact:
            raise EvidenceError(
                "inactive CSV header must be TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT"
            )
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise EvidenceError(
                    f"inactive row {row_number} has missing or extra cells"
                )
            team = row["TEAM"].strip().upper()
            player_id = row["PLAYER_OR_GSIS_ID"].strip()
            status = row["STATUS"].strip().upper()
            source_url = row["SOURCE_URL"].strip()
            observed_raw = row["OBSERVED_AT"].strip()
            if team not in teams:
                problems.append(f"row {row_number}: unknown team {team}")
                continue
            player = by_id.get(player_id)
            if player is None:
                problems.append(f"row {row_number}: exact player ID not found: {player_id}")
                continue
            if player.team != team:
                problems.append(f"row {row_number}: player/team conflict")
                continue
            if status not in {"INACTIVE", "ACTIVE"}:
                problems.append(f"row {row_number}: status must be ACTIVE or INACTIVE")
                continue
            parsed_url = urlparse(source_url)
            if parsed_url.scheme.lower() != "https" or not parsed_url.hostname:
                problems.append(f"row {row_number}: HTTPS source URL required")
                continue
            try:
                observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    raise ValueError
            except ValueError:
                problems.append(f"row {row_number}: timezone-aware OBSERVED_AT required")
                continue
            if player_id in statuses and statuses[player_id] != status:
                problems.append(f"row {row_number}: conflicting status for {player_id}")
                continue
            previous = observations.get(player_id)
            if previous is None or observed > previous:
                statuses[player_id] = status
                observations[player_id] = observed.astimezone(timezone.utc)
                source_urls[player_id] = source_url
    return InactiveStatusSnapshot(statuses, observations, source_urls, tuple(problems))


def parse_official_inactives(
    path: str | Path,
    players: Iterable[SalaryPlayer],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Compatibility wrapper for callers that need only statuses and problems."""
    snapshot = parse_official_inactive_snapshot(path, players)
    return snapshot.statuses, snapshot.problems
