"""SD5 readable review bound to exact prior-review artifacts.

This module is a presentation boundary, not a selector or release gate. It
independently reparses the exact salary, entry, assignment, normalized-policy,
audit and exported CSV bytes before constructing any readable summary. A
discrepancy raises a named error and no passed readable artifact is published.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .dk import EntryTemplate, parse_entries, parse_entry_bytes, parse_salaries
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup


READABLE_REVIEW_VERSION = "prior_only_readable_review_sd5_v1"
_ASSIGNMENT_HEADER = ("Entry ID", "CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")


class ReadableReviewError(ValueError):
    """A named fail-closed display reconciliation error."""


@dataclass(frozen=True)
class ReadableReviewArtifacts:
    data: dict[str, object]
    json_path: str
    json_sha256: str
    html_path: str
    html_sha256: str


def _problem(code: str, detail: object) -> str:
    return f"{code}:{detail}"


def _strict_assignments(raw: bytes) -> tuple[tuple[str, tuple[str, ...]], ...]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReadableReviewError(
            _problem("READABLE_REVIEW_ASSIGNMENT_ENCODING_INVALID", exc)
        ) from exc
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise ReadableReviewError(
            _problem("READABLE_REVIEW_ASSIGNMENT_CSV_INVALID", exc)
        ) from exc
    if not rows or tuple(rows[0]) != _ASSIGNMENT_HEADER:
        raise ReadableReviewError("READABLE_REVIEW_ASSIGNMENT_HEADER_MISMATCH")
    parsed: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) != 7:
            raise ReadableReviewError(
                _problem("READABLE_REVIEW_ASSIGNMENT_WIDTH", f"row={row_number}:width={len(row)}")
            )
        entry_id = row[0]
        roster = tuple(row[1:])
        if not entry_id.isdigit() or entry_id in seen:
            raise ReadableReviewError(
                _problem("READABLE_REVIEW_ASSIGNMENT_ENTRY_ID_INVALID", f"row={row_number}:entry={entry_id!r}")
            )
        if any(not dk_id.isdigit() for dk_id in roster):
            raise ReadableReviewError(
                _problem("READABLE_REVIEW_ASSIGNMENT_DK_ID_INVALID", f"row={row_number}")
            )
        seen.add(entry_id)
        parsed.append((entry_id, roster))
    return tuple(parsed)


def _mapping(value: object, label: str, problems: list[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        problems.append(_problem("READABLE_REVIEW_MAPPING_REQUIRED", label))
        return {}
    return value


def _sequence(value: object, label: str, problems: list[str]) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        problems.append(_problem("READABLE_REVIEW_LIST_REQUIRED", label))
        return ()
    return value


def _portable_path(path: Path, package_root: Path) -> tuple[str, str | None]:
    try:
        relative = path.resolve().relative_to(package_root.resolve()).as_posix()
        return relative, relative
    except ValueError:
        return path.name, None


def _artifact_expected_hash(
    name: str, path: Path, expected_hashes: Mapping[str, str]
) -> str | None:
    direct = expected_hashes.get(name)
    if direct:
        return str(direct)
    aliases = {
        "team_source": f"prior:{path.name}",
        "player_source": f"prior:{path.name}",
        "identity_map": f"prior:{path.name}",
        "team_splits": "frozen:team_stats",
        "team_projections": "projected:team_projections",
        "player_opportunities": "projected:player_opportunities",
        "source_ledger": "projected:source_ledger",
    }
    alias = aliases.get(name)
    return str(expected_hashes[alias]) if alias and alias in expected_hashes else None


def _read_json_record(
    path: Path, *, expected_sha256: str | None, label: str, problems: list[str]
) -> Mapping[str, object]:
    if not path.is_file():
        problems.append(_problem(f"READABLE_REVIEW_{label}_MISSING", path))
        return {}
    actual = sha256_file(path)
    if expected_sha256 and actual != expected_sha256:
        problems.append(
            _problem(
                f"READABLE_REVIEW_{label}_SHA256_MISMATCH",
                f"actual={actual}:expected={expected_sha256}",
            )
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(_problem(f"READABLE_REVIEW_{label}_INVALID", f"{type(exc).__name__}:{exc}"))
        return {}
    return _mapping(payload, label, problems)


def _parse_normalized_policy(
    path: Path,
    *,
    expected_sha256: str,
    expected_entries: tuple[str, ...],
    salary_sha256: str,
    game_id: str,
    person_bindings: Mapping[str, tuple[str, str]],
    problems: list[str],
) -> dict[str, object]:
    actual = sha256_file(path) if path.is_file() else "MISSING"
    if actual != expected_sha256:
        problems.append(
            _problem(
                "READABLE_REVIEW_NORMALIZED_POLICY_SHA256_MISMATCH",
                f"actual={actual}:expected={expected_sha256}",
            )
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(
            _problem("READABLE_REVIEW_NORMALIZED_POLICY_INVALID", f"{type(exc).__name__}:{exc}")
        )
        return {}
    root = _mapping(payload, "normalized_policy", problems)
    if root.get("schema_version") != "nfl_showdown_portfolio_policy_normalized_v1":
        problems.append("READABLE_REVIEW_NORMALIZED_POLICY_SCHEMA_MISMATCH")
    bindings = _mapping(root.get("bindings"), "normalized_policy.bindings", problems)
    policy_entries = tuple(str(value) for value in _sequence(bindings.get("entry_ids"), "policy.entry_ids", problems))
    if policy_entries != expected_entries:
        problems.append(
            _problem(
                "READABLE_REVIEW_POLICY_ENTRY_ID_ORDER_MISMATCH",
                f"actual={policy_entries}:expected={expected_entries}",
            )
        )
    if bindings.get("salary_sha256") != salary_sha256:
        problems.append("READABLE_REVIEW_POLICY_SALARY_BINDING_MISMATCH")
    if bindings.get("game_id") != game_id:
        problems.append("READABLE_REVIEW_POLICY_GAME_BINDING_MISMATCH")
    bound_people: dict[str, tuple[str, str]] = {}
    for raw in _sequence(bindings.get("person_identities"), "policy.person_identities", problems):
        row = _mapping(raw, "policy.person_identity", problems)
        person = str(row.get("underlying_id", ""))
        if not person or person in bound_people:
            problems.append(_problem("READABLE_REVIEW_POLICY_PERSON_BINDING_INVALID", person))
            continue
        bound_people[person] = (str(row.get("cpt_dk_id", "")), str(row.get("flex_dk_id", "")))
    if bound_people != dict(person_bindings):
        problems.append("READABLE_REVIEW_POLICY_PERSON_BINDINGS_MISMATCH")
    controls = _mapping(root.get("controls"), "normalized_policy.controls", problems)
    effective = _mapping(root.get("effective"), "normalized_policy.effective", problems)
    if effective.get("entry_count_denominator") != len(expected_entries):
        problems.append("READABLE_REVIEW_POLICY_DENOMINATOR_MISMATCH")
    limit_rows: dict[str, dict[str, object]] = {}
    for raw in _sequence(effective.get("people"), "normalized_policy.effective.people", problems):
        row = dict(_mapping(raw, "normalized_policy.effective.person", problems))
        person = str(row.get("underlying_id", ""))
        if not person or person in limit_rows:
            problems.append(_problem("READABLE_REVIEW_POLICY_PERSON_INVALID", person))
            continue
        for label in ("combined_max_entries", "captain_max_entries"):
            value = row.get(label)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                or value > len(expected_entries)
            ):
                problems.append(_problem("READABLE_REVIEW_POLICY_LIMIT_INVALID", f"person={person}:field={label}"))
        limit_rows[person] = row
    if set(limit_rows) != set(person_bindings):
        problems.append("READABLE_REVIEW_POLICY_EFFECTIVE_PEOPLE_MISMATCH")
    return {
        "entry_ids": policy_entries,
        "limits": limit_rows,
        "max_pairwise_person_overlap": controls.get("max_pairwise_person_overlap"),
        "effective_pairwise_person_overlap": controls.get("effective_pairwise_person_overlap"),
        "require_unique_lineups": controls.get("require_unique_lineups"),
    }


def _role_findings(selection_record: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    selector = selection_record.get("selection")
    if not isinstance(selector, Mapping):
        return by_person
    offensive = selector.get("offensive_roles")
    if isinstance(offensive, Mapping):
        for raw in offensive.get("findings", []):
            if isinstance(raw, Mapping) and raw.get("person"):
                by_person[str(raw["person"])].append(
                    {
                        "finding": raw.get("finding"),
                        "state": raw.get("state"),
                        "selection_action": raw.get("selection_action"),
                        "next_evidence_action": raw.get("next_evidence_action"),
                    }
                )
    return by_person


def _source_observations(
    reports: Mapping[str, object], selection_record: Mapping[str, object]
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for name in ("prior_package", "projection", "weather", "official_status"):
        raw = reports.get(name)
        if not isinstance(raw, Mapping):
            if name == "official_status":
                observations.append(
                    {
                        "category": "official_activity",
                        "state": "MISSING",
                        "observation": "No current official activity artifact was supplied.",
                        "observed_at": None,
                        "expires_at": None,
                        "source": None,
                    }
                )
            continue
        observations.append(
            {
                "category": name,
                "state": raw.get("freshness_state", raw.get("scope", "RECORDED")),
                "observation": (
                    {
                        "statuses": raw.get("statuses", {}),
                        "inactive_dk_ids": raw.get("inactive_dk_ids", []),
                        "scope": raw.get("scope"),
                    }
                    if name == "official_status"
                    else raw.get("basis", raw.get("expiry_basis", raw.get("scope", "RECORDED")))
                ),
                "observed_at": raw.get("observed_at"),
                "expires_at": raw.get("expires_at"),
                "source": raw.get("source_uri", raw.get("source_urls")),
            }
        )
    selector = selection_record.get("selection")
    if isinstance(selector, Mapping):
        for label in ("threshold_sensitive", "score_omissions"):
            for item in selector.get(label, []):
                observations.append(
                    {
                        "category": label,
                        "state": "PRIOR_ONLY_LIMITATION",
                        "observation": item,
                        "observed_at": None,
                        "expires_at": None,
                        "source": None,
                    }
                )
        offensive = selector.get("offensive_roles")
        if isinstance(offensive, Mapping):
            for raw in offensive.get("findings", []):
                if isinstance(raw, Mapping):
                    observations.append(
                        {
                            "category": "offensive_role",
                            "state": raw.get("state"),
                            "observation": f"{raw.get('person', '')}: {raw.get('finding', '')}",
                            "observed_at": None,
                            "expires_at": None,
                            "source": None,
                            "next_action": raw.get("next_evidence_action"),
                        }
                    )
    return observations


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return sha256_file(path)


def _escape(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return html.escape(str(value), quote=True)


def _html_table(headers: Sequence[str], rows: Iterable[Sequence[object]], css_class: str = "") -> str:
    head = "".join(f"<th>{_escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<table class="{_escape(css_class)}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _render_html(data: Mapping[str, object], *, data_sha256: str) -> bytes:
    truths = _mapping(data.get("truths"), "truths", [])
    entries = _sequence(data.get("entries"), "entries", [])
    exposure = _mapping(data.get("exposure"), "exposure", [])
    sections: list[str] = [
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Prior-only lineup review</title>",
        "<style>@page{size:landscape;margin:10mm}body{font-family:Aptos,Arial,sans-serif;color:#17223b;margin:24px}"
        "h1,h2,h3{color:#17324d;margin-bottom:8px}.warning{background:#fce4d6;border:2px solid #c00000;padding:12px;font-weight:700}"
        ".next{background:#fff2cc;border-left:5px solid #bf8f00;padding:10px}.truths{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}"
        ".truth{border:1px solid #9fbad0;padding:9px;background:#eef5fa}.truth b{display:block;font-size:11px}.pass{color:#006100;font-weight:700}"
        "table{width:100%;border-collapse:collapse;margin:8px 0 20px;font-size:11px;page-break-inside:auto}thead{display:table-header-group}"
        "th{background:#2f75b5;color:white;text-align:left;padding:6px}td{border:1px solid #ccd6df;padding:5px;vertical-align:top;overflow-wrap:anywhere}"
        "tr{page-break-inside:avoid}.entry{page-break-before:auto}.small{font-size:10px;color:#555}.money{text-align:right}</style></head><body>",
        "<h1>DraftKings NFL Showdown — prior-only lineup review</h1>",
        f'<div class="warning">{_escape(data.get("warning"))}</div>',
        '<div class="truths">',
    ]
    for label in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION"):
        sections.append(f'<div class="truth"><b>{_escape(label)}</b>{_escape(truths.get(label))}</div>')
    sections.extend(
        [
            "</div>",
            f'<p><b>Display reconciliation:</b> <span class="pass">{_escape(_mapping(data.get("reconciliation"), "reconciliation", []).get("status"))}</span></p>',
            f'<p class="next"><b>Next operator action:</b> {_escape(data.get("next_action"))}</p>',
            f'<p class="small">Readable review data SHA-256: {_escape(data_sha256)}</p>',
            "<h2>Exact entry assignments</h2>",
        ]
    )
    for raw_entry in entries:
        entry = _mapping(raw_entry, "entry", [])
        sections.append(
            f'<section class="entry"><h3>Entry {_escape(entry.get("entry_id"))} — {_escape(entry.get("contest_name") or "Contest label unavailable")}</h3>'
            f'<p>Contest ID {_escape(entry.get("contest_id"))} · Salary ${_escape(entry.get("salary_total"))} · Remaining ${_escape(entry.get("salary_remaining"))} · '
            f'PRIOR_ONLY central estimate {_escape(entry.get("prior_only_central_estimate_points"))} points</p>'
        )
        slot_rows = []
        for raw_slot in _sequence(entry.get("slots"), "entry.slots", []):
            slot = _mapping(raw_slot, "slot", [])
            findings = "; ".join(
                str(item.get("finding", ""))
                for item in _sequence(slot.get("role_findings"), "slot.role_findings", [])
                if isinstance(item, Mapping)
            )
            slot_rows.append(
                (
                    slot.get("slot"), slot.get("name"), slot.get("dk_roster_id"),
                    slot.get("underlying_person_id"), slot.get("team"), slot.get("salary"),
                    slot.get("prior_only_central_estimate_points"), slot.get("official_activity"),
                    slot.get("role_evidence_state"), findings,
                )
            )
        sections.append(
            _html_table(
                ("Slot", "Player", "Exact DK roster ID", "Underlying person ID", "Team", "Salary", "Prior-only points", "Official activity", "Role evidence", "Concerns"),
                slot_rows,
            )
        )
        sections.append("</section>")
    sections.append("<h2>Actual audited exposure</h2>")
    exposure_rows = []
    for raw in _sequence(exposure.get("people"), "exposure.people", []):
        row = _mapping(raw, "exposure.person", [])
        exposure_rows.append(
            (
                row.get("name"), row.get("underlying_person_id"), row.get("combined_count"),
                row.get("combined_percentage"), row.get("combined_max_count"), row.get("combined_max_percentage"),
                row.get("captain_count"), row.get("captain_percentage"), row.get("captain_max_count"),
                row.get("captain_max_percentage"), row.get("excluded"), row.get("exclusion_source"),
            )
        )
    sections.append(
        _html_table(
            ("Player", "Person ID", "Combined #", "Combined %", "Combined max #", "Combined max %", "Captain #", "Captain %", "Captain max #", "Captain max %", "Excluded", "Basis"),
            exposure_rows,
        )
    )
    sections.append(
        f'<p>Canonical uniqueness: {_escape(exposure.get("canonical_uniqueness"))}. '
        f'Configured/effective overlap maximum: {_escape(exposure.get("configured_pairwise_person_overlap"))} / {_escape(exposure.get("effective_pairwise_person_overlap"))}.</p>'
    )
    overlap_rows = [
        (row.get("entry_id_a"), row.get("entry_id_b"), row.get("actual_people"), row.get("maximum_people"))
        for row in _sequence(exposure.get("pairwise_overlap"), "exposure.pairwise_overlap", [])
        if isinstance(row, Mapping)
    ]
    sections.append(_html_table(("Entry A", "Entry B", "Actual shared people", "Maximum"), overlap_rows))
    sections.append("<h2>Evidence, role, and model limitations</h2>")
    evidence_rows = [
        (row.get("category"), row.get("state"), row.get("observation"), row.get("observed_at"), row.get("expires_at"), row.get("source"), row.get("next_action"))
        for row in _sequence(data.get("evidence_observations"), "evidence", [])
        if isinstance(row, Mapping)
    ]
    sections.append(_html_table(("Category", "State", "Observation", "Observed", "Expires", "Source", "Next action"), evidence_rows))
    sections.append("<h2>Named blockers</h2>")
    blockers = _sequence(data.get("blockers"), "blockers", [])
    sections.append("<ul>" + "".join(f"<li>{_escape(value)}</li>" for value in blockers) + "</ul>")
    sections.append("<h2>Artifact provenance and exact hashes</h2>")
    artifact_rows = []
    for row in _sequence(data.get("artifacts"), "artifacts", []):
        if not isinstance(row, Mapping):
            continue
        path_text = _escape(row.get("path"))
        href = row.get("href")
        if isinstance(href, str):
            path_text = f'<a href="{_escape(href)}">{path_text}</a>'
        artifact_rows.append((row.get("name"), path_text, row.get("sha256")))
    head = "<thead><tr><th>Name</th><th>Local artifact</th><th>SHA-256</th></tr></thead>"
    body = "".join(
        f"<tr><td>{_escape(name)}</td><td>{path_cell}</td><td>{_escape(digest)}</td></tr>"
        for name, path_cell, digest in artifact_rows
    )
    sections.append(f"<table>{head}<tbody>{body}</tbody></table>")
    hash_rows = [(key, value) for key, value in sorted(_mapping(data.get("hashes"), "hashes", []).items())]
    sections.append(_html_table(("Bound hash", "SHA-256"), hash_rows))
    sections.append("</body></html>")
    return "".join(sections).encode("utf-8")


def create_readable_review(
    *,
    slate: SlateContract,
    template: EntryTemplate,
    salary_path: str | Path,
    entry_path: str | Path,
    assignment_path: str | Path,
    exported_path: str | Path,
    artifacts: Mapping[str, str],
    expected_hashes: Mapping[str, str],
    reports: Mapping[str, object],
    truth_values: Mapping[str, bool | str],
    blockers: Sequence[str],
    next_action: str,
    output_dir: str | Path,
    package_root: str | Path,
) -> ReadableReviewArtifacts:
    """Create JSON and HTML only after exact independent display reconciliation."""

    if slate.mode is not EngineMode.SHOWDOWN:
        raise ReadableReviewError(f"READABLE_REVIEW_MODE_UNSUPPORTED:{slate.mode.value}")
    problems: list[str] = []
    salary_file = Path(salary_path).resolve()
    entry_file = Path(entry_path).resolve()
    assignment_file = Path(assignment_path).resolve()
    export_file = Path(exported_path).resolve()
    output_root = Path(output_dir).resolve()
    portable_root = Path(package_root).resolve()

    exact_files = (
        ("salary_csv", salary_file, slate.salary_hash),
        ("entry_csv", entry_file, template.raw_hash),
        ("assignments", assignment_file, expected_hashes.get("assignments")),
        ("bulk_entry_csv", export_file, expected_hashes.get("bulk_entry_csv")),
    )
    for label, path, expected in exact_files:
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if not expected or actual != expected:
            problems.append(
                _problem(
                    f"READABLE_REVIEW_{label.upper()}_SHA256_MISMATCH",
                    f"actual={actual}:expected={expected}",
                )
            )

    try:
        reparsed_slate = parse_salaries(salary_file)
        reparsed_template = parse_entries(entry_file)
        output_template = parse_entry_bytes(export_file.read_bytes(), source_name=str(export_file))
        assignment_pairs = _strict_assignments(assignment_file.read_bytes())
    except (OSError, ValueError) as exc:
        problems.append(_problem("READABLE_REVIEW_EXACT_ARTIFACT_PARSE_FAILED", f"{type(exc).__name__}:{exc}"))
        reparsed_slate = slate
        reparsed_template = template
        output_template = template
        assignment_pairs = ()

    if reparsed_slate != slate:
        problems.append("READABLE_REVIEW_SALARY_REPARSE_MISMATCH")
    if (
        reparsed_template.raw_hash != template.raw_hash
        or reparsed_template.header != template.header
        or reparsed_template.roster_columns != template.roster_columns
        or reparsed_template.authorizations != template.authorizations
        or reparsed_template.encoding != template.encoding
    ):
        problems.append("READABLE_REVIEW_ENTRY_REPARSE_MISMATCH")
    expected_entries = tuple(entry.entry_id for entry in reparsed_template.authorizations)
    output_entries = tuple(entry.entry_id for entry in output_template.authorizations)
    assignment_entries = tuple(entry for entry, _roster in assignment_pairs)
    if output_entries != expected_entries:
        problems.append(_problem("READABLE_REVIEW_OUTPUT_ENTRY_ORDER_MISMATCH", output_entries))
    if assignment_entries != expected_entries:
        problems.append(_problem("READABLE_REVIEW_ASSIGNMENT_ENTRY_ORDER_MISMATCH", assignment_entries))
    source_metadata = {
        entry.entry_id: (entry.contest_id, entry.contest_name, entry.entry_fee)
        for entry in reparsed_template.authorizations
    }
    output_metadata = {
        entry.entry_id: (entry.contest_id, entry.contest_name, entry.entry_fee)
        for entry in output_template.authorizations
    }
    if output_metadata != source_metadata:
        problems.append("READABLE_REVIEW_OUTPUT_ENTRY_METADATA_MISMATCH")
    output_rosters = {entry.entry_id: entry.existing_cells for entry in output_template.authorizations}
    assignment_rosters = dict(assignment_pairs)
    if output_rosters != assignment_rosters:
        problems.append("READABLE_REVIEW_OUTPUT_ASSIGNMENT_ROSTER_MISMATCH")

    selection_path_raw = artifacts.get("selection_report")
    selection_record = (
        _read_json_record(
            Path(selection_path_raw).resolve(),
            expected_sha256=expected_hashes.get("selection_report"),
            label="SELECTION_REPORT",
            problems=problems,
        )
        if selection_path_raw
        else {}
    )
    if not selection_path_raw:
        problems.append("READABLE_REVIEW_SELECTION_REPORT_MISSING")
    if tuple(str(value) for value in selection_record.get("reserved_entries", [])) != expected_entries:
        problems.append("READABLE_REVIEW_SELECTION_ENTRY_ORDER_MISMATCH")
    if selection_record.get("assignments_sha256") != expected_hashes.get("assignments"):
        problems.append("READABLE_REVIEW_SELECTION_ASSIGNMENT_HASH_MISMATCH")
    score_map_raw = _mapping(
        selection_record.get("selected_prior_points_by_dk_id"),
        "selection.selected_prior_points_by_dk_id",
        problems,
    )
    score_map: dict[str, float] = {}
    for dk_id, raw in score_map_raw.items():
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            problems.append(_problem("READABLE_REVIEW_SCORE_INVALID", dk_id))
            continue
        score_map[str(dk_id)] = float(raw)
    selection_lineups: dict[tuple[str, ...], Mapping[str, object]] = {}
    for raw in _sequence(selection_record.get("lineups"), "selection.lineups", problems):
        row = _mapping(raw, "selection.lineup", problems)
        roster = tuple(str(value) for value in _sequence(row.get("roster"), "selection.lineup.roster", problems))
        if roster in selection_lineups:
            problems.append(_problem("READABLE_REVIEW_SELECTION_DUPLICATE_ROSTER", roster))
        selection_lineups[roster] = row

    policy_view: dict[str, object] | None = None
    if "portfolio_policy_normalized" in artifacts:
        role_ids: dict[str, dict[str, str]] = defaultdict(dict)
        for player in reparsed_slate.players:
            role_ids[player.underlying_id][player.role] = player.dk_id
        expected_person_bindings = {
            person: (roles.get("CPT", ""), roles.get("FLEX", ""))
            for person, roles in sorted(role_ids.items())
        }
        normalized_path = Path(artifacts["portfolio_policy_normalized"]).resolve()
        normalized_expected = expected_hashes.get("portfolio_policy_normalized", "")
        policy_view = _parse_normalized_policy(
            normalized_path,
            expected_sha256=normalized_expected,
            expected_entries=expected_entries,
            salary_sha256=slate.salary_hash,
            game_id=slate.games[0].game_id,
            person_bindings=expected_person_bindings,
            problems=problems,
        )
        source_path_raw = artifacts.get("portfolio_policy_source")
        source_expected = expected_hashes.get("portfolio_policy_source")
        source_actual = (
            sha256_file(source_path_raw) if source_path_raw and Path(source_path_raw).is_file() else "MISSING"
        )
        if not source_expected or source_actual != source_expected:
            problems.append(
                _problem(
                    "READABLE_REVIEW_SOURCE_POLICY_SHA256_MISMATCH",
                    f"actual={source_actual}:expected={source_expected}",
                )
            )

    by_id = {player.dk_id: player for player in reparsed_slate.players}
    role_findings = _role_findings(selection_record)
    official = reports.get("official_status") if isinstance(reports.get("official_status"), Mapping) else {}
    official_statuses = official.get("statuses", {}) if isinstance(official, Mapping) else {}
    official_observed = official.get("observed_at", {}) if isinstance(official, Mapping) else {}
    if not isinstance(official_statuses, Mapping):
        official_statuses = {}
    if not isinstance(official_observed, Mapping):
        official_observed = {}

    entries_payload: list[dict[str, object]] = []
    combined_counts: Counter[str] = Counter()
    captain_counts: Counter[str] = Counter()
    people_by_entry: dict[str, frozenset[str]] = {}
    canonical_by_entry: dict[str, str] = {}
    for authorization in reparsed_template.authorizations:
        roster = output_rosters.get(authorization.entry_id, ())
        validation = validate_lineup(reparsed_slate, roster)
        if not validation.valid or validation.lineup is None:
            problems.append(
                _problem(
                    "READABLE_REVIEW_LINEUP_INVALID",
                    f"entry={authorization.entry_id}:errors={validation.errors}",
                )
            )
            continue
        selection_lineup = selection_lineups.get(tuple(roster))
        if selection_lineup is None:
            problems.append(_problem("READABLE_REVIEW_SELECTION_ROSTER_MISMATCH", authorization.entry_id))
        else:
            if selection_lineup.get("salary") != validation.lineup.salary:
                problems.append(_problem("READABLE_REVIEW_SELECTION_SALARY_MISMATCH", authorization.entry_id))
            if selection_lineup.get("canonical_key") != validation.lineup.canonical_key:
                problems.append(_problem("READABLE_REVIEW_SELECTION_CANONICAL_MISMATCH", authorization.entry_id))
        slots: list[dict[str, object]] = []
        lineup_prior_points = 0.0
        for index, dk_id in enumerate(roster):
            player = by_id.get(dk_id)
            if player is None:
                problems.append(_problem("READABLE_REVIEW_UNKNOWN_DK_ID", f"entry={authorization.entry_id}:id={dk_id}"))
                continue
            expected_role = "CPT" if index == 0 else "FLEX"
            if player.role != expected_role:
                problems.append(
                    _problem(
                        "READABLE_REVIEW_SLOT_ROLE_MISMATCH",
                        f"entry={authorization.entry_id}:slot={index + 1}:id={dk_id}",
                    )
                )
            if dk_id not in score_map:
                problems.append(_problem("READABLE_REVIEW_SELECTED_SCORE_MISSING", dk_id))
            points = score_map.get(dk_id, 0.0)
            lineup_prior_points += points
            person_findings = role_findings.get(player.underlying_id, [])
            role_state = (
                "; ".join(sorted({str(item.get("state")) for item in person_findings}))
                if person_findings
                else "NO_NAMED_ROLE_FINDING"
            )
            slots.append(
                {
                    "slot": expected_role if index == 0 else f"FLEX {index}",
                    "name": player.name,
                    "dk_roster_id": player.dk_id,
                    "underlying_person_id": player.underlying_id,
                    "team": player.team,
                    "position": player.position,
                    "salary": player.salary,
                    "prior_only_central_estimate_points": round(points, 3),
                    "official_activity": official_statuses.get(player.dk_id, "UNKNOWN_NOT_SUPPLIED"),
                    "official_observed_at": official_observed.get(player.dk_id),
                    "salary_status_raw": player.status_raw or "BLANK_NOT_OFFICIAL_ACTIVITY",
                    "role_evidence_state": role_state,
                    "role_findings": person_findings,
                }
            )
        if selection_lineup is not None:
            selected_total = selection_lineup.get("prior_points")
            if not isinstance(selected_total, (int, float)) or abs(float(selected_total) - lineup_prior_points) > 0.0015:
                problems.append(_problem("READABLE_REVIEW_SELECTION_PROJECTION_MISMATCH", authorization.entry_id))
        people = frozenset(by_id[dk_id].underlying_id for dk_id in roster if dk_id in by_id)
        people_by_entry[authorization.entry_id] = people
        combined_counts.update(people)
        captain_counts[by_id[roster[0]].underlying_id] += 1
        canonical_by_entry[authorization.entry_id] = validation.lineup.canonical_key
        entries_payload.append(
            {
                "entry_id": authorization.entry_id,
                "contest_id": authorization.contest_id,
                "contest_name": authorization.contest_name or None,
                "entry_fee": authorization.entry_fee,
                "slots": slots,
                "salary_total": validation.lineup.salary,
                "salary_remaining": reparsed_slate.salary_cap - validation.lineup.salary,
                "prior_only_central_estimate_points": round(lineup_prior_points, 3),
                "canonical_key": validation.lineup.canonical_key,
            }
        )

    policy_limits = policy_view.get("limits", {}) if policy_view else {}
    if not isinstance(policy_limits, Mapping):
        policy_limits = {}
    person_rows: list[dict[str, object]] = []
    display_by_person: dict[str, object] = {}
    for player in reparsed_slate.players:
        display_by_person.setdefault(player.underlying_id, player)
    denominator = len(expected_entries)
    participation = selection_record.get("participation_detail")
    external_exclusions: set[str] = set()
    if isinstance(participation, Mapping):
        for label in ("unavailable_people", "operator_excluded_people"):
            raw = participation.get(label, [])
            if isinstance(raw, (list, tuple)):
                external_exclusions.update(str(value) for value in raw)
    for person in sorted(display_by_person):
        player = display_by_person[person]
        limit = policy_limits.get(person, {}) if isinstance(policy_limits.get(person, {}), Mapping) else {}
        combined_max = limit.get("combined_max_entries", denominator)
        captain_max = limit.get("captain_max_entries", denominator)
        excluded = bool(limit.get("excluded", False)) or person in external_exclusions
        actual_combined = combined_counts.get(person, 0)
        actual_captain = captain_counts.get(person, 0)
        if not isinstance(combined_max, int) or isinstance(combined_max, bool):
            problems.append(_problem("READABLE_REVIEW_COMBINED_MAX_INVALID", person))
            combined_max = denominator
        if not isinstance(captain_max, int) or isinstance(captain_max, bool):
            problems.append(_problem("READABLE_REVIEW_CAPTAIN_MAX_INVALID", person))
            captain_max = denominator
        if actual_combined > combined_max:
            problems.append(
                _problem(
                    "READABLE_REVIEW_COMBINED_EXPOSURE_EXCEEDED",
                    f"person={person}:actual={actual_combined}:maximum={combined_max}",
                )
            )
        if actual_captain > captain_max:
            problems.append(
                _problem(
                    "READABLE_REVIEW_CAPTAIN_EXPOSURE_EXCEEDED",
                    f"person={person}:actual={actual_captain}:maximum={captain_max}",
                )
            )
        person_rows.append(
            {
                "underlying_person_id": person,
                "name": player.name,
                "team": player.team,
                "combined_count": actual_combined,
                "combined_percentage": round(100 * actual_combined / denominator, 3),
                "combined_max_count": combined_max,
                "combined_max_percentage": round(100 * int(combined_max) / denominator, 3),
                "captain_count": actual_captain,
                "captain_percentage": round(100 * actual_captain / denominator, 3),
                "captain_max_count": captain_max,
                "captain_max_percentage": round(100 * int(captain_max) / denominator, 3),
                "excluded": excluded,
                "exclusion_source": limit.get("exclusion_source") or ("PARTICIPATION" if person in external_exclusions else None),
            }
        )
    selection_payload = _mapping(selection_record.get("selection"), "selection.selection", problems)
    differentiation = _mapping(
        selection_payload.get("differentiation"),
        "selection.selection.differentiation",
        problems,
    )
    configured_overlap = (
        policy_view.get("max_pairwise_person_overlap")
        if policy_view
        else differentiation.get("max_person_overlap")
    )
    effective_overlap = (
        policy_view.get("effective_pairwise_person_overlap") if policy_view else (6 if configured_overlap is None else configured_overlap)
    )
    pairwise: list[dict[str, object]] = []
    for left_index, left in enumerate(expected_entries):
        for right in expected_entries[left_index + 1 :]:
            actual_overlap = len(people_by_entry.get(left, frozenset()) & people_by_entry.get(right, frozenset()))
            pairwise.append(
                {
                    "entry_id_a": left,
                    "entry_id_b": right,
                    "actual_people": actual_overlap,
                    "maximum_people": effective_overlap,
                }
            )
            if isinstance(effective_overlap, int) and actual_overlap > effective_overlap:
                problems.append(_problem("READABLE_REVIEW_PAIRWISE_OVERLAP_EXCEEDED", f"entries={left},{right}"))
    canonical_counts = Counter(canonical_by_entry.values())
    duplicate_keys = sorted(key for key, count in canonical_counts.items() if count > 1)
    unique_required = bool(policy_view.get("require_unique_lineups")) if policy_view else True
    if unique_required and duplicate_keys:
        problems.append(_problem("READABLE_REVIEW_CANONICAL_DUPLICATE", duplicate_keys))

    if policy_view is not None:
        audit_path_raw = artifacts.get("portfolio_policy_audit")
        audit_record = (
            _read_json_record(
                Path(audit_path_raw).resolve(),
                expected_sha256=expected_hashes.get("portfolio_policy_audit"),
                label="PORTFOLIO_AUDIT",
                problems=problems,
            )
            if audit_path_raw
            else {}
        )
        if not audit_path_raw:
            problems.append("READABLE_REVIEW_PORTFOLIO_AUDIT_MISSING")
        audit_overlap = [
            {
                "entry_id_a": row["entry_id_a"],
                "entry_id_b": row["entry_id_b"],
                "people": row["actual_people"],
            }
            for row in pairwise
        ]
        if audit_record.get("status") != "PASS":
            problems.append("READABLE_REVIEW_PORTFOLIO_AUDIT_NOT_PASS")
        if tuple(str(value) for value in audit_record.get("entry_ids", [])) != expected_entries:
            problems.append("READABLE_REVIEW_AUDIT_ENTRY_ID_MISMATCH")
        if audit_record.get("canonical_lineups") != canonical_by_entry:
            problems.append("READABLE_REVIEW_AUDIT_CANONICAL_MISMATCH")
        if audit_record.get("combined_person_counts") != dict(sorted(combined_counts.items())):
            problems.append("READABLE_REVIEW_AUDIT_COMBINED_EXPOSURE_MISMATCH")
        if audit_record.get("captain_counts") != dict(sorted(captain_counts.items())):
            problems.append("READABLE_REVIEW_AUDIT_CAPTAIN_EXPOSURE_MISMATCH")
        if audit_record.get("pairwise_person_overlap") != audit_overlap:
            problems.append("READABLE_REVIEW_AUDIT_OVERLAP_MISMATCH")
        audit_hashes = _mapping(audit_record.get("hashes"), "portfolio_audit.hashes", problems)
        expected_audit_hashes = {
            "salary_sha256": sha256_file(salary_file),
            "entry_sha256": sha256_file(entry_file),
            "source_policy_sha256": sha256_file(artifacts["portfolio_policy_source"]),
            "normalized_policy_sha256": sha256_file(artifacts["portfolio_policy_normalized"]),
            "assignment_artifact_sha256": sha256_file(assignment_file),
        }
        for label, expected in expected_audit_hashes.items():
            if audit_hashes.get(label) != expected:
                problems.append(_problem("READABLE_REVIEW_AUDIT_HASH_MISMATCH", label))

    artifact_rows: list[dict[str, object]] = []
    for name, raw_path in sorted(artifacts.items()):
        path = Path(raw_path).resolve()
        if not path.is_file():
            problems.append(
                _problem("READABLE_REVIEW_ARTIFACT_MISSING", f"artifact={name}:path={path}")
            )
            continue
        digest = sha256_file(path)
        expected = _artifact_expected_hash(name, path, expected_hashes)
        if expected and digest != expected:
            problems.append(
                _problem(
                    "READABLE_REVIEW_ARTIFACT_SHA256_MISMATCH",
                    f"artifact={name}:actual={digest}:expected={expected}",
                )
            )
        portable, local = _portable_path(path, portable_root)
        href = None
        if local is not None:
            html_relative = os.path.relpath(path, output_root).replace(os.sep, "/")
            href = html_relative
        artifact_rows.append({"name": name, "path": portable, "href": href, "sha256": digest})

    if problems:
        raise ReadableReviewError(";".join(problems))

    data: dict[str, object] = {
        "schema_version": READABLE_REVIEW_VERSION,
        "status": "PRIOR_ONLY_REVIEW",
        "truths": {
            label: truth_values[label]
            for label in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")
        },
        "warning": (
            "PRIOR_ONLY central estimates. This readable package and every generated "
            "DK_REVIEW_ENTRY CSV are for review only, not certified upload files."
        ),
        "next_action": next_action,
        "blockers": list(blockers),
        "reconciliation": {
            "status": "PASS",
            "basis": "INDEPENDENT_EXACT_BYTE_REPARSE_AND_RECOMPUTATION",
            "entry_count": denominator,
            "problems": [],
        },
        "entries": entries_payload,
        "exposure": {
            "entry_count_denominator": denominator,
            "people": person_rows,
            "canonical_uniqueness": "PASS" if not duplicate_keys else "FAIL",
            "unique_required": unique_required,
            "canonical_lineups": canonical_by_entry,
            "configured_pairwise_person_overlap": configured_overlap,
            "effective_pairwise_person_overlap": effective_overlap,
            "pairwise_overlap": pairwise,
        },
        "evidence_observations": _source_observations(reports, selection_record),
        "artifacts": artifact_rows,
        "hashes": dict(sorted((str(key), str(value)) for key, value in expected_hashes.items())),
    }
    json_payload = _canonical_json_bytes(data)
    json_sha = sha256_bytes(json_payload)
    html_payload = _render_html(data, data_sha256=json_sha)
    json_path = output_root / "prior_only_readable_review.json"
    html_path = output_root / "prior_only_readable_review.html"
    written_json_sha = _write_atomic(json_path, json_payload)
    written_html_sha = _write_atomic(html_path, html_payload)
    if written_json_sha != json_sha:
        raise ReadableReviewError("READABLE_REVIEW_JSON_WRITE_MISMATCH")
    return ReadableReviewArtifacts(
        data=data,
        json_path=str(json_path),
        json_sha256=written_json_sha,
        html_path=str(html_path),
        html_sha256=written_html_sha,
    )


def verify_readable_review_artifacts(
    *, json_path: str | Path, json_sha256: str, html_path: str | Path, html_sha256: str
) -> tuple[str, ...]:
    """Recheck already-written readable bytes without trusting a summary flag."""

    problems: list[str] = []
    for label, path, expected in (
        ("JSON", Path(json_path), json_sha256),
        ("HTML", Path(html_path), html_sha256),
    ):
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != expected:
            problems.append(
                _problem(
                    f"READABLE_REVIEW_{label}_SHA256_MISMATCH",
                    f"actual={actual}:expected={expected}",
                )
            )
    return tuple(problems)
