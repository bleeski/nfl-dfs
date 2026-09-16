---
paths:
  - "backlog.md"
  - "changelog.md"
  - "IMPLEMENTATION_STATUS.md"
  - "docs/session-prompts/**"
  - "docs/chunks/**"
---

# The session ledger

- These files are LF, not CRLF (verified 2026-09-16: 0 CRLF in all three;
  `.gitattributes` sets `* text=auto eol=lf`). Never assume an ending — read the
  bytes first and match what is there, because writing CRLF into an LF file
  rewrites every line and buries the real change in a whole-file diff. Check
  with a byte count before and after an edit.
- Read them by section, never whole: `backlog.md` head with `limit` (~230
  lines) plus the one brief in `docs/chunks/`; `changelog.md` first 80 lines
  before inserting under `## Unreleased`. History is in `docs/backlog-archive/`
  and `docs/changelog-archive/`; `settings.json` prompts before a `Read` there.
  Grep for the ruling or date first and read only the matching section. When the live changelog passes ~500
  lines, move the oldest entries to the archive verbatim.
- Chunk briefs live in `docs/chunks/<ID>-<slug>.md`; status lives only in
  `backlog.md` (Queue table and chunk index). A new chunk gets both.
- `backlog.md`: the current program section at the top is the queue. Change a
  chunk's status in place; never delete history; when a chunk closes, set the
  next dependency-satisfied chunk `READY` and write its prompt to
  `docs/session-prompts/<ID>-<slug>.md`. Statuses: `READY`, `IN_PROGRESS`,
  `BLOCKED`, `DONE`, `DEFERRED`.
- `changelog.md`: append a dated `###` section under `## Unreleased`. Added /
  Changed / Verification, with exact test counts, timings, hashes, and what was
  relaxed or left open. Never describe diagnostic or structurally legal output
  as certified or upload-ready.
- `IMPLEMENTATION_STATUS.md`: update only when working capability changed.
- A fact only Ben can supply gets a `[BEN: ...]` flag, listed again in the
  handoff. Never fill it with an invented specific.
- Session prompts follow `Q1B-settlement-intake.md`: title, paste instruction,
  runtime notes, why, scope, out of scope, acceptance, close-out.
