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
import os
import re
import subprocess
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
    """The list was narrowed from twelve entries to three on 2026-09-20.

    This test changed with it, and the changed assertions are named rather than
    deleted. It used to require `src/nfl_dfs/release.py`,
    `config/evidence_policy.json` and `.claude/rules/ledger.md` to be flagged.
    Ben's instruction that day was to stop requiring his label, because a
    non-engineer reviewing a diff to an evidence module produces a signature
    rather than a check. Those three assertions are inverted, not removed, so
    the narrowing is pinned in both directions and cannot drift back silently.

    What stayed is not code review. It is that Claude must not be able to
    quietly change what Claude is not allowed to do.
    """

    module = _load_protected_paths_module()
    globs = module.load_protected_globs()

    flagged = module.protected_matches(
        [
            "CLAUDE.md",
            ".github/protected-paths.txt",
            ".claude/settings.json",
            "src/nfl_dfs/release.py",
            "src/nfl_dfs/evidence.py",
            "config/evidence_policy.json",
            ".claude/rules/ledger.md",
            ".claude/rules/git-authority.md",
            ".github/workflows/ci.yml",
            "tests/test_repo_boundaries.py",
            "src/nfl_dfs/ownership.py",
        ],
        globs,
    )
    # Claude may not quietly rewrite its own boundaries, shorten this list, or
    # lift its own deny rules.
    assert "CLAUDE.md" in flagged
    assert ".github/protected-paths.txt" in flagged
    assert ".claude/settings.json" in flagged

    # Everything else is Claude's call on green CI. A label there was theatre:
    # the person signing it could not evaluate the diff.
    assert "src/nfl_dfs/release.py" not in flagged
    assert "src/nfl_dfs/evidence.py" not in flagged
    assert "config/evidence_policy.json" not in flagged
    assert ".claude/rules/ledger.md" not in flagged
    assert ".claude/rules/git-authority.md" not in flagged
    assert ".github/workflows/ci.yml" not in flagged

    # Ordinary work must stay mergeable without Ben, or the gate is just the old
    # bottleneck wearing a label.
    assert "tests/test_repo_boundaries.py" not in flagged
    assert "src/nfl_dfs/ownership.py" not in flagged


def test_the_protected_list_stays_short_enough_to_actually_read() -> None:
    """The narrowing only holds if the list does not grow back by accretion.

    Three entries, each answering one question: may Claude change what Claude is
    allowed to do. A fourth is not forbidden, but it is a decision, and pinning
    the exact set forces it to be justified in the same commit instead of added
    quietly.
    """

    module = _load_protected_paths_module()
    globs = module.load_protected_globs()
    assert set(globs) == {
        "CLAUDE.md",
        ".github/protected-paths.txt",
        ".claude/settings.json",
    }, (
        "The protected list changed. That is allowed, but say why in "
        "changelog.md and update this test in the same commit."
    )


# H3 (2026-09-23): the label is read from the live pull request, not the event
# payload. GitHub freezes the payload when the event fires, so a label added
# after CI ran could never clear the check that demanded it (PR #32). With
# `--live-labels` the script asks the API at job runtime and fails closed on any
# lookup problem; without the flag it is the offline tool it always was.

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"


def _live_env(monkeypatch, **overrides) -> None:
    env = {
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_REPOSITORY": "bleeski/nfl-dfs",
        "PR_NUMBER": "42",
        "GITHUB_TOKEN": "token-for-tests",
    }
    env.update(overrides)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("PR_LABELS", raising=False)


def _pull(*labels: str, number: int = 42) -> dict:
    return {"number": number, "labels": [{"name": label} for label in labels]}


class _Fail(str):
    """A queued response that makes the fake API raise ``LabelLookupError``."""


