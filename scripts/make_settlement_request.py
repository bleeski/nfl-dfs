#!/usr/bin/env python3
"""Assemble an ``nfl_settlement_request_v1`` from bytes already on disk.

Q1 built the settlement plane and left one gap: there is no builder for its
request. Hand-authoring one means writing a strict hash-bound JSON carrying
contest facts, five versions, nine artifact bindings, four release truths, the
evidence issues and a reference budget — for every contest, forever. This is
that builder.

It resolves every field from artifacts already frozen on disk, and refuses,
by name, anything it cannot. It never invents a hash, a field size, a release
truth, a timestamp or a prediction. In particular:

- **Release truths are copied, not re-derived.** They are read out of the frozen
  pre-lock run and carried across unchanged. Settlement capture must not be able
  to improve the release decision a slate actually shipped with, and a builder
  that recomputed them could do exactly that.
- **A missing artifact is a refusal, not a default.** ``settle --request`` binds
  nine artifacts by SHA-256; a builder that guessed at one would produce a
  request that fails at capture with a hash mismatch instead of here, with a
  name.

What this finds on the current repo
-----------------------------------

Run against Ben's 18 entered contests it refuses all 18, and the reasons are the
tranche's main finding rather than a bug in this file. Two of them are
structural:

``PRELOCK_MANIFEST_ABSENT``
    No ``data/runs/`` snapshot contains an ``nfl_prelock_run_manifest_v1``. Only
    the legacy ``build`` command writes one; the ``prior_review``/C1-C3 path that
    produced every contest Ben has actually entered never has. A pre-lock
    manifest is a record of what was predicted *before* lock, so it cannot be
    written afterwards — ``_validate_prelock_manifest`` will refuse every
    historical contest permanently.

``SCENARIO_BANK_ABSENT``
    Same cause: ``nfl_settlement_request_v1`` requires at least one
    ``nfl_scenario_bank_v1``, and no run directory holds one.

Both are recorded under Q1B in ``backlog.md``. The repair is an emitter on the
path Ben actually uses, which makes the *next* slate settleable; it cannot
recover the eighteen already played, and reconstructing one after the fact is
forbidden outright.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from nfl_dfs.dk import DraftKingsParseError, parse_entries, parse_salaries
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.exit(
        "nfl_dfs is not importable. Run this with the project's own interpreter:\n"
        "  Windows:      .venv\\Scripts\\python.exe scripts\\make_settlement_request.py\n"
        "  Linux: .venv-linux/bin/python scripts/make_settlement_request.py"
    )

RUNS_DIR = REPO_ROOT / "data" / "runs"
NORMALIZED_DIR = REPO_ROOT / "data" / "standings" / "normalized"
METRIC_REGISTRY = REPO_ROOT / "config" / "metric_registry_q1_v1.json"

REQUEST_VERSION = "nfl_settlement_request_v1"
PRELOCK_MANIFEST_VERSION = "nfl_prelock_run_manifest_v1"
SCENARIO_BANK_VERSION = "nfl_scenario_bank_v1"
METRIC_REGISTRY_VERSION = "nfl_metric_promotion_registry_v1"
STANDINGS_VERSION = "nfl_standings_csv_v2"

#: Reference budget. ``max_runtime_seconds`` is raised from Q1's registered 10.0
#: on measured evidence, not preference: the evaluator refuses 133,000 synthetic
#: entries at 10s and settles them exactly in 27.868447s, and settles the real
#: 126,020-entry field of 193391013 in well under that. 180s carries headroom for
#: a heavily tied field without becoming an excuse not to measure.
#:
#: ``max_entries`` stays at Q1's registered 200,000, which is a real ceiling and
#: not a tuning knob: contest 193028206 settled 832,342 entries, four times over
#: it, and the complete-field rule means there is no partial option. That contest
#: is named as excluded rather than quietly approximated.
DEFAULT_REFERENCE_BUDGET = {
    "max_entries": 200_000,
    "max_work_units": 4_000_000,
    "max_runtime_seconds": 180.0,
}

RELEASE_TRUTH_KEYS = ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")


class SettlementRequestError(ValueError):
    """A named refusal. Every message starts with a stable upper-case code."""


@dataclass
class Resolution:
    """What the builder could and could not resolve for one contest."""

    contest_id: str
    run_id: str | None = None
    resolved: dict = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    def block(self, code: str, detail: str) -> None:
        self.blockers.append(f"{code}: {detail}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_input_hash(manifest: dict, key: str) -> str | None:
    hashes = manifest.get("input_hashes")
    if not isinstance(hashes, dict):
        return None
    value = hashes.get(key)
    return value if isinstance(value, str) else None


def _schema_version(path: Path) -> str | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload.get("schema_version") if isinstance(payload, dict) else None


# ---------------------------------------------------------------------------
# Locating the frozen artifacts of one run
# ---------------------------------------------------------------------------


def classify_run_inputs(run_dir: Path) -> tuple[Path | None, Path | None]:
    """Find the salary and reserved-entry snapshots by schema, never by filename.

    ``data/runs/*/inputs/`` holds content-addressed files as often as named ones
    (``3a165717....csv``), so the only reliable classifier is whether the engine's
    own parser accepts the bytes — the same rule ``standings_checklist`` uses.
    """
    salary: Path | None = None
    entries: Path | None = None
    for candidate in sorted(run_dir.rglob("inputs/*.csv")):
        try:
            parse_entries(candidate)
        except DraftKingsParseError:
            pass
        else:
            entries = entries or candidate
            continue
        try:
            parse_salaries(candidate)
        except DraftKingsParseError:
            continue
        salary = salary or candidate
    return salary, entries


def find_prelock_manifest(run_dir: Path) -> Path | None:
    for candidate in sorted(run_dir.rglob("*.json")):
        if _schema_version(candidate) == PRELOCK_MANIFEST_VERSION:
            return candidate
    return None


def index_run_by_hash(run_dir: Path) -> dict[str, Path]:
    """Every file in the run, keyed by its SHA-256.

    Prediction and scenario artifacts are located by hash rather than by path or
    filename, because the pre-lock manifest already records exactly which bytes
    were predicted with. Searching for those bytes cannot bind the wrong file;
    searching for a plausible filename can.
    """
    index: dict[str, Path] = {}
    for candidate in sorted(run_dir.rglob("*")):
        if candidate.is_file():
            index.setdefault(sha256_file(candidate), candidate)
    return index


def declared_prediction_names(manifest: dict, scenario_names: set[str]) -> list[str]:
    """The prediction artifacts the pre-lock manifest itself declares.

    ``settlement._validate_prelock_manifest`` derives the expected set exactly
    this way and refuses on ``PRELOCK_PREDICTION_COVERAGE_MISMATCH`` if the
    request disagrees, so the manifest is the authority on these names and the
    builder must not coin its own.
    """
    versions = manifest.get("artifact_versions")
    if not isinstance(versions, dict):
        return []
    fixed = {"salary", "entries", "payouts", "assignments"}
    return sorted(set(versions) - fixed - scenario_names)


def find_assignments(run_dir: Path) -> list[Path]:
    """Every assignment CSV in the run, newest path last.

    Deliberately returns all of them rather than picking one. A run can hold
    several (an early review plus the export that actually reached DraftKings),
    and choosing between them is exactly the judgement a builder must not make
    silently — the caller names the one it means with ``--assignments``.
    """
    return [
        candidate
        for candidate in sorted(run_dir.rglob("*.csv"))
        if "assignment" in candidate.name.lower()
    ]




def find_release_truths(run_dir: Path) -> tuple[dict, Path] | None:
    """Read the four release truths out of the run's own frozen result.

    Copied verbatim. A settlement must not be able to report a better release
    decision than the slate actually shipped with, so these are never recomputed
    here from the artifacts they describe.
    """
    for candidate in sorted(run_dir.rglob("*.json")):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if all(key in payload for key in RELEASE_TRUTH_KEYS):
            return {key: payload[key] for key in RELEASE_TRUTH_KEYS}, candidate
    return None


def find_normalized_standings(contest_id: str) -> list[Path]:
    destination = NORMALIZED_DIR / contest_id
    if not destination.is_dir():
        return []
    return sorted(p for p in destination.glob("*.csv"))


def find_payouts(run_dir: Path, contest_id: str) -> Path | None:
    for candidate in sorted(run_dir.rglob("*.csv")):
        name = candidate.name.lower()
        if "payout" in name and (contest_id in name or "payout" == name[:6]):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_contest(
    contest_id: str,
    run_dir: Path,
    *,
    assignments: Path | None = None,
    payouts: Path | None = None,
    standings: Path | None = None,
) -> Resolution:
    """Resolve every requirement of ``nfl_settlement_request_v1`` for one contest."""
    resolution = Resolution(contest_id=contest_id, run_id=run_dir.name)
    if not run_dir.is_dir():
        resolution.block("RUN_SNAPSHOT_ABSENT", f"{run_dir} is not a directory")
        return resolution

    salary, entries = classify_run_inputs(run_dir)
    if salary is None:
        resolution.block(
            "SALARY_SNAPSHOT_ABSENT",
            f"no file under {run_dir.name}/inputs/ parses as a DraftKings salary CSV",
        )
    if entries is None:
        resolution.block(
            "ENTRY_TEMPLATE_ABSENT",
            f"no file under {run_dir.name}/inputs/ parses as a reserved-entry template",
        )

    if salary is not None:
        slate = parse_salaries(salary)
        resolution.resolved["salary"] = {
            "path": _repo_relative(salary),
            "sha256": slate.salary_hash,
            "artifact_version": "dk_salary_csv_v1",
        }
        resolution.resolved["mode"] = slate.mode.value
        resolution.resolved["draft_group"] = slate.draft_group
        resolution.resolved["scoring"] = slate.scoring_version

    if entries is not None:
        template = parse_entries(entries)
        contests = {auth.contest_id for auth in template.authorizations}
        if contest_id not in contests:
            resolution.block(
                "CONTEST_NOT_IN_ENTRY_TEMPLATE",
                f"{run_dir.name} authorizes {sorted(contests)}, not {contest_id}",
            )
        elif len(contests) > 1:
            # settlement.require_single_contest refuses a multi-contest template
            # outright, so naming it here beats failing at capture.
            resolution.block(
                "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED",
                f"{run_dir.name} binds {len(contests)} contests {sorted(contests)} in "
                "one reserved-entry file; settlement requires exactly one",
            )
        owned = sorted(
            auth.entry_id
            for auth in template.authorizations
            if auth.contest_id == contest_id
        )
        fees = {
            Decimal(str(auth.entry_fee))
            for auth in template.authorizations
            if auth.contest_id == contest_id
        }
        resolution.resolved["entries"] = {
            "path": _repo_relative(entries),
            "sha256": sha256_file(entries),
            "artifact_version": "dk_entry_csv_v1",
        }
        resolution.resolved["owned_entry_ids"] = owned
        resolution.resolved["entry_fee"] = str(sorted(fees)[0]) if fees else None

    manifest = find_prelock_manifest(run_dir)
    if manifest is None:
        resolution.block(
            "PRELOCK_MANIFEST_ABSENT",
            f"{run_dir.name} holds no {PRELOCK_MANIFEST_VERSION}. Only the legacy "
            "build command writes one; the prior_review/C1-C3 path does not. A "
            "pre-lock prediction record cannot be written after the fact.",
        )
    else:
        resolution.resolved["prelock_manifest"] = {
            "path": _repo_relative(manifest),
            "sha256": sha256_file(manifest),
            "artifact_version": PRELOCK_MANIFEST_VERSION,
        }

    manifest_payload: dict = {}
    if manifest is not None:
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            manifest_payload = loaded

    by_hash = index_run_by_hash(run_dir)

    scenario_records = manifest_payload.get("scenario_artifacts")
    scenario_records = scenario_records if isinstance(scenario_records, dict) else {}
    declared_model_status = str(manifest_payload.get("MODEL_STATUS") or "")
    if not scenario_records:
        if declared_model_status == "PRIOR_ONLY":
            # A prior-only run simulates nothing, so binding zero banks is the
            # truthful outcome rather than a gap. `SettlementCaptureRequest`
            # refuses an empty set for any other model status, so this cannot
            # quietly let a validated model through without its banks.
            resolution.resolved["scenarios"] = []
        else:
            resolution.block(
                "SCENARIO_BANK_ABSENT",
                f"{run_dir.name} declares no {SCENARIO_BANK_VERSION} and its model "
                f"status is {declared_model_status or 'unrecorded'}; only a "
                "PRIOR_ONLY model may settle without one",
            )
    else:
        scenarios = []
        for name in sorted(scenario_records):
            record = scenario_records[name]
            digest = record.get("sha256") if isinstance(record, dict) else None
            located = by_hash.get(digest) if digest else None
            if located is None:
                resolution.block(
                    "SCENARIO_BANK_BYTES_ABSENT",
                    f"{run_dir.name} declares scenario {name} at {digest} but holds "
                    "no file with those bytes",
                )
                continue
            scenarios.append(
                {
                    "name": name,
                    "path": _repo_relative(located),
                    "sha256": digest,
                    "artifact_version": record.get(
                        "schema_version", SCENARIO_BANK_VERSION
                    ),
                }
            )
        if scenarios:
            resolution.resolved["scenarios"] = scenarios

    prediction_names = declared_prediction_names(
        manifest_payload, set(scenario_records)
    )
    if not prediction_names:
        resolution.block(
            "PREDICTION_ARTIFACT_ABSENT",
            f"{run_dir.name} declares no frozen prediction artifact; the request "
            "requires at least one",
        )
    else:
        predictions = []
        versions = manifest_payload.get("artifact_versions", {})
        for name in prediction_names:
            digest = _manifest_input_hash(manifest_payload, name)
            located = by_hash.get(digest) if digest else None
            if located is None:
                resolution.block(
                    "PREDICTION_ARTIFACT_ABSENT",
                    f"{run_dir.name} declares prediction {name} at {digest} but holds "
                    "no file with those bytes",
                )
                continue
            predictions.append(
                {
                    "name": name,
                    "path": _repo_relative(located),
                    "sha256": digest,
                    "artifact_version": versions.get(name, ""),
                }
            )
        if predictions:
            resolution.resolved["predictions"] = predictions

    chosen_assignments = assignments or (
        find_assignments(run_dir)[0] if len(find_assignments(run_dir)) == 1 else None
    )
    if chosen_assignments is None:
        candidates = [_repo_relative(p) for p in find_assignments(run_dir)]
        resolution.block(
            "ASSIGNMENT_AMBIGUOUS" if candidates else "ASSIGNMENT_ABSENT",
            f"{run_dir.name} offers {candidates or 'no'} assignment CSVs; name one "
            "with --assignments rather than letting the builder choose",
        )
    else:
        resolution.resolved["assignments"] = {
            "path": _repo_relative(chosen_assignments),
            "sha256": sha256_file(chosen_assignments),
            "artifact_version": "nfl_assignment_csv_v1",
        }

    payout_path = payouts or find_payouts(run_dir, contest_id)
    if payout_path is None or not Path(payout_path).is_file():
        resolution.block(
            "PAYOUT_TABLE_ABSENT",
            f"no payout CSV for {contest_id}; the entry template does not carry "
            "payouts and they must never be inferred from a contest name",
        )
    else:
        resolution.resolved["payouts"] = {
            "path": _repo_relative(Path(payout_path)),
            "sha256": sha256_file(Path(payout_path)),
            "artifact_version": "nfl_payout_contract_v1",
        }

    standings_candidates = (
        [Path(standings)] if standings else find_normalized_standings(contest_id)
    )
    if not standings_candidates:
        resolution.block(
            "NORMALIZED_STANDINGS_ABSENT",
            f"no {STANDINGS_VERSION} under data/standings/normalized/{contest_id}/; "
            "run scripts/file_standings.py on the raw export first",
        )
    elif len(standings_candidates) > 1 and not standings:
        resolution.block(
            "NORMALIZED_STANDINGS_AMBIGUOUS",
            f"{len(standings_candidates)} normalized files for {contest_id}; name one "
            "with --standings",
        )
    else:
        chosen = standings_candidates[0]
        resolution.resolved["standings"] = {
            "path": _repo_relative(chosen),
            "sha256": sha256_file(chosen),
            "artifact_version": STANDINGS_VERSION,
        }
        resolution.resolved["observed_field_size"] = _count_rows(chosen)

    if not METRIC_REGISTRY.is_file():
        resolution.block("METRIC_REGISTRY_ABSENT", f"{METRIC_REGISTRY} is missing")
    else:
        resolution.resolved["metric_registry"] = {
            "path": _repo_relative(METRIC_REGISTRY),
            "sha256": sha256_file(METRIC_REGISTRY),
            "artifact_version": METRIC_REGISTRY_VERSION,
        }

    truths = find_release_truths(run_dir)
    if truths is None:
        resolution.block(
            "RELEASE_TRUTHS_ABSENT",
            f"{run_dir.name} holds no artifact carrying all four release truths; "
            "they are copied from the frozen run, never re-derived here",
        )
    else:
        resolution.resolved["release_truths"] = truths[0]
        resolution.resolved["release_truths_source"] = _repo_relative(truths[1])

    field_size = resolution.resolved.get("observed_field_size")
    if field_size is not None and field_size > DEFAULT_REFERENCE_BUDGET["max_entries"]:
        resolution.block(
            "REFERENCE_SIZE_BUDGET_EXCEEDED",
            f"{contest_id} settled {field_size} entries, over the registered "
            f"max_entries {DEFAULT_REFERENCE_BUDGET['max_entries']}. The "
            "complete-field rule allows no partial settlement, so this contest is "
            "excluded from the exact corpus rather than approximated.",
        )
    return resolution


def _count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def _repo_relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build_request(
    resolution: Resolution,
    *,
    settlement_id: str,
    captured_at: datetime,
    settled_at: datetime,
    objective: str,
    advertised_prize_value: Decimal,
    ticket_face_value: Decimal | None = None,
    evidence_issues: list[dict] | None = None,
    reference_budget: dict | None = None,
) -> dict:
    """Render the request. Refuses outright if anything is still unresolved."""
    if resolution.blockers:
        raise SettlementRequestError(
            "SETTLEMENT_REQUEST_INCOMPLETE: "
            + "; ".join(resolution.blockers)
        )
    got = resolution.resolved
    issues = list(evidence_issues or [])
    if not issues:
        # The contract requires an explicit issue whenever evidence is not PASS
        # or the model is not prospectively validated, which is every slate this
        # repo has ever produced. Stating it beats tripping the validator.
        issues = [
            {
                "state": "MISSING",
                "code": "PROSPECTIVE_VALIDATION_ABSENT",
                "detail": "No prospective validation corpus yet; Q6 is unstarted.",
            }
        ]
    return {
        "schema_version": REQUEST_VERSION,
        "settlement_id": settlement_id,
        "run_id": resolution.run_id,
        "captured_at": captured_at.isoformat(),
        "settled_at": settled_at.isoformat(),
        "contest": {
            "contest_id": resolution.contest_id,
            "draft_group": got["draft_group"],
            "mode": got["mode"],
            "entry_fee": got["entry_fee"],
            "field_size": got["observed_field_size"],
            "objective": objective,
            "advertised_prize_value": str(advertised_prize_value),
            "ticket_face_value": (
                str(ticket_face_value) if ticket_face_value is not None else None
            ),
        },
        "versions": {
            "salary_parser": "dk_csv_v1",
            "entry_parser": "dk_csv_v1",
            "payout_parser": "nfl_payout_csv_v2",
            "standings_parser": STANDINGS_VERSION,
            "assignment_parser": "nfl_assignment_csv_v1",
            "scoring": got["scoring"],
            "settlement": "nfl_reference_settlement_v1",
            "bundle_schema": "nfl_settlement_bundle_v1",
            "brief_schema": "nfl_run_settlement_brief_v1",
            "metric_registry_schema": METRIC_REGISTRY_VERSION,
        },
        "artifacts": {
            "salary": {"name": "salary", **got["salary"]},
            "entries": {"name": "entries", **got["entries"]},
            "payouts": {"name": "payouts", **got["payouts"]},
            "assignments": {"name": "assignments", **got["assignments"]},
            "prelock_manifest": {"name": "prelock_manifest", **got["prelock_manifest"]},
            "standings": {"name": "standings", **got["standings"]},
            "metric_registry": {"name": "metric_registry", **got["metric_registry"]},
            "predictions": got["predictions"],
            "scenarios": got["scenarios"],
        },
        "release_truths": got["release_truths"],
        "evidence_issues": issues,
        "reference_budget": dict(reference_budget or DEFAULT_REFERENCE_BUDGET),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble an nfl_settlement_request_v1 from frozen artifacts."
    )
    parser.add_argument("--contest", required=True)
    parser.add_argument("--run", help="a data/runs/<run_id> snapshot")
    parser.add_argument("--assignments", default=None)
    parser.add_argument("--payouts", default=None)
    parser.add_argument("--standings", default=None)
    parser.add_argument("--settlement-id", default=None)
    parser.add_argument("--objective", default="SMALL_GPP")
    parser.add_argument("--advertised-prize-value", default=None)
    parser.add_argument("--ticket-face-value", default=None)
    parser.add_argument("--settled-at", default=None, help="timezone-aware ISO 8601")
    parser.add_argument("--out", default=None, help="where to write the request JSON")
    parser.add_argument(
        "--report",
        action="store_true",
        help="resolve and report without building; never writes",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if not args.run:
            raise SettlementRequestError(
                "RUN_SNAPSHOT_REQUIRED: name the frozen data/runs snapshot the "
                "contest was built from with --run"
            )
        resolution = resolve_contest(
            args.contest,
            RUNS_DIR / args.run,
            assignments=Path(args.assignments) if args.assignments else None,
            payouts=Path(args.payouts) if args.payouts else None,
            standings=Path(args.standings) if args.standings else None,
        )
        if args.report:
            payload = {
                "contest_id": resolution.contest_id,
                "run_id": resolution.run_id,
                "resolved": sorted(resolution.resolved),
                "blockers": resolution.blockers,
                "settleable": not resolution.blockers,
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"contest {resolution.contest_id}  run {resolution.run_id}")
                print(f"  settleable: {payload['settleable']}")
                for blocker in resolution.blockers:
                    print(f"  BLOCKER {blocker}")
            return 0 if not resolution.blockers else 2

        if not args.advertised_prize_value:
            raise SettlementRequestError(
                "ADVERTISED_PRIZE_VALUE_REQUIRED: supply the contest's exact "
                "advertised cash-plus-ticket value; it is never inferred"
            )
        now = datetime.now(timezone.utc)
        settled_at = (
            datetime.fromisoformat(args.settled_at) if args.settled_at else now
        )
        if settled_at.tzinfo is None:
            raise SettlementRequestError(
                "SETTLED_AT_NOT_TIMEZONE_AWARE: supply a timezone-aware ISO 8601 time"
            )
        request = build_request(
            resolution,
            settlement_id=args.settlement_id or f"{args.contest}-{now:%Y%m%dT%H%M%SZ}",
            captured_at=now,
            settled_at=settled_at,
            objective=args.objective,
            advertised_prize_value=Decimal(args.advertised_prize_value),
            ticket_face_value=(
                Decimal(args.ticket_face_value) if args.ticket_face_value else None
            ),
        )
        payload = json.dumps(request, indent=2, sort_keys=True) + "\n"
        if args.out:
            destination = Path(args.out)
            if destination.exists():
                raise SettlementRequestError(
                    f"REQUEST_ALREADY_EXISTS: {destination} is never overwritten"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
            print(f"Wrote {_repo_relative(destination)}")
        else:
            print(payload, end="")
        return 0
    except (SettlementRequestError, DraftKingsParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
