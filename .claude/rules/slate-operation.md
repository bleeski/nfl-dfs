---
paths:
  - "docs/RUNBOOK.md"
  - "docs/OPERATOR_GUIDE.md"
  - "scripts/**"
---

# Operating a slate

Written 2026-09-20, from one lost Classic slate. `docs/RUNBOOK.md` holds the
procedure; this holds the habits the procedure kept assuming. Every line below
is here because it failed on a live slate, not because it sounded prudent.

The engine's own gates are not in scope here and are not negotiable: see
`CLAUDE.md` § Permanent boundaries. Nothing in this file relaxes one.

## Probe, never assert

**Never state that a source is unavailable without having tried it in this
session.** An unprobed absence is a guess wearing the clothes of a fact.

On 2026-09-20 a session reported "I have no depth chart to check against" and
built a quarterback filter out of prior-season workload instead. The nflverse
depth chart was on `github.com`, already proven reachable by that same run's own
prior build minutes earlier, and carried a snapshot from that morning naming
three starters the filter had rejected. All three were playing.

`scripts/session_probe.py` answers this for every allowlisted host in about
three seconds and is step 0 of the running order. Reachability demonstrated for
one dataset on a host generalises to every dataset on that host; go and look.

## Inventory before concluding something does not exist

**Read `scripts/` before deciding a capability is missing.** Exhausting the
blocked path is not the same as surveying the tree.

On 2026-09-20 `scripts/build_classic_portfolio.py` — the construction layer that
shipped the Week 1 portfolio when the solver failed — went unopened for ninety
minutes while six routes into a blocked gate were explored one at a time.
`scripts/qa_classic_portfolio.py` was never run at all, and its Tier 2 already
measured the defect that shipped.

The corollary: when a session solves something the hard way, the fix is not
finished until the operating document names it. A solution written only into a
retrospective is a solution the next operator will not find.

## Measure the clock

**Every statement about time comes from a command run at that moment.** Do not
extrapolate from an earlier reading.

On 2026-09-20 a session measured 11:05 ET once, then reasoned forward and told
Ben it was 12:10 with 50 minutes to lock. It was 11:24 with 96. He made
decisions on the drifted number.

The lock on a Classic slate is the **earliest** kickoff in the salary file, not
the latest. `scripts/session_probe.py --salaries <csv>` reports it measured.

## Verify before reporting a defect

**A structural claim about the engine gets a check first.** Sixty seconds of
grep beats a confident wrong diagnosis, which costs a round trip and sends the
operator looking in the wrong place.

On 2026-09-20 a session reported three identity blockers as people genuinely
absent from nflverse, and framed it as a defect making Classic unpublishable.
All six were present under name variants: a nickname, a diacritic, a known
alias and three full legal names.

The same rule covers numbers. Never write a test result, a hash or a timing into
a ledger or a handoff before watching the run that produced it finish.

## A blocked engine is not a blocked slate

Ben's standing ruling is that the worst outcome is no lineup. When a gate stops
the engine, the question is what the engine can still legally produce, not
whether to give up; `docs/RUNBOOK.md` § The Classic fallback path names the
chain. Say plainly which gates are unmet, keep `DO_NOT_UPLOAD`, and ship.

R28 (2026-09-22) makes that the rule rather than the workaround. Truth-claim
gates (official activity, current role, weather) stop certification, not the
file: it ships with each gap named as a limitation. Integrity gates (exact
DraftKings IDs, hashes, entry mapping, blank-cell authority, locked cells,
Classic/Showdown mode) still stop the file they protect. The engine catches up
in Sessions 03 to 12; until then the fallback chain is how a file gets out.

R29 (2026-09-22) is the one construction rule that does not bend: "within a
given portfolio keep all submitted lineups distinct and unique." When distinct
lineups run out, list the unfilled Entry IDs in the handoff. Never repeat a
lineup to fill a row.

The bound that does not move: **never invent an observation to clear a gate.**
Not a weather enum, not an activity row, not a role share. A portfolio built on
a fabricated observation is worse than no portfolio, because every hash in the
package then asserts something untrue.

## Run the gate before the handoff

`scripts/qa_classic_portfolio.py` is required, and Tier 2 is shown to Ben, not
just consulted. Tier 1 blocks; Tier 2 is the half that catches a portfolio which
is legal and bad. Pass `--backup-pairs`, because nothing else checks that the
rostered quarterback is his team's starter, and leave out any pair whose starter
is DraftKings-`OUT` — then the backup is the starter.

State what the portfolio does not have. With no ownership input there is no
leverage model, and mean-max in a large field is chalk.

## Decide what is yours to decide

Ben's standing preference is that a menu of approaches is work handed back to
him. Under a lock clock that is expensive: on 2026-09-20 a question was put to
him at the moment the clock mattered most, on a call he had already delegated.

Ask for facts only he has — a ruling, a file, a threshold he has not set. Decide
everything you could evaluate yourself, say which way you went and why, and let
him overturn it. Construction preferences are explicitly yours under the lock
clock ruling, except lineup uniqueness, which R29 took off that list.