def _checker(monkeypatch, changed, *, responses=()):
    """The script with git and the API replaced. Each response is returned in
    turn; a ``_Fail`` is raised as the loaded module's own ``LabelLookupError``."""

    module = _load_protected_paths_module()
    monkeypatch.setattr(module, "changed_paths", lambda base, head: tuple(changed))
    monkeypatch.setattr(module, "RETRY_DELAY_SECONDS", 0)
    queue = list(responses)
    calls: list[str] = []

    def fake_fetch(url: str, token: str):
        calls.append(url)
        item = queue.pop(0) if queue else _Fail("no response queued")
        if isinstance(item, _Fail):
            raise module.LabelLookupError(str(item))
        return item

    monkeypatch.setattr(module, "_fetch_json", fake_fetch)
    return module, calls


LIVE = ["--live-labels", "--base", "base-sha", "--head", "head-sha"]


@pytest.mark.parametrize("changed", [["CLAUDE.md"], ["src/nfl_dfs/ownership.py"]])
def test_a_failed_live_label_lookup_fails_the_check(monkeypatch, capsys, changed) -> None:
    """Fail closed, whether or not a protected path is touched. A gate that
    passes when it cannot look is worse than the defect H3 replaced."""

    _live_env(monkeypatch)
    module, calls = _checker(monkeypatch, changed, responses=[_Fail("HTTP 503"), _Fail("HTTP 503")])
    assert module.main(LIVE) == 2
    assert len(calls) == 2, "one retry, then fail"
    assert "PROTECTED_PATHS_CHECK_FAILED" in capsys.readouterr().err


def test_a_transient_lookup_failure_is_retried_once(monkeypatch) -> None:
    _live_env(monkeypatch)
    module, calls = _checker(
        monkeypatch,
        ["CLAUDE.md"],
        responses=[_Fail("connection reset"), _pull("ben-review")],
    )
    assert module.main(LIVE) == 0
    assert len(calls) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"GITHUB_TOKEN": None},
        {"GITHUB_TOKEN": ""},
        {"GITHUB_REPOSITORY": None},
        {"GITHUB_REPOSITORY": "not-a-repo"},
        {"PR_NUMBER": None},
        {"PR_NUMBER": "0"},
        {"PR_NUMBER": "42abc"},
        {"GITHUB_API_URL": None},
    ],
)
def test_live_labels_need_every_input(monkeypatch, overrides) -> None:
    _live_env(monkeypatch, **overrides)
    module, calls = _checker(monkeypatch, ["CLAUDE.md"], responses=[_pull("ben-review")])
    assert module.main(LIVE) == 2
    assert calls == []


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.github.com",
        "https://example.com",
        "https://api.github.com.example.com",
        "https://user@api.github.com",
        "https://api.github.com:8443",
        "https://api.github.com/some/prefix",
    ],
)
def test_live_labels_refuse_any_host_but_the_allowlisted_api(monkeypatch, api_url) -> None:
    _live_env(monkeypatch, GITHUB_API_URL=api_url)
    module, calls = _checker(monkeypatch, ["CLAUDE.md"], responses=[_pull("ben-review")])
    assert module.main(LIVE) == 2
    assert calls == [], "the request must never be sent"


def test_the_api_host_is_read_from_the_sources_allowlist() -> None:
    module = _load_protected_paths_module()
    assert module.LIVE_LABEL_API_HOST in module.allowed_hosts()


@pytest.mark.parametrize(
    "response",
    [
        [],
        {"labels": [{"name": "ben-review"}]},
        {"number": 41, "labels": [{"name": "ben-review"}]},
        {"number": "42", "labels": [{"name": "ben-review"}]},
        {"number": True, "labels": [{"name": "ben-review"}]},
        {"number": 42},
        {"number": 42, "labels": "ben-review"},
        {"number": 42, "labels": ["ben-review"]},
        {"number": 42, "labels": [{"id": 1}]},
    ],
)
def test_a_malformed_pull_request_response_fails_the_check(monkeypatch, response) -> None:
    _live_env(monkeypatch)
    module, _ = _checker(monkeypatch, ["CLAUDE.md"], responses=[response])
    assert module.main(LIVE) == 2


