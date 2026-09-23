---
paths:
  - "docs/ROADMAP.md"
  - "backlog.md"
  - "changelog.md"
  - "IMPLEMENTATION_STATUS.md"
  - "docs/chunks/**"
---

# The session ledger

- These files are LF, not CRLF (verified 2026-09-16 and again 2026-09-22;
  `.gitattributes` sets `* text=auto eol=lf`). Never assume an ending: read the
  bytes first and match what is there, because writing CRLF into an LF file
  rewrites every line and buries the real change in a whole-file diff.
  `tests/test_roadmap_queue.py` checks the roadmap and the ledgers.
- **`docs/ROADMAP.md` is the only queue** (since 2026-09-22). Status lives only
  in its §2.2 status board, between the `roadmap-table` markers, which
  `scripts/repo_state.py` parses. Statuses: `Pending`, `In Progress`,
  `Complete`, `Deferred`; "startable" is derived from `Depends on`. A row
  outside the markers, an undeclared status or an unreadable dependency fails
  the test. Change a status in place; never delete a row; a split session gets
  a `Session NNb` row directly below. Every status change adds a row to §4.
- At close-out rewrite §1's Quick-Start to the next startable session; the test
  fails if it names anything else. Session prompt files are retired
  (`docs/session-prompts/archive/`); the card in §2.3 is the prompt.
- `backlog.md` is a pointer stub. Its history is
  `docs/backlog-archive/backlog-through-2026-09-22.md`; never add work to it.
- Read by section, never whole: `docs/ROADMAP.md` §1, §2.1 and the one card;
  `changelog.md` first 80 lines before inserting under `## Unreleased`. History
  is in `docs/backlog-archive/` and `docs/changelog-archive/`; `settings.json`
  prompts before a `Read` there. Grep for the ruling or date first and read only
  the matching section. When the live changelog passes ~500 lines, move the
  oldest entries to the archive verbatim.
- Chunk briefs in `docs/chunks/<ID>-<slug>.md` are specifications. A card in
  §2.3 cites them; status never lives in a brief. A new task gets a row and a
  card; a new brief only when the card needs more than a card holds.
- `changelog.md`: append a dated `###` section under `## Unreleased`. Added /
  Changed / Verification, with exact test counts, timings, hashes, and what was
  relaxed or left open. Never describe diagnostic or structurally legal output
  as certified or upload-ready. The roadmap ledger row points at this entry.
- `IMPLEMENTATION_STATUS.md`: update only when working capability changed.
- A fact only Ben can supply gets a `[BEN: ...]` flag in the card of the session
  it blocks, and that session's `Depends on` gets `BEN ruling`. It is listed
  again in the handoff. Never fill it with an invented specific.
