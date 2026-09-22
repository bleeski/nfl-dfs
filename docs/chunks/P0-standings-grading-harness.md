# P0 — Standings grading harness, snapshots, and the failing test

Brief for chunk `P0` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: one deterministic command that grades a slate from its standings, so
  every later chunk's acceptance is a number the next session can reproduce.
- Read first: the findings report sections 2.2, 4.3, 5.3, 5.4 and appendix B;
  `src/nfl_dfs/settlement.py` (the `nfl_standings_csv_v2` normalizer and its two
  open contract defects); `scripts/file_standings.py`; `scripts/standings_checklist.py`;
  `tests/test_w6_live_preflight.py`.
- Files: new `src/nfl_dfs/standings_grade.py`; `src/nfl_dfs/cli.py` (one
  subcommand); `scripts/grade_standings.py` (thin wrapper); tests in
  `tests/test_standings_grade.py`; the one preflight test; new run folders under
  `data/runs/` for the two Showdown snapshots (operator item 2 supplies bytes;
  the session writes `intake.json` with hashes).
- Scope:
  - `nfl grade-standings --inbox data/standings/inbox --history <csv> --salary-map <json> --out data/standings/grades/<date>/`.
    Reads zips and loose CSVs, classifies mode from roster geometry, joins names
    to the same-slate salary file with zero tolerance for misses, and writes:
    per-contest thresholds (score to cash, top 1%, top 0.1%, first, tie size at
    rank 1), our entries with rank, percentile, dup count and per-lineup
    structural features, field feature lifts on the reference contest per slate
    (the section 4.3 table), duplication share of the top 1%, the user-portfolio
    concentration table (section 5.3), the hygiene bootstrap (section 5.4, seeded),
    and per-slate exposure of our portfolio against the field.
  - A `--payouts` option that, when a ladder is present, computes tie-pooled
    prize per entry (DK rule: pool the prizes of the ranks a tie group occupies)
    and prize share by duplication bucket.
  - Every table carries the contest's `N` including blanks, the reference-contest
    choice, and the statement that lifts describe this field only. Exports with
    `TimeRemaining > 0` are labelled `LIVE`, listed, and never graded. Metric
    definitions (top-1% rule, tie handling, paid rule, hygiene filters H1/H2,
    concentration bands) live in one registered module the later chunks import,
    so a challenger cannot be graded on a metric defined after the fact.
  - ~~Repair `test_live_check_refuses_once_a_selected_player_has_locked` by pinning
    `now` through `monkeypatch` as its docstring already says.~~ Done on
    2026-09-17, outside this chunk, because it blocked CI for every chunk. Every
    clock in that test now derives from the fixture's own lock times. Drop it
    from this chunk's acceptance; nothing else in P0 changes.
  - File the DAL@NYG and DEN@KC snapshots with `intake.json` hashes and the
    policy JSON already at the repo root moved in beside them (copy, do not delete
    the root files; that is a later cleanup with Ben's path list).
- Non-goals: no model, no ownership estimate, no change to selection or export,
  no settlement-corpus claims (the harness grades; it does not settle).
- Acceptance: the harness reproduces, to the printed precision, at least these
  report numbers: 71 owned entries with `Rank == Place`; DEN@KC 195526229 rank-1
  tie 206 and top-1% dup≥6 share 0.983; NE@SEA 193391013 23-way tie paying
  $54,065.22; pass-catcher=1 top-1% lift 1.60/1.53/2.08/1.39 across the four
  reference contests; Classic sub-5% count 0 top-1% rate 2.08%; 8,007
  user-portfolios with ≥10 entries. Runtime under three minutes on the 26 files.
  Full suite green.
- Hand-back: `docs/session-prompts/P2-contest-aware-policy.md` and
  `docs/session-prompts/P0b-provenance-completeness.md` written; P2 and P0b set
  `READY`.
