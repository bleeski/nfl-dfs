# Showdown retrospective: DAL @ NYG, 2026-09-13

First 20-entry live Showdown ship. Built under a 61-minute clock from a cold
session. Six portfolios generated, v6 shipped, export SHA-256
`a96f9e704f773d11802679acb6aceb45de5d67a369640653222be2277d540f04`.

Companion to `CLASSIC_C4_RETROSPECTIVE_2026-09-13.md`. Mechanics learned here
are also in project memory as `nfl-showdown-policy-mechanics.md`.

---

## 1. What shipped

v6: 20 lineups, 15 distinct people, 11 distinct captains, max pairwise person
overlap 4, salary 41,700 to 49,900, 9 of 20 rostering both starting QBs, zero
defects on the full deterministic sweep. `FILE_VALID=true`,
`EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`,
policy `ENFORCED_AND_INDEPENDENTLY_AUDITED`.

Timeline against a 20:20 ET lock:

| Clock | Event |
|---|---|
| T-61 | Session start, clock computed first |
| T-55 | Repo staged, inactives fetched in parallel |
| T-49 | R20 contest-scope regression found, patched |
| T-42 | Weather captured through the browser pane |
| T-33 | Policy schema rejected, regenerated |
| T-29 | TLS opt-in blocked by classifier, recovered by reusing frozen artifacts |
| T-21 | v3 shipped: legal, 12 people, one wasted lineup |
| T-14 | Adversarial agent returns; bank-truncation defect confirmed |
| T-11 | Agent's fix infeasible; v5 has a QB-less lineup |
| T-7  | v6 shipped |
| T+0  | Lock |
| post | Five further diversification attempts, all worse, none shipped |

## 2. Verification completed after the fact

**This should have happened before shipping and did not.** The skill is explicit:
run the replay anchor before touching selection or export. `review_export.py` is
the export path and it was patched 40 minutes before lock with no anchor and no
test run. Closing it afterwards:

- Replay anchor: `cowork-run --request .../20260909T222153Z-ne-sea-live-excl20/run_request.json
  --as-of 2026-09-09T22:21:53+00:00` exports
  `cf33f3e598270d40ea117d86ccac4ebce640b479baa8539b630f828aed585b96`. **Matches
  byte for byte.** The patch did not move the export path.
- Test suite on the patched tree: **650 passed, 1 failed, 1 skipped** in 167s.
  The failure is `test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`,
  which asserts `CERTIFIED_UPLOAD_PACKAGE` and gets `DO_NOT_UPLOAD`. **It
  reproduces on pristine source**, so it predates this session and is unrelated
  to the patch. It needs its own triage.

The outcome was clean. The process was not, and the process is the part that
generalizes.

## 3. Keep exactly as is

- **Start the clock first.** Every decision was paced against minutes-to-lock and
  that is why a legal file existed at T-21 instead of T-2.
- **Ship early, improve in place.** v3 went out legal and imperfect, then v6
  replaced it. At no point after T-21 was there no file on the board.
- **Re-verify every agent proposal through the real validator and selector.** The
  agent's diagnosis was correct and its fix was wrong. Shipping it unverified
  would have put a QB-less lineup into a live contest. This rule earned its keep
  on its second consecutive slate.
- **Independent deterministic QA on the exported bytes, not on the engine's own
  report.** Written by hand four times this session and caught the v5 defect
  immediately.
- **Only directly-quoted INACTIVE rows in `official_status_csv`.** Two
  independent sources, filtered to the DK pool, ten rows for five people. The
  honest `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED` report is the correct outcome.
- **Parallel tool calls.** Repo staging and inactives research in the same
  message, three policy variants in one call.

## 4. Where time went for no gain

| Minutes | Cause | Prevention |
|---:|---|---|
| ~6 | R20 regression: skill claimed a fix the tree did not have | Preflight that asserts documented invariants before the first build |
| ~3 | Policy schema guessed wrong (override shape, string fractions) | `scripts/make_showdown_policy.py`, the twin of `make_classic_policy.py` |
| ~2 | TLS env var blocked by the session classifier | Default to reusing a frozen package; treat `--build-priors` as optional |
| ~2 | Relative paths refused by the CLI | The generator emits absolute paths |
| ~8 | Five variants (A, B, C, D, F) that all died the same way | Derive the feasibility arithmetic before running, not after |
| ~6 | Thesis builds: subset binding refused, then merge collapsed to chalk | Predictable from the objective; see section 7 |