def test_a_live_review_label_clears_a_protected_change(monkeypatch, capsys) -> None:
    _live_env(monkeypatch)
    module, calls = _checker(monkeypatch, ["CLAUDE.md"], responses=[_pull("ben-review")])
    assert module.main(LIVE) == 0
    assert calls == ["https://api.github.com/repos/bleeski/nfl-dfs/pulls/42"]
    out = capsys.readouterr().out
    assert "`ben-review` present" in out and "CLAUDE.md" in out
    # The run log carries what was read and when, which is the H3 evidence.
    assert re.search(r"Live labels on pull request #42 at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", out)
    assert '["ben-review"]' in out


def test_without_the_live_label_each_protected_file_is_named(monkeypatch, capsys) -> None:
    _live_env(monkeypatch)
    module, _ = _checker(
        monkeypatch,
        ["CLAUDE.md", ".claude/settings.json", "src/nfl_dfs/ownership.py"],
        responses=[_pull("documentation")],
    )
    assert module.main(LIVE) == 1
    err = capsys.readouterr().err
    assert "PROTECTED_PATHS_WITHOUT_REVIEW" in err
    assert "  CLAUDE.md" in err and "  .claude/settings.json" in err
    assert "ownership.py" not in err


def test_a_frozen_payload_label_cannot_clear_the_live_check(monkeypatch) -> None:
    """The exact PR #32 shape inverted: the payload says labelled, the pull
    request says not. The live answer wins."""

    _live_env(monkeypatch)
    monkeypatch.setenv("PR_LABELS", '["ben-review"]')
    module, _ = _checker(monkeypatch, ["CLAUDE.md"], responses=[_pull()])
    assert module.main(LIVE) == 1


@pytest.mark.parametrize("labels", [(), ("ben-review",)])
def test_an_unprotected_change_is_clear_with_or_without_the_label(monkeypatch, capsys, labels) -> None:
    _live_env(monkeypatch)
    module, _ = _checker(monkeypatch, ["src/nfl_dfs/ownership.py"], responses=[_pull(*labels)])
    assert module.main(LIVE) == 0
    assert "No protected path touched (1 changed)." in capsys.readouterr().out


def test_without_the_flag_the_script_never_calls_the_api(monkeypatch) -> None:
    _live_env(monkeypatch)
    module, calls = _checker(monkeypatch, ["CLAUDE.md"], responses=[_pull("ben-review")])
    assert module.main(["--base", "base-sha", "--head", "head-sha"]) == 1
    monkeypatch.setenv("PR_LABELS", '["ben-review"]')
    assert module.main(["--base", "base-sha", "--head", "head-sha"]) == 0
    assert calls == []


def test_the_local_run_still_works_offline() -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PR_LABELS", "BASE_SHA", "HEAD_SHA", "PR_NUMBER", "GITHUB_TOKEN"}
    }
    # Any attempt at the network would hit a closed port.
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        env[key] = "http://127.0.0.1:9"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_protected_paths.py"),
         "--base", "HEAD", "--head", "HEAD"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "No protected path touched (0 changed).\n"


def test_the_protected_paths_workflow_reruns_on_label_changes() -> None:
    text = (WORKFLOWS / "protected-paths.yml").read_text(encoding="utf-8")
    assert "types: [opened, synchronize, reopened, labeled, unlabeled]" in text
    assert "python3 scripts/check_protected_paths.py --live-labels" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "pull-requests: read" in text
    assert "PR_LABELS" not in text


def test_no_workflow_reads_the_frozen_label_payload() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        assert "github.event.pull_request.labels" not in path.read_text(encoding="utf-8"), path.name


def test_exactly_one_workflow_defines_the_protected_paths_job() -> None:
    owners = [
        path.name
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.fullmatch(r"  protected-paths:\s*", line)
    ]
    assert owners == ["protected-paths.yml"]


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
