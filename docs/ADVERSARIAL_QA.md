# Adversarial portfolio QA

A build can pass every gate this repo has and still be a bad bet. On 2026-09-10
the SF@LAR Showdown run returned `FILE_VALID=true`,
`ENFORCED_AND_INDEPENDENTLY_AUDITED` and `DISPLAY_RECONCILIATION=PASS` while
shipping a lineup that rostered Brock Purdy and his own backup, a lineup with no
quarterback at all, two entries that differed only by a $200 punt, and a
candidate pool that still contained two officially inactive players. Every one
of those is invisible to legality, byte fidelity and policy enforcement, because
none of those gates asks whether the portfolio makes sense.

This document specifies the pass that asks. It applies to Classic and Showdown.

## What this is not

It is not a new release gate. The prior-only path already ends
`DO_NOT_UPLOAD`, and nothing here changes the four release truths. It is not a
model, an ownership estimate or an edge claim. It does not relax anything: a
coherence finding never unblocks a build, it only makes a defect visible before
the operator acts on it.

## Two layers

The pass splits by what can be settled deterministically and what needs
judgment. Keep them separate; they have different trust properties.

**Layer A — deterministic coherence checks, in code.** Cheap, replayable,
hash-bound, and they run on every build with no operator involvement. These are
the checks that would have caught the two-QB lineup, the no-QB lineup, the
near-duplicate pair and the inactive players still sitting in the pool. Layer A
is the backlog item `QA1`.

**Layer B — the adversarial agent pass, procedural.** Judgment, external data,
and reading the engine against its own claims. Runs in the Cowork session before
an operator handoff. Layer B needs no new code and is in force now; it is
specified in `CLAUDE.md`, in this document, and in the `nfl-showdown-lineups`
skill.

---

# Layer A — deterministic coherence checks

## Where the output goes

One new report block, `portfolio_coherence`, emitted by the prior-review path
alongside `pool_coverage` and reconciled into the readable review the same way
every other block is. Schema `nfl_portfolio_coherence_v1`. Every finding carries
`code`, `severity`, `mode`, the exact entry IDs and underlying person IDs it
concerns, the computed numbers behind it, and one `next_action` string.

Severities are `DEFECT` (a construction that is wrong regardless of any model),
`STRUCTURE` (the portfolio is worse-diversified than the policy implies) and
`CONTEXT` (reported so a reader does not draw the wrong conclusion). Only
`DEFECT` findings are surfaced in the top-level `next` action.

## Roster coherence

Applies to both modes unless noted.

| Code | Severity | Rule |
|---|---|---|
| `SINGLE_JOB_SPLIT` | `DEFECT` | A lineup holds two people from the same team whose modeled shares of a single-holder role sum to ≥ 0.9. The QB attempt share is the exact case; express the rule over any share that partitions one job. |
| `NO_QB_IN_LINEUP` | `DEFECT` | Showdown only. A lineup with no quarterback from either team. Classic forces one by roster slot. |
| `ROLE_GROUP_SATURATED` | `STRUCTURE` | A lineup holds more people from one team-position group than the group's modeled volume supports. Both kickers in one lineup is the common case. |
| `OFFICIALLY_INACTIVE_ROSTERED` | `DEFECT` | A roster ID appears in the supplied `official_status_csv` `INACTIVE` set. Selection already excludes these, so this is a post-export assertion; if it ever fires, the export path is broken. |
| `INACTIVE_STILL_SELECTABLE` | `DEFECT` | A person the operator-supplied status evidence marks `INACTIVE` is still in the candidate pool. Fires when no status file was supplied at all, which is the state that matters. |

## Portfolio structure

| Code | Severity | Rule |
|---|---|---|
| `EFFECTIVE_INDEPENDENT_ENTRIES` | `STRUCTURE` | `N / (1 + (N-1) · mean pairwise outcome correlation)`, computed by running the selected entries through the engine's own simulator at a registered seed and scenario count. Report the number always; flag when `effN / N` falls below a registered threshold. On 2026-09-10 an 11-entry portfolio scored 1.25. |
| `NEAR_DUPLICATE_PAIR` | `STRUCTURE` | Any entry pair whose outcome correlation exceeds a registered threshold despite passing canonical uniqueness. Name both entry IDs and the exact people that differ. The 2026-09-10 build had a pair at 0.994 separated by one $200 player. |
| `CHALK_CONCENTRATION` | `STRUCTURE` | Share of entries whose differentiating slot sits in the top-K of the pool by salary. Showdown keys on the captain; Classic keys on the highest-salary core. Salary is the only ownership proxy available until `Q3` lands, and the finding must say so in its own text. |
| `UNUSED_SELECTABLE_POOL` | `CONTEXT` | Count and names of selectable people with zero exposure, with salary. 18 of 32 on 2026-09-10. |
| `SALARY_REMAINING` | `CONTEXT` | Per-entry and portfolio maximum unspent salary, reported next to the cheapest legal upgrade available to that entry. Reported as context precisely so a reader does not "fix" it: on 2026-09-10 the $600 remainders were unspendable and the entry that spent exactly to the cap was the true global maximum. |

## Model-versus-market divergence

| Code | Severity | Rule |
|---|---|---|
| `PRICED_BUT_UNSCORED` | `DEFECT` | The highest-salary person excluded by a role or history gate, named at top level with both salaries. On 2026-09-10 this was De'Zhaun Stribling at $9,900 CPT, SF's projected perimeter WR2, excluded with zero share. |
| `MODEL_MARKET_RESIDUAL` | `STRUCTURE` | Rank correlation between the engine's prior points and DraftKings `AvgPointsPerGame` across the priced pool, plus the five largest per-person residuals. On 2026-09-10 the correlation was 0.941 and the largest residual was Brock Purdy at −9.7, which is the QB-committee data artifact showing up as a number. |

