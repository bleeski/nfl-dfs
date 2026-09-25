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
from .entry_groups import plan_entries, subset_binding_problems, unbound_rows
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup


READABLE_REVIEW_VERSION = "prior_only_readable_review_sd5_v2"
# Each row's source (Session 11b, the reason for v2): the policy's joint solve, or
# sequential Showdown filling the rows a subset policy leaves unbound (every row
# when there is no policy).
ROW_SOURCE_POLICY = "POLICY"
ROW_SOURCE_FILL = "SHOWDOWN_SEQUENTIAL"
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
    # Since Session 11b the policy binds the fillable rows or a subset of them in
    # template order, and its own rows are its denominator.
    if policy_entries != expected_entries and subset_binding_problems(policy_entries, expected_entries):
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
    if effective.get("entry_count_denominator") != len(policy_entries):
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
                or value > len(policy_entries)
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


def _unbound_rows_section(
    unbound_entries: Sequence[str],
    *,
    output_rosters: Mapping[str, Sequence[str]],
    people_by_entry: Mapping[str, frozenset[str]],
    by_id: Mapping[str, object],
    selection_payload: Mapping[str, object],
    excluded_people: set[str],
    official_statuses: Mapping[str, object],
    problems: list[str],
) -> dict[str, object] | None:
    """The second section (Session 11b): the rows a subset policy leaves to the fill.

    The policy's caps never covered them. Their legality, byte identity and
    distinctness against every other row are checked with the rest; here, the
    run's own exclusions and official inactives, and the fill's own overlap cap
    among its rows. `None` when the policy binds every row, or there is none.
    """

    if not unbound_entries:
        return None
    fill = selection_payload.get("unbound_fill")
    if not isinstance(fill, Mapping) or fill.get("lineups") != len(unbound_entries):
        problems.append(_problem("READABLE_REVIEW_UNBOUND_FILL_REPORT_MISMATCH", list(unbound_entries)))
        fill = {}
    differentiation = fill.get("differentiation") if isinstance(fill.get("differentiation"), Mapping) else {}
    configured = differentiation.get("max_person_overlap")
    effective = 6 if configured is None else configured
    exposure: Counter[str] = Counter()
    for entry_id in unbound_entries:
        for dk_id in output_rosters.get(entry_id, ()):
            player = by_id.get(dk_id)
            if player is None:
                continue
            person = getattr(player, "underlying_id")
            if person in excluded_people:
                problems.append(_problem("READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON",
                                         f"entry={entry_id}:person={person}"))
            if official_statuses.get(dk_id) == "INACTIVE":
                problems.append(_problem("READABLE_REVIEW_UNBOUND_ROW_NOT_ACTIVE",
                                         f"entry={entry_id}:id={dk_id}"))
        exposure.update(people_by_entry.get(entry_id, frozenset()))
    pairwise: list[dict[str, object]] = []
    for left_index, left in enumerate(unbound_entries):
        for right in unbound_entries[left_index + 1:]:
            shared = len(people_by_entry.get(left, frozenset()) & people_by_entry.get(right, frozenset()))
            pairwise.append({"entry_id_a": left, "entry_id_b": right, "actual_people": shared,
                             "maximum_people": effective})
            if isinstance(effective, int) and shared > effective:
                problems.append(_problem("READABLE_REVIEW_PAIRWISE_OVERLAP_EXCEEDED", f"entries={left},{right}"))
    return {
        "source": ROW_SOURCE_FILL,
        "entry_ids": list(unbound_entries),
        "basis": "THE_RUN_S_OWN_EXCLUSIONS_AND_THE_FILL_S_OVERLAP_NOT_THE_POLICY_S_CAPS",
        "checks": [
            "LEGALITY_AND_BYTES_WITH_EVERY_ROW",
            "DISTINCT_FROM_EVERY_POLICY_FILL_AND_PREFILLED_LINEUP",
            "NO_PERSON_THE_RUN_EXCLUDES",
            "NO_OFFICIAL_INACTIVE_ROW",
            "FILL_PAIRWISE_OVERLAP",
        ],
        "configured_pairwise_person_overlap": configured,
        "effective_pairwise_person_overlap": effective,
        "pairwise_overlap": pairwise,
        "person_exposure": dict(sorted(exposure.items())),
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


def _kicker_assumptions(selection_record: Mapping[str, object]) -> list[dict[str, object]]:
    """Every prior-only kicker assumption the selector leaned on, by person.

    CLAUDE.md requires the one-kicker fallback to be reported as an assumption,
    not as a confirmed role. The selector records it under
    `selection.kicker_roles.assumptions`; before this the review surface never
    read that list, so a kicker in every lineup showed `NO_NAMED_ROLE_FINDING`.
    """

    selector = selection_record.get("selection")
    if not isinstance(selector, Mapping):
        return []
    kicker = selector.get("kicker_roles")
    if not isinstance(kicker, Mapping):
        return []
    findings: list[dict[str, object]] = []
    for raw in kicker.get("assumptions", []):
        text = str(raw)
        person = None
        for part in text.split(":"):
            if part.startswith("person="):
                person = part[len("person="):]
        findings.append(
            {
                "person": person,
                "finding": text,
                "state": str(kicker.get("allocation_basis") or "PRIOR_ONLY_SOLE_LISTED_ASSUMPTION"),
                "selection_action": "DIAGNOSTIC",
                "next_evidence_action": (
                    "capture approved current kicker-role evidence"
                    " (nfl_kicker_role_evidence_v1) before treating this role as confirmed"
                ),
            }
        )
    for raw in kicker.get("coverage_gaps", []):
        findings.append(
            {
                "person": None,
                "finding": str(raw),
                "state": "KICKER_ROLE_COVERAGE_GAP",
                "selection_action": "DIAGNOSTIC",
                "next_evidence_action": None,
            }
        )
    return findings


def _pool_coverage_view(
    selection_record: Mapping[str, object],
    slate: SlateContract,
    selectable_count_expected: int | None,
    problems: list[str],
) -> dict[str, object] | None:
    """Reconcile the selector's pool-coverage summary against the exact salary bytes.

    The counts and salary totals are recomputed here from the reparsed salary
    pool and the per-person reasons the selector recorded; a disagreement is a
    named display failure like every other mismatch in this module.
    """

    raw = selection_record.get("pool_coverage")
    if not isinstance(raw, Mapping):
        return None
    rows = _sequence(raw.get("people"), "selection.pool_coverage.people", problems)
    by_person: dict[str, list] = defaultdict(list)
    for player in slate.players:
        by_person[player.underlying_id].append(player)
    recomputed: dict[str, dict[str, object]] = {}
    excluded_people: list[dict[str, object]] = []
    reason_by_person: dict[str, str] = {}
    seen: set[str] = set()
    for item in rows:
        row = _mapping(item, "selection.pool_coverage.person", problems)
        person = str(row.get("person", ""))
        reason = str(row.get("reason", ""))
        if person not in by_person:
            problems.append(_problem("READABLE_REVIEW_POOL_COVERAGE_UNKNOWN_PERSON", person))
            continue
        seen.add(person)
        players = by_person[person]
        flex_salary = sum(p.salary for p in players if p.role == "FLEX")
        cpt_salary = sum(p.salary for p in players if p.role == "CPT")
        if row.get("flex_salary") != flex_salary or row.get("cpt_salary") != cpt_salary:
            problems.append(_problem("READABLE_REVIEW_POOL_COVERAGE_SALARY_MISMATCH", person))
        bucket = reason.split(":", 1)[0]
        entry = recomputed.setdefault(
            bucket, {"people": 0, "flex_salary": 0, "cpt_salary": 0}
        )
        entry["people"] = int(entry["people"]) + 1
        entry["flex_salary"] = int(entry["flex_salary"]) + flex_salary
        entry["cpt_salary"] = int(entry["cpt_salary"]) + cpt_salary
        reason_by_person[person] = reason
        if reason != "SELECTABLE":
            first = players[0]
            excluded_people.append(
                {
                    "underlying_person_id": person,
                    "name": first.name,
                    "team": first.team,
                    "position": first.position,
                    "dk_status": str(row.get("dk_status", "")),
                    "reason": reason,
                    "flex_salary": flex_salary,
                    "cpt_salary": cpt_salary,
                }
            )
    if seen != set(by_person):
        problems.append("READABLE_REVIEW_POOL_COVERAGE_PEOPLE_INCOMPLETE")
    declared = _mapping(raw.get("by_reason"), "selection.pool_coverage.by_reason", problems)
    for bucket, values in recomputed.items():
        declared_bucket = declared.get(bucket)
        if not isinstance(declared_bucket, Mapping) or any(
            declared_bucket.get(key) != value for key, value in values.items()
        ):
            problems.append(_problem("READABLE_REVIEW_POOL_COVERAGE_TOTAL_MISMATCH", bucket))
    selectable = int(recomputed.get("SELECTABLE", {}).get("people", 0))
    if raw.get("selectable_people") != selectable:
        problems.append(
            _problem(
                "READABLE_REVIEW_POOL_COVERAGE_SELECTABLE_MISMATCH",
                f"declared={raw.get('selectable_people')}:recomputed={selectable}",
            )
        )
    # The participation contract's own count is a separate fact: everyone the
    # DK status and operator/official exclusions leave, before any role gate.
    if (
        selectable_count_expected is not None
        and raw.get("participation_selectable_people") not in (None, selectable_count_expected)
    ):
        problems.append(
            _problem(
                "READABLE_REVIEW_POOL_COVERAGE_PARTICIPATION_MISMATCH",
                f"declared={raw.get('participation_selectable_people')}:participation={selectable_count_expected}",
            )
        )
    unallocated = raw.get("unallocated_by_team")
    return {
        "people_in_pool": len(by_person),
        "selectable_people": selectable,
        "participation_selectable_people": raw.get("participation_selectable_people"),
        "by_reason": {
            bucket: {**values, "names": (declared.get(bucket) or {}).get("names", [])}
            for bucket, values in sorted(recomputed.items())
        },
        "by_team_position": raw.get("by_team_position"),
        "excluded_people": excluded_people,
        "reason_by_person": reason_by_person,
        "unallocated_by_team": unallocated if isinstance(unallocated, Mapping) else {},
        "note": raw.get("note"),
    }


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
            unallocated = offensive.get("unallocated_by_team")
            if isinstance(unallocated, Mapping):
                for team, fields in sorted(unallocated.items()):
                    if not isinstance(fields, Mapping):
                        continue
                    held = {
                        str(field): round(float(value), 4)
                        for field, value in sorted(fields.items())
                        if isinstance(value, (int, float)) and float(value) > 0
                    }
                    if held:
                        observations.append(
                            {
                                "category": "unallocated_volume",
                                "state": "PRIOR_ONLY_LIMITATION",
                                "observation": f"{team}: prior-season share held by unselectable people, not reassigned: {held}",
                                "observed_at": None,
                                "expires_at": None,
                                "source": None,
                                "next_action": None,
                            }
                        )
        kicker = selector.get("kicker_roles")
        if isinstance(kicker, Mapping):
            for finding in _kicker_assumptions(selection_record):
                observations.append(
                    {
                        "category": "kicker_role",
                        "state": finding.get("state"),
                        "observation": finding.get("finding"),
                        "observed_at": kicker.get("observed_at"),
                        "expires_at": kicker.get("expires_at"),
                        "source": kicker.get("evidence_path"),
                        "next_action": finding.get("next_evidence_action"),
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


def _render_classic_html(data: Mapping[str, object], *, data_sha256: str) -> bytes:
    """Render the C3 Classic schema without changing SD5 Showdown bytes."""

    truths = _mapping(data.get("truths"), "truths", [])
    entries = _sequence(data.get("entries"), "entries", [])
    exposure = _mapping(data.get("exposure"), "exposure", [])
    scope = _mapping(data.get("portfolio_scope"), "portfolio_scope", [])
    bank = _mapping(scope.get("candidate_bank"), "candidate_bank", [])
    joint = _mapping(scope.get("joint_selection"), "joint_selection", [])
    sections: list[str] = [
        '<!doctype html><html><head><meta charset="utf-8"><title>Classic prior-only lineup review</title>',
        "<style>@page{size:landscape;margin:9mm}body{font-family:Aptos,Arial,sans-serif;color:#17223b;margin:22px}"
        "h1,h2,h3{color:#17324d;margin-bottom:8px}.warning{background:#fce4d6;border:2px solid #c00000;padding:12px;font-weight:700}"
        ".scope{background:#fff2cc;border-left:5px solid #bf8f00;padding:10px}.truths{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}"
        ".truth{border:1px solid #9fbad0;padding:9px;background:#eef5fa}.truth b{display:block;font-size:11px}.pass{color:#006100;font-weight:700}"
        "table{width:100%;border-collapse:collapse;margin:8px 0 20px;font-size:10px;page-break-inside:auto}thead{display:table-header-group}"
        "th{background:#2f75b5;color:white;text-align:left;padding:5px}td{border:1px solid #ccd6df;padding:4px;vertical-align:top;overflow-wrap:anywhere}"
        "tr{page-break-inside:avoid}.entry{page-break-before:auto}.small{font-size:9px;color:#555}</style></head><body>",
        "<h1>DraftKings NFL Classic — prior-only exact-template review</h1>",
        f'<div class="warning">{_escape(data.get("warning"))}</div>',
        '<div class="truths">',
    ]
    for label in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION"):
        sections.append(
            f'<div class="truth"><b>{_escape(label)}</b>{_escape(truths.get(label))}</div>'
        )
    sections.extend(
        [
            "</div>",
            f'<p><b>Display reconciliation:</b> <span class="pass">{_escape(_mapping(data.get("reconciliation"), "reconciliation", []).get("status"))}</span></p>',
            '<div class="scope"><b>Bounded-bank scope:</b> '
            f'{_escape(bank.get("status"))}; requested {_escape(bank.get("requested_candidates"))}, '
            f'produced {_escape(bank.get("produced_candidates"))}; exhaustive={_escape(bank.get("exhaustive"))}. '
            f'Joint solve {_escape(joint.get("status"))} over '
            f'{_escape(joint.get("optimality_scope") or "the actual bank, stopped at a limit: feasible, not proven optimal")}. '
            'No full-slate optimality, calibrated performance, ownership, field, duplication, payout, economics, or EV claim.</div>',
            f'<p class="scope"><b>Next operator action:</b> {_escape(data.get("next_action"))}</p>',
            f'<p class="small">Readable review data SHA-256: {_escape(data_sha256)}</p>',
            "<h2>Exact Entry-ID assignments in template order</h2>",
        ]
    )
    for raw_entry in entries:
        entry = _mapping(raw_entry, "entry", [])
        sections.append(
            f'<section class="entry"><h3>Entry {_escape(entry.get("entry_id"))} — {_escape(entry.get("contest_name") or "Contest label unavailable")}</h3>'
            f'<p>Source {_escape(entry.get("source"))} · '
            f'Contest ID {_escape(entry.get("contest_id"))} · Salary ${_escape(entry.get("salary_total"))} · '
            f'Remaining ${_escape(entry.get("salary_remaining"))} · PRIOR_ONLY central estimate '
            f'{_escape(entry.get("prior_only_central_estimate_points"))} points · Games {_escape(entry.get("games"))} · '
            f'Groups {_escape(entry.get("group_matches"))} · Stack values {_escape(entry.get("stack_values"))}</p>'
        )
        slot_rows = []
        for raw_slot in _sequence(entry.get("slots"), "entry.slots", []):
            slot = _mapping(raw_slot, "slot", [])
            findings = "; ".join(
                f"{item.get('state')} [{item.get('source_sha256')}]"
                for item in _sequence(slot.get("role_findings"), "slot.role_findings", [])
                if isinstance(item, Mapping)
            )
            slot_rows.append(
                (
                    slot.get("slot"), slot.get("name"), slot.get("dk_roster_id"),
                    slot.get("underlying_person_id"), slot.get("position"), slot.get("team"),
                    slot.get("opponent"), slot.get("game_id"), slot.get("salary"),
                    slot.get("prior_only_central_estimate_points"), slot.get("official_activity"),
                    slot.get("official_observed_at"), slot.get("role_evidence_state"), findings,
                )
            )
        sections.append(
            _html_table(
                (
                    "Slot", "Player", "Exact DK ID", "Underlying person", "Position", "Team",
                    "Opponent", "Game", "Salary", "Prior-only points", "Official activity",
                    "Activity observed", "Current-role evidence", "Role source/hash",
                ),
                slot_rows,
            )
        )
        sections.append("</section>")

    sections.append("<h2>Exact audited policy counts and limits</h2>")
    people_rows = []
    for raw in _sequence(exposure.get("people"), "exposure.people", []):
        row = _mapping(raw, "exposure.person", [])
        if int(row.get("actual_count", 0) or 0) or row.get("excluded") or int(row.get("minimum_count", 0) or 0):
            people_rows.append(
                (
                    row.get("name"), row.get("underlying_person_id"), row.get("team"),
                    row.get("position"), row.get("actual_count"), row.get("actual_percentage"),
                    row.get("minimum_count"), row.get("maximum_count"), row.get("excluded"),
                    row.get("exclusion_source"),
                )
            )
    sections.append(
        _html_table(
            ("Player", "Person ID", "Team", "Position", "Actual #", "Actual %", "Min #", "Max #", "Excluded", "Basis"),
            people_rows,
        )
    )
    for title, key in (("Team counts", "teams"), ("Game counts", "games"), ("Group counts", "groups"), ("Stack-rule counts", "stack_rules")):
        rows = []
        for raw in _sequence(exposure.get(key), f"exposure.{key}", []):
            row = _mapping(raw, f"exposure.{key}.row", [])
            rows.append(
                (
                    row.get("id"), row.get("rule_type"), row.get("strength"),
                    row.get("actual_count"), row.get("minimum_count"), row.get("maximum_count"),
                    row.get("minimum_players", row.get("minimum_value")),
                    row.get("maximum_players", row.get("maximum_value")),
                )
            )
        sections.append(f"<h3>{_escape(title)}</h3>")
        sections.append(
            _html_table(("ID", "Type", "Strength", "Actual #", "Min #", "Max #", "Per-lineup min", "Per-lineup max"), rows)
        )
    sections.append(
        f'<p>Canonical uniqueness: {_escape(exposure.get("canonical_uniqueness"))}. '
        f'Pairwise underlying-person overlap maximum: {_escape(exposure.get("effective_pairwise_person_overlap"))}.</p>'
    )
    overlap_rows = [
        (row.get("entry_id_a"), row.get("entry_id_b"), row.get("actual_people"), row.get("maximum_people"))
        for row in _sequence(exposure.get("pairwise_overlap"), "exposure.pairwise_overlap", [])
        if isinstance(row, Mapping)
    ]
    sections.append(_html_table(("Entry A", "Entry B", "Actual shared people", "Maximum"), overlap_rows))
    unbound = data.get("unbound_rows")
    if isinstance(unbound, Mapping):
        # Session 11c: the rows a subset policy leaves to C1.
        sections.append("<h2>Rows the policy leaves unbound, filled by C1</h2>")
        sections.append(
            f'<p>Entry IDs {_escape(unbound.get("entry_ids"))}, filled by {_escape(unbound.get("source"))} after '
            "the policy's joint solve. The policy's bounds, overlap cap and denominator do not cover them; "
            f'they are checked for {_escape(unbound.get("checks"))}. C1 cuts only exact rosters: the most '
            "people one of them shares with any filled row is "
            f'{_escape(unbound.get("maximum_person_overlap_with_any_filled_row"))}.</p>'
        )
        sections.append(_html_table(
            ("Person ID", "Unbound rows holding them"),
            list(_mapping(unbound.get("person_exposure"), "unbound.person_exposure", []).items())))

    coverage = data.get("pool_coverage")
    if isinstance(coverage, Mapping):
        sections.append("<h2>Complete-slate coverage and unallocated volume</h2>")
        sections.append(
            f'<p>{_escape(coverage.get("people_in_pool"))} people in the salary pool; '
            f'{_escape(coverage.get("selectable_people"))} selectable. {_escape(coverage.get("note"))}</p>'
        )
        reason_rows = []
        for reason, values in _mapping(coverage.get("by_reason"), "coverage.by_reason", []).items():
            if isinstance(values, Mapping):
                reason_rows.append((reason, values.get("people"), values.get("flex_salary"), values.get("names")))
        sections.append(_html_table(("Reason", "People", "Salary", "Names"), reason_rows))
        unallocated_rows = []
        for team, fields in _mapping(coverage.get("unallocated_by_team"), "coverage.unallocated", []).items():
            if isinstance(fields, Mapping):
                unallocated_rows.append((team, *[fields.get(key) for key in ("qb_attempt_share", "carry_share", "target_share", "rushing_td_share", "receiving_td_share")]))
        sections.append(
            _html_table(("Team", "QB attempt share", "Carry share", "Target share", "Rushing TD share", "Receiving TD share"), unallocated_rows)
        )

    sections.append("<h2>Evidence and limitations</h2>")
    evidence_rows = [
        (row.get("category"), row.get("state"), row.get("observation"), row.get("observed_at"), row.get("expires_at"), row.get("source"), row.get("next_action"))
        for row in _sequence(data.get("evidence_observations"), "evidence", [])
        if isinstance(row, Mapping)
    ]
    sections.append(_html_table(("Category", "State", "Observation", "Observed", "Expires", "Source", "Next action"), evidence_rows))
    sections.append("<ul>" + "".join(f"<li>{_escape(value)}</li>" for value in _sequence(data.get("limitations"), "limitations", [])) + "</ul>")
    sections.append("<h2>Named blockers</h2><ul>" + "".join(f"<li>{_escape(value)}</li>" for value in _sequence(data.get("blockers"), "blockers", [])) + "</ul>")
    sections.append("<h2>Artifact provenance and exact hashes</h2>")
    artifact_rows = []
    for row in _sequence(data.get("artifacts"), "artifacts", []):
        if not isinstance(row, Mapping):
            continue
        path_text = _escape(row.get("path"))
        if isinstance(row.get("href"), str):
            path_text = f'<a href="{_escape(row.get("href"))}">{path_text}</a>'
        artifact_rows.append((row.get("name"), path_text, row.get("sha256")))
    head = "<thead><tr><th>Name</th><th>Local artifact</th><th>SHA-256</th></tr></thead>"
    body = "".join(
        f"<tr><td>{_escape(name)}</td><td>{path_cell}</td><td>{_escape(digest)}</td></tr>"
        for name, path_cell, digest in artifact_rows
    )
    sections.append(f"<table>{head}<tbody>{body}</tbody></table>")
    sections.append("</body></html>")
    return "".join(sections).encode("utf-8")


def _render_html(data: Mapping[str, object], *, data_sha256: str) -> bytes:
    if data.get("mode") == "CLASSIC":
        return _render_classic_html(data, data_sha256=data_sha256)
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
            f'PRIOR_ONLY central estimate {_escape(entry.get("prior_only_central_estimate_points"))} points · '
            f'Source {_escape(entry.get("source"))}</p>'
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
    unbound = data.get("unbound_rows")
    if isinstance(unbound, Mapping):
        sections.append("<h2>Rows the policy leaves unbound, filled sequentially</h2>")
        sections.append(
            f'<p>Entry IDs {_escape(unbound.get("entry_ids"))}, filled by {_escape(unbound.get("source"))} after '
            "the policy's joint solve. The policy's caps and denominator do not cover them; they are checked "
            f'for {_escape(unbound.get("checks"))}. Overlap maximum among them: '
            f'{_escape(unbound.get("effective_pairwise_person_overlap"))}.</p>'
        )
        sections.append(_html_table(
            ("Entry A", "Entry B", "Actual shared people", "Maximum"),
            [(row.get("entry_id_a"), row.get("entry_id_b"), row.get("actual_people"), row.get("maximum_people"))
             for row in _sequence(unbound.get("pairwise_overlap"), "unbound.pairwise_overlap", [])
             if isinstance(row, Mapping)]))
    coverage = data.get("pool_coverage")
    if isinstance(coverage, Mapping):
        sections.append("<h2>Pool coverage: who could not be selected, and why</h2>")
        sections.append(
            f'<p>{_escape(coverage.get("people_in_pool"))} people in the salary pool, '
            f'{_escape(coverage.get("selectable_people"))} selectable.</p>'
        )
        reason_rows = []
        for bucket, values in _mapping(coverage.get("by_reason"), "pool_coverage.by_reason", []).items():
            if not isinstance(values, Mapping):
                continue
            reason_rows.append(
                (
                    bucket, values.get("people"), values.get("flex_salary"), values.get("cpt_salary"),
                    "; ".join(str(name) for name in values.get("names", []) if name is not None),
                )
            )
        sections.append(
            _html_table(("Reason", "People", "FLEX salary", "CPT salary", "Names"), reason_rows)
        )
        excluded_rows = [
            (
                row.get("name"), row.get("team"), row.get("position"), row.get("dk_status"),
                row.get("reason"), row.get("flex_salary"), row.get("cpt_salary"),
            )
            for row in _sequence(coverage.get("excluded_people"), "pool_coverage.excluded_people", [])
            if isinstance(row, Mapping)
        ]
        sections.append("<h3>Excluded people</h3>")
        sections.append(
            _html_table(("Player", "Team", "Position", "DK status", "Reason", "FLEX salary", "CPT salary"), excluded_rows)
        )
        unallocated_rows = []
        for team, fields in _mapping(coverage.get("unallocated_by_team"), "pool_coverage.unallocated", []).items():
            if isinstance(fields, Mapping):
                unallocated_rows.append(
                    (team, *[fields.get(key) for key in ("qb_attempt_share", "carry_share", "target_share", "rushing_td_share", "receiving_td_share")])
                )
        sections.append("<h3>Prior-season volume left unallocated</h3>")
        sections.append(
            _html_table(("Team", "QB attempt share", "Carry share", "Target share", "Rushing TD share", "Receiving TD share"), unallocated_rows)
        )
        sections.append(f'<p class="small">{_escape(coverage.get("note"))}</p>')
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
    template_entries = tuple(entry.entry_id for entry in reparsed_template.authorizations)
    output_entries = tuple(entry.entry_id for entry in output_template.authorizations)
    assignment_entries = tuple(entry for entry, _roster in assignment_pairs)
    # Per-row authority (Session 11): the portfolio is the plan's fillable rows,
    # and every other row keeps the template's own cells. From here on
    # `expected_entries` means the portfolio's rows (selection, policy,
    # denominators, overlap, audit), and the output keeps the template's order.
    forbidden_keys: frozenset[str] = frozenset()
    try:
        entry_plan = plan_entries(reparsed_template, reparsed_slate)
        fillable = entry_plan.fillable
        forbidden_keys = entry_plan.forbidden_keys
    except ValueError as exc:
        problems.append(_problem("READABLE_REVIEW_ENTRY_REPARSE_MISMATCH", f"{type(exc).__name__}:{exc}"))
        fillable = template_entries
    expected_entries = fillable
    if output_entries != template_entries:
        problems.append(_problem("READABLE_REVIEW_OUTPUT_ENTRY_ORDER_MISMATCH", output_entries))
    if assignment_entries != fillable:
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
    source_rosters = {entry.entry_id: entry.existing_cells for entry in reparsed_template.authorizations}
    expected_rosters = {eid: assignment_rosters.get(eid, source_rosters.get(eid, ())) for eid in output_rosters}
    if output_rosters != expected_rosters or set(assignment_rosters) - set(output_rosters):
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

    # Session 11b: the policy's checks (counts, limits, denominator, overlap and
    # the audit) cover the rows it binds; the rows the fill wrote get the second
    # section below. Without a policy, or with one binding every row, the two are
    # the same rows as before.
    bound_entries = (
        tuple(policy_view.get("entry_ids") or expected_entries) if policy_view is not None else expected_entries
    )
    bound_set = set(bound_entries)
    unbound_entries = unbound_rows(bound_entries, expected_entries)
    sources = {
        entry_id: (ROW_SOURCE_POLICY if policy_view is not None and entry_id in bound_set else ROW_SOURCE_FILL)
        for entry_id in expected_entries
    }
    # A selection record from before Session 11b names no sources; the review
    # derives them. One that names them must agree.
    if "row_sources" in selection_record and selection_record.get("row_sources") != sources:
        problems.append(_problem("READABLE_REVIEW_ROW_SOURCE_MISMATCH", selection_record.get("row_sources")))

    by_id = {player.dk_id: player for player in reparsed_slate.players}
    role_findings = _role_findings(selection_record)
    for finding in _kicker_assumptions(selection_record):
        if finding.get("person"):
            role_findings[str(finding["person"])].append(
                {key: value for key, value in finding.items() if key != "person"}
            )
    participation_summary = selection_record.get("participation")
    selectable_expected = (
        participation_summary.get("selectable_people")
        if isinstance(participation_summary, Mapping)
        and isinstance(participation_summary.get("selectable_people"), int)
        else None
    )
    pool_coverage = _pool_coverage_view(
        selection_record, reparsed_slate, selectable_expected, problems
    )
    coverage_reasons: Mapping[str, str] = (
        pool_coverage.get("reason_by_person", {}) if pool_coverage else {}
    )
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
    filled_rows = set(fillable)
    for authorization in reparsed_template.authorizations:
        if authorization.entry_id not in filled_rows:
            continue  # a preserved or unresolved row: the byte audit holds it
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
        if authorization.entry_id in bound_set:
            combined_counts.update(people)
            captain_counts[by_id[roster[0]].underlying_id] += 1
        canonical_by_entry[authorization.entry_id] = validation.lineup.canonical_key
        if validation.lineup.canonical_key in forbidden_keys:
            problems.append(_problem("ENTRY_PREFILLED_LINEUP_REPEATED", authorization.entry_id))
        entries_payload.append(
            {
                "entry_id": authorization.entry_id,
                "source": sources.get(authorization.entry_id),
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
    denominator = len(bound_entries)
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
                "excluded": excluded or coverage_reasons.get(person, "SELECTABLE") != "SELECTABLE",
                "exclusion_source": (
                    limit.get("exclusion_source")
                    or (
                        coverage_reasons.get(person)
                        if coverage_reasons.get(person, "SELECTABLE") != "SELECTABLE"
                        else None
                    )
                    or ("PARTICIPATION" if person in external_exclusions else None)
                ),
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
    for left_index, left in enumerate(bound_entries):
        for right in bound_entries[left_index + 1 :]:
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
    if (unique_required or unbound_entries) and duplicate_keys:
        # R29 across the whole portfolio: policy rows, fill rows and prefilled rows.
        problems.append(_problem("READABLE_REVIEW_CANONICAL_DUPLICATE", duplicate_keys))
    unbound_payload = _unbound_rows_section(
        unbound_entries,
        output_rosters=output_rosters,
        people_by_entry=people_by_entry,
        by_id=by_id,
        selection_payload=selection_payload,
        excluded_people={
            *external_exclusions,
            *(person for person, reason in coverage_reasons.items() if reason != "SELECTABLE"),
        },
        official_statuses=official_statuses,
        problems=problems,
    )

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
        if tuple(str(value) for value in audit_record.get("entry_ids", [])) != bound_entries:
            problems.append("READABLE_REVIEW_AUDIT_ENTRY_ID_MISMATCH")
        if audit_record.get("canonical_lineups") != {
            entry_id: key for entry_id, key in canonical_by_entry.items() if entry_id in bound_set
        }:
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
            "entry_count": len(expected_entries),
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
        "unbound_rows": unbound_payload,
        "pool_coverage": (
            {key: value for key, value in pool_coverage.items() if key != "reason_by_person"}
            if pool_coverage is not None
            else None
        ),
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