The eight-minute item is the real lesson. Variants A, B, D and F each failed with
QB-less lineups for one reason, and the arithmetic that predicts it fits on a
line. Four runs were spent discovering something derivable in thirty seconds.

**Rule to adopt: before running a policy variant, write down the binding
constraint arithmetic and check it. If it does not clear, do not run it.**

## 5. The QB-starvation arithmetic

DK prices backup QBs in a flat tier ($6,000 FLEX here, against $9,600 and
$10,400 for the starters). Zeroing the backups to prevent the starter-plus-backup
defect leaves exactly two real QBs. The engine has no minimum-position
constraint, so with both starters capped at `c`, available QB slots are `2c`. If
`b` lineups roster both QBs and `s` roster one, then `2b + s <= 2c` while
`b + s + n = 20`, where `n` is the number of QB-less lineups. Measured:

| combined cap | distinct people | QB-less lineups |
|---|---|---|
| 16 (shipped) | 15 | 0 |
| 11 | 14 | 5 |
| 8 | 21 | 11 |
| 6 | 25 | 13 |

Tightening combined exposure to diversify a Showdown portfolio does not produce
leverage. It exhausts the viable players and backfills with min-salary bodies:
variant A produced a $9,400 lineup and a Giants DST captain.

## 6. The candidate bank is the binding constraint, not the objective

The bank is `max(32, 4 x entries)` = 80 at 20 entries and it **hit the cap**:
`CANDIDATE_LIMIT_REACHED_INCOMPLETE`, `complete: false`. Composition was captain
33 (11 people x 3), chain 19, exclusion 15, fill 13.

`plan_captain_strata` seeds captains in descending prior order only until summed
integer maxima cover `entries + 2`. At captain cap 2 that is exactly 11 people,
and those 11 are the only people who can ever captain. Malik Nabers was
`SELECTABLE` with no gate against him and appeared in zero lineups because **no
candidate in the bank contained him**. The solve never had the option.

This was found by the adversarial agent, not by me. My own read was that Nabers
"scored low," which was wrong in a way that mattered: a scoring problem is fixed
by fixing the score, a bank problem is fixed by changing the strata.

**Diagnostic order for any exposure surprise: read
`candidate_bank.strata.captain` first, then `pool_coverage`, then the objective.**

## 7. Answers to the open questions

### 7a. Formalizing the agent QA pass

Three artifacts, none of which exist yet:

1. **`scripts/qa_showdown_portfolio.py`**, the twin of the existing
   `scripts/qa_classic_portfolio.py`. It takes the source template, the export
   and the salary file and returns pass or a defect list: byte diff restricted to
   the six roster cells on reserved rows, exactly one CPT and five FLEX with
   correct role rows, person uniqueness, salary cap, both teams, exactly one QB
   or an explicit allowance, no starter with his own backup, at most one kicker,
   at most one DST, no DST alongside its own offense, pairwise overlap inside the
   cap, lineup uniqueness, entry-ID coverage, and no ID that is OUT, IR or on the
   official inactive list. Hand-writing this four times in one session is the
   argument for it.
2. **A stored adversarial prompt template** in `docs/`, with fixed sections:
   slate context, artifact paths, engine paths, the conceded-limitations list so
   the agent goes past them, the ranked asks, the output contract
   (SEVERITY / claim / `file:line` or computed number / impact / fix expressible
   in existing controls), and the three rules (no fetch, no writes, advisory only).
   The limitations list is what made tonight's agent productive: it skipped the
   known problems and went to the bank.
3. **A standing rule, already proven twice:** any agent-proposed policy runs
   through the real validator and the real selector, and the resulting export
   goes through the deterministic QA script, before it ships.

Run the data track in parallel with the agent, because the agent cannot fetch.

### 7b. Formalizing darts, and lineups that run against the priors

The central finding: **darts cannot be produced by loosening constraints.** They
need a different objective or a different prior, and the current engine has
neither.

`portfolio.RISK_MEASURE = MEAN_CVAR_05_CONVEX_V1` with `RISK_AVERSION = 0.0`
looks like a variance lever and is not. CVaR at 5% is the left tail, so raising
`risk_aversion` makes selection more conservative. It also lives in
`portfolio.py`, on the simulation path that `prior_review` never calls
(`portfolio.py:133`, `:148`). Do not reach for it.

