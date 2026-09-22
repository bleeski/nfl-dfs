---
name: standings-checklist
description: Generate the list of DraftKings NFL contests Ben has entered that still need their standings export pulled and dropped in data/standings/inbox/, in the nfl-dfs workspace, and hand it back as a clickable HTML checklist plus a regenerated CONTESTS_AWAITING_STANDINGS.md. Use this whenever Ben asks what NFL standings we need to pull, what contests are missing standings, to regenerate or refresh the awaiting-standings list, for a pull checklist, or says something like "what do we need to pull down", "give me the standings checklist", or "what's left to pull", even if he doesn't name the file or the tool. Also use it to record a contest as unrecoverable (DK's export is gone) or as a placeholder/synthetic ID so future runs stop listing it. This is not nfl-classic-lineups or nfl-showdown-lineups, which build lineups from an uploaded salary/entries CSV, and not `nfl.sh settle`, which scores a complete hash-bound standings artifact: this skill only finds which already-entered contests are missing an export.
---

# NFL standings pull checklist

Ben enters a lot of DraftKings NFL contests, mostly cheap Showdown satellites
and qualifiers riding the same entry file as one main contest. Each one needs
its standings export pulled from DK by hand (DraftKings is never automated,
per `CLAUDE.md`'s permanent boundaries) and dropped in
`data/standings/inbox/`. This skill answers "which ones am I still missing"
by running the repo's own tool and handing back the checklist.

It is the NFL analog of `mlb-standings-pull-checklist`, with one structural
difference: nfl-dfs is single-operator, so there is **no claim step**. Do not
invent a `claim.py`-style take/release around this run.

## What it produces

- `data/standings/CONTESTS_AWAITING_STANDINGS.md` — the pull list, oldest
  evidence date first (DK's export ages out some days after a contest
  settles, so the oldest unpulled contests are the ones at risk, not the
  newest).
- `data/standings/standings_pulls_<date>.html` — the same list as a clickable
  checklist, plus `CONTESTS_AWAITING_STANDINGS.html` as the stable-name copy
  of the newest one. Clicking a contest's "Open export" link opens the DK
  download in a new tab **and** ticks that row off, so working the list is one
  click per contest, not two.

Evidence date is the newest date any entry file for that contest carries: a
`data/runs/` snapshot ID (`20260910-showdown-sf-lar`), else that file's own
modification date. It is a proxy for when the contest ran, not a DraftKings
fact; the entry CSV does not contain a contest date, and the outputs say so.

## Run it

```bash
.venv-linux/bin/python scripts/standings_checklist.py
```

That's the whole command: it writes the markdown and both HTML files and
prints the counts. `--json` prints the machine-readable report and writes
nothing (use it to answer a quick question in chat without touching the
repo). It never touches the network.

Read the tool's own module docstring for the exact discovery rules rather
than re-deriving them here. In short: it reuses `nfl_dfs.dk.parse_entries`,
the engine's own parser, against every CSV under `data/runs/*/inputs/` plus
loose `DKEntries*` / `DK_REVIEW_ENTRY*` CSVs in the repo root and
`Claude outputs/`; a salary CSV fails that parse and is skipped. Contests
found only outside `data/runs/` are tagged `loose` (real, but not hash-bound
— the 2026-09-13 DAL@NYG slate was built under a lock clock and only ever
existed as root CSVs). A contest counts as `filed` the moment any filename in
`data/standings/inbox/` carries its ID; that is a "something landed" check,
not a schema check. `normalized` and `settled` are stronger and separate
states — see below.

## Present the result

Send Ben the generated HTML so he gets a clickable card, and give him a
one-line summary: how many awaiting, filed, normalized, settled and
dispositioned, and which date is oldest (the thing to pull first). Only
`settled` means a contest entered the validation corpus. Do not re-paste the
contest list into chat; the file is the deliverable. If the count is small,
naming them inline instead is fine.

Two things worth a sentence in the summary when they are non-empty, because
they mean the scan found something a human should look at:

- **Loose-only contests** — every source for that contest was a repo-root or
  `Claude outputs/` CSV. Real contests, but hand-editable, so the entry count
  is worth a second look.
- **Unresolved inbox IDs** — a file in the inbox whose digit run matches no
  entered contest. Not a blocker; could be a contest run outside this repo, a
  renamed file, or a stale export. Name it rather than swallowing it.

## Recording a dead pull or a placeholder

When Ben confirms a pull is actually gone (DK contest history purged, export
comes back at zero bytes on a second attempt), record it so the tool stops
asking:

```bash
.venv-linux/bin/python scripts/standings_checklist.py --mark-unrecoverable CONTEST_ID "zero bytes on second pull, <date>"
```

For a synthetic or test contest ID that should stop showing up, use
`--mark-placeholder CONTEST_ID "<why it isn't a real contest>"` instead. Both
append to `data/standings/dispositions.json`, and both refuse a duplicate
rather than overwriting one. Never guess at either: these are Ben's calls
about what happened to a contest.

## The rules that hold regardless

1. **Never fetch DraftKings.** Ben pulls every export himself. The tool only
   ever writes the export URL as a string, built from a contest ID that came
   out of his own entry CSV; the fetch is his click, in his own logged-in
   browser. That is the same manual action `CLAUDE.md` already requires, and
   it is the only reason the link is allowed to exist. Never fetch it from a
   session, a script, or browser automation.
2. **`data/standings/inbox/` is flat.** Never sort exports into per-contest
   or per-mode subfolders; the filename scan only reads the top level.
3. **No claim step.** Single-operator repo. See above.
4. **Dropping a file in the inbox is still only the first of three states.**
   A raw DraftKings export does not satisfy `nfl.sh settle`'s complete-field,
   hash-bound `nfl_standings_csv_v2` contract: it carries no `Prize` column at
   all and names its lineups instead of identifying them. Since Q1B there *is*
   a downstream filer — `scripts/file_standings.py` — which converts one export
   into the contract artifact given the contest's payout table and the frozen
   salary snapshot for that slate, and refuses by name without them. Never
   invent an ad hoc filer inside this skill; run that tool, or report what it
   refused.
5. **A settled contest is the only one that counts for validation.** As of
   2026-09-14 the corpus holds zero, because no `data/runs/` snapshot carries
   the `nfl_prelock_run_manifest_v1` and `nfl_scenario_bank_v1` that
   `settle --request` binds — the `prior_review`/C1-C3 path never emits them.
   A pre-lock prediction record must never be reconstructed after the fact.
   See Q1B in `docs/backlog-archive/backlog-through-2026-09-22.md` and
   `docs/ROADMAP.md` Session 30.

Everything in `CLAUDE.md` applies, especially the permanent boundaries:
DraftKings login, contest entry, upload and money movement are manual;
uploaded bytes and earlier outputs are never overwritten. This skill reads
`data/runs/`, the repo root and `Claude outputs/`, and writes only under
`data/standings/`.

## This is not

- **nfl-classic-lineups / nfl-showdown-lineups** — they build a portfolio
  from an uploaded DK salary + entries CSV. They produce the entries; this
  one chases the results after the contest is over.
- **`sh ./nfl.sh settle`** — the scoring/settlement pipeline, which needs a
  normalized, complete-field, hash-bound standings artifact. A raw export
  sitting in the inbox is not that.

If Ben asks to actually pull the standings, or to upload anything: stop.
Pulling is his manual click; uploads never happen from a session at all.
This skill's job ends at handing him the checklist.

## For Ben, if he wants to run it himself

Windows desktop, from the repository root:

```powershell
.venv\Scripts\python.exe scripts\standings_checklist.py
```

Cloud session, from the repository root:

```sh
.venv-linux/bin/python scripts/standings_checklist.py
```

The checklist lands at `data\standings\standings_pulls_<date>.html` — open it
in a browser while logged into DraftKings.
