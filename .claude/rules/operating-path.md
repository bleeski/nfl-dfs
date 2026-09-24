---
paths:
  - "src/nfl_dfs/prior_review.py"
  - "src/nfl_dfs/cowork.py"
  - "src/nfl_dfs/cli.py"
  - "src/nfl_dfs/readable_review.py"
  - "src/nfl_dfs/classic_review.py"
  - "src/nfl_dfs/review_export.py"
  - "src/nfl_dfs/workbook.py"
  - "src/nfl_dfs/certification.py"
  - "src/nfl_dfs/release.py"
---

# The operating path (`prior_review`) and its review artifacts

- `prior_review` has three success exits (Showdown, Classic C1/C2, Classic C3).
  Every exit emits the pre-lock manifest and reports the release truths,
  `DELIVERY_STATE` among them (`nfl_release_truths_v2`, R28);
  a change that reaches one exit must reach all three, with a test per exit.
- The baseline goes first (R28, Session 06). `run-slate` builds and publishes
  it right after intake, before the probe, policy, priors, weather, roles or
  any solve, and every exit reads the pointer back: the result's
  `DELIVERY_STATE`, `latest_deliverable` and the delivery half of
  `release_truths` describe the file the pointer names, with
  `IMPROVEMENT_NOT_DELIVERED` (`P`) when that is still the baseline. A review
  CSV replaces the baseline only through `delivery.replace`; publish is for a
  run whose baseline did not publish. A blocked stage, the pre-review blocked
  exit, a withheld CSV, a refused C1 export and the outer handler all leave the
  baseline named. Exit codes keep their meaning: the baseline never turns a
  failed review into 0.
- A new `DK_REVIEW_ENTRY` CSV is written only after the independent audit
  returns `PASS`. A time or search limit with no incumbent, solver errors,
  incomplete-bank exhaustion, modeled-bank infeasibility, assignment mismatch,
  audit failure or input mutation preserve earlier outputs and write nothing
  new. Since Session 08 a limit that leaves a validated incumbent, or a C2 bank
  a limit stopped with the entry count and a policy-feasible witness, does
  write one after that audit, named as `PORTFOLIO_SELECTION_LIMIT_INCUMBENT` or
  `CANDIDATE_BANK_STOPPED_AT_LIMIT`, and never called optimal. Classic C1 exports
  its own `assignments.csv` in `run-slate` through the baseline's writer and
  audit (`DK_REVIEW_ENTRY_C1_<run_id>.csv`, rung 4); C2 without C3 writes no
  CSV. No operating profile writes `DK_UPLOAD` (only `certify` and governed
  `late-swap` can, and neither is on this path).
- Review JSON/HTML/workbook are rebuilt from the exact bound artifacts and
  reconciled (`DISPLAY_RECONCILIATION=PASS`). Any disagreement is
  `READABLE_REVIEW_FAILED` (Classic: `CLASSIC_C3_READABLE_REVIEW_FAILED`) and
  exit code 2, classified code by code through the gate registry (R28,
  Session 05). A roster, Entry ID or byte disagreement (`V`), or a code the
  registry cannot classify, withholds the CSV: the result does not advertise
  it. Any other keeps it in the result and both indexes with a presentation
  limitation, once `delivery.replace` (or `publish`) has revalidated it. C3 removes only its
  failed JSON and HTML; `LATEST_DELIVERABLE.json` names only a revalidated file.
- Escape markup and render spreadsheet-active prefixes inert without changing
  the source bytes. HTML is self-contained (no external assets).
- Exit code 0 means review generation completed. The `warning` and
  `meaning` strings must keep saying `PRIOR_ONLY / DO_NOT_UPLOAD`; do not soften
  them to make output read better.
- Refuse a supplied policy on profiles that do not support it rather than
  ignoring it; refuse an `assignment_csv` on `prior_review` (that is the manual
  guardrail path, kept separate on purpose).
- New diagnostics (quantiles, `max_person_share`, `predicted_copies`,
  `SALARY_RANK_DIVERGENCE`) are additional named fields with their own
  `does_not_establish` text; they never change a release truth.
