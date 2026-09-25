#!/usr/bin/env python3
"""Generate a C2 Classic portfolio policy with structure that is actually enforced.

The registered template's defaults are the worst configuration this engine
supports: all four stack rules ship `ADVISORY` with `minimum_entries: 0`, which
the solver does not enforce, and `default_search_limits` asks for
`max(32, entries + 24)` candidates out of a several-hundred-person Classic pool.
Measured on the supplied 719-person fixture at a 1000-candidate bank, 828 of
1000 generated candidates were `NAKED_QB`. A portfolio built from that bank is
legal, audited, and close to the worst shape available for a large-field GPP.

This writes the policy that turns the machinery on: QB pass-catcher and
bring-back rules at `HARD` strength with real `minimum_entries`, a candidate
bank sized to the pool rather than to the entry count, and exposure and overlap
caps that scale with the portfolio.

RUNGS. Hard structure can make the joint solve infeasible, and a portfolio that
never gets built is a worse outcome than an imperfect one: an imperfect lineup
can be late-swapped, a missed lock cannot be recovered. So the policy is emitted
at a requested rung, and each rung relaxes exactly one class of CONSTRUCTION
preference. The table lives in `src/nfl_dfs/relaxation.py` (Session 10), which
`run-slate` walks itself; this script is a thin wrapper that writes one rung:

  0  every entry stacks QB + pass catcher; 70% carry a bring-back; overlap 5;
     player exposure <= 50% of entries
  1  bring-back drops to 34% of entries
  2  bring-back drops to ADVISORY; overlap 6; player exposure <= 65%
  3  QB pass-catcher holds on half the entries; overlap 7; no exposure caps
  4  emit nothing; run C1 with no policy at all, which is the proven floor

Rung 4 is the floor: C1 needs no policy, and when it runs out of distinct
lineups the baseline stays the file with its unfilled Entry IDs named (R29).
Since Session 10 `run-slate` walks down the ladder inside one run when a C2
bank or joint solve fails on a trigger, and records every step; this script is
for writing the rung-0 policy it starts from, or one rung by hand.

NOTHING ON THIS LADDER TOUCHES EVIDENCE. Official activity, current role,
weather, identity, expiry and hash binding are truth claims and are not
construction preferences. They are never relaxed here or anywhere else.

THE LOCK CLOCK (R31, Session 07b). The bank is sized to the time `run-slate`
will have, not only to `--minutes`. The delivery deadline is
`--delivery-deadline-utc`, or the earliest lock minus 5 minutes; the improvement
stops `config/runtime.json`'s reserve before it, as `run-slate`'s does. The
declared bank budget plus the joint solve stay within 75% of the window left
(the joint solve at most 20% of it), at this host's measured seconds per
candidate (`--host-rates`, the slowest of its last five Classic banks) or
0.28 s when it has none. When even the floor bank does not fit, or the window
has already closed, it writes nothing and exits 2, naming rung 4 or saying the
baseline is the file. A replay of a past slate passes a later
`--delivery-deadline-utc`.

SUBSETS (Session 11b). `--entry-id`, repeatable, binds only those rows, in
template order; each must be a fillable blank row. The rung table and the bank
count the bound rows, and the validator accepts the policy. In run-slate C2
fills the bound rows and C1 the rest, with every C2 lineup and prefilled roster
a no-good (Session 11c); C3's package names each row's source.

Example:

    python scripts/make_classic_policy.py \\
        --salaries <run>/inputs/DKSalaries.csv \\
        --entries  <run>/inputs/DKEntries.csv \\
        --out      <run>/policy/classic_portfolio_policy.json \\
        --rung 0
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from nfl_dfs.classic_portfolio_policy import classic_portfolio_policy_template
from nfl_dfs.deadline import SOLVE_MINIMUM_SECONDS, Budget, read_candidate_rate, runtime_stop_minutes
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.relaxation import (
    DEFAULT_SECONDS_PER_CANDIDATE,
    GENERATION_HEADROOM,
    JOINT_SHARE,
    ROSTER_SIZE,
    WINDOW_SHARE,
    BankDoesNotFit,
    classic_exposure_fraction,
    classic_limits,
    classic_overlap,
    classic_rung_controls,
    classic_stack_rules,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_JSON = REPO_ROOT / "config" / "runtime.json"
DEFAULT_HOST_RATES = REPO_ROOT / "data" / "runs" / "host_candidate_rates.json"

# The rung table's names before it moved to `nfl_dfs.relaxation` (Session 10).
_stack_rules = classic_stack_rules
_overlap = classic_overlap
_exposure_fraction = classic_exposure_fraction
_limits = classic_limits
__all__ = ["BankDoesNotFit", "DEFAULT_SECONDS_PER_CANDIDATE", "GENERATION_HEADROOM", "JOINT_SHARE",
           "WINDOW_SHARE", "main"]


def _rate(path: Path) -> tuple[float, str]:
    """This host's seconds per Classic candidate, and where the number came from."""

    measured = read_candidate_rate(path, mode="CLASSIC")
    if measured is None:
        return DEFAULT_SECONDS_PER_CANDIDATE, (
            f"{DEFAULT_SECONDS_PER_CANDIDATE:g} s per candidate (the default: {path} holds no"
            " Classic rate for this host)")
    seconds = float(measured["seconds_per_candidate"])
    return seconds, (
        f"{seconds:g} s per candidate (this host's slowest of its last"
        f" {measured['observations']} Classic banks, {path})")


