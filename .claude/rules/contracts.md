---
paths:
  - "docs/DATA_CONTRACTS.md"
  - "src/nfl_dfs/contracts.py"
  - "src/nfl_dfs/*policy*.py"
  - "src/nfl_dfs/prelock_manifest.py"
  - "src/nfl_dfs/settlement.py"
  - "src/nfl_dfs/reference_settlement.py"
---

# Structured inputs are contracts

- Every structured input has a named, versioned contract in
  `docs/DATA_CONTRACTS.md` (`nfl_<thing>_v<n>`). A schema change is a new
  version with its own section; an existing version is never mutated so that
  archived artifacts stay readable.
- Contracts bind exact bytes: salary SHA-256, entry SHA-256, draft group, ordered
  Entry IDs, complete person identity maps. A binding mismatch is a refusal with
  a named code, never a warning.
- Fractions are exact decimals in the file (`fraction_unit`), integers are
  recomputed as effective integer caps, and the independent audit reparses the
  canonical normalized bytes rather than trusting the in-memory object.
- Refuse rather than guess: a field that cannot be resolved from bytes already on
  disk is a named blocker. No defaults for contest facts, payout tiers, field
  size, or ticket value.
- One freshness rule lives in `contracts.SourceFreshness`; do not add a second.
  The consumed source ledger is `nfl_source_ledger_v2`; v1 stays readable but
  cannot certify.
