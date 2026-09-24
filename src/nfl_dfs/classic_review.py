"""C3 downstream Classic audit, exact-template review export, and readable data.

This module deliberately does not import the C2 candidate producer, joint
selector, or C2 audit.  It accepts only paths and expected hashes, reparses the
canonical artifacts, recomputes the selected-portfolio semantics, constructs
the proposed DraftKings bytes in memory, and publishes review artifacts only
after the downstream audit passes.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from .classic_portfolio_policy import (
    NormalizedClassicPortfolioPolicy,
    parse_normalized_classic_policy_bytes,
    validate_classic_portfolio_policy_bytes,
)
from .contracts import EngineMode, SlateContract
from .dk import CLASSIC_COLUMNS, parse_entries, parse_entry_bytes, parse_salaries, reconcile_template
from .evidence import parse_official_inactive_snapshot
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup, write_upload_bytes
from .portfolio_policy import canonical_decimal_json_bytes
from .readable_review import _render_html


AUDIT_VERSION = "prior_only_classic_export_audit_c3_v2"
READABLE_VERSION = "prior_only_readable_review_classic_c3_v1"
SCORE_SNAPSHOT_VERSION = "nfl_classic_selected_prior_scores_c3_v1"

_REQUIRED_ARTIFACTS = (
    "team_source",
    "player_source",
    "identity_map",
    "team_projections",
    "player_opportunities",
    "source_ledger",
    "team_splits",
    # `official_status_csv` is optional since Session 09 (R28): a run with no
    # activity file is delivered with that gap named, and its binding is `None`.
    "offensive_role_evidence_json",
    "portfolio_policy_source",
    "portfolio_policy_normalized",
    "classic_candidate_bank",
    "classic_assignment",
    "classic_portfolio_audit",
    "selection_report",
    "complete_slate_coverage",
    "classic_selected_scores",
)

_IMMUTABLE_BINDING_ARTIFACTS = {
    "team_prior_sha256": "team_source",
    "player_prior_sha256": "player_source",
    "identity_map_sha256": "identity_map",
    "team_projections_sha256": "team_projections",
    "player_opportunities_sha256": "player_opportunities",
    "source_ledger_sha256": "source_ledger",
    "official_status_sha256": "official_status_csv",
    "offensive_role_evidence_sha256": "offensive_role_evidence_json",
    # Optional, exactly like the weather package below it: bound when the run
    # carried one, `None` when it did not. It is deliberately not in
    # `_REQUIRED_ARTIFACTS` — a slate whose quarterbacks need no depth chart is
    # a normal slate, not an incomplete one.
    "qb_depth_role_evidence_sha256": "qb_depth_role_evidence_json",
    "weather_evidence_sha256": "weather_evidence_json",
    "source_policy_sha256": "portfolio_policy_source",
    "normalized_policy_sha256": "portfolio_policy_normalized",
    "candidate_bank_sha256": "classic_candidate_bank",
    "assignment_sha256": "classic_assignment",
    "classic_portfolio_audit_sha256": "classic_portfolio_audit",
}

_C2_AUDIT_HASH_ARTIFACTS = {
    "salary_sha256": "salary_csv",
    "entry_sha256": "entry_csv",
    "team_prior_sha256": "team_source",
    "player_prior_sha256": "player_source",
    "identity_map_sha256": "identity_map",
    "team_projections_sha256": "team_projections",
    "player_opportunities_sha256": "player_opportunities",
    "source_ledger_sha256": "source_ledger",
    "team_splits_sha256": "team_splits",
    "source_policy_sha256": "portfolio_policy_source",
    "normalized_policy_sha256": "portfolio_policy_normalized",
    "candidate_bank_sha256": "classic_candidate_bank",
    "assignment_sha256": "classic_assignment",
}
_CANONICAL_NEWLINE_SCHEMAS = {
    "prior_only_classic_portfolio_audit_c2_v1",
    "nfl_classic_prior_review_selection_c2_v1",
    "nfl_classic_slate_coverage_c2_v1",
    SCORE_SNAPSHOT_VERSION,
}


class ClassicReviewError(ValueError):
    """A named fail-closed C3 discrepancy."""


class ClassicReviewPresentationError(ClassicReviewError):
    """The readable review failed after the export and its audit passed (R28, Session 05).

    The export CSV and its audit stay on disk, re-verified after the failure by
    hash, reparse and the `DK_UPLOAD` check; only the readable JSON and HTML are
    removed. The message is the presentation code, or
    `CLASSIC_C3_READABLE_RENDER_FAILED` for an exception that carries none.
    """

    def __init__(
        self,
        message: str,
        *,
        export_path: str,
        export_sha256: str,
        audit_path: str,
        audit_sha256: str,
        audit: dict[str, object],
    ) -> None:
        super().__init__(message)
        self.export_path = export_path
        self.export_sha256 = export_sha256
        self.audit_path = audit_path
        self.audit_sha256 = audit_sha256
        self.audit = audit


@dataclass(frozen=True)
class ClassicReviewArtifacts:
    data: dict[str, object]
    audit: dict[str, object]
    audit_path: str
    audit_sha256: str
    export_path: str
    export_sha256: str
    json_path: str
    json_sha256: str
    html_path: str
    html_sha256: str


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"nonfinite JSON number {value}")


def _strict_json(raw: bytes, *, label: str, canonical: bool = False) -> Mapping[str, object]:
    try:
        payload = json.loads(
            raw.decode("utf-8-sig"),
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_pairs_without_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClassicReviewError(f"CLASSIC_C3_{label}_JSON_INVALID:{exc}") from exc
    if not isinstance(payload, Mapping):
        raise ClassicReviewError(f"CLASSIC_C3_{label}_OBJECT_REQUIRED")
    if canonical:
        schema = str(payload.get("schema_version") or payload.get("audit_version") or "")
        if schema in _CANONICAL_NEWLINE_SCHEMAS:
            plain = json.loads(
                raw.decode("utf-8"),
                parse_constant=_reject_nonfinite,
                object_pairs_hook=_pairs_without_duplicates,
            )
            expected = (
                json.dumps(dict(plain), sort_keys=True, separators=(",", ":"), default=str)
                + "\n"
            ).encode("utf-8")
        else:
            expected = canonical_decimal_json_bytes(payload)
        if raw != expected:
            raise ClassicReviewError(f"CLASSIC_C3_{label}_BYTES_NOT_CANONICAL")
    return payload


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")


def _artifact_expected_hash(
    name: str, path: Path, expected_hashes: Mapping[str, str]
) -> str | None:
    direct = expected_hashes.get(name)
    if direct:
        return str(direct)
    aliases = {
        "team_source": "prior:team_prior.json",
        "player_source": "prior:player_prior.json",
        "identity_map": "prior:identity_map.json",
        "team_projections": "projected:team_projections",
        "player_opportunities": "projected:player_opportunities",
        "source_ledger": "projected:source_ledger",
        "team_splits": "frozen:team_stats",
    }
    alias = aliases.get(name)
    if alias and alias in expected_hashes:
        return str(expected_hashes[alias])
    for candidate in (
        f"prior:{path.name}",
        f"proposal:{path.name}",
        f"projected:{path.stem}",
    ):
        if candidate in expected_hashes:
            return str(expected_hashes[candidate])
    return None


def _tracked_paths(
    salary_path: Path,
    entry_path: Path,
    artifacts: Mapping[str, str],
) -> dict[str, Path]:
    paths = {"salary_csv": salary_path, "entry_csv": entry_path}
    for name, raw_path in artifacts.items():
        paths[str(name)] = Path(raw_path).resolve()
    return paths


def _expected_for_paths(
    paths: Mapping[str, Path], expected_hashes: Mapping[str, str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, path in paths.items():
        expected = _artifact_expected_hash(name, path, expected_hashes)
        if expected:
            result[name] = expected
    return result


def _hash_checkpoint(
    name: str,
    paths: Mapping[str, Path],
    expected: Mapping[str, str],
) -> dict[str, str]:
    actual: dict[str, str] = {}
    problems: list[str] = []
    for label, path in sorted(paths.items()):
        digest = sha256_file(path) if path.is_file() else "MISSING"
        actual[label] = digest
        wanted = expected.get(label)
        if wanted is None:
            problems.append(f"CLASSIC_C3_EXPECTED_HASH_MISSING:{label}")
        elif digest != wanted:
            problems.append(
                f"CLASSIC_C3_{name}_HASH_MISMATCH:{label}:actual={digest}:expected={wanted}"
            )
    if problems:
        raise ClassicReviewError(";".join(problems))
    return actual


def _integer(value: object, *, label: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ClassicReviewError(f"CLASSIC_C3_{label}_INTEGER_INVALID:{value!r}")
    return value


def _sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise ClassicReviewError(f"CLASSIC_C3_{label}_ARRAY_REQUIRED")
    return value


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ClassicReviewError(f"CLASSIC_C3_{label}_OBJECT_REQUIRED")
    return value


def _stack_value(slate: SlateContract, roster: Sequence[str], rule_type: str) -> int:
    """C3's independent copy of the registered C2 stack semantics."""

    by_id = {row.dk_id: row for row in slate.players}
    rows = [by_id[str(dk_id)] for dk_id in roster]
    quarterbacks = [row for row in rows if row.position == "QB"]
    if len(quarterbacks) != 1:
        raise ClassicReviewError("CLASSIC_C3_QB_CARDINALITY_INVALID")
    qb = quarterbacks[0]
    if rule_type == "QB_PASS_CATCHER":
        return sum(row.team == qb.team and row.position in {"WR", "TE"} for row in rows)
    if rule_type == "QB_BRINGBACK":
        return sum(
            row.team == qb.opponent and row.position in {"RB", "WR", "TE"}
            for row in rows
        )
    if rule_type == "RB_DST_PAIR":
        dst_teams = {row.team for row in rows if row.position == "DST"}
        return sum(row.position == "RB" and row.team in dst_teams for row in rows)
    if rule_type == "SECONDARY_GAME_CORRELATION":
        return sum(
            {game.away_team, game.home_team}.issubset(
                {
                    row.team
                    for row in rows
                    if row.game_id == game.game_id and row.position != "DST"
                }
            )
            for game in slate.games
            if game.game_id != qb.game_id
        )
    raise ClassicReviewError(f"CLASSIC_C3_STACK_RULE_UNREGISTERED:{rule_type}")


