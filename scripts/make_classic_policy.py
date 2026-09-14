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
from pathlib import Path

from nfl_dfs.classic_portfolio_policy import classic_portfolio_policy_template
from nfl_dfs.dk import parse_entries, parse_salaries

ROSTER_SIZE = 9


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


def _limits(count: int, pool_people: int, rung: int, *, minutes: float) -> dict[str, int]:
    """Size the bank to the pool, not to the entry count.

    Measured on the 719-person supplied fixture in the cloud container at 20
    entries, two processors: a 1000-candidate bank with the rung-0 HARD stack
    rules generated in 273.6s and the joint MILP then solved it in 0.39s,
    selecting all 20 entries. Generation is the whole cost, the joint solve is
    free, and hard stack rules make generation slower per candidate than the
    unconstrained default. The rate below is the measured constrained rate with
    headroom, so a bank that fits the requested minutes does not then trip
    CANDIDATE_BANK_TIMEOUT and cost a rung for nothing.
    """
    per_candidate_seconds = 0.28
    affordable = int((minutes * 60.0) / per_candidate_seconds)
    target = max(32, count + 24, min(2000, affordable))
    if rung >= 3:
        target = max(32, count + 24, target // 2)
    total_ms = int(min(3_600_000, max(30_000, target * per_candidate_seconds * 1000 * 2.0)))
    return {
        "candidate_limit": target,
        "candidate_total_milliseconds": total_ms,
        "candidate_per_solve_milliseconds": 5_000,
        "selection_milliseconds": int(min(3_600_000, max(10_000, 1_000 * count))),
    }


def main(argv: "list[str] | None" = None) -> int:
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
    limits = _limits(count, len(people), args.rung, minutes=args.minutes)
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
