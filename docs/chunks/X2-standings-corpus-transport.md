# X2 — Give the standings corpus a durable, cloud-reachable home

Brief for chunk `X2` of the cloud-operability track. Status and dependencies are
tracked in `backlog.md` (Queue table and chunk index); this file is the
specification. Written 2026-09-20 from the cloud audit's finding F1.

**The decision is made. Ben ruled option (A) on 2026-09-21**, recorded as `R27`
in `backlog.md`; operator item 1b is closed. Build (A) and only (A): private
GitHub release assets with authenticated retrieval added to `sources.py`. The
R27 stanza carries the bounds and they are binding. Options (B) and (C) below
are kept for the reasoning, not as live choices.

- Goal: the 26 DraftKings standings exports are reachable from a cloud session,
  so the chunks that grade against them can run anywhere.
- Evidence: `data/standings/inbox/` is gitignored. A fresh clone has none of the
  corpus, so `P0`, `P0b`, `P4a`, `P4b` and `P5` cannot run in a cloud session at
  all. This is not a bug in those chunks; it is a transport gap. The grading
  data is on Ben's Windows checkout and reaches nowhere else.
- Why it gates the prize path: `P0` is the standings grading harness. Until the
  engine can grade its own historical output, `MODEL_STATUS` cannot leave
  `PRIOR_ONLY` and no promotion claim is available at any horizon. Everything
  downstream of calibration waits behind this transport question.

## The choice, and what was ruled

Recorded verbatim from operator item 1b. **(A) was ruled on 2026-09-21.**

- **(A) Private GitHub release assets, with authenticated retrieval added to
  `sources.py`.** Recommended in the audit. One pull request; the
  repository stays at its current ~1.5MB; the corpus gets the same treatment as
  every other source, meaning raw bytes, hash, source URI, observed time, parser
  version and a license decision. The cost is that authenticated retrieval is
  new surface in the allowlist module.
- **(B) Commit the corpus.** No engineering. The repository goes from ~1.5MB to
  roughly 80MB and grows with every slate, and clone time grows with it for
  every session forever.
- **(C) `P0` stays a Windows-only chunk.** No engineering, no repository growth,
  and the engine is permanently split across two machines: cloud sessions can
  develop the harness but can never run it against real data.

## Scope, once the option is chosen

- Implement whichever option Ben picked, and only that one.
- Under (A): extend `src/nfl_dfs/sources.py` with authenticated release-asset
  retrieval. Keep every capture invariant: raw bytes retained, sha256 recorded,
  canonical source URI recorded, timezone-aware observation time, parser version,
  license decision. Credentials come from the environment, never from a file in
  the repository and never from a literal in code.
- Under any option, record the transport decision and its date in
  `docs/DATA_CONTRACTS.md` so a later session does not relitigate it.

## Constraints

- **The corpus is immutable.** `data/standings/inbox/` is an immutable snapshot
  directory. Whatever transport lands must never overwrite a file there, and
  `.claude/settings.json` denies `Read` on the inbox for token reasons: print a
  schema-level summary with a script instead.
- **Never fetch DraftKings.** The exports are operator downloads. This chunk
  moves files Ben already downloaded; it does not acquire them. No path here may
  contact DraftKings for any reason.
- **A transported file is not a verified file.** Hash-bind on arrival and prove
  the bytes match what was published. A corpus that arrives without a hash
  binding is unbound hard evidence, which is `DO_NOT_UPLOAD`.
- Under (A), never commit a credential, and never log one.

## Acceptance

- A fresh cloud container can obtain the corpus by a documented command, and the
  obtained bytes hash-match the source.
- A test proves the transport refuses a byte-mismatched file rather than
  accepting it.
- Nothing under `data/standings/inbox/` is overwritten; demonstrate with hashes
  before and after.
- `P0` is unblocked: state explicitly in the changelog whether it can now run in
  a cloud session, with the evidence.
- Full suite green.

## Non-goals

No grading logic; that is `P0`. No change to the standings contract. No new
source beyond the corpus transport itself.

## Hand-back

Set `P0` runnable-in-cloud and write `docs/session-prompts/P0-standings-grading-harness.md`
(it already exists; refresh its runtime notes with the transport command).
