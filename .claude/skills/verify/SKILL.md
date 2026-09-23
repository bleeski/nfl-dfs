---
name: verify
description: Run the nfl-dfs verification stack (focused tests, complete pinned suite, doctor, compile/import, git diff --check) and paste the evidence. Use before claiming a roadmap session is done, or whenever Ben asks "is it green".
disable-model-invocation: true
---

Run the full verification stack and report evidence, not summaries.

1. Focused: `.\nfl.ps1 test tests/<changed test files>` (Linux: `sh ./nfl.sh test ...`).
2. Complete pinned suite with an extended tool timeout (600000 ms) or in the
   background with polling: `.\nfl.ps1 test`, or on Linux
   `sh ./nfl.sh test 2>&1 | tee /tmp/pytest.log` so step 7 records this run
   rather than a second one. Record the exact
   `N passed, M skipped[, K failed] in Ns` line. A run killed by the tool timeout
   is not a result; rerun it.
3. `.\nfl.ps1 doctor`; expect `pass_status: true`.
4. `python -m compileall` or a direct import of every changed module.
5. `git diff --check`.
6. Compare against the baseline recorded at session start. Any new failure or
   skip is named with the test id. The only expected skip is the platform one
   (the junction test on Linux, symlink permission on Windows); the known
   failure list is in `CLAUDE.md`.

7. Record it so the next session inherits it, whatever the result:
   `python3 scripts/record_verify.py --from-log /tmp/pytest.log` from step 2's
   log, or `--result-line '<the exact line>'` on Windows. Never run the suite a
   second time just to record it.
8. `python3 scripts/check_protected_paths.py` to learn now, not at merge time,
   whether this work needs Ben's `ben-review` label.

Output: a short table of check → result, then the pasted result lines. If any
check is red, say the session is not `Complete` and what is left.

A local green is what earns the push. CI (`suite`, `boundaries`,
`protected-paths`) is the gate that actually decides the merge, so never push
speculatively hoping CI will sort it out.