def _audit_template_bytes(
    *,
    source_bytes: bytes,
    output_bytes: bytes,
    encoding: str,
    roster_start: int,
    roster_width: int,
    assignments: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    source_lines = split_byte_lines(source_bytes)
    output_lines = split_byte_lines(output_bytes)
    if len(source_lines) != len(output_lines):
        return ("CLASSIC_C3_EXPORT_PHYSICAL_LINE_COUNT_CHANGED",)
    problems: list[str] = []
    seen: set[str] = set()
    roster_end = roster_start + roster_width
    for line_number, (source_line, output_line) in enumerate(
        zip(source_lines, output_lines, strict=True), start=1
    ):
        source_body, source_ending = split_line_ending(source_line)
        output_body, output_ending = split_line_ending(output_line)
        if source_ending != output_ending:
            problems.append(f"CLASSIC_C3_EXPORT_LINE_ENDING_CHANGED:line={line_number}")
        try:
            source_row = next(csv.reader(io.StringIO(source_line.decode(encoding), newline="")))
            output_row = next(csv.reader(io.StringIO(output_line.decode(encoding), newline="")))
            source_spans = csv_field_spans(source_body)
            output_spans = csv_field_spans(output_body)
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            problems.append(f"CLASSIC_C3_EXPORT_REPARSE_FAILED:line={line_number}:{exc}")
            continue
        source_id = source_row[0].strip() if source_row else ""
        output_id = output_row[0].strip() if output_row else ""
        if source_id != output_id:
            problems.append(f"CLASSIC_C3_EXPORT_ENTRY_ID_CHANGED:line={line_number}")
            continue
        if source_id not in assignments:
            if source_line != output_line:
                problems.append(f"CLASSIC_C3_EXPORT_UNAUTHORIZED_BYTES_CHANGED:line={line_number}")
            continue
        seen.add(source_id)
        if any(source_row[roster_start:roster_end]):
            problems.append(f"CLASSIC_C3_EXPORT_PREFILLED_AUTHORIZED_ENTRY:{source_id}")
        if len(source_spans) != len(output_spans):
            problems.append(f"CLASSIC_C3_EXPORT_FIELD_COUNT_CHANGED:line={line_number}")
            continue
        for index, ((left_start, left_end), (right_start, right_end)) in enumerate(
            zip(source_spans, output_spans, strict=True)
        ):
            if roster_start <= index < roster_end:
                continue
            if source_body[left_start:left_end] != output_body[right_start:right_end]:
                problems.append(
                    f"CLASSIC_C3_EXPORT_NON_ROSTER_FIELD_CHANGED:line={line_number}:field={index + 1}"
                )
                break
        if source_row[:roster_start] != output_row[:roster_start]:
            problems.append(f"CLASSIC_C3_EXPORT_METADATA_CHANGED:line={line_number}")
        if source_row[roster_end:] != output_row[roster_end:]:
            problems.append(f"CLASSIC_C3_EXPORT_TRAILING_CELLS_CHANGED:line={line_number}")
        if tuple(value.strip() for value in output_row[roster_start:roster_end]) != assignments[source_id]:
            problems.append(f"CLASSIC_C3_EXPORT_ROSTER_MISMATCH:{source_id}")
    if seen != set(assignments):
        problems.append(
            f"CLASSIC_C3_EXPORT_ENTRY_COVERAGE_MISMATCH:actual={sorted(seen)}:expected={sorted(assignments)}"
        )
    return tuple(problems)


def _role_evidence(
    *,
    path: Path,
    slate: SlateContract,
    selected_people: set[str],
    required_people: set[str],
    audit_at: datetime,
) -> dict[str, dict[str, object]]:
    payload = _strict_json(path.read_bytes(), label="OFFENSIVE_ROLE_EVIDENCE")
    if payload.get("schema_version") != "nfl_classic_offensive_role_evidence_c1_v1":
        raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_SCHEMA_MISMATCH")
    if payload.get("salary_sha256") != slate.salary_hash:
        raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_SALARY_BINDING_MISMATCH")
    if tuple(str(value) for value in _sequence(payload.get("game_ids"), label="ROLE_GAME_IDS")) != tuple(
        game.game_id for game in slate.games
    ):
        raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_GAME_ORDER_MISMATCH")
    sources: dict[str, Mapping[str, object]] = {}
    source_root = path.parent
    for raw in _sequence(payload.get("sources"), label="ROLE_SOURCES"):
        source = _mapping(raw, label="ROLE_SOURCE")
        digest = str(source.get("sha256", ""))
        if not digest or digest in sources:
            raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_SOURCE_ID_INVALID")
        if source.get("support_kind") != "NUMERICAL_ALLOCATION" or source.get("synthetic") is True:
            raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_SOURCE_UNSUPPORTED:{digest}")
        relative = Path(str(source.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ClassicReviewError(f"CLASSIC_C3_OFFENSIVE_ROLE_SOURCE_PATH_INVALID:{relative}")
        captured = (source_root / relative).resolve()
        try:
            captured.relative_to(source_root.resolve())
        except ValueError as exc:
            raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_SOURCE_PATH_ESCAPE") from exc
        if sha256_file(captured) != digest:
            raise ClassicReviewError(f"CLASSIC_C3_OFFENSIVE_ROLE_SOURCE_SHA256_MISMATCH:{digest}")
        expires = datetime.fromisoformat(str(source.get("expires_at", "")).replace("Z", "+00:00"))
        if expires.tzinfo is None or audit_at.astimezone(timezone.utc) > expires.astimezone(timezone.utc):
            raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_EVIDENCE_STALE:{digest}")
        sources[digest] = source
    by_person = {row.underlying_id: row for row in slate.players}
    selected_offense = {
        person for person in selected_people if by_person[person].position in {"QB", "RB", "WR", "TE"}
    }
    facts: dict[str, dict[str, object]] = {}
    for raw in _sequence(payload.get("declarations"), label="ROLE_DECLARATIONS"):
        declaration = _mapping(raw, label="ROLE_DECLARATION")
        digest = str(declaration.get("source_sha256", ""))
        source = sources.get(digest)
        if source is None:
            raise ClassicReviewError(f"CLASSIC_C3_OFFENSIVE_ROLE_DECLARATION_SOURCE_MISSING:{digest}")
        for recipient_raw in _sequence(declaration.get("recipients"), label="ROLE_RECIPIENTS"):
            recipient = _mapping(recipient_raw, label="ROLE_RECIPIENT")
            person = str(recipient.get("underlying_id", ""))
            if person not in selected_offense:
                continue
            player = by_person[person]
            if (
                str(recipient.get("dk_id", "")) != player.dk_id
                or declaration.get("team") != player.team
                or declaration.get("game_id") != player.game_id
                or person in facts
            ):
                raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_IDENTITY_MISMATCH:{person}")
            shares = _mapping(recipient.get("shares"), label="ROLE_SHARES")
            for field, value in shares.items():
                if not isinstance(value, (int, Decimal)) or isinstance(value, bool):
                    raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_SHARE_INVALID:{person}:{field}")
                number = float(value)
                if not math.isfinite(number) or not 0 <= number <= 1:
                    raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_SHARE_INVALID:{person}:{field}")
            facts[person] = {
                "state": "SOURCE_SUPPORTED_ADJUSTMENT",
                "source_sha256": digest,
                "source_uri": source.get("source_uri"),
                "observed_at": source.get("observed_at"),
                "expires_at": source.get("expires_at"),
                "shares": {str(key): float(value) for key, value in sorted(shares.items())},
            }
    # Only the people the selection gate recorded as source-supported have to
    # appear here. Anyone else selected on a history-derived prior is named in
    # the review as such; a package that stops covering a person the gate
    # claimed is still a hard disagreement.
    missing = sorted(required_people.intersection(selected_offense).difference(facts))
    if missing:
        raise ClassicReviewError(f"CLASSIC_C3_SELECTED_ROLE_EVIDENCE_MISSING:{missing}")
    return facts


def _portable_artifacts(
    paths: Mapping[str, Path],
    hashes: Mapping[str, str],
    *,
    package_root: Path,
    html_root: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, path in sorted(paths.items()):
        try:
            portable = path.resolve().relative_to(package_root.resolve()).as_posix()
        except ValueError:
            portable = path.name
        try:
            href = os.path.relpath(path, html_root).replace(os.sep, "/")
        except ValueError:
            href = None
        rows.append(
            {"name": name, "path": portable, "href": href, "sha256": hashes[name]}
        )
    return rows


def _atomic_write(path: Path, payload: bytes) -> str:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return sha256_file(path)


def _safe_remove_created(paths: Sequence[Path]) -> None:
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
            temporary = path.with_name(path.name + ".tmp")
            if temporary.is_file():
                temporary.unlink()
        except OSError:
            pass


def _verify_kept_export(
    export_file: Path,
    export_sha: str,
    audit_file: Path,
    audit_sha: str,
    reparsed_output,
) -> None:
    """The export and its audit are still the bytes that passed, and nothing upload-named exists."""

    try:
        final_reparse = parse_entry_bytes(export_file.read_bytes(), source_name=str(export_file))
    except Exception as exc:  # noqa: BLE001 - written bytes must fail closed
        raise ClassicReviewError(
            f"CLASSIC_C3_FINAL_OUTPUT_REPARSE_FAILED:{type(exc).__name__}:{exc}"
        ) from exc
    if reparsed_output is None or final_reparse.authorizations != reparsed_output.authorizations:
        raise ClassicReviewError("CLASSIC_C3_FINAL_OUTPUT_REPARSE_MISMATCH")
    if sha256_file(export_file) != export_sha or sha256_file(audit_file) != audit_sha:
        raise ClassicReviewError("CLASSIC_C3_FINAL_OUTPUT_SHA256_MISMATCH")
    if list(export_file.parent.glob("DK_UPLOAD_*.csv")):
        raise ClassicReviewError("CLASSIC_C3_DK_UPLOAD_ARTIFACT_PROHIBITED")


def create_classic_review_package(
    *,
    salary_path: str | Path,
    entry_path: str | Path,
    artifacts: Mapping[str, str],
    expected_hashes: Mapping[str, str],
    audit_at: datetime,
    output_path: str | Path,
    output_dir: str | Path,
    package_root: str | Path,
    blockers: Sequence[str] = (),
    next_action: str = (
        "Review every exact Entry ID, roster ID, policy limit, evidence fact, and limitation. "
        "Do not upload this prior-only review CSV."
    ),
) -> ClassicReviewArtifacts:
    """Publish the C3 package only after independent byte/semantic reconciliation."""

    if audit_at.tzinfo is None:
        raise ClassicReviewError("CLASSIC_C3_AUDIT_CLOCK_REQUIRES_TIMEZONE")
    missing = [name for name in _REQUIRED_ARTIFACTS if name not in artifacts]
    if missing:
        raise ClassicReviewError(f"CLASSIC_C3_REQUIRED_ARTIFACT_MISSING:{missing}")
    salary_file = Path(salary_path).resolve()
    entry_file = Path(entry_path).resolve()
    export_file = Path(output_path).resolve()
    review_root = Path(output_dir).resolve()
    package = Path(package_root).resolve()
    audit_file = review_root / "classic_review_export_audit.json"
    json_file = review_root / "prior_only_readable_review.json"
    html_file = review_root / "prior_only_readable_review.html"
    new_files = (export_file, audit_file, json_file, html_file)
    existing = [str(path) for path in new_files if path.exists()]
    if existing:
        raise ClassicReviewError(f"CLASSIC_C3_OUTPUT_EXISTS:{existing}")
    review_root.mkdir(parents=True, exist_ok=True)
    export_file.parent.mkdir(parents=True, exist_ok=True)

    tracked = _tracked_paths(salary_file, entry_file, artifacts)
    expected = _expected_for_paths(tracked, expected_hashes)
    intake_hashes = _hash_checkpoint("INTAKE", tracked, expected)
    problems: list[str] = []
    created: list[Path] = []
    presenting = False
    try:
        slate = parse_salaries(salary_file)
        template = parse_entries(entry_file)
        reconcile_template(template, slate)
        if slate.mode is not EngineMode.CLASSIC or template.roster_columns != CLASSIC_COLUMNS:
            raise ClassicReviewError("CLASSIC_C3_MODE_MISMATCH")
        if any(any(item.existing_cells) for item in template.authorizations):
            raise ClassicReviewError("CLASSIC_C3_BLANK_CELL_AUTHORITY_REQUIRED")
        entry_ids = tuple(item.entry_id for item in template.authorizations)

        source_raw = tracked["portfolio_policy_source"].read_bytes()
        normalized_raw = tracked["portfolio_policy_normalized"].read_bytes()
        policy = parse_normalized_classic_policy_bytes(normalized_raw)
        source_validation = validate_classic_portfolio_policy_bytes(
            source_raw,
            slate=slate,
            entry_ids=entry_ids,
            entry_sha256=template.raw_hash,
        )
        if not source_validation.valid or source_validation.policy is None:
            raise ClassicReviewError(
                "CLASSIC_C3_SOURCE_POLICY_INVALID:" + ";".join(source_validation.blockers())
            )
        if source_validation.policy.canonical_bytes() != normalized_raw:
            raise ClassicReviewError("CLASSIC_C3_SOURCE_NORMALIZED_POLICY_DISAGREEMENT")
        if policy.entry_ids != entry_ids:
            raise ClassicReviewError("CLASSIC_C3_POLICY_ENTRY_ORDER_MISMATCH")

        bank = _strict_json(
            tracked["classic_candidate_bank"].read_bytes(), label="CANDIDATE_BANK", canonical=True
        )
        assignment = _strict_json(
            tracked["classic_assignment"].read_bytes(), label="ASSIGNMENT", canonical=True
        )
        c2_audit = _strict_json(
            tracked["classic_portfolio_audit"].read_bytes(), label="C2_AUDIT", canonical=True
        )
        selection = _strict_json(
            tracked["selection_report"].read_bytes(), label="SELECTION", canonical=True
        )
        coverage = _strict_json(
            tracked["complete_slate_coverage"].read_bytes(), label="COVERAGE", canonical=True
        )
        score_snapshot = _strict_json(
            tracked["classic_selected_scores"].read_bytes(), label="SCORES", canonical=True
        )
        if bank.get("schema_version") != "nfl_classic_candidate_bank_c2_v1":
            problems.append("CLASSIC_C3_CANDIDATE_BANK_SCHEMA_MISMATCH")
        if assignment.get("schema_version") != "nfl_classic_portfolio_assignment_c2_v1":
            problems.append("CLASSIC_C3_ASSIGNMENT_SCHEMA_MISMATCH")
        if c2_audit.get("audit_version") != "prior_only_classic_portfolio_audit_c2_v1":
            problems.append("CLASSIC_C3_C2_AUDIT_SCHEMA_MISMATCH")
        if selection.get("schema_version") != "nfl_classic_prior_review_selection_c2_v1":
            problems.append("CLASSIC_C3_SELECTION_SCHEMA_MISMATCH")
        if coverage.get("schema_version") != "nfl_classic_slate_coverage_c2_v1":
            problems.append("CLASSIC_C3_COVERAGE_SCHEMA_MISMATCH")
        if score_snapshot.get("schema_version") != SCORE_SNAPSHOT_VERSION:
            problems.append("CLASSIC_C3_SCORE_SNAPSHOT_SCHEMA_MISMATCH")

        actual_hash = intake_hashes
        expected_bindings = {
            "salary_sha256": actual_hash["salary_csv"],
            "entry_sha256": actual_hash["entry_csv"],
            **{
                binding: actual_hash.get(artifact)
                for binding, artifact in _IMMUTABLE_BINDING_ARTIFACTS.items()
            },
            "weather_source_sha256_by_game": {
                name.removeprefix("weather_source:"): digest
                for name, digest in sorted(actual_hash.items())
                if name.startswith("weather_source:")
            },
        }
        for record_name, record in (("SELECTION", selection), ("COVERAGE", coverage)):
            bindings = _mapping(record.get("immutable_bindings"), label=f"{record_name}_BINDINGS")
            for label, digest in expected_bindings.items():
                if bindings.get(label) != digest:
                    problems.append(f"CLASSIC_C3_{record_name}_BINDING_MISMATCH:{label}")
            for truth, wanted in (
                ("FILE_VALID", True),
                ("MODEL_STATUS", "PRIOR_ONLY"),
                ("RELEASE_DECISION", "DO_NOT_UPLOAD"),
            ):
                if record.get(truth) != wanted:
                    problems.append(f"CLASSIC_C3_{record_name}_{truth}_MISMATCH")
        if selection.get("mode") != "CLASSIC" or coverage.get("mode") != "CLASSIC":
            problems.append("CLASSIC_C3_REVIEW_MODE_MISMATCH")
        if selection.get("draft_group") != slate.draft_group:
            problems.append("CLASSIC_C3_DRAFT_GROUP_MISMATCH")
        if bank.get("normalized_policy_sha256") != actual_hash["portfolio_policy_normalized"]:
            problems.append("CLASSIC_C3_CANDIDATE_POLICY_BINDING_MISMATCH")
        if assignment.get("normalized_policy_sha256") != actual_hash["portfolio_policy_normalized"]:
            problems.append("CLASSIC_C3_ASSIGNMENT_POLICY_BINDING_MISMATCH")
        if assignment.get("candidate_bank_sha256") != actual_hash["classic_candidate_bank"]:
            problems.append("CLASSIC_C3_ASSIGNMENT_CANDIDATE_BINDING_MISMATCH")
        if c2_audit.get("status") != "PASS" or c2_audit.get("problems") != []:
            problems.append("CLASSIC_C3_C2_AUDIT_NOT_PASS")
        policy_review = _mapping(selection.get("portfolio_policy"), label="SELECTION_PORTFOLIO_POLICY")
        enforcement = _mapping(policy_review.get("enforcement"), label="SELECTION_ENFORCEMENT")
        if enforcement.get("status") != "ENFORCED_AND_INDEPENDENTLY_AUDITED":
            problems.append("CLASSIC_C3_C2_ENFORCEMENT_STATUS_MISMATCH")
        if enforcement.get("candidate_bank_status") != bank.get("status"):
            problems.append("CLASSIC_C3_C2_CANDIDATE_STATUS_MISMATCH")
        # Session 08: a joint selection a time or search limit stopped with a
        # valid incumbent is accepted, labelled, with no optimality scope; only
        # a proven optimum is scoped to the actual bank.
        joint_status = enforcement.get("joint_selection_status")
        joint_scopes = {
            "OPTIMAL_ACTUAL_CANDIDATE_BANK": "ACTUAL_CANDIDATE_BANK",
            "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK": None,
        }
        if joint_status not in joint_scopes:
            problems.append("CLASSIC_C3_C2_JOINT_SELECTION_NOT_OPTIMAL_ACTUAL_BANK")
        if enforcement.get("optimality_scope") != joint_scopes.get(joint_status, "ACTUAL_CANDIDATE_BANK"):
            problems.append("CLASSIC_C3_C2_OPTIMALITY_SCOPE_MISMATCH")
        for label, digest in (
            ("source_policy_sha256", actual_hash["portfolio_policy_source"]),
            ("normalized_policy_sha256", actual_hash["portfolio_policy_normalized"]),
            ("candidate_bank_sha256", actual_hash["classic_candidate_bank"]),
            ("assignment_sha256", actual_hash["classic_assignment"]),
            ("audit_sha256", actual_hash["classic_portfolio_audit"]),
        ):
            if policy_review.get(label) != digest:
                problems.append(f"CLASSIC_C3_C2_POLICY_RECORD_BINDING_MISMATCH:{label}")
        if policy_review.get("independent_audit") != c2_audit:
            problems.append("CLASSIC_C3_C2_EMBEDDED_AUDIT_DISAGREEMENT")
        policy_coverage = _mapping(coverage.get("policy_coverage"), label="COVERAGE_POLICY")
        if policy_coverage.get("independent_audit") != c2_audit:
            problems.append("CLASSIC_C3_COVERAGE_EMBEDDED_AUDIT_DISAGREEMENT")

        raw_candidates = _sequence(bank.get("candidates"), label="CANDIDATES")
        candidate_by_roster: dict[tuple[str, ...], Mapping[str, object]] = {}
        for raw in raw_candidates:
            candidate = _mapping(raw, label="CANDIDATE")
            roster = tuple(str(value) for value in _sequence(candidate.get("roster"), label="CANDIDATE_ROSTER"))
            if roster in candidate_by_roster:
                problems.append("CLASSIC_C3_CANDIDATE_ROSTER_DUPLICATE")
            candidate_by_roster[roster] = candidate
        requested_candidates = _integer(bank.get("requested_candidates"), label="CANDIDATE_REQUESTED", minimum=1)
        produced_candidates = _integer(bank.get("produced_candidates"), label="CANDIDATE_PRODUCED", minimum=1)
        if produced_candidates != len(raw_candidates):
            problems.append("CLASSIC_C3_CANDIDATE_COUNT_MISMATCH")
        if bank.get("canonical_unique_candidates") != len(
            {str(item.get("canonical_key", "")) for item in candidate_by_roster.values()}
        ):
            problems.append("CLASSIC_C3_CANDIDATE_CANONICAL_COUNT_MISMATCH")
        # A bank stopped at a limit that still held the entry count and its
        # POLICY_FEASIBLE witness is accepted under a status naming the limit.
        if bank.get("status") not in {
            "BOUNDED_COMPLETION",
            "EXHAUSTIVE_COMPLETION",
            "BOUNDED_TIME_LIMIT_STOP",
            "BOUNDED_SEARCH_LIMIT_STOP",
        }:
            problems.append(f"CLASSIC_C3_CANDIDATE_BANK_NOT_ACCEPTED:{bank.get('status')}")
        if bank.get("policy_feasible_chain_status") != "POLICY_FEASIBLE":
            problems.append("CLASSIC_C3_POLICY_FEASIBLE_CHAIN_NOT_PASS")

        raw_pairs = _sequence(assignment.get("entry_assignments"), label="ENTRY_ASSIGNMENTS")
        pairs: list[tuple[str, tuple[str, ...]]] = []
        for raw in raw_pairs:
            item = _mapping(raw, label="ENTRY_ASSIGNMENT")
            pairs.append(
                (
                    str(item.get("entry_id", "")),
                    tuple(str(value) for value in _sequence(item.get("roster"), label="ASSIGNMENT_ROSTER")),
                )
            )
        if tuple(entry for entry, _roster in pairs) != entry_ids:
            problems.append("CLASSIC_C3_ASSIGNMENT_ENTRY_ORDER_OR_COVERAGE_MISMATCH")
        assignments = {entry: roster for entry, roster in pairs}
        if len(assignments) != len(pairs):
            problems.append("CLASSIC_C3_ASSIGNMENT_ENTRY_DUPLICATE")

        by_id = {row.dk_id: row for row in slate.players}
        people_by_entry: dict[str, frozenset[str]] = {}
        canonical_by_entry: dict[str, str] = {}
        player_counts: Counter[str] = Counter()
        team_counts: Counter[str] = Counter()
        game_counts: Counter[str] = Counter()
        group_counts: Counter[str] = Counter()
        stack_counts: Counter[str] = Counter()
        stack_values_by_entry: dict[str, dict[str, int]] = {}
        group_matches_by_entry: dict[str, list[str]] = {}
        entries_payload: list[dict[str, object]] = []

        scores_raw = _mapping(score_snapshot.get("scores_by_dk_id"), label="SCORES_BY_DK_ID")
        score_map: dict[str, float] = {}
        for dk_id, value in scores_raw.items():
            if not isinstance(value, (int, Decimal)) or isinstance(value, bool) or not math.isfinite(float(value)):
                problems.append(f"CLASSIC_C3_SCORE_INVALID:{dk_id}")
            else:
                score_map[str(dk_id)] = float(value)
        selected_ids = {dk_id for _entry, roster in pairs for dk_id in roster}
        if set(score_map) != selected_ids:
            problems.append("CLASSIC_C3_SELECTED_SCORE_COVERAGE_MISMATCH")
        if score_snapshot.get("salary_sha256") != slate.salary_hash:
            problems.append("CLASSIC_C3_SCORE_SALARY_BINDING_MISMATCH")
        if score_snapshot.get("assignment_sha256") != actual_hash["classic_assignment"]:
            problems.append("CLASSIC_C3_SCORE_ASSIGNMENT_BINDING_MISMATCH")

        # R28 (Session 09): a selected person with no exact-ID activity row, or a
        # run with no official status file at all, is a named limitation, not a
        # refusal. A row that is not ACTIVE still refuses, and the bound
        # artifacts must agree with this re-read about who lacks a row.
        status_path = tracked.get("official_status_csv")
        coverage_activity = coverage.get("official_status_coverage")
        statuses: Mapping[str, str] = {}
        observed_by_id: Mapping[str, datetime] = {}
        source_by_id: Mapping[str, str] = {}
        if status_path is None:
            if coverage_activity is not None:
                raise ClassicReviewError("CLASSIC_C3_OFFICIAL_STATUS_ARTIFACT_REQUIRED")
        else:
            status = parse_official_inactive_snapshot(status_path, slate.players)
            if status.problems:
                problems.extend(f"CLASSIC_C3_OFFICIAL_STATUS_INVALID:{item}" for item in status.problems)
            statuses = status.statuses
            observed_by_id = status.observed_at_by_id
            source_by_id = status.source_url_by_id
        for dk_id in sorted(selected_ids, key=int):
            if statuses.get(dk_id, "ACTIVE") != "ACTIVE":
                problems.append(f"CLASSIC_C3_SELECTED_ACTIVITY_NOT_ACTIVE:{dk_id}:{statuses.get(dk_id)}")
        selected_people = {by_id[dk_id].underlying_id for dk_id in selected_ids if dk_id in by_id}
        covered_people = {row.underlying_id for row in slate.players if row.dk_id in statuses}
        activity_missing = sorted(selected_people - covered_people)
        selected_gate = _mapping(coverage.get("selected_evidence_gate"), label="SELECTED_EVIDENCE_GATE")
        gate_activity = sorted(
            str(item.get("person"))
            for item in _sequence(selected_gate.get("activity_gaps") or (), label="ACTIVITY_GAPS")
            if isinstance(item, Mapping)
        )
        expected_gate_status = "PASS_WITH_NAMED_LIMITATIONS" if activity_missing else "PASS"
        if selected_gate.get("status") != expected_gate_status or selected_gate.get("gaps") != []:
            problems.append("CLASSIC_C3_SELECTED_EVIDENCE_GATE_NOT_PASS")
        if gate_activity != activity_missing:
            problems.append("CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH")
        # R17 extended to Classic, 2026-09-12. The selection gate decides which
        # selected offensive people rest on a captured numerical allocation and
        # which rest on a history-derived prior. C3 re-derives that split from
        # the gate artifact rather than assuming one: every person the gate
        # claims is source-supported must still be covered by the role package
        # here, so a package that stops covering him is caught; a person the
        # gate recorded as history-derived needs no entry and is named in the
        # review instead. The artifact is required exactly when the gate claims
        # at least one source-supported role.
        claimed_source_supported = {
            str(item.get("person"))
            for item in _sequence(
                selected_gate.get("selected_role_observations") or (),
                label="SELECTED_ROLE_OBSERVATIONS",
            )
            if isinstance(item, Mapping)
            and item.get("state") == "SOURCE_SUPPORTED_ADJUSTMENT"
            and item.get("person")
        }
        required_role_people = claimed_source_supported.intersection(selected_people)
        role_path = tracked.get("offensive_role_evidence_json")
        if role_path is None:
            if required_role_people:
                raise ClassicReviewError("CLASSIC_C3_OFFENSIVE_ROLE_ARTIFACT_REQUIRED")
            role_facts: dict[str, dict[str, object]] = {}
        else:
            role_facts = _role_evidence(
                path=role_path,
                slate=slate,
                selected_people=selected_people,
                required_people=required_role_people,
                audit_at=audit_at,
            )
        position_by_person = {row.underlying_id: row.position for row in slate.players}
        history_derived_people = sorted(
            person
            for person in selected_people
            if position_by_person.get(person) in {"QB", "RB", "WR", "TE"}
            and person not in role_facts
        )
        if coverage_activity is not None:
            activity_coverage = _mapping(coverage_activity, label="OFFICIAL_STATUS_COVERAGE")
            if activity_coverage.get("selected_without_row") != activity_missing:
                problems.append("CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH")
        elif status_path is not None:
            problems.append("CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH")

        selection_lineups: dict[tuple[str, ...], Mapping[str, object]] = {}
        for raw in _sequence(selection.get("lineups"), label="SELECTION_LINEUPS"):
            item = _mapping(raw, label="SELECTION_LINEUP")
            roster = tuple(str(value) for value in _sequence(item.get("roster"), label="SELECTION_ROSTER"))
            selection_lineups[roster] = item

        for authorization in template.authorizations:
            roster = assignments.get(authorization.entry_id, ())
            if roster not in candidate_by_roster:
                problems.append(f"CLASSIC_C3_ASSIGNMENT_OUTSIDE_CANDIDATE_BANK:{authorization.entry_id}")
            valid = validate_lineup(slate, roster)
            if not valid.valid or valid.lineup is None:
                problems.extend(
                    f"CLASSIC_C3_LINEUP_ILLEGAL:{authorization.entry_id}:{item}"
                    for item in valid.errors
                )
                continue
            rows = [by_id[dk_id] for dk_id in roster]
            people = frozenset(row.underlying_id for row in rows)
            teams = frozenset(row.team for row in rows)
            games = frozenset(row.game_id for row in rows)
            people_by_entry[authorization.entry_id] = people
            canonical_by_entry[authorization.entry_id] = valid.lineup.canonical_key
            player_counts.update(people)
            team_counts.update(teams)
            game_counts.update(games)
            group_matches: list[str] = []
            for group in policy.groups:
                count = len(people.intersection(group.member_ids))
                if group.minimum_players <= count <= group.maximum_players:
                    group_matches.append(group.group_id)
            group_counts.update(group_matches)
            group_matches_by_entry[authorization.entry_id] = group_matches
            stack_values: dict[str, int] = {}
            for rule in policy.stack_rules:
                value = _stack_value(slate, roster, rule.rule_type)
                stack_values[rule.rule_id] = value
                if rule.minimum_value <= value <= rule.maximum_value:
                    stack_counts.update((rule.rule_id,))
            stack_values_by_entry[authorization.entry_id] = stack_values
            candidate = candidate_by_roster.get(roster, {})
            if candidate.get("canonical_key") != valid.lineup.canonical_key:
                problems.append(f"CLASSIC_C3_CANDIDATE_CANONICAL_MISMATCH:{authorization.entry_id}")
            if candidate.get("people") != sorted(people):
                problems.append(f"CLASSIC_C3_CANDIDATE_PEOPLE_MISMATCH:{authorization.entry_id}")
            if candidate.get("teams") != sorted(teams) or candidate.get("games") != sorted(games):
                problems.append(f"CLASSIC_C3_CANDIDATE_SCOPE_MISMATCH:{authorization.entry_id}")
            lineup_score = sum(score_map.get(dk_id, 0.0) for dk_id in roster)
            selected_lineup = selection_lineups.get(roster)
            if selected_lineup is None:
                problems.append(f"CLASSIC_C3_SELECTION_ROSTER_MISSING:{authorization.entry_id}")
            else:
                if selected_lineup.get("salary") != valid.lineup.salary:
                    problems.append(f"CLASSIC_C3_SELECTION_SALARY_MISMATCH:{authorization.entry_id}")
                if selected_lineup.get("canonical_key") != valid.lineup.canonical_key:
                    problems.append(f"CLASSIC_C3_SELECTION_CANONICAL_MISMATCH:{authorization.entry_id}")
                if abs(float(selected_lineup.get("prior_points", math.inf)) - lineup_score) > 0.0000015:
                    problems.append(f"CLASSIC_C3_SELECTION_SCORE_MISMATCH:{authorization.entry_id}")
            slots: list[dict[str, object]] = []
            for slot, player in zip(CLASSIC_COLUMNS, rows, strict=True):
                role = role_facts.get(player.underlying_id)
                slots.append(
                    {
                        "slot": slot,
                        "name": player.name,
                        "dk_roster_id": player.dk_id,
                        "underlying_person_id": player.underlying_id,
                        "team": player.team,
                        "opponent": player.opponent,
                        "game_id": player.game_id,
                        "position": player.position,
                        "salary": player.salary,
                        "prior_only_central_estimate_points": round(score_map.get(player.dk_id, 0.0), 6),
                        "official_activity": statuses.get(player.dk_id),
                        "official_observed_at": (
                            observed_by_id[player.dk_id].isoformat()
                            if player.dk_id in observed_by_id
                            else None
                        ),
                        "official_source": source_by_id.get(player.dk_id),
                        "salary_status_raw": player.status_raw or "BLANK_NOT_OFFICIAL_ACTIVITY",
                        "role_evidence_state": (
                            role.get("state") if role else "NOT_APPLICABLE_DST"
                        ),
                        "role_findings": [role] if role else [],
                    }
                )
            entries_payload.append(
                {
                    "entry_id": authorization.entry_id,
                    "contest_id": authorization.contest_id,
                    "contest_name": authorization.contest_name or None,
                    "entry_fee": authorization.entry_fee,
                    "slots": slots,
                    "salary_total": valid.lineup.salary,
                    "salary_remaining": slate.salary_cap - valid.lineup.salary,
                    "prior_only_central_estimate_points": round(lineup_score, 6),
                    "canonical_key": valid.lineup.canonical_key,
                    "teams": sorted(teams),
                    "games": sorted(games),
                    "group_matches": group_matches,
                    "stack_values": stack_values,
                }
            )

        if policy.require_unique_lineups and len(set(canonical_by_entry.values())) != len(entry_ids):
            problems.append("CLASSIC_C3_CANONICAL_LINEUP_DUPLICATE")
        pairwise: list[dict[str, object]] = []
        for left_index, left in enumerate(entry_ids):
            for right in entry_ids[left_index + 1 :]:
                overlap = len(people_by_entry.get(left, frozenset()) & people_by_entry.get(right, frozenset()))
                pairwise.append(
                    {
                        "entry_id_a": left,
                        "entry_id_b": right,
                        "actual_people": overlap,
                        "maximum_people": policy.max_pairwise_person_overlap,
                    }
                )
                if overlap > policy.max_pairwise_person_overlap:
                    problems.append(f"CLASSIC_C3_PAIRWISE_OVERLAP_EXCEEDED:{left}:{right}:{overlap}")

        def check_bounds(kind: str, bounds, counts: Counter[str]) -> list[dict[str, object]]:
            rows: list[dict[str, object]] = []
            for bound in bounds:
                actual = counts[bound.entity_id]
                if not bound.minimum_entries <= actual <= bound.maximum_entries:
                    problems.append(
                        f"CLASSIC_C3_{kind}_BOUND:{bound.entity_id}:{actual}:"
                        f"expected={bound.minimum_entries}..{bound.maximum_entries}"
                    )
                rows.append(
                    {
                        "id": bound.entity_id,
                        "actual_count": actual,
                        "minimum_count": bound.minimum_entries,
                        "maximum_count": bound.maximum_entries,
                        "exclusion_source": bound.exclusion_source,
                    }
                )
            return rows

        player_rows = check_bounds("PLAYER", policy.player_bounds, player_counts)
        team_rows = check_bounds("TEAM", policy.team_bounds, team_counts)
        game_rows = check_bounds("GAME", policy.game_bounds, game_counts)
        group_rows: list[dict[str, object]] = []
        for rule in policy.groups:
            actual = group_counts[rule.group_id]
            if rule.hard and not rule.minimum_entries <= actual <= rule.maximum_entries:
                problems.append(f"CLASSIC_C3_GROUP_BOUND:{rule.group_id}:{actual}")
            group_rows.append(
                {
                    "id": rule.group_id,
                    "strength": rule.strength,
                    "actual_count": actual,
                    "minimum_count": rule.minimum_entries,
                    "maximum_count": rule.maximum_entries,
                    "minimum_players": rule.minimum_players,
                    "maximum_players": rule.maximum_players,
                }
            )
        stack_rows: list[dict[str, object]] = []
        for rule in policy.stack_rules:
            actual = stack_counts[rule.rule_id]
            if rule.hard and not rule.minimum_entries <= actual <= rule.maximum_entries:
                problems.append(f"CLASSIC_C3_STACK_BOUND:{rule.rule_id}:{actual}")
            stack_rows.append(
                {
                    "id": rule.rule_id,
                    "rule_type": rule.rule_type,
                    "strength": rule.strength,
                    "actual_count": actual,
                    "minimum_count": rule.minimum_entries,
                    "maximum_count": rule.maximum_entries,
                    "minimum_value": rule.minimum_value,
                    "maximum_value": rule.maximum_value,
                }
            )
        for person in policy.exact_exclusions:
            if player_counts[person]:
                problems.append(f"CLASSIC_C3_EXACT_EXCLUSION_SELECTED:{person}")

        c2_hashes = _mapping(c2_audit.get("hashes"), label="C2_AUDIT_HASHES")
        for label, recorded_digest in sorted(c2_hashes.items()):
            artifact_name = _C2_AUDIT_HASH_ARTIFACTS.get(label)
            if artifact_name is None and label.endswith("_sha256"):
                artifact_name = label.removesuffix("_sha256")
            if artifact_name is None or artifact_name not in actual_hash:
                problems.append(f"CLASSIC_C3_C2_AUDIT_HASH_SOURCE_MISSING:{label}")
            elif recorded_digest != actual_hash[artifact_name]:
                problems.append(f"CLASSIC_C3_C2_AUDIT_HASH_DISAGREEMENT:{label}")
        expected_c2_maps = {
            "canonical_lineups": canonical_by_entry,
            "player_counts": dict(sorted(player_counts.items())),
            "team_counts": dict(sorted(team_counts.items())),
            "game_counts": dict(sorted(game_counts.items())),
            "group_counts": {
                rule.group_id: group_counts[rule.group_id] for rule in policy.groups
            },
            "stack_counts": {
                rule.rule_id: stack_counts[rule.rule_id] for rule in policy.stack_rules
            },
        }
        for label, recomputed in expected_c2_maps.items():
            if c2_audit.get(label) != recomputed:
                problems.append(f"CLASSIC_C3_C2_AUDIT_SEMANTIC_DISAGREEMENT:{label}")
        c2_overlap = [
            {"entry_id_a": row["entry_id_a"], "entry_id_b": row["entry_id_b"], "people": row["actual_people"]}
            for row in pairwise
        ]
        if c2_audit.get("pairwise_person_overlap") != c2_overlap:
            problems.append("CLASSIC_C3_C2_AUDIT_SEMANTIC_DISAGREEMENT:pairwise_overlap")

        selection_pairs = tuple(
            (
                str(_mapping(raw, label="SELECTION_ENTRY_ASSIGNMENT").get("entry_id", "")),
                tuple(
                    str(value)
                    for value in _sequence(
                        _mapping(raw, label="SELECTION_ENTRY_ASSIGNMENT").get("roster"),
                        label="SELECTION_ENTRY_ROSTER",
                    )
                ),
            )
            for raw in _sequence(selection.get("entry_assignments"), label="SELECTION_ENTRY_ASSIGNMENTS")
        )
        if selection_pairs != tuple(pairs):
            problems.append("CLASSIC_C3_SELECTION_ASSIGNMENT_DISAGREEMENT")
        selection_assignment_map = _mapping(
            selection.get("assignments_by_entry_id"), label="SELECTION_ASSIGNMENT_MAP"
        )
        if selection_assignment_map != {
            entry_id: list(roster) for entry_id, roster in sorted(assignments.items())
        }:
            problems.append("CLASSIC_C3_SELECTION_ASSIGNMENT_MAP_DISAGREEMENT")

        proposed = write_upload_bytes(template, assignments)
        problems.extend(
            _audit_template_bytes(
                source_bytes=entry_file.read_bytes(),
                output_bytes=proposed,
                encoding=template.encoding,
                roster_start=template.roster_start_index,
                roster_width=len(template.roster_columns),
                assignments=assignments,
            )
        )
        try:
            reparsed_output = parse_entry_bytes(proposed, source_name=str(export_file))
            reconcile_template(reparsed_output, slate)
        except Exception as exc:  # noqa: BLE001 - proposed bytes must fail closed
            reparsed_output = None
            problems.append(
                f"CLASSIC_C3_PROPOSED_OUTPUT_REPARSE_FAILED:{type(exc).__name__}:{exc}"
            )
        if reparsed_output is not None:
            if tuple(item.entry_id for item in reparsed_output.authorizations) != entry_ids:
                problems.append("CLASSIC_C3_PROPOSED_OUTPUT_ENTRY_ORDER_MISMATCH")
            if {
                item.entry_id: item.existing_cells for item in reparsed_output.authorizations
            } != assignments:
                problems.append("CLASSIC_C3_PROPOSED_OUTPUT_ASSIGNMENT_MISMATCH")
        if problems:
            raise ClassicReviewError(";".join(problems))
        # What a limit left unproven travels with the file (Session 08). The
        # codes are the ones `run-slate` reports; neither is ever called optimal.
        limit_notes: list[str] = []
        if bank.get("status") in {"BOUNDED_TIME_LIMIT_STOP", "BOUNDED_SEARCH_LIMIT_STOP"}:
            limit_notes.append(
                f"CANDIDATE_BANK_STOPPED_AT_LIMIT:{bank.get('status')}:"
                f"{produced_candidates}_of_{requested_candidates}_candidates"
            )
        if joint_status == "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK":
            limit_notes.append(
                "PORTFOLIO_SELECTION_LIMIT_INCUMBENT:FEASIBLE_UNDER_EVERY_POLICY_BOUND_NOT_PROVEN_OPTIMAL"
            )
        # Missing activity travels with the file under the code `run-slate`
        # names (Session 09); it is never reported as a pass.
        if activity_missing:
            limit_notes.append(
                (
                    "OFFICIAL_STATUS_REQUIRED:NO_OFFICIAL_STATUS_FILE_SUPPLIED"
                    if status_path is None
                    else "OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED:NO_EXACT_ID_ROW_IN_SUPPLIED_FILE"
                )
                + f":{len(activity_missing)}_of_{len(selected_people)}_selected_people"
            )

        pre_export_hashes = _hash_checkpoint("PRE_EXPORT", tracked, expected)
        export_sha = sha256_bytes(proposed)
        if _atomic_write(export_file, proposed) != export_sha:
            raise ClassicReviewError("CLASSIC_C3_EXPORT_PARTIAL_OR_WRITE_HASH_MISMATCH")
        created.append(export_file)
        post_write_hashes = _hash_checkpoint("POST_WRITE", tracked, expected)
        if sha256_file(export_file) != export_sha:
            raise ClassicReviewError("CLASSIC_C3_EXPORT_POST_WRITE_SHA256_MISMATCH")
        if export_file.name.startswith("DK_UPLOAD_"):
            raise ClassicReviewError("CLASSIC_C3_DK_UPLOAD_NAME_PROHIBITED")

        audit_record: dict[str, object] = {
            "schema_version": AUDIT_VERSION,
            "status": "PASS",
            "passed": True,
            "problems": [],
            "mode": "CLASSIC",
            "entry_ids": list(entry_ids),
            "truths": {
                "FILE_VALID": True,
                "EVIDENCE_STATE": selection.get("EVIDENCE_STATE", "UNKNOWN"),
                "MODEL_STATUS": "PRIOR_ONLY",
                "RELEASE_DECISION": "DO_NOT_UPLOAD",
            },
            "hash_checkpoints": {
                "intake": intake_hashes,
                "immediately_before_export": pre_export_hashes,
                "after_final_write": {**post_write_hashes, "bulk_entry_csv": export_sha},
            },
            "output": {
                "path": export_file.name,
                "sha256": export_sha,
                "entries": len(entry_ids),
                "roster_cells_rewritten_per_entry": 9,
                "unchanged_non_roster_bytes": True,
            },
            "candidate_bank": {
                "status": bank.get("status"),
                "exhaustive": bank.get("exhaustive"),
                "requested_candidates": requested_candidates,
                "produced_candidates": produced_candidates,
                "canonical_unique_candidates": bank.get("canonical_unique_candidates"),
                "coverage": bank.get("coverage"),
                "policy_feasible_chain_status": bank.get("policy_feasible_chain_status"),
                "search_scope": bank.get("search_scope"),
            },
            "joint_selection": {
                "status": joint_status,
                "optimality_scope": enforcement.get("optimality_scope"),
                "c2_audit_status": c2_audit.get("status"),
            },
            "recomputed": {
                "canonical_lineups": canonical_by_entry,
                "player_counts": dict(sorted(player_counts.items())),
                "team_counts": dict(sorted(team_counts.items())),
                "game_counts": dict(sorted(game_counts.items())),
                "group_counts": expected_c2_maps["group_counts"],
                "stack_counts": expected_c2_maps["stack_counts"],
                "pairwise_person_overlap": pairwise,
                "selected_activity": "INCOMPLETE" if activity_missing else "PASS",
                "selected_activity_without_row": activity_missing,
                "selected_current_roles": "PASS",
            },
            "checks_run": [
                "STRICT_IMMUTABLE_SALARY_AND_ENTRY_REPARSE",
                "SOURCE_AND_CANONICAL_NORMALIZED_POLICY_REPARSE",
                "CANDIDATE_ASSIGNMENT_C2_AUDIT_SELECTION_COVERAGE_REPARSE",
                "COMPLETE_MODE_DRAFT_GROUP_GAME_TEAM_PERSON_POSITION_SLOT_IDENTITY",
                "EVERY_SELECTED_LINEUP_ELIGIBILITY_SALARY_TWO_GAME_RULE",
                "ALL_HARD_PLAYER_TEAM_GAME_GROUP_STACK_COUNTS",
                "EXACT_EXCLUSIONS_CANONICAL_UNIQUENESS_ALL_PAIRWISE_OVERLAPS",
                (
                    "SELECTED_CURRENT_ROLE_EVIDENCE_AND_NO_SELECTED_NON_ACTIVE_ROW"
                    if activity_missing
                    else "SELECTED_CURRENT_ACTIVITY_AND_ROLE_EVIDENCE"
                ),
                "BLANK_CELL_AUTHORITY_AND_UNCHANGED_NON_ROSTER_TEMPLATE_BYTES",
                "PROPOSED_OUTPUT_REPARSE_SHA256_AND_POST_WRITE_REPARSE",
            ],
            "limitations": [
                "BOUNDED_CANDIDATE_BANK_NOT_FULL_SLATE_OPTIMALITY",
                "PRIOR_ONLY_CENTRAL_ESTIMATE_NOT_CEILING_LEVERAGE_EV_ROI_WIN_OR_CASH_PROBABILITY",
                "NO_OWNERSHIP_FIELD_DUPLICATION_PAYOUT_OR_ECONOMICS",
                "REVIEW_CSV_NOT_CERTIFIED_AND_NOT_UPLOAD_AUTHORIZATION",
                *limit_notes,
            ],
            "next_action": next_action,
        }
        audit_payload = _canonical_json_bytes(audit_record)
        audit_sha = sha256_bytes(audit_payload)
        if _atomic_write(audit_file, audit_payload) != audit_sha:
            raise ClassicReviewError("CLASSIC_C3_AUDIT_WRITE_MISMATCH")
        created.append(audit_file)

        pre_render_paths = {**tracked, "bulk_entry_csv": export_file, "classic_export_audit": audit_file}
        pre_render_expected = {**expected, "bulk_entry_csv": export_sha, "classic_export_audit": audit_sha}
        pre_render_hashes = _hash_checkpoint("PRE_RENDER", pre_render_paths, pre_render_expected)

        # R28 (Session 05): from here to the readable post-write check is
        # presentation. A failure in it keeps the export and its audit, once
        # `_verify_kept_export` passes them again, and removes only the JSON and HTML.
        presenting = True
        denominator = len(entry_ids)
        display_by_person = {row.underlying_id: row for row in slate.players}
        for row in player_rows:
            person = str(row["id"])
            player = display_by_person[person]
            row.update(
                {
                    "underlying_person_id": person,
                    "name": player.name,
                    "team": player.team,
                    "position": player.position,
                    "actual_percentage": round(100 * int(row["actual_count"]) / denominator, 3),
                    "minimum_percentage": round(100 * int(row["minimum_count"]) / denominator, 3),
                    "maximum_percentage": round(100 * int(row["maximum_count"]) / denominator, 3),
                    "excluded": person in policy.exact_exclusions,
                }
            )
        review_paths = {**pre_render_paths}
        review_hashes = {**pre_render_hashes}
        portable_rows = _portable_artifacts(
            review_paths, review_hashes, package_root=package, html_root=review_root
        )
        data: dict[str, object] = {
            "schema_version": READABLE_VERSION,
            "mode": "CLASSIC",
            "status": "PRIOR_ONLY_REVIEW",
            "truths": audit_record["truths"],
            "warning": (
                "PRIOR_ONLY central estimates and a bounded actual candidate bank. "
                "This exact-template CSV is a review artifact, not a certified upload file."
            ),
            "next_action": next_action,
            "blockers": list(blockers),
            "limitations": audit_record["limitations"],
            "reconciliation": {
                "status": "PASS",
                "basis": "INDEPENDENT_EXACT_BYTE_REPARSE_AND_RECOMPUTATION_C3",
                "entry_count": denominator,
                "problems": [],
            },
            "portfolio_scope": {
                "candidate_bank": audit_record["candidate_bank"],
                "joint_selection": audit_record["joint_selection"],
                "downstream_export_audit": "PASS",
            },
            "entries": entries_payload,
            "exposure": {
                "entry_count_denominator": denominator,
                "people": player_rows,
                "teams": team_rows,
                "games": game_rows,
                "groups": group_rows,
                "stack_rules": stack_rows,
                "canonical_uniqueness": "PASS",
                "unique_required": policy.require_unique_lineups,
                "canonical_lineups": canonical_by_entry,
                "configured_pairwise_person_overlap": policy.max_pairwise_person_overlap,
                "effective_pairwise_person_overlap": policy.max_pairwise_person_overlap,
                "pairwise_overlap": pairwise,
            },
            "pool_coverage": coverage.get("pool_coverage"),
            "evidence_observations": [
                {
                    "category": "SELECTED_OFFICIAL_ACTIVITY",
                    "state": "UNKNOWN" if activity_missing else "PASS",
                    "observation": (
                        f"{len(selected_people) - len(activity_missing)} of {len(selected_people)}"
                        " selected people have exact ACTIVE rows"
                        + (
                            f"; {len(activity_missing)} have no row: {', '.join(activity_missing)}"
                            if activity_missing
                            else ""
                        )
                    ),
                    "observed_at": min(
                        (observed_by_id[dk_id] for dk_id in selected_ids if dk_id in observed_by_id),
                        default=None,
                    ).isoformat()
                    if any(dk_id in observed_by_id for dk_id in selected_ids)
                    else None,
                    "expires_at": None,
                    "source": sorted({source_by_id[dk_id] for dk_id in selected_ids if dk_id in source_by_id}),
                    "next_action": (
                        "Capture a fresh exact-ID ACTIVE or INACTIVE row for each person named, and refresh near lock."
                        if activity_missing
                        else "Refresh official activity near lock."
                    ),
                },
                {
                    "category": "SELECTED_CURRENT_OFFENSIVE_ROLE",
                    "state": "UNKNOWN" if history_derived_people else "PASS",
                    "observation": (
                        f"{len(role_facts)} selected offensive people have source-supported"
                        f" numerical allocations; {len(history_derived_people)} rest on a"
                        " prior-season history prior, which is not a current role"
                    ),
                    "history_derived_people": history_derived_people,
                    "observed_at": sorted({str(item.get('observed_at')) for item in role_facts.values()}),
                    "expires_at": sorted({str(item.get('expires_at')) for item in role_facts.values()}),
                    "source": sorted({str(item.get('source_uri')) for item in role_facts.values()}),
                    "next_action": (
                        "Capture a numerical current-team allocation for any person whose role"
                        " you doubt; refresh any existing allocation when its source expires."
                        if history_derived_people
                        else "Refresh any role allocation when its source expires or the role changes."
                    ),
                },
            ],
            "artifacts": portable_rows,
            "hashes": dict(sorted(review_hashes.items())),
            "hash_checkpoints": {
                **audit_record["hash_checkpoints"],
                "before_review_rendering": pre_render_hashes,
            },
        }
        json_payload = _canonical_json_bytes(data)
        json_sha = sha256_bytes(json_payload)
        html_payload = _render_html(data, data_sha256=json_sha)
        html_sha = sha256_bytes(html_payload)
        if _atomic_write(json_file, json_payload) != json_sha:
            raise ClassicReviewError("CLASSIC_C3_READABLE_JSON_WRITE_MISMATCH")
        created.append(json_file)
        if _atomic_write(html_file, html_payload) != html_sha:
            raise ClassicReviewError("CLASSIC_C3_READABLE_HTML_WRITE_MISMATCH")
        created.append(html_file)
        if sha256_file(json_file) != json_sha or sha256_file(html_file) != html_sha:
            raise ClassicReviewError("CLASSIC_C3_READABLE_POST_WRITE_MISMATCH")
        presenting = False
        _verify_kept_export(export_file, export_sha, audit_file, audit_sha, reparsed_output)
        return ClassicReviewArtifacts(
            data=data,
            audit=audit_record,
            audit_path=str(audit_file),
            audit_sha256=audit_sha,
            export_path=str(export_file),
            export_sha256=export_sha,
            json_path=str(json_file),
            json_sha256=json_sha,
            html_path=str(html_file),
            html_sha256=html_sha,
        )
    except Exception as exc:
        if presenting:
            try:
                _verify_kept_export(export_file, export_sha, audit_file, audit_sha, reparsed_output)
            except Exception as integrity:  # noqa: BLE001 - an unverifiable export is not kept
                _safe_remove_created((*created, *new_files))
                raise integrity from exc
            _safe_remove_created((json_file, html_file))
            kept = {
                "export_path": str(export_file),
                "export_sha256": export_sha,
                "audit_path": str(audit_file),
                "audit_sha256": audit_sha,
                "audit": audit_record,
            }
            if isinstance(exc, ClassicReviewError):
                raise ClassicReviewPresentationError(str(exc), **kept) from exc
            raise ClassicReviewPresentationError(
                f"CLASSIC_C3_READABLE_RENDER_FAILED:{type(exc).__name__}:{exc}", **kept
            ) from exc
        _safe_remove_created((*created, *new_files))
        raise
