# P8: Showdown game theses as sleeves

Brief for chunk `P8`. Status, dependencies and hand-back are tracked in
`docs/ROADMAP.md` (status board and the Session 23b card); this file is the
specification. Written 2026-09-25 from the DAL@NYG Showdown retrospective
(`docs/SHOWDOWN_RETROSPECTIVE_2026-09-13_DAL_NYG.md` §7b, §7c, §7e, §9 #1 and
#4) and the 2026-09-15 standings findings
(`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` §1, §8.1 C, §8.2 G
to I).

## Goal

One Showdown run builds its portfolio as a **core plus named thesis sleeves**.
Each sleeve owns declared rows, every lineup in it provably follows its game
script, the sleeves never collapse onto the same chalk, and no one person
dominates the whole portfolio. Every run still ends `PRIOR_ONLY /
DO_NOT_UPLOAD`. A thesis is a structure Ben chooses, not a forecast the engine
makes.

## Why

- **Retro §7c, blocker 1.** A policy had to bind every row, so a thesis could
  not own 4 of 20 entries. Session 11b removed it: a Showdown policy may bind a
  subset, and sequential Showdown fills the rest.
- **Retro §7c, blocker 2.** Five theses run over all 20 rows and merged gave
  Dak Prescott 20 of 20 and five distinct captains, worse than the single-policy
  build. Every thesis maximized the same mean objective, and a thesis written as
  `excluded_people` shapes the supporting cast but never binds the captain: the
  NYG-blowout thesis captained Dak and rostered CeeDee Lamb. A thesis has to be
  a correlated structure the solver must satisfy, captain included.
- **Findings §8.1 C and §1.** Portfolios with 85% or more of entries on one
  player had 1.4x to 12x the zero-paid rate in 4 of 4 games (8,007 field
  portfolios). Ours ran 0.94, 0.80, 0.73 and 1.00. Caps raised to make a solve
  feasible were the only diversification control.
- **Findings §8.2 G.** A hygiene core plus a bounded sleeve of script bets
  raised P(at least one top-1% finish) from 0.19 to 0.28 and cut P(zero paid)
  from 0.007 to 0.002 across the four games. That result is fitted to those
  games (a hypothesis, not a proven edge), and the script features each had 1.5
  to 6.5x lift where they hit and 0.00 to 0.25x where they missed. So each
  sleeve must be small, and the core must carry the paid count.

## Scope

### 1. The lineup-rule vocabulary (Showdown policy v2)

`nfl_showdown_portfolio_policy_v2`. v1 is unchanged and still accepted. v2 adds
`lineup_rules`, each applied to every lineup on the rows the policy binds:

- **Count rule**: `{rule_id, slot, teams, positions, people, minimum,
  maximum}`. `slot` is `CPT`, `FLEX` or `ANY`, and every other selector
  narrows it. It counts the lineup's roster slots that match. Captain rules are
  count rules on `CPT`: "captain from team X" is `slot=CPT, teams=[X],
  minimum=1`. Per-team splits, position counts and "no kicker" are all count
  rules.
- **Pair rule**: `forbid_pair` and `require_pair` on exact people, plus a
  registered `DST_WITH_OWN_OFFENSE` form.
- **Salary-left bounds**: `salary_left_min`, `salary_left_max`.

Every rule is a linear constraint in the lineup MILP and in every SD3 bank
stratum, so the bank holds lineups that satisfy it. The audit and the readable
review recompute every rule from the roster bytes. People are named by the
exact identity triple, and teams and positions only as the salary file states
them.

Session 23's hygiene bounds (P2: `qb_count`, kicker and DST counts, salary
left) are instances of the count rule. Session 23 adds only what this cannot
express, such as `pass_catchers_with_rostered_qb`, and registers it as the next
version, never a second v2.

### 2. The thesis catalog