`MODEL_MARKET_RESIDUAL` needs an explicit ruling because it looks like a policy
violation and is not. `CLAUDE.md` quarantines `AvgPointsPerGame` to untouched
raw salary bytes and forbids it as a numerical model input, and
`opportunity.py` asserts its absence from the model contract. That ban is on
*inputs*. Reading the column as a read-only cross-check, after projection, in a
code path that cannot write back to any model artifact, is a different act and a
legitimate one: it is the cheapest available detector of exactly the class of
error that produced the Purdy artifact. The implementing session must keep the
existing assertion passing and must add a test proving the check cannot mutate
a projection, an opportunity row or a candidate.

## Mode differences

Showdown and Classic share every check above. The differences are narrow:

- `NO_QB_IN_LINEUP` is Showdown-only.
- `SINGLE_JOB_SPLIT` fires at QB almost exclusively in Showdown, because DK
  Classic has one QB slot and its FLEX excludes quarterbacks. In Classic the
  same rule catches backfield committees sharing one carry share.
- `CHALK_CONCENTRATION` keys on the captain in Showdown and on the top-salary
  core in Classic.
- Classic evaluates the checks per game as well as per portfolio, because a
  multi-game slate can be well diversified overall and concentrated inside one
  game.

## Acceptance

- Every check has a fixture that fires it and a fixture that does not.
- The 2026-09-10 SF@LAR artifacts are a regression fixture: the pre-fix
  portfolio must produce `SINGLE_JOB_SPLIT`, `NO_QB_IN_LINEUP`,
  `INACTIVE_STILL_SELECTABLE` (Atwell and Watkins), at least one
  `NEAR_DUPLICATE_PAIR`, and `PRICED_BUT_UNSCORED` naming Stribling.
- Findings are deterministic across repeated runs at a fixed seed.
- The block reconciles into the readable review with the same exact-byte
  discipline as every other block, and a disagreement is a named
  `READABLE_REVIEW_FAILED` blocker.
- No check writes to any model, projection, candidate or policy artifact.

---

# Layer B — the adversarial agent pass

Runs after a build completes and before any operator handoff on a slate that
will actually be entered. Two tracks, run concurrently because the agent must
not fetch.

## Track 1 — external data

The operator runs this, not the agent. Three things, in descending value:

**Official inactives.** The single highest-value input available on game day
and the only named blocker that changes a roster rather than paperwork. Build
`official_status_csv` from it. The contract lives only in `evidence.py` and
`prior_review.py`, not in `docs/DATA_CONTRACTS.md`; until that gap is closed,
three rules earned on 2026-09-10:

- Filter the inactive list to people who are actually in the DK pool first. DK
  Showdown lists only QB/RB/WR/TE/K/DST, and a row for a cornerback or an
  offensive lineman raises `OFFICIAL_STATUS_INVALID` and kills the entire run.
- Supply only directly-quoted `INACTIVE` rows. `ACTIVE` rows are inert in
  selection and "not on the inactives list" is an inference; keep inferences out
  of a hash-bound evidence artifact and accept the honest
  `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED` report instead.
- The run must fall inside `[OBSERVED_AT − 5 min, OBSERVED_AT + 3 h]`.

**Depth charts and projected starting lineups.** These do not enter the engine,
because a qualitative starter label cannot become a numerical share and the repo
is right to refuse that. They enter the *handoff*, as named blind spots. On
2026-09-10 they established that the engine's SF pass-catcher hierarchy was
inverted and that the QB split was an artifact, neither of which the engine
could see.

**Market total and spread.** Cheap to fetch and usually low-impact on the
current engine, because the total feeds only the DST points-allowed tier. Fetch
it, but do not spend the last half hour before lock chasing it.

## Track 2 — the adversarial read

Spawn a subagent with the run artifacts, the engine source, the governing docs,
and an explicit instruction to assume the build is wrong until the artifacts
prove otherwise. The brief must carry:

- The shipped portfolio inline, so the agent does not have to discover it.
- The known and already-conceded limitations, so it spends its effort past them.
- Hard rules: read code before asserting anything about code and cite
  `file:line`; compute numbers rather than eyeball them; write nothing in the
  repo; do not fetch.
- The five questions: grade against the Dual-Optimization Mandate from the code
  rather than the docs' self-description; find structural defects in these
  specific lineups; propose Pareto improvements expressible in the existing
  controls; find captain or core leverage; name the missing data that would
  change the build and say whether an existing contract can ingest it.
- A request to rank findings by expected dollar impact, and to end with the
  three changes it would make and one thing it would not change that a naive
  reviewer would.

## Rules earned on 2026-09-10

**Re-verify the agent's own recommendations.** Round 1 proposed a policy that
looked clean and put two kickers in the captain slot, because capping a kicker's
combined exposure does nothing to stop him captaining and a cheap captain
preserves the expensive core underneath. Any policy an agent proposes is run
through the real validator and the real selector, and the deterministic Layer A
checks are re-run on the final artifact, before anything ships.

**The agent's verdict is advisory.** It never becomes a hard gate. This system's
gates are hash-bound and replayable; a language model's opinion is neither, and
wiring one into a release decision would be the single worst change available to
this repo. It informs the operator and it does not block the pipeline.

**The clock is the binding constraint, not the iteration budget.** Time-box the
pass against lock. A pass that has not finished is worth less than a build that
ships. On 2026-09-10 two rounds finished inside the window and a third would not
have.

## Handoff

The operator handoff reports, alongside the four release truths: every `DEFECT`
finding from Layer A, the effective-independent-entries number, the top
`PRICED_BUT_UNSCORED` person, the agent's three recommended changes and whether
each was taken, and any blind spot that could not be honestly closed.
