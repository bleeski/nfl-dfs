"""`nfl baseline` (Session 04, R28, R29): a deliverable file from the DraftKings bytes alone.

R28 puts a baseline first: before priors, weather, roles or any model, a file
built from the salary and entries bytes Ben downloaded, so a slate is never lost
to a gate that only a model needs. This module is that baseline. It reads no
network, no prior, no weather and no role evidence, and it never claims more
than its bytes support:

- intake classifies both files by schema, snapshots them under the run folder
  and parses only the snapshots;
- only exact current-slate DraftKings IDs enter it: the salary file's own rows,
  cross-checked against the player table the entries export carries;
- a Classic/Showdown mismatch, a prefilled row (until Session 11) or any other
  integrity gate stops the file it protects;
- people DraftKings flags `OUT`, `IR` or `D` leave the pool through
  `contracts.unavailable_people`, exactly as `freeze_prior_package` derives it;
- lineups follow the registered `BASELINE_SALARY_RANK_V1` objective, distinct by
  exact roster (R29), under a per-solve limit and a whole-run budget;
- only blank authorized rows are filled, through `lineups.write_upload_bytes`,
  into a new `DK_BASELINE_ENTRY_V1_<run_id>.csv` (`nfl_baseline_entry_csv_v1`);
- an independent audit reparses those bytes from disk before they are kept;
- the run reports `DELIVERY_STATE` with every unfilled Entry ID, beside the four
  v1 truths (`nfl_release_truths_v2`), and every gap as a registered limitation.

The file is legal and byte-audited. It is not certified: `MODEL_STATUS` is
`PRIOR_ONLY` and `RELEASE_DECISION` is `DO_NOT_UPLOAD`, and a `DELIVERABLE`
state is not upload clearance.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    UNAVAILABLE_DK_STATUSES,
    CertificationBasis,
    DeliveryLimitation,
    DeliveryState,
    GateClass,
    ModelStatus,
    ReleaseEvidenceState,
    ReleaseTruthsV2,
    SlateContract,
    unavailable_people,
)
from .cowork import classify_csv
from .dk import (
    DraftKingsParseError,
    EntryTemplate,
    embedded_pool_ids,
    parse_entries,
    parse_entry_bytes,
    parse_salaries,
    reconcile_template,
    single_contest_problems,
)
from .gate_registry import GateRegistry, load_gate_registry
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup, write_upload_bytes
from .optimizer import LineupOptimizer
from .referee import audit_output_bytes
from .release import derive_delivery_state, derive_release_policy, release_truths_v2

REPORT_VERSION = "nfl_baseline_report_v1"
OUTPUT_CONTRACT = "nfl_baseline_entry_csv_v1"
OUTPUT_PREFIX = "DK_BASELINE_ENTRY_V1_"
OBJECTIVE_VERSION = "BASELINE_SALARY_RANK_V1"
# Measured on the supplied fixtures (changelog, Session 04): the slowest single
# solve took 1.3 s, and 150 distinct lineups took about 3 s Classic and 6 s
# Showdown in all. The defaults leave several times that.
DEFAULT_PER_SOLVE_SECONDS = 5.0
DEFAULT_BUDGET_SECONDS = 60.0

OBJECTIVE: Mapping[str, object] = {
    "version": OBJECTIVE_VERSION,
    "direction": "MAXIMIZE",
    "score": "each salary row's DraftKings salary in dollars; a captain row at its own 1.5x price",
    "definition": (
        "Lineups in non-increasing total DraftKings salary. Each is a highest-salary legal"
        " lineup not already chosen, over the salary rows the availability contract leaves,"
        " with an exact-roster cut against every earlier lineup. It is solved one salary"
        " level at a time: one salary-maximizing solve finds the level, then zero-objective"
        " solves with a salary floor at that level take its other lineups."
    ),
    "tie_break": (
        "Among lineups of equal total salary the deterministic solver's order decides;"
        " it expresses no judgement of quality. The solver's seed for the k-th lineup is"
        " k (0-based), so the same bytes give the same file, and each solve starts its"
        " search somewhere new instead of beside the lineup before it."
    ),
    "seed_rule": "HiGHS random_seed = the number of lineups already built",
    "why": (
        "Salary is the only number in the DraftKings bytes the engine may read, and it is"
        " DraftKings' own price. Spending it is the one construction rule that needs no"
        " other evidence."
    ),
    "does_not_establish": [
        "EXPECTED_POINTS",
        "PROJECTION",
        "CONTEST_ECONOMICS",
        "WIN_OR_CASH_LIKELIHOOD",
        "OWNERSHIP_OR_LEVERAGE",
        "OFFICIAL_ACTIVE_STATUS",
        "CURRENT_TEAM_ROLE",
        "WEATHER",
        "MODEL_VALIDATION",
        "UPLOAD_CLEARANCE",
    ],
}

WARNING = (
    "PRIOR_ONLY / DO_NOT_UPLOAD. A legal, byte-audited baseline built from the DraftKings"
    " bytes alone, ranked by salary. It is not certified and carries no expected-points,"
    " return, win, cash, ownership or edge claim. DELIVERY_STATE says a valid file exists"
    " to hand over, not that uploading is cleared; uploading stays Ben's manual decision."
)
CHECKS_NOT_RUN = (
    "OFFICIAL_ACTIVITY_EVIDENCE",
    "CURRENT_ROLE_EVIDENCE",
    "WEATHER_CAPTURE",
    "PRIOR_OR_PROJECTION_MODEL",
    "CONTEST_ECONOMICS",
    "OWNERSHIP_AND_DUPLICATION",
    "LOCK_CLOCK",
)
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")


@dataclass(frozen=True)
class BuiltLineup:
    roster: tuple[str, ...]
    salary: int
    canonical_key: str
    found_by: str
    time_limited: bool
    solve_seconds: float


@dataclass(frozen=True)
class BuildResult:
    lineups: tuple[BuiltLineup, ...]
    stop_reason: str
    solves: int
    salary_levels: tuple[int, ...]


@dataclass(frozen=True)
class BaselineOutcome:
    run_id: str
    run_dir: Path
    report_path: Path | None
    output_path: Path | None
    output_sha256: str | None
    truths: ReleaseTruthsV2
    assignments: Mapping[str, tuple[str, ...]]
    report: Mapping[str, object]

    @property
    def exit_code(self) -> int:
        """0 delivers every row, 3 delivers some and names the rest, 2 delivers none."""

        return {DeliveryState.DELIVERABLE: 0, DeliveryState.DELIVERABLE_PARTIAL: 3}.get(
            self.truths.delivery_state, 2
        )


def build_distinct_lineups(
    slate: SlateContract,
    *,
    count: int,
    excluded_ids: tuple[str, ...],
    per_solve_seconds: float,
    deadline: float,
    clock: Callable[[], float],
) -> BuildResult:
    """Up to `count` distinct legal lineups in `BASELINE_SALARY_RANK_V1` order.

    The clock is read once per solve, against `deadline`. A lineup is kept only
    if the shared validator passes it and its exact roster is new (R29); an exact
    no-good cut then removes it from every later solve.
    """

    if count <= 0:
        return BuildResult((), "FILLED", 0, ())
    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded_ids, time_limit_seconds=per_solve_seconds
    )
    by_salary = {player.dk_id: float(player.salary) for player in slate.players}
    zero = dict.fromkeys(by_salary, 0.0)
    built: list[BuiltLineup] = []
    seen: set[str] = set()
    levels: list[int] = []
    solves = 0
    level: int | None = None  # None: find the next level; else take lineups at it
    while len(built) < count:
        remaining = deadline - clock()
        if remaining <= 0:
            return BuildResult(tuple(built), "BUDGET_EXHAUSTED", solves, tuple(levels))
        optimizer.set_time_limit(min(per_solve_seconds, remaining))
        optimizer.set_salary_floor(level)
        optimizer.set_random_seed(len(built))
        result = optimizer.solve(by_salary if level is None else zero)
        solves += 1
        if result.roster is None:
            if level is not None:
                level = None  # this level is spent or unproven; the next maximum decides
                continue
            stop = (
                "DISTINCT_LINEUPS_EXHAUSTED"
                if result.status == "INFEASIBLE"
                else "SOLVE_LIMIT_WITHOUT_LINEUP"
            )
            return BuildResult(tuple(built), stop, solves, tuple(levels))
        if result.validation is None or result.validation.lineup is None:
            return BuildResult(tuple(built), "SOLVER_PRODUCED_ILLEGAL_LINEUP", solves, tuple(levels))
        lineup = result.validation.lineup
        if lineup.canonical_key in seen:
            return BuildResult(tuple(built), "SOLVER_REPEATED_A_LINEUP", solves, tuple(levels))
        seen.add(lineup.canonical_key)
        optimizer.add_no_good(lineup.roster)
        found_by = "SALARY_LEVEL_MAXIMUM" if level is None else "SALARY_LEVEL_MEMBER"
        if level is None:
            level = lineup.salary
            levels.append(level)
        built.append(
            BuiltLineup(
                roster=lineup.roster,
                salary=lineup.salary,
                canonical_key=lineup.canonical_key,
                found_by=found_by,
                time_limited=result.status == "FEASIBLE_LIMIT",
                solve_seconds=round(result.elapsed_seconds, 4),
            )
        )
    return BuildResult(tuple(built), "FILLED", solves, tuple(levels))


def audit_baseline_bytes(
    raw: bytes,
    *,
    salary_path: Path,
    entries_path: Path,
    assignments: Mapping[str, tuple[str, ...]],
    unfilled: tuple[str, ...],
) -> list[str]:
    """Every reason the bytes are not the template with exactly `assignments` filled.

    Independent of the build: both snapshots are parsed afresh, the availability
    set is re-derived from the salary bytes, the byte audit compares every line
    against the template, and the reparsed rows are validated again.
    """

    problems: list[str] = []
    slate = parse_salaries(salary_path)
    source = parse_entries(entries_path)
    byte_audit = audit_output_bytes(entries_path, raw, source, assignments)
    if not byte_audit.valid:
        problems.extend(f"BYTE_AUDIT:{problem}" for problem in byte_audit.problems)
    try:
        reparsed = parse_entry_bytes(raw, source_name="baseline-output.csv")
        reconcile_template(reparsed, slate)
    except ValueError as exc:
        problems.append(f"BASELINE_AUDIT_REPARSE_FAILED:{exc}")
        return problems
    if [e.entry_id for e in reparsed.authorizations] != [e.entry_id for e in source.authorizations]:
        problems.append("BASELINE_AUDIT_ENTRY_ORDER_MISMATCH:the reparsed Entry IDs differ from the template's")
    filled = {e.entry_id: e.existing_cells for e in reparsed.authorizations if any(e.existing_cells)}
    blank = {e.entry_id for e in reparsed.authorizations if not any(e.existing_cells)}
    if filled != dict(assignments) or blank != set(unfilled):
        problems.append("REPARSE_ASSIGNMENT_MISMATCH:the reparsed rows are not the assigned and unfilled rows")
    by_id = {player.dk_id: player for player in slate.players}
    unavailable = unavailable_people(slate.players)
    keys: set[str] = set()
    for entry_id, roster in filled.items():
        result = validate_lineup(slate, roster)
        if result.lineup is None:
            problems.append(f"BASELINE_AUDIT_LINEUP_ILLEGAL:{entry_id}:{'; '.join(result.errors)}")
            continue
        if result.lineup.canonical_key in keys:
            problems.append(f"BASELINE_AUDIT_DUPLICATE_LINEUP:{entry_id}")
        keys.add(result.lineup.canonical_key)
        if unavailable.intersection(by_id[dk_id].underlying_id for dk_id in roster):
            problems.append(f"BASELINE_AUDIT_UNAVAILABLE_PERSON:{entry_id}")
    return problems


def _code(text: str, fallback: str) -> str:
    head = text.split(":", 1)[0].strip()
    return head if _CODE.fullmatch(head) else fallback


def _snapshot(source: Path, inputs: Path) -> tuple[Path, str]:
    digest = sha256_file(source)
    suffix = source.suffix.lower()
    if len(suffix) > 10 or not all(character.isalnum() or character == "." for character in suffix):
        suffix = ""
    target = inputs / f"{digest}{suffix}"
    if not target.exists():
        shutil.copyfile(source, target)
    if sha256_file(target) != digest:
        raise OSError(f"the snapshot of {source} does not hash to {digest}")
    return target, digest


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_baseline(
    *,
    salaries: str | Path,
    entries: str | Path,
    out_dir: str | Path,
    run_id: str | None = None,
    per_solve_seconds: float = DEFAULT_PER_SOLVE_SECONDS,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> BaselineOutcome:
    """Build, write, audit and report the baseline file for one pair of DraftKings files."""

    wall_start = time.perf_counter()
    started = clock()
    for name, value in (("per_solve_seconds", per_solve_seconds), ("budget_seconds", budget_seconds)):
        if not isinstance(value, (int, float)) or not 0 < float(value) < float("inf"):
            raise ValueError(f"{name} must be a positive number of seconds")
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    registry = load_gate_registry()
    supplied = {"--salaries": Path(salaries).resolve(), "--entries": Path(entries).resolve()}
    hashes = {flag: sha256_file(path) if path.is_file() else "UNREADABLE" for flag, path in supplied.items()}
    run_id = run_id or (
        f"baseline-{moment:%Y%m%dT%H%M%SZ}-"
        + sha256_bytes("|".join(hashes.values()).encode("ascii"))[:8]
    )
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be 1-80 ASCII letters, digits, hyphens or underscores")
    run_dir = Path(out_dir).resolve() / run_id
    limitations: list[DeliveryLimitation] = []
    report: dict[str, object] = {
        "schema_version": REPORT_VERSION,
        "generated_at": moment.isoformat(),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "gate_registry_sha256": registry.sha256,
        "command": {"per_solve_seconds": per_solve_seconds, "budget_seconds": budget_seconds},
        "objective": dict(OBJECTIVE),
        "checks_not_run": list(CHECKS_NOT_RUN),
        "warning": WARNING,
    }

    if run_dir.exists():
        limitations.append(registry.limitation(
            "RUN_ID_COLLISION", detail=f"{run_dir} exists; a baseline run never writes into an earlier run's folder"))
        return _finish(report, registry, limitations, run_dir=run_dir, write_report=False,
                       wall_start=wall_start)
    inputs = run_dir / "inputs"
    inputs.mkdir(parents=True)

    kinds: dict[str, str | None] = {}
    snapshots: dict[str, tuple[Path, str]] = {}
    for flag, path in supplied.items():
        try:
            kinds[flag] = classify_csv(path)
            snapshots[flag] = _snapshot(path, inputs)
        except (OSError, ValueError) as exc:
            kinds[flag] = None
            limitations.append(registry.limitation(
                "BASELINE_INPUT_UNREADABLE", detail=f"{flag} {path}: {type(exc).__name__}: {exc}"))
    by_kind = {kind: flag for flag, kind in kinds.items() if kind}
    report["inputs"] = {
        role: {
            "supplied_as": by_kind.get(kind),
            "path": str(supplied[by_kind[kind]]) if kind in by_kind else None,
            "sha256": snapshots[by_kind[kind]][1] if by_kind.get(kind) in snapshots else None,
            "snapshot": str(snapshots[by_kind[kind]][0]) if by_kind.get(kind) in snapshots else None,
            "classified_by": "SCHEMA",
        }
        for role, kind in (("salaries", "salary_csv"), ("entries", "entry_csv"))
    }
    report["inputs"]["supplied_schemas"] = {flag: kinds.get(flag) for flag in supplied}
    _write_json(run_dir / "intake.json", {
        key: report[key] for key in ("schema_version", "generated_at", "run_id", "inputs")})
    if set(by_kind) != {"salary_csv", "entry_csv"} or len(by_kind) != len(kinds):
        if not any(item.code == "BASELINE_INPUT_UNREADABLE" for item in limitations):
            limitations.append(registry.limitation(
                "BASELINE_INPUT_SCHEMA_UNRESOLVED",
                detail=f"one salary CSV and one entries CSV are required; by schema they are {kinds}"))
        return _finish(report, registry, limitations, run_dir=run_dir, wall_start=wall_start)

    salary_path, salary_hash = snapshots[by_kind["salary_csv"]]
    entries_path, entries_hash = snapshots[by_kind["entry_csv"]]
    try:
        slate = parse_salaries(salary_path)
        template = parse_entries(entries_path)
        reconcile_template(template, slate)
        pool = embedded_pool_ids(entries_path.read_bytes())
    except DraftKingsParseError as exc:
        limitations.append(registry.limitation(_code(str(exc), "INTAKE_FAILED"), detail=str(exc)))
        return _finish(report, registry, limitations, run_dir=run_dir, wall_start=wall_start)
    except (OSError, ValueError) as exc:
        limitations.append(registry.limitation("INTAKE_FAILED", detail=f"{type(exc).__name__}: {exc}"))
        return _finish(report, registry, limitations, run_dir=run_dir, wall_start=wall_start)

    salary_ids = {player.dk_id for player in slate.players}
    if pool is None:
        cross_check = "ABSENT"
        limitations.append(registry.limitation(
            "BASELINE_ENTRY_POOL_CROSS_CHECK_UNAVAILABLE",
            detail="the entries file carries no player table, so its draft group is not cross-checked"
                   " against the salary file's IDs"))
    elif set(pool) != salary_ids:
        cross_check = "MISMATCH"
        limitations.append(registry.limitation(
            "BASELINE_ENTRY_POOL_ID_MISMATCH",
            detail=f"{len(salary_ids - set(pool))} salary IDs are missing from the entries file's player"
                   f" table and {len(set(pool) - salary_ids)} of its IDs are missing from the salary file"))
    else:
        cross_check = "PASS"
    prefilled = tuple(e.entry_id for e in template.authorizations if any(e.existing_cells))
    authorized = tuple(e.entry_id for e in template.authorizations if not any(e.existing_cells))
    if prefilled:
        limitations.append(registry.limitation(
            "ENTRY_BLANK_CELL_AUTHORITY_REQUIRED", entry_ids=prefilled,
            detail="the template has prefilled rows; the baseline fills only a template whose authorized"
                   " rows are all blank, as prior_review does, until Session 11"))
    for problem in single_contest_problems(template):
        limitations.append(registry.limitation(_code(problem, "INTAKE_FAILED"), detail=problem))
    excluded_people = unavailable_people(slate.players)
    excluded_ids = tuple(sorted(p.dk_id for p in slate.players if p.underlying_id in excluded_people))
    report["slate"] = {
        "mode": slate.mode.value,
        "draft_group": slate.draft_group,
        "salary_sha256": salary_hash,
        "entries_sha256": entries_hash,
        "salary_rows": len(slate.players),
        "games": [game.game_id for game in slate.games],
        "earliest_lock_at": min(game.lock_at for game in slate.games).isoformat(),
        "entry_rows": len(template.authorizations),
        "blank_authorized_rows": len(authorized),
        "prefilled_rows": list(prefilled),
        "contest_ids": sorted({e.contest_id for e in template.authorizations}),
    }
    report["pool"] = {
        "availability_contract": "contracts.unavailable_people",
        "unavailable_statuses": sorted(UNAVAILABLE_DK_STATUSES),
        "excluded_people": sorted(excluded_people),
        "excluded_salary_rows": len(excluded_ids),
        "eligible_salary_rows": len(slate.players) - len(excluded_ids),
        "entry_pool_cross_check": cross_check,
    }
    if any(item.gate_class is GateClass.V for item in limitations):
        return _finish(report, registry, limitations, run_dir=run_dir, authorized=authorized,
                       wall_start=wall_start)

    built = build_distinct_lineups(
        slate,
        count=len(authorized),
        excluded_ids=excluded_ids,
        per_solve_seconds=per_solve_seconds,
        deadline=started + budget_seconds,
        clock=clock,
    )
    assignments = {entry_id: lineup.roster for entry_id, lineup in zip(authorized, built.lineups)}
    unfilled = authorized[len(assignments):]
    person = {player.dk_id: player.underlying_id for player in slate.players}
    uses = Counter(person[dk_id] for lineup in built.lineups for dk_id in lineup.roster)
    report["construction"] = {
        "stop_reason": built.stop_reason,
        "lineups_built": len(built.lineups),
        "solves": built.solves,
        "salary_levels": list(built.salary_levels),
        "people_used": len(uses),
        "most_used_person_lineups": max(uses.values(), default=0),
        "elapsed_seconds": round(time.perf_counter() - wall_start, 3),
    }
    report["lineups"] = [
        {"entry_id": entry_id, "roster": list(lineup.roster), "salary": lineup.salary,
         "found_by": lineup.found_by, "time_limited": lineup.time_limited,
         "solve_seconds": lineup.solve_seconds}
        for entry_id, lineup in zip(authorized, built.lineups)
    ]
    detail = f"{len(built.lineups)} distinct lineups built for {len(authorized)} blank rows"
    if built.stop_reason == "DISTINCT_LINEUPS_EXHAUSTED" and unfilled:
        limitations.append(registry.limitation(
            "BASELINE_DISTINCT_LINEUPS_EXHAUSTED", entry_ids=unfilled,
            detail=f"{detail}: the pool left after {len(excluded_people)} unavailable people holds no"
                   " other legal lineup, and R29 never repeats one"))
    elif built.stop_reason == "BUDGET_EXHAUSTED":
        limitations.append(registry.limitation(
            "BASELINE_RUN_BUDGET_EXHAUSTED", detail=f"{detail} inside the {budget_seconds} s run budget"))
    elif built.stop_reason == "SOLVE_LIMIT_WITHOUT_LINEUP":
        limitations.append(registry.limitation(
            "BASELINE_SOLVE_LIMIT_WITHOUT_LINEUP",
            detail=f"{detail}; a {per_solve_seconds} s solve found no further lineup"))
    elif built.stop_reason == "SOLVER_PRODUCED_ILLEGAL_LINEUP":
        limitations.append(registry.limitation(
            "SOLVER_PRODUCED_ILLEGAL_LINEUP", entry_ids=unfilled,
            detail=f"{detail}; the solver returned a lineup the shared validator refused"))
    elif built.stop_reason == "SOLVER_REPEATED_A_LINEUP":
        limitations.append(registry.limitation(
            "DUPLICATE_LINEUP_SELECTED", entry_ids=unfilled,
            detail=f"{detail}; the solver returned an exact roster already chosen, which R29 refuses"))
    if not assignments:
        return _finish(report, registry, limitations, run_dir=run_dir, authorized=authorized,
                       wall_start=wall_start)

    output = run_dir / f"{OUTPUT_PREFIX}{run_id}.csv"
    written = _write_audited(
        output, template=template, salary_path=salary_path, entries_path=entries_path,
        salary_hash=salary_hash, assignments=assignments, unfilled=unfilled, registry=registry,
        limitations=limitations, report=report)
    return _finish(report, registry, limitations, run_dir=run_dir, authorized=authorized,
                   assignments=assignments if written else {}, output=output if written else None,
                   wall_start=wall_start)


def _write_audited(
    output: Path,
    *,
    template: EntryTemplate,
    salary_path: Path,
    entries_path: Path,
    salary_hash: str,
    assignments: Mapping[str, tuple[str, ...]],
    unfilled: tuple[str, ...],
    registry: GateRegistry,
    limitations: list[DeliveryLimitation],
    report: dict[str, object],
) -> bool:
    """Write the bytes only once the independent audit passes the copy on disk."""

    report["audit"] = {"status": "NOT_RUN", "problems": []}
    if sha256_file(entries_path) != template.raw_hash:
        limitations.append(registry.limitation(
            "ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE", detail=f"{entries_path} changed during the run"))
        return False
    if sha256_file(salary_path) != salary_hash:
        limitations.append(registry.limitation(
            "SALARY_CHANGED_BEFORE_ARTIFACT_PUBLISH", detail=f"{salary_path} changed during the run"))
        return False
    try:
        raw = write_upload_bytes(template, assignments, unfilled=unfilled)
    except (OSError, ValueError) as exc:
        limitations.append(registry.limitation(
            "FILE_CONSTRUCTION_FAILED", detail=f"{type(exc).__name__}: {exc}"))
        return False
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(raw)
    on_disk = temporary.read_bytes()
    problems = audit_baseline_bytes(on_disk, salary_path=salary_path, entries_path=entries_path,
                                    assignments=assignments, unfilled=unfilled)
    report["audit"] = {
        "status": "FAIL" if problems else "PASS",
        "problems": problems,
        "checks_run": [
            "SNAPSHOT_HASHES_UNCHANGED",
            "INDEPENDENT_BYTE_AUDIT_AGAINST_THE_TEMPLATE",
            "REPARSE_OF_THE_WRITTEN_BYTES",
            "ENTRY_ID_ORDER_AND_COVERAGE",
            "SHARED_VALIDATOR_ON_EVERY_REPARSED_ROW",
            "EXACT_ROSTER_DISTINCTNESS",
            "NO_UNAVAILABLE_PERSON",
            "POST_WRITE_SHA256",
        ],
    }
    if problems:
        temporary.unlink(missing_ok=True)
        for problem in problems:
            limitations.append(registry.limitation(_code(problem, "BYTE_AUDIT"), detail=problem))
        return False
    digest = sha256_bytes(on_disk)
    temporary.replace(output)
    if sha256_file(output) != digest:
        output.unlink(missing_ok=True)
        limitations.append(registry.limitation(
            "POST_WRITE_HASH_MISMATCH", detail=f"{output} does not hash to the audited {digest}"))
        return False
    report["output"] = {
        "path": str(output),
        "sha256": digest,
        "bytes": len(on_disk),
        "contract_version": OUTPUT_CONTRACT,
        "filled_rows": len(assignments),
        "unfilled_rows": list(unfilled),
    }
    return True


def _finish(
    report: dict[str, object],
    registry: GateRegistry,
    limitations: list[DeliveryLimitation],
    *,
    run_dir: Path,
    wall_start: float,
    authorized: tuple[str, ...] = (),
    assignments: Mapping[str, tuple[str, ...]] | None = None,
    output: Path | None = None,
    write_report: bool = True,
) -> BaselineOutcome:
    """The five truths from what happened, the report beside the file, and the outcome."""

    assignments = dict(assignments or {})
    limitations += [
        registry.limitation(
            "OFFICIAL_STATUS_REQUIRED",
            detail="the baseline reads the DraftKings bytes alone: only DraftKings' own OUT, IR and D"
                   " flags were applied, and no official activity evidence was consulted"),
        registry.limitation(
            "OFFENSIVE_CURRENT_ROLE_UNRESOLVED", detail="no current-role evidence was consulted"),
        registry.limitation(
            "WEATHER_CAPTURE_REQUIRED",
            detail="no weather was captured; whether any game needs it is not established here"),
        registry.limitation(
            "MODEL_NOT_PROSPECTIVELY_VALIDATED",
            detail="salary rank is a cold-start prior, not a validated model"),
    ]
    file_valid = output is not None
    policy = derive_release_policy(
        file_valid=file_valid,
        evidence_state=ReleaseEvidenceState.UNKNOWN,
        model_status=ModelStatus.PRIOR_ONLY,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
        file_blockers=[item.code for item in limitations if item.gate_class is GateClass.V],
        evidence_blockers=["OFFICIAL_STATUS_REQUIRED", "OFFENSIVE_CURRENT_ROLE_UNRESOLVED",
                           "WEATHER_CAPTURE_REQUIRED"],
    )
    delivery = derive_delivery_state(
        file_valid=file_valid,
        authorized_entry_ids=authorized,
        delivered_entry_ids=tuple(assignments) if file_valid else (),
        limitations=limitations,
    )
    truths = release_truths_v2(policy, delivery)
    report["release_truths"] = truths.model_dump(mode="json", by_alias=True)
    report["status"] = policy.status
    report.setdefault("output", None)
    report["timing"] = {"wall_seconds": round(time.perf_counter() - wall_start, 3)}
    report_path = run_dir / "baseline_report.json" if write_report else None
    if report_path is not None:
        _write_json(report_path, report)
    digest = report["output"]["sha256"] if isinstance(report["output"], dict) else None
    return BaselineOutcome(
        run_id=str(report["run_id"]),
        run_dir=run_dir,
        report_path=report_path,
        output_path=output,
        output_sha256=digest,
        truths=truths,
        assignments=assignments,
        report=report,
    )


def summary(outcome: BaselineOutcome) -> dict[str, object]:
    """What `nfl baseline` prints: the truths, the file, the unfilled rows, the gaps."""

    truths = outcome.truths
    return {
        "status": outcome.report.get("status", "DO_NOT_UPLOAD"),
        "command": "baseline",
        "FILE_VALID": truths.file_valid,
        "EVIDENCE_STATE": truths.evidence_state.value,
        "MODEL_STATUS": truths.model_status.value,
        "RELEASE_DECISION": truths.release_decision.value,
        "DELIVERY_STATE": truths.delivery_state.value,
        "baseline_entry_csv": str(outcome.output_path) if outcome.output_path else None,
        "baseline_entry_sha256": outcome.output_sha256,
        "delivered_rows": len(truths.delivered_entry_ids),
        "unfilled_entry_ids": list(truths.unfilled_entry_ids),
        "limitations": [
            {"code": item.code, "class": item.gate_class.value, "stops": item.stops.value,
             "entry_ids": list(item.entry_ids), "detail": item.detail}
            for item in truths.delivery_limitations
        ],
        "report": str(outcome.report_path) if outcome.report_path else None,
        "run_dir": str(outcome.run_dir),
        "wall_seconds": outcome.report.get("timing", {}).get("wall_seconds"),
        "warning": WARNING,
    }
