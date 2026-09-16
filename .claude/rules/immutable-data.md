---
paths:
  - "data/**"
  - "tests/fixtures/supplied/**"
  - "Claude outputs/**"
  - "DKEntries_*.csv"
  - "*_official_status.csv"
  - "*_portfolio_policy_*.json"
---

# Uploaded bytes and run snapshots

- Files under `data/standings/inbox/`, `data/runs/<run>/inputs/`, and
  `tests/fixtures/supplied/` are DraftKings downloads or exact snapshots of
  them. Never edit, rename, reformat, or delete one. Derive from them into a new
  content-addressed file and record the source SHA-256 beside it.
- A new run is a new folder under `data/runs/` with `intake.json` naming every
  input path and hash. Never write a second run's output into an earlier folder.
- `data/runs/*` and `data/standings/inbox/*` are gitignored on purpose (bulk
  operator data). Small records that are Ben's rulings (`dispositions.json`,
  checklists) are tracked; keep that split.
- The loose `DKEntries_*.csv`, `*_official_status.csv` and
  `*_portfolio_policy_*.json` files at the repo root are the shipped DAL@NYG and
  DEN@KC artifacts. Copy them into snapshot folders; do not move or delete them
  without Ben's path list.
- Classify a file by its schema (header row, roster geometry), never by its name.
- Never Read one of these files into context. A standings export is up to 167
  MB and a salary file is a few hundred rows; print the header, row count and a
  hash with a short script and reason from that. Tests exercise them through
  pytest, not through the context window.
