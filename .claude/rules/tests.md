---
paths:
  - "tests/**"
  - "pyproject.toml"
---

# Tests

- Run focused files first, then the complete pinned suite. Record the exact
  `N passed, M skipped` line and wall time in `changelog.md`.
- Fixtures whose freshness matters derive expiry from the same clock the code
  under test reads: pass `now` (or `monkeypatch` it), never hardcode a date.
- Never delete, skip, or loosen a test to make a run pass. If a test is wrong,
  the changelog names the test and the reason before the fix.
- Golden coverage plus adversarial cases for every parser: truncated input,
  duplicate identity, missing column, blank lineup, wrong mode, field-size
  disagreement. Each yields a named refusal, not a repaired file.
- A determinism test (same bytes in, byte-identical artifact out) and a
  mutation test (a changed input byte withholds the artifact) accompany every
  new writer.
- No network in tests. Approved-source adapters are exercised through captured
  fixture bytes.
- At most one platform skip is expected: the Windows junction test on Linux,
  the symlink-permission case on Windows. Any other skip is a finding.