What a dart actually requires:

- **A ceiling statistic per player**, computed from frozen prior-season data:
  per-game max, P90, and the rate of games above a threshold. The agent computed
  these tonight from `stats_player_week_2025`. Theo Johnson's best 2025 game in
  15 tries was 21.3, capping him near 32 as captain against winning showdown
  scores of roughly 135 to 145. That is a disqualifying fact for a captain and it
  is fully derivable from data already in the frozen package.
- **A second objective mode** on the selection path: rank candidates on ceiling
  rather than mean. Not a replacement, a mode.
- **A dart sleeve**: N of the entries built under the ceiling objective and the
  rest under the mean objective, merged. This needs the subset-binding change in
  7c.

Until that lands, the honest dart mechanism is the one v6 used: a
`max_captain_exposure` override of `0.0` on captains disqualified by ceiling,
which frees their strata slot and promotes the next eligible person. That is how
Nabers got in.

### 7c. Game theses, and making lineups adhere to one

The frame is right and was tested tonight. It failed for two specific reasons,
both fixable.

**Blocker 1:** `PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH`. The policy must bind
every reserved Entry ID, so a thesis cannot own 4 of 20 entries.

**Blocker 2:** running each thesis over all 20 entries and taking 4 each collapses
to chalk. Every thesis still maximizes the same mean objective, and Dak Prescott
was the top prior under all five. The merged file had Dak 20/20 and 5 distinct
captains, worse than the single-policy build. The NYG-blowout thesis captained
Dak and rostered CeeDee Lamb, because `excluded_people` shapes the supporting
cast and never binds the captain.

A thesis is a correlated structure, not an exclusion list. The theses worth
encoding for a single NFL game:

| Thesis | Structure |
|---|---|
| Favorite blowout | Favorite DST, favorite RB, favorite QB at reduced weight, dog reduced to garbage-time passing |
| Dog blowout (upset) | Mirror, dog DST live |
| Shootout both ways | Both QBs, both WR1s, no DST, no kicker |
| One-sided explosion | One offense fully stacked, the other's WR1 only as the bring-back |
| Low-scoring grind | Both kickers, one or both DSTs, RBs, TEs, no premium WR captain |
| Ground and clock control | Both backfields, QB rushing, TEs, kicker |
| Special teams / defensive score | DST captain, min-salary offense underneath |

Enforcing them needs constraints the Showdown policy does not have and the
Classic C2 policy already does:

- `captain_must_be_in(set)` or `captain_team`
- `min_players_per_team` / `max_players_per_team`
- `require_at_least_one(position)`, which independently fixes QB starvation
- `forbid_pair(DST_X, offense_X)` and its inverse `require_pair`
- registered stack rules, ported from the Classic implementation

**This single feature set unlocks darts, theses and captain breadth at once. It
is the highest-value item in this document.**

### 7d. Ownership and leverage

Leverage is my exposure minus field exposure. With no field exposure there is no
leverage, only guessing. Current state:

- `ownership.py` has `cold_start_states`, whose realized captain distribution
  tops near 3.6% where real showdown chalk runs 20 to 35 percent. It is present
  and miscalibrated, so it is not usable.
- Free sources are paywalled at the level that matters. 4for4's captain section
  is behind a subscription; the DK Network article is a DraftKings host and is
  off limits by the source policy.

Three options, in order of cost:

1. **A salary-derived ownership prior, no external source.** Showdown captain
   ownership follows CPT salary rank and projected points closely. A monotone
   prior fitted to that shape gives a usable field estimate from the salary file
   alone, with zero licensing risk. It will be wrong in the tails and still
   beats 3.6%. Note that DK `AvgPointsPerGame` cannot enter it; the salary column
   can.
2. **A paid capture adapter** (4for4, Establish The Run, Stokastic) through
   `sources.py` with a license decision and retained bytes. This is the clean
   answer and it is a spending decision for Ben, not a technical one.
3. **Post-hoc calibration.** DK publishes realized ownership after contests
   settle. Capture it every week, and within a handful of slates there is a real
   fitted model. This costs nothing but time and it is the only path that ends
   with a calibrated number rather than an assumption.

