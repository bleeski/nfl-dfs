# QA1 — automated adversarial QA with constraint injection

Paste this whole file as the first message of a fresh Cowork dev session against
the `nfl-dfs` project. Do not run it on a slate day.

---

You are implementing tranche **QA1** in Ben's personal `nfl-dfs` repo. Read
`CLAUDE.md` first; it is binding, including the section "Shipping under a lock
clock". Then read `backlog.md` (the QA1 entry under "Next action"),
`docs/COWORK_RUNBOOK.md`, and `IMPLEMENTATION_STATUS.md`. Finish the session by
updating `backlog.md` and `changelog.md`. Never `git add .`, and never commit,
push or open a PR without an explicit reviewed path list from Ben.

## Runtime, before anything else

`device_bash` is dead: a Windows update released 2026-09-08 stops the Cowork
workspace mounting the folder, and it returns `sandbox-helper: no Plan9 drive
shares mounted`. Test it once, then work in the cloud container: stage the tree
with `device_stage_files` (src / tests / root+config+templates+scripts / docs is
four calls at 50 paths each), build with `sh ./nfl.sh setup` (~9s), and write
changes back with `device_commit_files` using a `stagedPath` under
`/mnt/user-data/outputs/` plus the `expectedMtimeMs` from the stage result.
Point `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and `NFL_DFS_UV_PYTHON_DIR` at
the scratchpad, copy `README.md` and `LICENSE` too, and do not add another `-q`.
Baseline to reproduce before you change anything: **630 passed, 1 skipped** in
roughly 150-215s.

## What exists today

The pre-handoff QA pass is a human procedure: a subagent reads the portfolio and
the artifacts, writes prose findings, and a person retypes the ones they accept
into a policy JSON. Section 6 of Ben's master spec
(`DFS_ENGINE_COWORK_SKILL_MASTER_SPEC.md`) wants something different: an audit
that emits **MILP constraints rather than prose**, applies a strict Pareto
filter, re-solves, and iterates at most three times with an early exit when an
iteration produces zero improvements.

Relevant code: `src/nfl_dfs/classic_portfolio.py` (bank + joint solve),
`src/nfl_dfs/classic_portfolio_policy.py` (the `nfl_classic_portfolio_policy_c2_v1`
contract, `SearchLimits`, exposure bounds, groups, stack rules),
`src/nfl_dfs/classic_review.py` (C3 independent audit),
`src/nfl_dfs/qa.py` and `src/nfl_dfs/referee.py` (the existing report-only QA and
REFEREE machinery, which is the precedent for "may block, never tunes"), and
`scripts/make_classic_policy.py` (the rung ladder and what a generated policy
looks like).

## The design question you must answer before writing code

The spec's Pareto filter is `ΔCeiling_contest >= 0 AND ΔSafety_portfolio >= 0`
with at least one strict inequality. **This engine has no ceiling and no
covariance.** `classic_portfolio.py` maximizes a sum of independent per-player
central estimates; `simulation.py` is not on the `prior_review` path and, when
measured on 2026-09-10, produced cross-team output correlation of about 0.004,
so its tail is not a ceiling either. `ownership.py` produces a flat distribution
and is never called by this path.

So decide, and write the decision down in `backlog.md` before implementing:
what do ΔCeiling and ΔSafety actually measure here? They will be proxies
computed from the prior objective and the portfolio's own structure (for example
prior-points total, count of distinct people, pairwise person overlap
distribution, stack and bring-back coverage, exposure concentration). **Name them
as proxies in every artifact and every report.** Do not call a proxy a ceiling, a
safety margin, EV, ROI, win probability, or calibrated anything. If you cannot
define one honestly, say so and implement only the half you can defend.

## Scope

1. A new module (suggested `src/nfl_dfs/adversarial_qa.py`) with a versioned
   contract, e.g. `nfl_classic_adversarial_qa_v1`, that takes the canonical C2
   artifacts (normalized policy, candidate bank, assignment, selection report,
   coverage) and returns typed findings.
2. Findings must be **expressible as policy deltas**, not prose: an added or
   tightened exposure bound, an exclusion, a group, a stack-rule change. A
   finding that cannot be expressed as a delta is reported and discarded, never
   applied by hand. The agent never edits a CSV cell and never touches an
   assignment.
3. Deterministic detectors first, because they are the ones that caught real
   defects on 2026-09-10: a lineup rostering a player alongside his own backup,
   a lineup with no QB, two entries separated by a single minimum-salary player,
   an officially inactive DK ID anywhere in the bank, over-concentration in one
   game, and a dominated asset (same role volume and team total, materially
   higher salary or exposure).
4. The loop: apply the accepted deltas to the policy, re-solve through the real
   `build_classic_candidate_bank` and `solve_classic_portfolio`, recompute the
   proxies, accept the iteration only if the Pareto rule holds, cap at three
   iterations, early-exit on zero improvements. Persist every iteration's policy
   hash, deltas, proxy values and accept/reject decision.
5. Fail-open, per `CLAUDE.md` "Shipping under a lock clock": **if the loop cannot
   improve the portfolio, or a re-solve is infeasible, or the time budget is
   spent, the ORIGINAL portfolio survives untouched.** QA1 must never be able to
   leave a run with no portfolio. Give it an explicit wall-clock budget and have
   it return the best accepted iteration so far when the budget expires.
6. Advisory, never a gate. Like REFEREE, it may report and it may block a
   promotion claim, but it does not certify and it does not change any of the
   four release truths. `MODEL_STATUS=PRIOR_ONLY` and
   `RELEASE_DECISION=DO_NOT_UPLOAD` are invariant.

## Out of scope

Ownership, field generation, duplication, payouts, economics, EV, and the
production portfolio selector. Do not import them and add a monkeypatch test
proving you did not, the way `test_classic_prior_review.py` does. Do not change
`prior_review.py`'s evidence gates. Do not start C4.

## Acceptance

- Golden coverage for each detector, plus adversarial cases where a proposed
  delta is correctly rejected by the Pareto filter.
- A test proving the original portfolio survives an infeasible re-solve, a
  budget expiry, and a zero-improvement iteration.
- A determinism test: identical inputs produce identical findings, deltas and
  final assignment hashes.
- The complete pinned suite passes with no regression from 630 passed, 1 skipped.
- `./nfl.ps1 doctor`, changed-module compile/import, and `git diff --check` pass.
- `backlog.md` records the proxy definitions and moves QA1 out of `READY`;
  `changelog.md` records the measured evidence.

## Tone of the finished work

State plainly what the agent can and cannot see. It is a structural critic over a
prior-only portfolio with no ownership or correlation model underneath it. That
makes it genuinely useful for catching the QB-and-his-own-backup class of defect
and genuinely unable to tell Ben whether a lineup will win money. Say both.
