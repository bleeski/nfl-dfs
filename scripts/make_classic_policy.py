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
preference:

  0  every entry stacks QB + pass catcher; 70% carry a bring-back; overlap 5;
     player exposure <= 50% of entries
  1  bring-back drops to 34% of entries
  2  bring-back drops to ADVISORY; overlap 6; player exposure <= 65%
  3  QB pass-catcher holds on half the entries; overlap 7; no exposure caps
  4  emit nothing; run C1 with no policy at all, which is the proven floor

Rung 4 is not a failure mode to avoid at all costs, it is the floor that
guarantees a legal portfolio exists. Walk down the ladder as far as you need to
and report the rung you landed on.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_JSON = REPO_ROOT / "config" / "runtime.json"
DEFAULT_HOST_RATES = REPO_ROOT / "data" / "runs" / "host_candidate_rates.json"
ROSTER_SIZE = 9
# The 2026-09-12 cloud measurement below, with the room kept for it: a declared
# bank budget is twice the expected generation time, and the bank plus joint
# solve may declare 75% of the improvement window, the joint solve at most 20%.
DEFAULT_SECONDS_PER_CANDIDATE = 0.28
GENERATION_HEADROOM = 2.0
WINDOW_SHARE, JOINT_SHARE = 0.75, 0.20


class BankDoesNotFit(ValueError):
    """Even the floor bank and its joint solve exceed the window's share."""


def _stack_rules(count: int, rung: int) -> list[dict[str, object]]:
    """QB correlation is the only edge this objective can express structurally.

    The objective is a sum of independent per-player central estimates: there is
    no covariance term and no ceiling, so a stack is worth nothing to the solver
    on its own. The only way correlation enters a Classic portfolio today is as
    a hard constraint on which candidates may be built.
    """
    if rung <= 0:
        pass_catcher_entries, bringback_entries, bringback_strength = count, math.ceil(0.70 * count), "HARD"
    elif rung == 1:
        pass_catcher_entries, bringback_entries, bringback_strength = count, math.ceil(0.34 * count), "HARD"
    elif rung == 2:
        pass_catcher_entries, bringback_entries, bringback_strength = count, 0, "ADVISORY"
    else:
        pass_catcher_entries, bringback_entries, bringback_strength = math.ceil(0.50 * count), 0, "ADVISORY"

    return [
        {
            "rule_id": "qb-pass-catcher",
            "rule_type": "QB_PASS_CATCHER",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": min(pass_catcher_entries, count),
            "maximum_entries": count,
            "strength": "HARD",
        },
        {
            "rule_id": "qb-bringback",
            "rule_type": "QB_BRINGBACK",
            "minimum_value": 1,
            "maximum_value": 6,
            "minimum_entries": min(bringback_entries, count),
            "maximum_entries": count,
            "strength": bringback_strength,
        },
        {
            "rule_id": "secondary-game-correlation",
            "rule_type": "SECONDARY_GAME_CORRELATION",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": 0,
            "maximum_entries": count,
            "strength": "ADVISORY",
        },
        {
            "rule_id": "rb-dst-pair",
            "rule_type": "RB_DST_PAIR",
            "minimum_value": 1,
            "maximum_value": 2,
            "minimum_entries": 0,
            "maximum_entries": count,
            "strength": "ADVISORY",
        },
    ]


def _overlap(rung: int) -> int:
    return {0: 5, 1: 5, 2: 6}.get(rung, 7)


def _exposure_fraction(rung: int) -> float | None:
    return {0: 0.50, 1: 0.50, 2: 0.65}.get(rung)


