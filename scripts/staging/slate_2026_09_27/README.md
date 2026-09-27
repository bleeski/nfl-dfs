# Staged slate tooling, 2026-09-27 (Week 3 Classic)

Scratch scripts from the Week 3 slate session, as they ran (trailing
whitespace stripped), saved so a later session can turn them into supported
tools. They are not supported yet:
paths are hard-coded to that session's scratch folder
(`/tmp/claude-0/wk3aux`), nothing imports them, and they have no tests.
`changelog.md` (2026-09-27 entries) records what each one produced.

- `build_theses.py`: the five-thesis Classic builder. It calls
  `scripts/build_classic_portfolio.py` once per thesis and seed, then selects
  24 lineups across all candidates under global caps (exposure 7, overlap 5,
  unique rosters, at most two lineups per QB within a thesis). The final run
  produced `DK_REVIEW_ENTRY_wk3_theses_24_v4.csv` (`7ddac0e2...9d95`).
  Known slip, fixed in this copy: the builder refuses an existing `--out`, so
  each run needs fresh paths and must check the builder's exit code.
- `swap_inactives.py`: replaces newly inactive players (single swap, then a
  two-player fallback when the replacement breaks position counts), and
  applies value adds for named replacements. The v5 value adds and v6 salary
  redeploy were one-off inline scripts in that session, not this file.
- `example_portfolio_v7.json`: the final portfolio shape both scripts read
  and write (`lineups`, `assignments_by_entry_id`, `unfilled_entry_ids`,
  `construction`).
- `example_slate_context.json`: `scripts/make_slate_context.py` output for
  that slate.