Do 1 and 3 together. Revisit 2 once 3 shows how far off 1 is.

### 7e. Broadening captains without forcing diversity

Not "20 distinct captains." That was tested as variant C and it is infeasible at
18 eligible captains, and it would be wrong even if it were feasible.

The principle: **a captain earns a slot if his ceiling times 1.5 can win the
contest.** Mean prior is the wrong ranking for the captain slot specifically,
because the captain multiplies variance as well as expectation. Selecting captain
strata on a ceiling statistic rather than mean prior removes Theo Johnson and
Devin Singletary on merit and admits Nabers and Likely on merit. That is what v6
did by hand and it is a fifteen-line change to the strata planner.

Second, smaller lever: the bank cap of `max(32, 4 x entries)` binds at 20
entries. Raising it to `6 x entries` deepens every stratum, at a cost in solve
time that is affordable inside the existing budget.

## 8. Questions we are not asking yet

1. **Why is this one portfolio?** 20 entries across 8 contests at 3 entry fees
   were treated as a single portfolio. A winner-take-all needs maximum ceiling; a
   satellite needs to clear a threshold and nothing more; a 20-max GPP needs
   correlated diversity. Contest-aware allocation is probably a larger edge than
   anything else in this document, and it is currently not modelled at all.
2. **How would we know if any of this works?** `settlement.py` exists and no
   settlement loop is being run. Score tonight's 20 lineups against the real box
   score, record captain and exposure decisions against outcomes, and within a
   season there is a feedback signal. Without it every tuning decision is blind.
3. **Should Week 1 be treated differently?** All priors are prior-season, so
   Week 1 is structurally the engine's worst week and it improves as 2026 data
   accrues. That argues for smaller Week 1 stakes and a larger dart allocation,
   which is a bankroll decision rather than a code change.
4. **Why do offense and DST imply different game totals?** Offense is priced off
   prior-season rates while the DST points-allowed tier uses the market total,
   inside the same call. One of them is wrong on any given slate.
5. **What is the minimum ownership input that changes a decision?** Worth
   answering before building an ownership model, because it sets how accurate the
   model has to be.
6. **Is the target-share unit defect affecting Classic too?** `prior_score.py:243`
   is shared. If so it is mispricing every player who missed time, on every slate.

## 9. Ranked backlog

| # | Item | Why |
|---|---|---|
| 1 | Showdown policy constraints: captain-team, min/max per team, require-position, forbid/require pair, stack rules | Unlocks theses, darts and captain breadth at once; independently fixes QB starvation |
| 2 | `TARGET_SHARE` per-game vs `ROLE_CAPACITY` season-aggregate unit mismatch (`prior_score.py:243`) | Understates Nabers 2.77x and every player who missed time; check Classic exposure |
| 3 | `scripts/qa_showdown_portfolio.py` | Hand-written four times in one session |
| 4 | Allow `entry_ids` to bind a subset of reserved entries | Makes thesis-per-sleeve and dart sleeves first-class |
| 5 | Captain strata ranked on a ceiling statistic, not mean prior | Intelligent captain breadth rather than forced diversity |
| 6 | `scripts/make_showdown_policy.py` with a rung ladder | Classic has one; Showdown guessing cost 3 minutes on a live clock |
| 7 | Preflight asserting documented invariants (R20 and friends) before the first build | Regression cost 6 minutes on a live clock |
| 8 | Settlement loop: score every shipped portfolio after the game | No feedback signal exists today |
| 9 | Ownership: salary-derived prior plus post-hoc realized capture | Leverage is uncomputable without field exposure |
| 10 | Triage `test_w6_live_preflight::test_live_check_refuses_once_a_selected_player_has_locked` | Pre-existing failure, unrelated to this session |
| 11 | Resolve the `NFL_DFS_TLS_ALLOW_NONSTRICT_CA` classifier block | `--build-priors` unusable in a fresh session |

## 10. Recovery worth remembering

`--build-priors` failed on a blocked TLS opt-in. An earlier run in the same
session had already captured all seven nflverse artifacts with hashes and a
twelve-hour expiry. Running `priors-freeze` against that proposal directory and
passing `--prior-package-dir` on the rerun needed no network at all.

**A failed `--build-priors` does not mean a failed slate.** Check for an existing
proposal directory before treating the fetch as the critical path.