`config/showdown_theses_v1.json`: registered, versioned templates of lineup
rules, with the teams as named roles. The plan binds each role to one of the
slate's two teams. The engine never infers a favorite, an underdog or a game
script, whether from a spread, a total, a contest name or a model.

The rules below are the retro's §7c structures, written as counts. They are
starting templates and construction preferences (`S`), not evidence. Changing
one is Ben's call and makes a new catalog version.

| Thesis (roles) | Rules |
|---|---|
| `BLOWOUT(winner, loser)`: a favorite blowout, or an upset with the roles swapped | Captain from `winner`; `winner` holds at least 4 of 6; `winner` DST and RB at least 1 each; `loser` RB, K and DST 0 (the loser appears only as garbage-time passing) |
| `SHOOTOUT` | QB at least 1 per team; WR at least 1 per team; K and DST 0; captain a QB or WR |
| `ONE_SIDED_EXPLOSION(team, other)` | `team` holds 5 of 6; `other`'s one player is a WR (the bring-back); captain from `team` |
| `LOW_SCORING_GRIND` | Both kickers; DST at least 1; RB at least 1; TE at least 1; no WR captain |
| `GROUND_AND_CLOCK` | RB at least 1 per team; TE at least 1; K at least 1; WR at most 1; captain an RB or QB |
| `DEFENSIVE_SCORE(team, other)` | Captain is `team`'s DST; `other`'s QB 0 |

The retro's "favorite QB at reduced weight" and "QB rushing" are objective
weights, not counts. They wait for a per-sleeve objective (Session 25).

### 3. The portfolio plan

`nfl_showdown_portfolio_plan_v1`, supplied instead of a single policy. It binds
the exact salary and entry SHA-256 values and holds:

- `core`: a v1 or v2 policy, or `null`. It binds every fillable row no sleeve
  binds. With `null`, sequential Showdown fills those rows (Session 11b's fill).
- `sleeves`: each has a `sleeve_id`, a `thesis` (catalog id, catalog version
  and role bindings) and/or its own `lineup_rules`, its `entry_ids`, and its
  SD3 caps (Captain, combined, overlap) over its own rows. The `entry_ids` are a
  non-empty subset of the fillable rows, in template order, and no row is in
  two sleeves.
- `max_person_share`: across every filled row of the portfolio, core and
  sleeves together. Default 0.80, the field median among multi-entry
  portfolios. Session 23 reuses this control for single-policy runs rather
  than adding a second one.

A row bound twice, a prefilled or unknown row, overlapping sleeves, a role bound
to a team not on the slate, or an unregistered thesis is a `V` refusal. An
infeasible count (a rule no lineup can meet) is `S`.

### 4. Solve order

1. **Sleeves**, in plan order. Each is an SD3 joint solve over its rows. Every
   earlier lineup and every preserved prefilled roster is a no-good (R29). Its
   per-person caps are the smaller of its own caps and what the plan-level cap
   has left.
2. **The core** runs last, under the same leftover capacity.

`max_person_share` therefore holds by construction, and the audit recomputes
it. Sleeves go first because their rules are narrow and they are most likely to
run out of capacity; the core has the widest pool. If leftover capacity starves
the core on real slates, the upgrade is one joint solve across sleeves. Record
the evidence before building it.

### 5. Relaxation

Each sleeve walks Session 10's `SHOWDOWN_RUNGS` on its own rows: its Captain,
combined and overlap caps loosen. **Its thesis rules never relax.** A relaxed
thesis is a different bet, and shipping it under the old name would be silent.
A sleeve that is still infeasible is dropped by name
(`THESIS_SLEEVE_DROPPED`, `S`), and the core fills its rows. `max_person_share`
relaxes after every sleeve rung and before rung 4 (P2's order). Rung 4 is no
plan: sequential Showdown over every fillable row, as today. Uniqueness is
never on the ladder.

### 6. Audit and review

- **SD3 audit**: once per sleeve and once for the core, each over its own rows
  (Session 11b's split).
- **Plan audit**: over every filled row.
  - Each lineup's sleeve rules, recomputed from its roster bytes.
  - `max_person_share`, naming the person.
  - Distinctness across sleeves, core and prefilled rows (`V`).
  - The plan's hashes.
- **Readable review v3**:
  - Each row's `source`: its sleeve ID, `CORE`, or `SHOWDOWN_SEQUENTIAL`.
  - A section per sleeve: its thesis, role bindings, rows, captains, exposure
    and a pass for each rule.
  - A portfolio summary: max person share with the person named, distinct
    captains, and mean pairwise overlap within and across sleeves.

### 7. The generator

`scripts/make_showdown_plan.py`:

- `--core` takes the flags `make_showdown_policy.py` takes.
- `--sleeve BLOWOUT:winner=NYG,loser=DAL:3` is repeatable. Rows are
  allocated deterministically from the end of the template, and `--entry-id`
  places a sleeve's rows by hand.
- A role bound to a team the salary file does not hold stops the script.

Once Session 23's contest facts exist, sleeve rows go to
`FIRST_PLACE_OBJECTIVE` rows first.

## Must hold

- R29 across the whole portfolio: every sleeve, the core and every prefilled
  row. No filled cell ever changes, and a Classic/Showdown mismatch stops the
  run.
- Each thesis is Ben's stated choice, never inferred.
- A thesis is a construction preference. No output calls one likely, calibrated
  or +EV, and nothing claims a sleeve wins.
- `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. Exit codes
  keep their meaning.
- A plan with only a core over every row gives the same file as today's
  single-policy run, byte for byte (Session 11b's `SD3_FULL_FILLABLE_SHA256`).

## Out of scope

- A per-sleeve objective: a dart or ceiling sleeve, captain strata on a
  ceiling statistic, the retro's §7b and §7e (Session 25). In v1 each sleeve
  has an `objective` field, which must be the mean objective.
- Ownership and leverage (Sessions 26 and 27).
- Contest-aware row placement (Session 23).
- Classic theses. C2 already has groups and stack rules, and a Classic plan
  follows Session 11c.
- Whether theses pay. That is P0's to measure (Session 18). Session 22's
  pre-registration record names the plan, so its sleeves get graded.

## Acceptance

Each item is a test, through `run-slate` where it can be, on the supplied NE@SEA
Showdown fixture with a pinned clock.

1. **A 20-row plan.** Core 10 rows, `SHOOTOUT` 3, `BLOWOUT(winner=SEA,
   loser=NE)` 3, `BLOWOUT(winner=NE, loser=SEA)` 2, `LOW_SCORING_GRIND` 2.
   - Every sleeve lineup passes its thesis rules, recomputed from the bytes.
   - No lineup repeats.
   - `max_person_share` is at most 0.80, and the review names the person.
   - The portfolio has more distinct captains than a core-only build of the same
     20 rows under the same caps. This is a mechanism check against blocker 2's
     collapse, not an edge claim.
2. **Rules never relax.** A sleeve made infeasible by its rules is dropped by
   name after its cap rungs, the core fills its rows, and no rule loosened.
3. **Binding refusals.** Overlapping sleeves, a sleeve binding a prefilled row,
   and a role bound to an absent team are each refused `V`.
4. **Audit mutations.** A sleeve lineup edited to break a rule, a repeat across
   sleeves, and a `max_person_share` breach are each named.
5. **Core-only plan.** It gives the same file hash as today's single policy.
6. **Replay and suite.** A replay is byte-identical, and the full suite is
   green.

## Breakpoint

If the diff passes about 1,500 changed lines, land the vocabulary, the catalog
and one thesis sleeve on a subset with the core as the fill (v2 plus Session
11b's path). The multi-sleeve plan, `max_person_share`, the ladder per sleeve
and readable review v3 then go to Session 23c.
