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
  Every exit emits the pre-lock manifest and reports the four release truths
  (a fifth, `DELIVERY_STATE`, has had a contract since Session 03 under R28;
  Sessions 04 to 09 bring it to the exits);
  a change that reaches one exit must reach all three, with a test per exit.
- A new `DK_REVIEW_ENTRY` CSV is written only after the independent audit
  returns `PASS`. Time limits, solver errors, incomplete-bank exhaustion,
  modeled-bank infeasibility, assignment mismatch, audit failure or input
  mutation preserve earlier outputs and write nothing new. Classic C1/C2 write
  no upload-shaped CSV at all; no operating profile writes `DK_UPLOAD` (only
  `certify` and governed `late-swap` can, and neither is on this path).
- Review JSON/HTML/workbook are rebuilt from the exact bound artifacts and
  reconciled (`DISPLAY_RECONCILIATION=PASS`). Any disagreement is
  `READABLE_REVIEW_FAILED` (Classic: `CLASSIC_C3_READABLE_REVIEW_FAILED`) and
  exit code 2, classified code by code through the gate registry (R28,
  Session 05). A roster, Entry ID or byte disagreement (`V`), or a code the
  registry cannot classify, withholds the CSV: the result does not advertise
  it. Any other keeps it in the result and both indexes with a presentation
  limitation, once `delivery.publish` has revalidated it. C3 removes only its
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