def _limits(
    count: int,
    pool_people: int,
    rung: int,
    *,
    minutes: float,
    seconds_per_candidate: float = DEFAULT_SECONDS_PER_CANDIDATE,
    window_seconds: float | None = None,
) -> dict[str, int]:
    """Size the bank to the pool, not to the entry count, and to the window.

    Measured on the 719-person supplied fixture in the cloud container at 20
    entries, two processors: a 1000-candidate bank with the rung-0 HARD stack
    rules generated in 273.6s and the joint MILP then solved it in 0.39s,
    selecting all 20 entries. Generation is the whole cost, the joint solve is
    free, and hard stack rules make generation slower per candidate than the
    unconstrained default. The declared budget is twice the expected time at
    `seconds_per_candidate`, so a bank that fits the requested minutes does not
    then trip CANDIDATE_BANK_TIMEOUT and cost a rung for nothing.

    Session 07b. `seconds_per_candidate` is this host's measured rate when it
    has one (the C4 retrospective measured 4 to 6 s). With `window_seconds`,
    the seconds left before the improvement stops, the declared bank budget
    plus the joint solve stay within `WINDOW_SHARE` of it and the joint solve
    within `JOINT_SHARE`; the rest is the run's own before selection. Raises
    `BankDoesNotFit` when even the floor bank, `max(32, entries + 24)`, does not.
    """
    per_candidate_seconds = float(seconds_per_candidate)
    if not (math.isfinite(per_candidate_seconds) and per_candidate_seconds > 0):
        raise ValueError(f"seconds_per_candidate must be a finite number above zero, not {seconds_per_candidate!r}")
    floor = max(32, count + 24)
    affordable = int((minutes * 60.0) / per_candidate_seconds)
    selection_seconds = min(3_600.0, max(10.0, 1.0 * count))
    if window_seconds is not None:
        selection_seconds = min(selection_seconds, JOINT_SHARE * window_seconds)
        generation_seconds = WINDOW_SHARE * window_seconds - selection_seconds
        affordable = min(affordable, max(0, int(
            generation_seconds / (per_candidate_seconds * GENERATION_HEADROOM))))
    target = max(floor, min(2000, affordable))
    if rung >= 3:
        target = max(floor, target // 2)

    def declared_ms(candidates: int) -> int:
        return int(min(3_600_000, max(
            30_000, candidates * per_candidate_seconds * 1000 * GENERATION_HEADROOM)))

    total_ms = declared_ms(target)
    selection_ms = int(1_000 * selection_seconds)
    # A bank above the floor was sized to fit, so only the floor bank (or the
    # 30 s least budget any bank declares) can fail this.
    if window_seconds is not None and (
            selection_seconds < SOLVE_MINIMUM_SECONDS
            or (total_ms + selection_ms) / 1000.0 > WINDOW_SHARE * window_seconds):
        floor_ms = declared_ms(floor)
        raise BankDoesNotFit(
            f"even the floor bank of {floor} candidates at {per_candidate_seconds:g} s each"
            f" declares {floor_ms / 1000:.0f} s and its joint solve {selection_ms / 1000:.1f} s,"
            f" {(floor_ms + selection_ms) / 1000:.1f} s together, over {WINDOW_SHARE:.0%} of the"
            f" {window_seconds:.1f} s window ({WINDOW_SHARE * window_seconds:.1f} s)"
        )
    return {
        "candidate_limit": target,
        "candidate_total_milliseconds": total_ms,
        "candidate_per_solve_milliseconds": 5_000,
        "selection_milliseconds": selection_ms,
    }


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
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    count = len(entry_ids)
    if count == 0:
        raise SystemExit("the entries file reserves no Entry IDs")

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

    controls: dict[str, object] = {
        "stack_rules": _stack_rules(count, args.rung),
        "max_pairwise_person_overlap": min(_overlap(args.rung), ROSTER_SIZE - 1),
        "require_unique_lineups": True,
    }
    if fraction is not None and count > 2:
        cap = max(1, math.ceil(fraction * count))
        controls["player_exposure_bounds"] = [
            {
                "underlying_id": row.underlying_id,
                "dk_id": row.dk_id,
                "minimum_entries": 0,
                "maximum_entries": cap,
                "hard": True,
            }
            for row in sorted(
                {row.underlying_id: row for row in slate.players}.values(),
                key=lambda row: row.underlying_id,
            )
        ]

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
    print(f"entries:           {count}")
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
    print("If the run reports MODELED_BANK_INFEASIBILITY, INCOMPLETE_BANK_EXHAUSTION,")
    print("CANDIDATE_BANK_TIMEOUT or CANDIDATE_BANK_SEARCH_LIMIT, regenerate at "
          f"--rung {args.rung + 1} and rerun. Do not ask permission; report the rung you landed on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
