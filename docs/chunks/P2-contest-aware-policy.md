# P2 — Contest-aware assignment, structural hygiene, and the concentration control

Brief for chunk `P2` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

Hand-back lines below that name a `docs/session-prompts/` file or a `READY`
status predate the roadmap. At close-out follow `.claude/skills/close-out/SKILL.md`
instead: the session card and the §1 Quick-Start replace per-chunk prompts.

- Goal: the policy layer can express the five construction rules that held in
  all four games, cap portfolio concentration, and stop mapping the weakest
  lineups onto first-place contests.
- Evidence: report sections 4.3, 5.1 to 5.4, 8.1 A and C, 8.2 G to I.
- Read first: `src/nfl_dfs/portfolio_policy.py` (Showdown contract v1),
  `src/nfl_dfs/classic_portfolio_policy.py` (already has groups and stack
  rules), `src/nfl_dfs/portfolio_enforcement.py`, `selection.py:assignments_for_entries`,
  `scripts/make_showdown_policy.py`, `scripts/make_classic_policy.py` and its rung
  ladder, `docs/RUN_RECORD_20260914_DEN_KC.md` defects 4 and 5.
- Files: the six above, `docs/DATA_CONTRACTS.md`, tests.
- Scope:
  - Showdown policy v2 adds per-lineup structural bounds: `qb_count` min/max,
    `pass_catchers_with_rostered_qb` min/max, `salary_left` min/max,
    `kicker_count` max, `dst_count` max; Classic policy gains `salary_left`
    bounds and `offense_against_own_dst` max if absent. Every new bound is
    recomputed independently in the audit from the roster bytes.
  - Portfolio-level `max_person_share` (share of entries containing one
    underlying person, CPT or FLEX) in both contracts, audited, and reported in
    every review as `max_person_share` with the person named. Generators default
    it to 0.80, the field median among multi-entry portfolios.
  - Generator defaults (relaxable rungs, in this order when a rung is dropped:
    salary band, pass-catcher band, K/DST caps, QB count, `max_person_share`):
    Showdown one QB, one to two pass catchers with him, $0 to $1,500 left, at
    most one K and one DST, two-QB lineups capped at the entry count times 0.4;
    Classic one to two pass catchers, at least one bring-back, $0 to $1,000 left,
    no offense against own DST, DST not on the QB's team. No kicker or DST
    exclusion by default: kickers were in 45% and 68% of the top 1% in NE@SEA
    and SF@LAR, defenses in 68% and 82% in NE@SEA and DEN@KC, and the engine
    portfolios carried none of either.
  - Assignment order becomes a policy input with three registered values:
    `prior_points_desc` (current), `round_robin_by_contest` (new default), and
    `tail_proxy_desc` (accepted only when a lineup tail statistic is present,
    which P3b provides). `contest_facts_csv` (contest id, field size, places
    paid) tags each entry with its paid fraction; entries under 5% are labelled
    `FIRST_PLACE_OBJECTIVE` in the review. The label is a fact from supplied
    numbers, never inferred from a contest name.
- Non-goals: no scenario bank, no ownership, no change to the objective, no
  retrospective tuning of the bands to any single game (the bands above are the
  four-game-stable set and nothing else).
- Acceptance: the DAL@NYG and DEN@KC snapshots re-run under the new generator
  produce portfolios whose `max_person_share` ≤ 0.80, hygiene pass rate 100% at
  rung 0, satellite rows no longer receive the lowest-prior lineups, and the P0
  harness scores them against the archived fields (report both; do not present
  the rerun as achievable pre-lock, it is a mechanism check). Infeasible bounds
  fail closed with the rung named. Full suite green.
- Hand-back: `docs/session-prompts/P4a-ownership-challenger.md`; P4a `READY`;
  C4 stays `BLOCKED` on operator files.
