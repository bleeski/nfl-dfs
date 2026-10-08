"""`sync.ps1` is Ben's own script and the one nothing in a cloud container can run.

The `boundaries` CI job parses it with the PowerShell parser. These tests add
what a parse cannot see, as static rules over the text: no PowerShell 7 syntax
(Ben's shell is Windows PowerShell 5.1), no destructive command, and the only
branch deletion is `git branch -d`, which git refuses for an unmerged branch.
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "sync.ps1"


def _code() -> str:
    """The script without its leading help block and without comment lines."""
    text = SCRIPT.read_bytes().decode("utf-8")
    text = re.sub(r"<#.*?#>", "", text, count=1, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def test_the_script_is_ascii_with_lf_endings():
    data = SCRIPT.read_bytes()
    data.decode("ascii")
    assert b"\r" not in data


def test_clean_is_a_switch_parameter():
    code = _code()
    assert "[CmdletBinding()]" in code
    assert re.search(r"param\(\s*\[switch\]\$Clean\s*\)", code)


def test_no_powershell_seven_syntax():
    code = _code()
    for token in ("&&", "||", "?.", "??", "-Parallel", "ForEach-Object -Parallel"):
        assert token not in code, token
    assert not re.search(r"\s\?\s.+\s:\s", code), "a ternary"


def test_no_destructive_command_appears_in_the_code():
    code = _code()
    for banned in (
        "git reset",
        "git stash",
        "git clean",
        "git restore",
        "git rebase",
        "git push",
        "git add -A",
        "git add .",
        "git checkout --",
        "Remove-Item",
        "branch -D",
        "--force",
    ):
        assert banned not in code, banned


def test_the_only_git_commands_are_the_expected_ones():
    code = _code()
    verbs = set(re.findall(r"\bgit (\S+)", code))
    advice = {"status", "add", "commit", "checkout"}  # printed advice, inside Write-Host strings
    allowed = {"rev-parse", "status", "fetch", "merge-base", "switch", "log", "pull", "diff", "branch"} | advice
    assert verbs <= allowed, verbs - allowed
    run_lines = [
        line for line in code.splitlines() if re.search(r"\bgit (add|commit|checkout)\b", line) and "Write-Host" not in line
    ]
    assert run_lines == [], "add, commit and checkout appear only as advice Ben reads"


def test_the_only_branch_deletion_is_git_branch_d_on_names_from_post_merge():
    code = _code()
    deletions = [line.strip() for line in code.splitlines() if re.search(r"git branch -", line)]
    assert deletions == ["git branch -d $name"]
    assert "post_merge.py --no-fetch --no-open-prs --format local-merged-names" in code


def test_the_venv_interpreter_comes_first_and_the_store_stub_is_refused():
    code = _code()
    assert code.index(r".venv\Scripts\python.exe") < code.index("Get-Command python")
    assert "WindowsApps" in code


def test_the_advice_never_tells_ben_to_stage_everything():
    text = SCRIPT.read_bytes().decode("ascii")
    assert "git add -A" not in text and "git add ." not in text
    assert "git add <the files you want, by name>" in text
