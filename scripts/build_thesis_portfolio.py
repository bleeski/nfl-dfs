#!/usr/bin/env python3
"""Multi-thesis Classic portfolio: construction only. NOT the evidence layer.

Provenance: generalizes `scripts/staging/slate_2026_09_27/build_theses.py`,
which built the Week 3 24-lineup thesis portfolio by calling
`scripts/build_classic_portfolio.py` once per thesis and seed, then selecting
across every thesis's candidates under a global cap. This turns its five
hardcoded theses (market-tilt, storm-proof indoor, storm-bust shootout,
underdog flip, and a salary-ranked "priors wrong" fade) into a JSON config any
slate can supply, and fixes the one bug that slipped through that session: a
reused `--out` path whose builder call refused (`OUTPUT_EXISTS`) went
unchecked, so a later thesis silently read an earlier one's stale file. Every
builder call here gets a path this process has never used before, named by a
monotonic counter no config or retry can collide with, and its exit code is
checked before the file is opened at all.

Each thesis is a variant of the same slate: its own team-total table (the
supplied market totals, a two-team-swapped "flip", a named "bust" override, or
a flat number), an optional QB-team restriction, an optional "only these teams
may start a DST" restriction, and a per-team-and-position score multiplier
(passed to the builder as `role_boosts`, exactly as it already reads them).
A trailing "priors wrong" thesis is built from the OTHER theses' own most-used
players: the `fade_count` most-rostered (DST excluded) are removed, and the
surviving pool is scored by salary alone against a flat team-total table --
the thesis that the market, not the prior, is wrong.

Every candidate lineup from every thesis and seed then competes in one global,
round-robin selection: quota per thesis, a global exposure cap, a global
overlap cap, and a per-thesis cap on lineups sharing a QB. Selection ranks by
the *un-boosted* gated score, so a thesis's own tilt never contaminates which
of its own candidates looks best.

Session 62 (R37): unused salary is never a defect, so no builder call gets a salary floor
unless the operator passes `--min-salary` (the default was 48500), and the fill step then
takes salary-driven swaps ONLY as Pareto gains: `swap_inactives.redeploy` runs on the
assigned rows (a swap must raise the row's prior and leave every washout proxy no worse,
never touching the QB, the DST, the stack, the bring-back or a `--protect` person; the priors-wrong
thesis's rows are left alone, since the pass ranks by the prior that thesis bets against; the report
is `construction.pareto_redeploy`). `--protect-from` reads a Classic run's
`judgment_pass.protected_people`. The pass never costs the portfolio: if it cannot run, the
selection ships unchanged with `NOT_RUN` and the reason named. `--no-pareto-redeploy` skips it.

Exit codes: 0 every fillable Entry ID got a lineup; 3 written with a
shortfall, each one named on stderr (R29: never a repeated lineup to close
it); 2 refused by name, nothing written.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3
CONFIG_SCHEMA = "nfl_dfs_thesis_portfolio_config_v1"
DEFAULT_MULTIPLIER = 3
CLASSIC_CAP = 50000
# The thesis built by salary alone against the prior ("the market, not the prior, is wrong"): a redeploy that
# ranks by the prior would undo it, so the Pareto pass leaves its rows alone.
PRIORS_WRONG_NAME = "PRIORS_WRONG_SALARY_FLAT"


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


def load_config(path: str) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != CONFIG_SCHEMA:
        raise Refused("CONFIG_SCHEMA_MISMATCH", f"{path} is not a {CONFIG_SCHEMA} document")
    if not doc.get("theses"):
        raise Refused("CONFIG_HAS_NO_THESES", f"{path} names no theses")
    for thesis in doc["theses"]:
        if "name" not in thesis or "quota" not in thesis:
            raise Refused("THESIS_MISSING_FIELD", f"{thesis} needs name and quota")
    return doc


def load_scores(path: str) -> dict[str, float]:
    try:
        with open(path, encoding="utf-8") as handle:
            by_id = json.load(handle)["by_dk_id"]
        return {str(k): float(v) for k, v in by_id.items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused("SCORES_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")


def load_salaries(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sal = {row["ID"]: row for row in rows if row.get("ID")}
    if not sal:
        raise Refused("SALARIES_EMPTY", f"{path} has no readable rows")
    return sal


def load_slate_context_totals(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in (doc.get("implied_team_totals") or {}).items()}


def read_entries_template(path: str) -> list[str]:
    """Blank, wide-enough Entry IDs, in template order (Classic: 9 roster cells)."""

    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0] if rows else []
    if "Entry Fee" not in header:
        raise Refused("NOT_A_CLASSIC_TEMPLATE", f"{path} has no Entry Fee column")
    fee = header.index("Entry Fee")
    end = fee + 1 + 9
    blank = []
    for row in rows[1:]:
        entry_id = row[0].strip() if row else ""
        if not entry_id.isdigit():
            continue
        cells = [c.strip() for c in row[fee + 1:end]] if len(row) >= end else []
        if len(row) >= end and not any(cells):
            blank.append(entry_id)
    if not blank:
        raise Refused("NO_BLANK_ENTRY_ROWS", f"{path} has no blank authorized row wide enough to fill")
    return blank


# --------------------------------------------------------------------------- #
# Team-total variants and per-thesis score subsets
# --------------------------------------------------------------------------- #


def team_totals_variant(kind: str, market: dict, config: dict) -> dict[str, float]:
    if kind == "market":
        return dict(market)
    if kind == "flip":
        flipped = dict(market)
        for a, b in config.get("flip_pairs") or ():
            if a in market and b in market:
                flipped[a], flipped[b] = market[b], market[a]
        return flipped
    if kind == "bust":
        bust = dict(market)
        bust.update({str(k): float(v) for k, v in (config.get("bust_overrides") or {}).items()})
        return bust
    if kind.startswith("flat"):
        value = float(config.get("flat_team_total", 22.5))
        return {team: value for team in market}
    raise Refused("TEAM_TOTALS_KIND_UNKNOWN", kind)


def thesis_scores(base_scores: dict[str, float], sal: dict, thesis: dict) -> dict[str, float]:
    restrict_qb = thesis.get("restrict_qb_teams")
    dst_teams = thesis.get("exclude_dst_unless_teams")
    out = {}
    for dk_id, score in base_scores.items():
        row = sal.get(dk_id)
        if row is None:
            continue
        position, team = row["Position"], row["TeamAbbrev"]
        if position == "QB" and restrict_qb is not None and team not in restrict_qb:
            continue
        if position == "DST" and dst_teams is not None and team not in dst_teams:
            continue
        out[dk_id] = score
    return out


def thesis_role_boosts(sal: dict, multipliers: dict) -> dict[str, float]:
    """`{team: {position: multiplier}}` -> `{Name: multiplier}`, the shape
    `build_classic_portfolio.py --slate-context` already reads."""

    boosts = {}
    for dk_id, row in sal.items():
        team_multipliers = multipliers.get(row["TeamAbbrev"])
        if not team_multipliers:
            continue
        multiplier = team_multipliers.get(row["Position"])
        if multiplier is not None and multiplier != 1.0:
            boosts[row["Name"]] = float(multiplier)
    return boosts


# --------------------------------------------------------------------------- #
# Builder invocation: a fresh --out per call, exit code checked before reading.
# --------------------------------------------------------------------------- #

_OUT_PATHS = itertools.count()


def run_builder(
    a, work_dir: Path, *, label: str, scores: dict, team_totals: dict, role_boosts: dict,
    lineups: int, seed: int, max_overlap: int, runner=subprocess.run,
) -> list[list[str]]:
    """One `build_classic_portfolio.py` call. Returns its distinct rosters, or
    `[]` if the call did not exit 0 or 3 -- never reads a path this call did
    not itself just write."""

    index = next(_OUT_PATHS)
    scores_path = work_dir / f"{index:05d}_{label}_scores.json"
    ctx_path = work_dir / f"{index:05d}_{label}_ctx.json"
    out_path = work_dir / f"{index:05d}_{label}_out.json"
    for path in (scores_path, ctx_path, out_path):
        if path.exists():
            raise Refused("STALE_WORK_PATH", f"{path} already exists; refusing to reuse it")
    scores_path.write_text(json.dumps({"by_dk_id": scores}), encoding="utf-8")
    ctx_path.write_text(
        json.dumps({"implied_team_totals": team_totals, "projected_ownership": {}, "role_boosts": role_boosts}),
        encoding="utf-8",
    )
    command = [
        a.python, a.builder,
        "--scores", str(scores_path), "--salaries", a.salaries, "--status", a.status,
        "--slate-context", str(ctx_path), "--lineups", str(lineups), "--out", str(out_path),
        "--max-exposure", str(max(3, lineups * 2 // 5)), "--max-overlap", str(max_overlap),
        "--min-salary", str(a.min_salary), "--seed", str(seed),
    ]
    if a.require_bringback:
        command.append("--require-bringback")
    result = runner(command, capture_output=True, text=True)
    if result.returncode not in (0, 3):
        print(
            f"BUILDER_REFUSED {label} seed={seed}: exit {result.returncode}: "
            f"{(result.stderr or '')[-400:]}",
            file=sys.stderr,
        )
        return []
    if not out_path.exists():
        raise Refused("BUILDER_WROTE_NOTHING", f"{label} seed={seed} exited {result.returncode} with no {out_path}")
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    return [lineup["roster"] for lineup in doc.get("lineups", [])]


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def select_portfolio(candidates_by_thesis: dict, base_scores: dict, quotas: dict, *,
                      max_exposure: int, max_overlap: int, per_thesis_qb_cap: int, sal: dict):
    def qb_of(roster):
        return next((dk_id for dk_id in roster if sal.get(dk_id, {}).get("Position") == "QB"), None)

    def score_of(roster):
        return sum(base_scores.get(dk_id, 0.0) for dk_id in roster)

    pools = {
        thesis: sorted(
            {frozenset(roster): roster for roster in rosters}.values(),
            key=score_of, reverse=True,
        )
        for thesis, rosters in candidates_by_thesis.items()
    }
    chosen: list[list[str]] = []
    tags: list[str] = []
    exposure: collections.Counter = collections.Counter()
    qb_per_thesis: collections.Counter = collections.Counter()
    seen: set[frozenset] = set()
    progress = True
    total_target = sum(quotas.values())
    while progress and len(chosen) < total_target:
        progress = False
        for thesis, quota in quotas.items():
            if sum(1 for tag in tags if tag == thesis) >= quota:
                continue
            for roster in pools.get(thesis, []):
                key = frozenset(roster)
                if key in seen:
                    continue
                if any(exposure[dk_id] + 1 > max_exposure for dk_id in roster):
                    continue
                if any(len(key & frozenset(existing)) > max_overlap for existing in chosen):
                    continue
                qb = qb_of(roster)
                if qb is not None and qb_per_thesis[(thesis, qb)] >= per_thesis_qb_cap:
                    continue
                chosen.append(roster)
                tags.append(thesis)
                seen.add(key)
                exposure.update(roster)
                if qb is not None:
                    qb_per_thesis[(thesis, qb)] += 1
                progress = True
                break
    return chosen, tags


# --------------------------------------------------------------------------- #
# The Pareto pass at the fill step (Session 62, R37)
# --------------------------------------------------------------------------- #


def _swap_module():
    """`scripts/swap_inactives.py`, which owns the Classic legality mirror and the Pareto rule this step
    uses. Loaded by sibling path, and reused when a test or another script already loaded it."""

    existing = sys.modules.get("swap_inactives")
    if existing is not None and hasattr(existing, "redeploy"):
        return existing
    spec = importlib.util.spec_from_file_location(
        "swap_inactives", Path(__file__).resolve().parent / "swap_inactives.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["swap_inactives"] = module
    spec.loader.exec_module(module)
    return module


def resolve_protected(a) -> dict:
    """`{dk_id: name}` for `--protect` and `--protect-from`. A refusal is the operator's own typo, so it
    stops the build before any builder call rather than quietly protecting nobody."""

    tokens = list(getattr(a, "protect", None) or [])
    source = getattr(a, "protect_from", None)
    if not tokens and not source:
        return {}
    swap = _swap_module()
    try:
        return swap.resolve_protect(
            swap.load_salaries(a.salaries), tokens, swap.load_protected_from(source) if source else [])
    except swap.Refused as exc:
        raise Refused(exc.code, exc.detail)


def pareto_redeploy_pass(a, assignments, base_scores, protect, *, entry_ids, max_exposure, max_overlap) -> dict:
    """Salary-driven swaps on the assigned rows, taken only as Pareto gains (`swap_inactives.redeploy`: the
    row's prior rises, no washout proxy is worse, the QB, DST, stack, bring-back and every protected person
    stay). Only `entry_ids` are considered (every row but the priors-wrong thesis's), though every row counts in
    the proxies; an explicit `--min-salary` is honored like the builder honors it. Edits `assignments` only
    when it finishes. Never fatal (the lock-clock ruling: the file ships and the gap is named): a pass that
    cannot run leaves the selection as it was and says why."""

    if not getattr(a, "pareto_redeploy", True):
        return {"state": "DISABLED", "reason": "--no-pareto-redeploy"}
    try:
        short = sorted(eid for eid, roster in assignments.items() if len(roster) != 9)
        if short:
            raise ValueError(f"ROSTERS_NOT_NINE_CELLS: {short[:5]}")
        swap = _swap_module()
        sal = swap.load_salaries(a.salaries)
        trial = {eid: list(roster) for eid, roster in assignments.items()}
        _log, report = swap.redeploy(
            swap.Board(sal, CLASSIC_CAP, int(getattr(a, "min_salary", 0) or 0)), base_scores, trial, list(entry_ids),
            protect=protect, gated=swap.load_gated(a.scores, sal) | swap.load_inactive_ids(a.status),
            max_exposure=max_exposure, max_overlap=max_overlap,
        )
        assignments.update(trial)
        report["left_alone"] = {PRIORS_WRONG_NAME: sorted(set(assignments) - set(entry_ids))}
        return report
    except Exception as exc:  # noqa: BLE001 - see the docstring
        reason = f"{type(exc).__name__}: {exc}"
        print(f"PARETO_REDEPLOY_NOT_RUN {reason}", file=sys.stderr)
        return {"state": "NOT_RUN", "reason": reason}


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def write_new(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused("VERIFICATION_FAILED", "temporary file does not hold the portfolio bytes")
        if out.exists():
            raise Refused("OUTPUT_EXISTS", f"{out} appeared while building")
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def parse_excluded_entries(pairs: list[str]) -> dict[str, str]:
    excluded = {}
    for pair in pairs:
        entry_id, _, reason = pair.partition(":")
        excluded[entry_id.strip()] = reason.strip() or "operator excluded"
    return excluded


def build(a, *, runner=subprocess.run) -> dict:
    out = Path(a.out)
    if out.exists():
        raise Refused("OUTPUT_EXISTS", f"{a.out} already exists; an earlier portfolio is never overwritten")
    protect = resolve_protected(a)
    work_dir = Path(a.work_dir)
    if work_dir.exists():
        raise Refused("WORK_DIR_EXISTS", f"{a.work_dir} already exists; every run gets a fresh scratch directory")
    work_dir.mkdir(parents=True)

    config = load_config(a.config)
    base_scores = {k: v for k, v in load_scores(a.scores).items() if v > 0}
    sal = load_salaries(a.salaries)
    market = load_slate_context_totals(a.slate_context) or {
        str(k): float(v) for k, v in (config.get("market_team_totals") or {}).items()
    }
    if not market:
        raise Refused("NO_TEAM_TOTALS", "pass --slate-context, or put market_team_totals in the config")

    seeds = config.get("seeds") or [913]
    multiplier = int(config.get("lineups_per_thesis_multiplier", DEFAULT_MULTIPLIER))
    global_cfg = config.get("global") or {}
    max_exposure = a.max_exposure if a.max_exposure is not None else int(global_cfg.get("max_exposure", 7))
    max_overlap = a.max_overlap if a.max_overlap is not None else int(global_cfg.get("max_overlap", 5))
    per_thesis_qb_cap = (
        a.per_thesis_qb_cap if a.per_thesis_qb_cap is not None
        else int(global_cfg.get("per_thesis_qb_cap", 2))
    )

    quotas: dict[str, int] = {}
    candidates: dict[str, list[list[str]]] = {}
    for thesis in config["theses"]:
        name, quota = thesis["name"], int(thesis["quota"])
        quotas[name] = quota
        totals = team_totals_variant(thesis.get("team_totals", "market"), market, config)
        scores = thesis_scores(base_scores, sal, thesis)
        boosts = thesis_role_boosts(sal, thesis.get("score_multipliers") or {})
        rosters: list[list[str]] = []
        for seed in seeds:
            rosters.extend(run_builder(
                a, work_dir, label=name, scores=scores, team_totals=totals, role_boosts=boosts,
                lineups=quota * multiplier, seed=seed, max_overlap=max_overlap, runner=runner,
            ))
        candidates[name] = rosters

    priors_wrong = config.get("priors_wrong")
    faded: list[str] = []
    if priors_wrong:
        heavy = collections.Counter(
            dk_id for rosters in candidates.values() for roster in rosters for dk_id in roster
        )
        fade_count = int(priors_wrong.get("fade_count", 12))
        faded = [
            dk_id for dk_id, _n in heavy.most_common(fade_count * 4)
            if sal.get(dk_id, {}).get("Position") != "DST"
        ][:fade_count]
        name, quota = PRIORS_WRONG_NAME, int(priors_wrong.get("quota", 4))
        quotas[name] = quota
        salary_scores = {
            dk_id: float(row["Salary"]) / 1000.0
            for dk_id, row in sal.items()
            if dk_id in base_scores and dk_id not in faded
        }
        flat_totals = team_totals_variant("flat", market, config)
        rosters = []
        for seed in seeds:
            rosters.extend(run_builder(
                a, work_dir, label=name, scores=salary_scores, team_totals=flat_totals, role_boosts={},
                lineups=quota * multiplier, seed=seed, max_overlap=max_overlap, runner=runner,
            ))
        candidates[name] = rosters

    chosen, tags = select_portfolio(
        candidates, base_scores, quotas,
        max_exposure=max_exposure, max_overlap=max_overlap,
        per_thesis_qb_cap=per_thesis_qb_cap, sal=sal,
    )

    excluded_entries = parse_excluded_entries(a.exclude_entry_id)
    fillable = [eid for eid in read_entries_template(a.entries) if eid not in excluded_entries]
    assignments = {eid: roster for eid, roster in zip(fillable, chosen)}
    pareto = pareto_redeploy_pass(
        a, assignments, base_scores, protect, max_exposure=max_exposure, max_overlap=max_overlap,
        entry_ids=[eid for eid, tag in zip(assignments, tags) if tag != PRIORS_WRONG_NAME])
    final = list(assignments.values()) + chosen[len(assignments):]
    unfilled = [eid for eid in fillable if eid not in assignments] + list(excluded_entries)

    doc = {
        "lineups": [
            {
                "index": n + 1,
                "roster": roster,
                "thesis": tag,
                "salary": sum(int(sal[dk_id]["Salary"]) for dk_id in roster),
                "prior_points": round(sum(base_scores.get(dk_id, 0.0) for dk_id in roster), 3),
            }
            for n, (roster, tag) in enumerate(zip(final, tags))
        ],
        "assignments_by_entry_id": assignments,
        "unfilled_entry_ids": unfilled,
        "operator_excluded_entry_ids": excluded_entries,
        "construction": {
            "theses": quotas,
            "faded_in_priors_wrong": sorted(sal[dk_id]["Name"] for dk_id in faded if dk_id in sal),
            "max_exposure": max_exposure,
            "max_overlap": max_overlap,
            "per_thesis_qb_cap": per_thesis_qb_cap,
            "seeds": seeds,
            "candidates_generated": {name: len(rosters) for name, rosters in candidates.items()},
            "pareto_redeploy": pareto,
        },
    }
    data = json.dumps(doc, indent=1).encode("utf-8")
    write_new(out, data)
    return {
        "unfilled": unfilled,
        "built": len(chosen),
        "asked": len(fillable),
        "pareto": pareto,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv=None, *, runner=subprocess.run) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scores", required=True, help="gated pool scores json, read as ['by_dk_id']")
    ap.add_argument("--salaries", required=True, help="DKSalaries.csv")
    ap.add_argument("--status", required=True, help="official_status.csv")
    ap.add_argument("--entries", required=True, help="DKEntries template; its blank rows are the reserved Entry IDs")
    ap.add_argument("--config", required=True, help="thesis config json")
    ap.add_argument("--slate-context", help="scripts/make_slate_context.py output; implied_team_totals")
    ap.add_argument("--work-dir", required=True, help="scratch directory for builder calls; must not exist")
    ap.add_argument("--out", required=True, help="portfolio json to write; a new path, never an input")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--builder", default=str(Path(__file__).resolve().parent / "build_classic_portfolio.py"))
    ap.add_argument("--exclude-entry-id", action="append", default=[],
                    help="ENTRY_ID:REASON, left unfilled and named on purpose")
    ap.add_argument("--max-exposure", type=int, default=None)
    ap.add_argument("--max-overlap", type=int, default=None)
    ap.add_argument("--per-thesis-qb-cap", type=int, default=None)
    ap.add_argument("--min-salary", type=int, default=0,
                    help="a salary floor for every builder call; default none: unused salary is never a defect (R37)")
    ap.add_argument("--protect", action="append", default=[],
                    help="a DraftKings ID or exact name the Pareto pass never moves (repeatable)")
    ap.add_argument("--protect-from",
                    help="a run-slate cowork_run.json or Classic coverage JSON: protect judgment_pass.protected_people")
    ap.add_argument("--no-pareto-redeploy", dest="pareto_redeploy", action="store_false", default=True,
                    help="skip the salary-driven Pareto pass at the fill step")
    ap.add_argument("--require-bringback", action="store_true", default=True)
    ap.add_argument("--no-require-bringback", dest="require_bringback", action="store_false")
    a = ap.parse_args(argv)
    try:
        result = build(a, runner=runner)
    except Refused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED
    print(f"built {result['built']} of {result['asked']} fillable entries")
    if result["pareto"].get("rule"):
        print("\n".join(_swap_module().render_pareto_report(result["pareto"])))
    else:
        print(f"pareto redeploy: {result['pareto']['state']} ({result['pareto']['reason']})")
    print(f"sha256: {result['sha256']}")
    print(f"wrote: {a.out}")
    if result["unfilled"]:
        print(
            f"UNFILLED_AUTHORIZED_ROWS: {len(result['unfilled'])} blank authorized rows have no lineup: "
            f"{result['unfilled']}",
            file=sys.stderr,
        )
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
