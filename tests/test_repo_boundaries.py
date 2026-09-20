"""The permanent boundaries in ``CLAUDE.md``, asserted instead of described.

Claude merges its own pull requests once CI is green (``docs/CLAUDE_CODE_SETUP.md``),
so the boundaries that used to rely on Ben reading a diff have to be executable.
Each test here pins one invariant that prose alone previously carried. A change
that trips one of these is not a style disagreement: it is a change to what the
engine is allowed to do, and it belongs in a pull request Ben looks at.

These are structural checks over the source tree. They deliberately overlap the
per-path behavioural tests elsewhere in the suite; those prove one code path
behaves, these prove no new code path was added that does not.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src" / "nfl_dfs"


def _load_protected_paths_module():
    """Import ``scripts/check_protected_paths.py`` without a package on sys.path."""
    script = PROJECT_ROOT / "scripts" / "check_protected_paths.py"
    spec = importlib.util.spec_from_file_location("check_protected_paths", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source_modules() -> tuple[Path, ...]:
    return tuple(sorted(SRC.glob("*.py")))


def _local_imports(module_name: str) -> set[str]:
    """Return the ``nfl_dfs`` sibling modules that ``module_name`` imports."""
    path = SRC / f"{module_name}.py"
    if not path.is_file():
        return set()
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                found.add(node.module.split(".")[0])
            elif node.module and node.module.startswith("nfl_dfs"):
                parts = node.module.split(".")
                if len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("nfl_dfs."):
                    found.add(alias.name.split(".")[1])
    return {name for name in found if (SRC / f"{name}.py").is_file()}


def _import_closure(root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(_local_imports(current) - seen)
    return seen


# --------------------------------------------------------------------------
# The protected list, which is what stops Claude merging Ben's decisions.
# --------------------------------------------------------------------------


def test_protected_path_list_is_loadable_and_covers_the_named_files() -> None:
    module = _load_protected_paths_module()
    globs = module.load_protected_globs()
    assert globs, "the protected list must never be emptied"

    # Every literal entry (no glob metacharacter) has to name a file that exists,
    # otherwise the list silently stops protecting something that was renamed.
    for pattern in globs:
        if any(ch in pattern for ch in "*?["):
            continue
        assert (PROJECT_ROOT / pattern).exists(), f"protected path no longer exists: {pattern}"


def test_protected_path_matcher_flags_a_boundary_change_and_ignores_a_test() -> None:
    module = _load_protected_paths_module()
    globs = module.load_protected_globs()

    flagged = module.protected_matches(
        [
            "CLAUDE.md",
            "src/nfl_dfs/release.py",
            "config/evidence_policy.json",
            ".claude/rules/ledger.md",
            "tests/test_repo_boundaries.py",
            "src/nfl_dfs/ownership.py",
        ],
        globs,
    )
    assert "CLAUDE.md" in flagged
    assert "src/nfl_dfs/release.py" in flagged
    assert "config/evidence_policy.json" in flagged
    assert ".claude/rules/ledger.md" in flagged
    # Ordinary work must stay mergeable without Ben, or the gate is just the old
    # bottleneck wearing a label.
    assert "tests/test_repo_boundaries.py" not in flagged
    assert "src/nfl_dfs/ownership.py" not in flagged


# --------------------------------------------------------------------------
# Nothing on the prior-review path can produce an upload-shaped package.
# --------------------------------------------------------------------------

# `cli` and `late_swap` build a `DK_UPLOAD_` path on the legacy certified path.
# `classic_review` and `classic_scale_acceptance` name it only to refuse it.
# A fifth module appearing here means a new writer was added.
DK_UPLOAD_MODULES = frozenset(
    {"cli.py", "late_swap.py", "classic_review.py", "classic_scale_acceptance.py"}
)


def test_dk_upload_is_confined_to_a_pinned_set_of_modules() -> None:
    mentions = {
        path.name
        for path in _source_modules()
        if "DK_UPLOAD" in path.read_text(encoding="utf-8")
    }
    assert mentions == DK_UPLOAD_MODULES, (
        "a module started referring to DK_UPLOAD. Adding a writer is a release-truth "
        "change and belongs in a pull request Ben reviews; adding a refusal is fine "
        "but still has to be recorded here."
    )


def test_prior_review_cannot_reach_a_dk_upload_writer() -> None:
    closure = _import_closure("prior_review")
    assert "cli" not in closure
    assert "late_swap" not in closure


def test_prior_review_does_not_import_field_or_portfolio_economics() -> None:
    # `.claude/rules/operating-path.md` states this, and the prior-review report
    # asserts the claim as a string. This proves the structure behind the claim.
    closure = _import_closure("prior_review")
    assert "field" not in closure
    assert "economics" not in closure


# --------------------------------------------------------------------------
# AvgPointsPerGame stays in the untouched raw-byte layer.
# --------------------------------------------------------------------------

APPG_MODULES = frozenset({"dk.py", "cowork.py"})


def test_avg_points_per_game_never_leaves_the_raw_byte_layer() -> None:
    mentions = {
        path.name
        for path in _source_modules()
        if "AvgPointsPerGame" in path.read_text(encoding="utf-8")
    }
    assert mentions == APPG_MODULES, (
        "AvgPointsPerGame reached a module outside the raw DraftKings reader. It may "
        "never influence normalized inputs, projections, candidates or selection."
    )


# --------------------------------------------------------------------------
# Retrieval stays inside the allowlist.
# --------------------------------------------------------------------------

EXPECTED_ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "raw.githubusercontent.com",
        "api.github.com",
        "api.sleeper.app",
        "api.weather.gov",
        "api.the-odds-api.com",
    }
)
EXPECTED_PROHIBITED_HOSTS = frozenset(
    {"nfl.com", "www.nfl.com", "draftkings.com", "www.draftkings.com"}
)


def test_source_allowlist_is_pinned() -> None:
    from nfl_dfs import sources

    assert frozenset(sources.ALLOWED_HOSTS) == EXPECTED_ALLOWED_HOSTS, (
        "the retrieval allowlist changed. Every host needs a recorded license "
        "decision before it can be a model input."
    )
    assert frozenset(sources.PROHIBITED_HOSTS) == EXPECTED_PROHIBITED_HOSTS, (
        "a DraftKings or NFL host left the prohibited set. Automated retrieval from "
        "DraftKings is a permanent boundary."
    )


# --------------------------------------------------------------------------
# Diagnostics never get dressed up as proven economics.
# --------------------------------------------------------------------------

BANNED_TOKENS = frozenset({"ev", "roi", "win_probability", "cash_probability", "edge"})

# `CALIBRATED` in exactly that casing is the registered influence tier in
# `learning.py`, a promotion state rather than a claim about a prior. Any other
# casing is the claim, and stays banned.
CALIBRATED_TIER_LITERAL = "CALIBRATED"


def _banned_occurrences() -> list[tuple[str, int, str, str]]:
    found: list[tuple[str, int, str, str]] = []
    for path in _source_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value.strip()
                lowered = literal.lower()
                if lowered in BANNED_TOKENS:
                    found.append((path.name, node.lineno, "string", literal))
                elif lowered == "calibrated" and literal != CALIBRATED_TIER_LITERAL:
                    found.append((path.name, node.lineno, "string", literal))
            elif isinstance(node, ast.Name) and node.id.lower() in BANNED_TOKENS:
                found.append((path.name, node.lineno, "name", node.id))
            elif isinstance(node, ast.arg) and node.arg.lower() in BANNED_TOKENS:
                found.append((path.name, node.lineno, "argument", node.arg))
            elif isinstance(node, ast.Attribute) and node.attr.lower() in BANNED_TOKENS:
                found.append((path.name, node.lineno, "attribute", node.attr))
    return found


def test_no_module_names_a_value_ev_roi_or_edge() -> None:
    occurrences = _banned_occurrences()
    rendered = "\n".join(
        f"  {name}:{line} {kind} {text!r}" for name, line, kind, text in occurrences
    )
    assert not occurrences, (
        "cold-start projections, ownership, fields and duplication estimates are "
        "diagnostics or priors. They are never EV, ROI, win probability, cash "
        f"probability, calibrated ownership or proven edge.\n{rendered}"
    )


# --------------------------------------------------------------------------
# Every current path still ends PRIOR_ONLY / DO_NOT_UPLOAD.
# --------------------------------------------------------------------------


def test_release_truths_are_the_four_named_fields() -> None:
    from nfl_dfs import release

    text = (SRC / "release.py").read_text(encoding="utf-8")
    for truth in ("file_valid", "evidence_state", "model_status", "release_decision"):
        assert truth in text, f"release truth {truth} disappeared from release.py"
    assert "DO_NOT_UPLOAD" in text
    assert hasattr(release, "ReleasePolicyResult")


def test_certified_upload_still_requires_a_prospectively_validated_model() -> None:
    # `FILE_VALID` never implies release, and a CERTIFIED compatibility status
    # derives only from RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE. Every current
    # path ends PRIOR_ONLY / DO_NOT_UPLOAD until Q6 promotion.
    from nfl_dfs.contracts import ModelStatus, ReleaseDecision

    assert ModelStatus.PRIOR_ONLY.value == "PRIOR_ONLY"
    assert ModelStatus.PROSPECTIVELY_VALIDATED.value == "PROSPECTIVELY_VALIDATED"
    assert ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE.value == "CERTIFIED_UPLOAD_PACKAGE"
    assert ReleaseDecision.DO_NOT_UPLOAD.value == "DO_NOT_UPLOAD"

    contracts_text = (SRC / "contracts.py").read_text(encoding="utf-8")
    assert "ModelStatus.PROSPECTIVELY_VALIDATED" in contracts_text, (
        "the guard tying a CERTIFIED release decision to a prospectively validated "
        "model status is gone from contracts.py"
    )


@pytest.mark.parametrize("module_name", ["prior_review", "classic_review"])
def test_review_modules_still_say_do_not_upload(module_name: str) -> None:
    text = (SRC / f"{module_name}.py").read_text(encoding="utf-8")
    assert "DO_NOT_UPLOAD" in text, (
        f"{module_name}.py stopped saying DO_NOT_UPLOAD. Exit code 0 means review "
        "generation completed, never that uploading is cleared."
    )


# --------------------------------------------------------------------------
# The Bash guard, which catches what prefix matching in settings.json cannot.
# --------------------------------------------------------------------------


def _load_bash_guard():
    hook = PROJECT_ROOT / ".claude" / "hooks" / "guard_bash.py"
    spec = importlib.util.spec_from_file_location("guard_bash", hook)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REFUSED_COMMANDS = (
    # The two shapes a prefix rule in settings.json cannot see: a flag after an
    # allowed prefix, and a second command in a chain.
    "git push -u origin claude/x --force",
    "git status && git push --force origin main",
    "git log --oneline -5; git commit --amend -m 'x'",
    # And the plain forms, which settings.json also denies.
    "git push --force-with-lease origin claude/x",
    "git push -f origin claude/x",
    "git push origin main",
    "git push origin HEAD:main",
    # Refspec forms reach main with no `main` token after `origin` and force
    # with no `--force` token at all. An adversarial review found these after
    # the first version of the guard shipped without them.
    "git push origin +HEAD:main",
    "git push origin feature:main",
    "git push origin +feature:main",
    "git push origin feature:refs/heads/main",
    "git push origin HEAD:refs/heads/main",
    "git push origin +claude/x:claude/x",
    "git commit --amend --no-edit",
    "git add -A",
    "git add --all src/",
    "git add -u",
    "git add -u; echo done",
    "git add -u && git commit -m x",
    # `-u` among other flags, in either order, is still the whole tree.
    "git add -v -u",
    "git add -u -v",
    # A pathspec that is itself the whole tree does not narrow `-u`. From the
    # repository root `git add -u .` stages every tracked change exactly like
    # the bare form. An adversarial review found these after the first version
    # of the narrowed pattern was written.
    "git add -u .",
    "git add -u ./",
    "git add -u *",
    "git add -u :/",
    "git add -v -u .",
    "git add .",
    "git rebase origin/main",
    "git filter-branch --tree-filter true HEAD",
    "git reset --hard origin/main",
    "git clean -fd",
    # Everything but the two read-only stash verbs. Bare `git stash` is
    # `stash push`, and so is every flag-first form: git takes flags in place
    # of the `push` keyword, which is why naming the mutating verbs was the
    # wrong shape and an allowlist of `list`/`show` is the right one.
    "git stash",
    "git stash push -m wip",
    "git stash save wip",
    "git stash pop",
    "git stash apply",
    "git stash drop",
    "git stash clear",
    "git stash branch recovered",
    "git stash -u",
    "git stash --include-untracked",
    "git stash -a",
    "git stash -p",
    "git stash -k",
    "git status && git stash push",
    "git status && git stash -u",
    "git branch -D claude/x",
)

ALLOWED_COMMANDS = (
    # Ordinary work must stay unobstructed, or the guard becomes the bottleneck
    # it was written to remove.
    "git status --short --branch",
    "git add src/nfl_dfs/ownership.py tests/test_ownership.py",
    "git commit -m 'Add the thing'",
    "git push -u origin claude/p0-standings-grading-harness",
    "git push origin --delete claude/p0-standings-grading-harness",
    # A non-forced refspec onto a claude/* branch, and a branch whose name
    # merely contains "main". Neither may be caught by the refspec patterns.
    "git push origin HEAD:refs/heads/claude/p0-standings-grading-harness",
    "git push -u origin claude/main-runbook-rewrite",
    "git branch -d claude/p0-standings-grading-harness",
    "git merge origin/main",
    "git diff --check",
    "git log --oneline -15",
    "sh ./nfl.sh test tests/test_repo_boundaries.py",
    # `-f` as part of another word, and a filename that merely contains "main".
    "grep -rn --include=*.py -f patterns.txt src/",
    "git add docs/main-runbook.md",
    # Two false positives recorded on 2026-09-17 and repaired in H2. A scoped
    # `-u` is an explicit path list, and both read-only stash verbs are
    # read-only. Neither ever risked anything; both cost a workaround.
    "git add -u src/nfl_dfs/ownership.py",
    "git add -u src/ tests/",
    # A pathspec makes `-u` scoped whichever side of it the flag sits on.
    "git add src/nfl_dfs/ownership.py -u",
    "git add -v -u src/nfl_dfs/ownership.py",
    "git stash list",
    "git stash show",
    "git stash show -p stash@{0}",
    "git stash list -n 5",
    # Writing a document or a test that mentions a refused command. The guard
    # caught this on itself the first time it ran, which is how it was found.
    "cat > docs/rule.md <<'EOF'\nNever run `git push --force`.\nEOF",
    "printf '%s\\n' 'git add -A is refused' >> notes.txt",
    'echo "git reset --hard is refused"',
)


@pytest.mark.parametrize("command", REFUSED_COMMANDS)
def test_bash_guard_refuses_destructive_git(command: str) -> None:
    guard = _load_bash_guard()
    assert guard.forbidden_reason(command) is not None, f"guard let through: {command}"


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_bash_guard_allows_ordinary_work(command: str) -> None:
    guard = _load_bash_guard()
    reason = guard.forbidden_reason(command)
    assert reason is None, f"guard wrongly refused {command!r}: {reason}"


def test_the_deny_list_does_not_reinstate_the_repaired_false_positives() -> None:
    """Two layers, one answer.

    `.claude/settings.json` denies by prefix and the guard denies by pattern.
    Repairing only the guard would leave `git add -u <path>` and
    `git stash list` refused by the prefix rule, so the settings file has to be
    narrowed with it. This is what keeps the two halves from drifting again.
    """
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]

    assert "Bash(git add -u:*)" not in deny, "the prefix rule would refuse `git add -u <path>` again"
    assert "Bash(git stash:*)" not in deny, "the prefix rule would refuse `git stash list` again"
    # The bare forms stay refused in both layers.
    assert "Bash(git add -u)" in deny
    assert "Bash(git stash)" in deny
    for verb in ("push", "save", "pop", "apply", "drop", "clear"):
        assert f"Bash(git stash {verb}:*)" in deny, f"`git stash {verb}` must stay denied by prefix"


def test_the_bash_guard_never_reaches_the_network_on_an_ordinary_command() -> None:
    """`forbidden_reason` is called on every Bash call and must stay pure.

    The freshness gate can fetch, so it lives behind a separate entry point that
    a non-push command never reaches. If the two were ever merged, this file's
    own parametrized tests would start making network calls.
    """
    guard = _load_bash_guard()
    source = (PROJECT_ROOT / ".claude" / "hooks" / "guard_bash.py").read_text(encoding="utf-8")
    body = source.split("def forbidden_reason")[1].split("\ndef ")[0]

    assert "subprocess" not in body and "push_freshness" not in body
    assert hasattr(guard, "stale_push_reason"), "the fetching half must be its own function"
    # A non-push command must not even import the gate.
    sys.modules.pop("push_freshness", None)
    assert guard.stale_push_reason("ls -la") is None
    assert "push_freshness" not in sys.modules


# --------------------------------------------------------------------------
# Launcher hygiene. Several instances work this repository at once.
# --------------------------------------------------------------------------


def test_launchers_give_each_run_its_own_pytest_basetemp() -> None:
    """Two concurrent suites must not share `--basetemp`.

    pytest deletes basetemp at the start of every run, so a fixed path means the
    second run wipes the first mid-flight. Measured on 2026-09-17: two
    concurrent runs produced three phantom failures in
    `test_classic_review_c3[20]`, `[150]` and `test_cowork_rerun_regressions`,
    none of which were real. A grep, not a behavioural test: actually racing two
    suites would cost five minutes and be flaky by construction.
    """
    posix = (PROJECT_ROOT / "nfl.sh").read_text(encoding="utf-8")
    powershell = (PROJECT_ROOT / "nfl.ps1").read_text(encoding="utf-8")

    assert "nfl-dfs-pytest/$$" in posix, (
        "nfl.sh lost the per-process component of --basetemp; concurrent suites "
        "will delete each other's temp directories"
    )
    assert "nfl-dfs-pytest\\$PID" in powershell, (
        "nfl.ps1 lost the per-process component of --basetemp"
    )
    # The cache is deliberately shared, so `--lf` and `--ff` still work.
    assert "nfl-dfs-pytest-cache" in posix
    assert "nfl-dfs-pytest-cache" in powershell