def _bound(fillable: "tuple[str, ...]", requested: "list[str]") -> "tuple[str, ...]":
    """The rows `--entry-id` names, in template order (Session 11b); every fillable row without it."""

    if not requested:
        return tuple(fillable)
    wanted = [str(item).strip() for item in requested]
    repeated = sorted({item for item in wanted if wanted.count(item) > 1})
    if repeated:
        raise SystemExit(f"ENTRY_ID_REPEATED: {repeated}")
    outside = [item for item in wanted if item not in set(fillable)]
    if outside:
        raise SystemExit(
            f"ENTRY_ID_NOT_FILLABLE: {outside} are not fillable blank rows of the template (a prefilled,"
            f" partly filled, unresolved or unknown row is never bound); fillable: {list(fillable)}")
    return tuple(item for item in fillable if item in set(wanted))


def main(argv: "list[str] | None" = None, *, wall: "Callable[[], datetime] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salaries", required=True)
    parser.add_argument("--entries", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rung", type=int, default=0, choices=(0, 1, 2, 3, 4))
    parser.add_argument(
        "--minutes",
        type=float,
        default=4.0,
        help="wall-clock minutes to spend generating candidates (default 4)",
    )
    parser.add_argument(
        "--delivery-deadline-utc",
        default=None,
        help="aware ISO-8601 delivery deadline (default: the earliest lock minus 5 minutes);"
             " the bank fits the window before the improvement stops",
    )
    parser.add_argument(
        "--host-rates",
        default=str(DEFAULT_HOST_RATES),
        help="this host's measured candidate rates (default data/runs/host_candidate_rates.json)",
    )
    parser.add_argument(
        "--entry-id",
        action="append",
        default=[],
        help="bind only this fillable Entry ID (repeatable); C1 fills the rest after the joint solve",
    )
    args = parser.parse_args(argv)

    if args.rung == 4:
        print(
            "rung 4 emits no policy by design. Run cowork-run without "
            "--portfolio-policy-json; C1 sequential selection is the proven floor "
            "and always produces a legal portfolio."
        )
        return 0

    slate = parse_salaries(Path(args.salaries))
    entries = parse_entries(Path(args.entries))
    # The rows a policy binds: the template's fillable blank rows (Session 11),
    # the same list `run-slate` validates the policy against; its intake checks
    # the mode.
    fillable = plan_entries(entries, slate).fillable
    if not fillable:
        raise SystemExit("the entries file reserves no blank Entry ID to fill")
    entry_ids = _bound(fillable, args.entry_id)
    count = len(entry_ids)

    people = {row.underlying_id for row in slate.players}
    seconds_per_candidate, rate_line = _rate(Path(args.host_rates))
    # The same arithmetic `run-slate` keeps: its deadline, its stop, its reserve.
    # A runtime.json it cannot read fails here, by its own name.
    stop_minutes = runtime_stop_minutes(json.loads(RUNTIME_JSON.read_text(encoding="utf-8")))
    try:
        budget = Budget.build(
            slate.games,
            requested_deadline=args.delivery_deadline_utc,
            stop_minutes=stop_minutes,
            **({"wall": wall} if wall is not None else {}),
        )
    except ValueError as exc:
        parser.error(f"--delivery-deadline-utc: {exc}")
    for code, detail in budget.events:
        if code == "DEADLINE_AFTER_EARLIEST_LOCK":
            print(f"WARNING {code}: {detail}")
    window = 0.0 if budget.passed_at_start else max(0.0, budget.improvement_remaining())
    clock_line = (f"delivery deadline {budget.deadline.isoformat()} ({budget.deadline_source});"
                  f" the improvement stops at {budget.improvement_stop.isoformat()}")
    if window < SOLVE_MINIMUM_SECONDS:
        print(clock_line)
        print(
            f"No policy written: the improvement window closed at {budget.improvement_stop.isoformat()}"
            f" ({budget.now().isoformat()} now). run-slate will skip its review and hand over the"
            " baseline; hand that file over. For a replay of a past slate, pass a later"
            " --delivery-deadline-utc."
        )
        return 2
    try:
        limits = _limits(count, len(people), args.rung, minutes=args.minutes,
                         seconds_per_candidate=seconds_per_candidate, window_seconds=window)
    except BankDoesNotFit as exc:
        print(clock_line)
        print(f"rate:              {rate_line}")
        print(
            f"No policy written: {exc}. Take rung 4: run-slate without --portfolio-policy-json,"
            " so C1 sequential selection builds the portfolio in the time left."
        )
        return 2
    fraction = _exposure_fraction(args.rung)
    controls = classic_rung_controls(slate, count, args.rung)

    document = classic_portfolio_policy_template(
        slate,
        entry_ids,
        entry_sha256=entries.raw_hash,
        controls=controls,
        limits=limits,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rules = {rule["rule_id"]: rule for rule in controls["stack_rules"]}
    print(f"wrote {out}")
    print(f"rung:              {args.rung}")
    print(f"entries:           {count}" + (f" of {len(fillable)} fillable" if count < len(fillable) else ""))
    if count < len(fillable):
        print(f"subset:            C1 fills the other {len(fillable) - count} fillable rows"
              " after the C2 joint solve (Session 11c)")
    print(f"salary people:     {len(people)}")
    print(f"candidate bank:    {limits['candidate_limit']} "
          f"(template default would be {max(32, count + 24)})")
    print(f"candidate budget:  {limits['candidate_total_milliseconds'] / 1000:.0f}s")
    print(f"joint solve:       {limits['selection_milliseconds'] / 1000:.1f}s")
    print(f"rate:              {rate_line}")
    print(f"window:            {window:.0f}s before the improvement stops; {clock_line}")
    print(f"QB+pass catcher:   HARD on {rules['qb-pass-catcher']['minimum_entries']}/{count} entries")
    print(f"bring-back:        {rules['qb-bringback']['strength']} on "
          f"{rules['qb-bringback']['minimum_entries']}/{count} entries")
    print(f"max person overlap:{controls['max_pairwise_person_overlap']} of {ROSTER_SIZE}")
    if fraction is not None and count > 2:
        print(f"player exposure:   <= {max(1, math.ceil(fraction * count))}/{count} entries")
    else:
        print("player exposure:   uncapped at this rung")
    print()
    print("run-slate walks the ladder from here itself (Session 10): on a bank or joint-solve")
    print("trigger it re-sizes the bank, then relaxes one rung at a time down to C1, inside the")
    print("run's deadline, and names every step in the result's `relaxation` record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
