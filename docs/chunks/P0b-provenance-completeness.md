# P0b — Provenance completeness, manual-build manifests, pre-registration

Brief for chunk `P0b` of the prize-tail program. Status, dependencies and hand-back are tracked in `backlog.md` (Queue table and chunk index); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: every set of lineups Ben enters, engine-built or not, leaves a pre-lock
  record that a later grading can be attributed to, and no review CSV is called
  shipped while its policy bytes are missing from the run folder.
- Evidence: Week 1 Classic (20 entries, $100) ran from
  `DKEntries_NFL_Week1_LATESWAP_FINAL.csv` with no build artifact; the SF@LAR
  shipped CSV rosters a person its `portfolio_policy_FINAL.json` excludes, and
  the policy that produced it is not in `data/runs`; DAL@NYG and DEN@KC ran with
  no `data/runs` snapshot at all.
- Read first: `src/nfl_dfs/prelock_manifest.py` (Q1C), `src/nfl_dfs/preflight.py`,
  `src/nfl_dfs/cowork.py` (`prior_review_artifacts` and the hash map),
  the 2026-09-14 close-out in `Next action`.
- Files: `prelock_manifest.py`, `prior_review.py`, `cli.py`, new
  `src/nfl_dfs/preregistration.py`, tests.
- Scope:
  - Run-folder completeness: the top-level result may advertise a
    `DK_REVIEW_ENTRY` only when the normalized policy bytes, source policy bytes,
    prior vector, candidate bank, selection report and the CSV's hash are all
    present under the run folder and named in `prior_review_artifacts`. A miss is
    `PROVENANCE_INCOMPLETE`, a named blocker, and the CSV is still written.
  - `nfl record-manual-entries --salaries <csv> --entries <filled DKEntries>`:
    validates legality and exact IDs, writes a `nfl_prelock_run_manifest_v1` for
    a hand-built or externally built set of lineups with
    `build_source=MANUAL`, hashes both files, and refuses after the earliest lock
    on the slate. It certifies nothing and must say so; it exists so the next
    Week 1 is gradable.
  - Pre-registration record: `preregistration.json` in the run folder naming
    the champion configuration, the challenger (policy hash, objective version,
    sleeve size), the grading metrics by registered name, and the slate. Written
    before lock, hashed into the manifest, read by the harness at grading time.
- Non-goals: no settlement, no change to any release truth, no automatic
  recording of anything after lock.
- Acceptance: a fixture with a filled DKEntries file produces a manifest that
  `grade-standings` later joins to a standings export by Entry ID; a run folder
  missing its normalized policy is refused as `PROVENANCE_INCOMPLETE` while an
  identical complete folder passes; full suite green.
- Hand-back: none new; P2 is already `READY` from P0.
