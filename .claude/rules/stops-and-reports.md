---
paths:
  - "**"
---

# When to stop, and how a run ends

Written 2026-09-23 from Anthropic's prompting guide for the model this
repository runs (claude.dev blog, 2026-09-22). That model works longer on its
own than earlier ones and keeps Ben posted as it goes; on a long task it
sometimes stops to report instead of going on. It follows a rule that names
those stops, so this file names them, for every kind of session.
`slate-operation.md` adds the stops a slate wants; `git-authority.md` says what
needs no asking. Nothing here relaxes a boundary in `CLAUDE.md`.

## Keep going

When a step does not need Ben, take it. Put status, findings and
recommendations in the same message as the next command. A message with no
command in it ends the turn, and the work waits until Ben comes back, often
from a phone and often hours later.

Four endings have no place in a session:

- a summary that names the next step instead of taking it;
- an offer to continue, or to stop unless he objects;
- a list of choices none of which blocks the work;
- stopping to report because a stage finished.

A question that does not block is a `[BEN: ...]` flag or a line under
**Needs Ben** in the final report, not a stopped turn. A judgment call is
yours: decide it, say which way and why, and let Ben overturn it.

## Stop and ask

Besides any stop that `CLAUDE.md` or the skill you are running names, stop
only when one of these holds:

- the next step needs a fact only Ben has (a ruling, a file, a threshold he has
  not set), and nothing else in the task can proceed without it;
- the next step is destructive or reaches outside this repository, and no rule
  here already authorizes it. What the permanent boundaries in `CLAUDE.md` or
  `git-authority.md` forbid stays forbidden; asking does not make it allowed;
- the task is done.

A pull request that touches a protected path is not a stop: label it
`ben-review`, say so, and finish everything else.

## Keep the task list in a file

A session that will run long keeps its working list in `state/tasks/<SNN>.md`,
or `state/tasks/<slug>.md` for work that is not a roadmap session. `state/` is
gitignored apart from `claims.json`, so the file never reaches a diff. Write it
before the first code change: the card's acceptance verbatim, the files to
touch, the tests to write first, assumptions and tradeoffs, the breakpoint and
what is out of scope, then one `- [ ]` line per item. Tick items as they land,
add what you find, and keep the last suite line and any open `[BEN: ...]` flag
in it. Read the file, not the scrollback, to see where the run is.

It survives compaction, which the scrollback does not, and the session-start
hook prints each task file's progress after a compaction or `/clear`. It is
working notes, never status: `docs/ROADMAP.md` §2.2 is still the only status.

## How a run ends

End every run, slate or development, with three parts in this order:

1. **Needs Ben.** Every decision, file, label, approval or manual step he owes,
   first, because it is the first thing he reads. For a slate that includes the
   file path, its release truths and each named gap. Write "nothing" when
   nothing is owed.
2. **Changed.** What landed, with the pull request link, whether it merged, and
   the exact suite line.
3. **Found.** What was relaxed, what is left open, and anything you could not
   confirm, with where you looked.
