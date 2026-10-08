"""`scripts/post_merge.py` reads a checkout and says what a merge left behind.

The script is read-only on purpose. A script that ran `git push --delete` or
`git branch -d` would sit behind `Bash(python3 scripts/:*)`, a blanket allow, so
neither `.claude/settings.json` nor `.claude/hooks/guard_bash.py` would ever see
the command. It therefore classifies and prints; the mutating commands are
typed as their own Bash calls (or run by `sync.ps1`, Ben's own script), where
the deny list, the guard and the permission classifier can see them.

These tests run real git against a bare `origin` and a clone under `tmp_path`,
with git's own configuration isolated, so they behave the same on the Windows
CI job as on Linux. Fixtures are written with `write_bytes` for the same reason
(Session 66 lost two CI cycles to `write_text` and a platform path).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXED_DATE = "2026-10-01T12:00:00+0000"
NOW = "2026-10-08T12:00:00Z"

# Deliberately a second copy, not imported from the script: a mutant that widens
# the script's own allowlist must still fail the recorded-calls test below.
READ_ONLY_SUBCOMMANDS = {
    "fetch",
    "rev-parse",
    "rev-list",
    "for-each-ref",
    "merge-base",
    "log",
    "status",
    "stash",
    "worktree",
    "show",
    "diff",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


post_merge = _load("post_merge_under_test", PROJECT_ROOT / "scripts" / "post_merge.py")
guard_bash = _load("guard_bash_for_post_merge", PROJECT_ROOT / ".claude" / "hooks" / "guard_bash.py")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}"
    return result.stdout.strip()


class World:
    def __init__(self, root: Path, origin: Path, work: Path) -> None:
        self.root, self.origin, self.work = root, origin, work

    def commit(self, name: str, text: str, message: str, cwd: Path | None = None) -> str:
        cwd = cwd or self.work
        (cwd / name).write_bytes(text.encode("utf-8"))
        git(cwd, "add", "--", name)
        git(cwd, "commit", "-m", message)
        return git(cwd, "rev-parse", "HEAD")

    def branch(self, name: str, *, message: str = "branch work", push: bool = True) -> str:
        """A branch with one commit of its own, back on `main` afterwards."""
        git(self.work, "switch", "main")
        git(self.work, "switch", "-c", name)
        sha = self.commit(name.replace("/", "_") + ".txt", name, message)
        if push:
            git(self.work, "push", "-u", "origin", name)
        git(self.work, "switch", "main")
        return sha

    def merge(self, name: str) -> str:
        """Merge a branch into main with a merge commit and push main."""
        git(self.work, "switch", "main")
        git(self.work, "merge", "--no-ff", name, "-m", f"Merge {name}")
        git(self.work, "push", "origin", "main")
        return git(self.work, "rev-parse", "HEAD")

    def check(self, capsys, *flags: str, fmt: str = "json", fetch: bool = False):
        argv = ["--repo", str(self.work), "--now", NOW, "--format", fmt, *flags]
        if not fetch:
            argv.append("--no-fetch")
        code = post_merge.main(argv)
        out = capsys.readouterr().out
        return code, (json.loads(out) if fmt == "json" else out)


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    config = tmp_path / "gitconfig"
    config.write_bytes(
        b"[core]\n\tautocrlf = false\n"
        b"[init]\n\tdefaultBranch = main\n"
        b"[user]\n\tname = Test\n\temail = test@example.invalid\n"
        b'[protocol "file"]\n\tallow = always\n'
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_DATE", FIXED_DATE)
    monkeypatch.setenv("GIT_COMMITTER_DATE", FIXED_DATE)
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", origin.as_uri(), str(work))
    built = World(tmp_path, origin, work)
    built.commit("README.md", "one\n", "first")
    git(work, "push", "-u", "origin", "main")
    return built


def _by_name(report: dict, name: str, scope: str) -> dict:
    (row,) = [b for b in report["branches"] if b["name"] == name and b["scope"] == scope]
    return row


def _codes(items: list[dict]) -> set[str]:
    return {item["code"] for item in items}


# --- a quiet repository ---------------------------------------------------


def test_a_clean_checkout_with_nothing_owed_is_in_sync(world, capsys):
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 0
    assert report["verdict"] == "IN_SYNC"
    assert report["blockers"] == [] and report["claude_commands"] == [] and report["for_ben"] == []
    assert report["schema_version"] == "nfl_post_merge_check_v1"


# --- classification -------------------------------------------------------


def test_an_unmerged_claude_branch_is_reported_and_never_gets_a_command(world, capsys):
    world.branch("claude/claim-only", message="Claim Session 66")
    code, report = world.check(capsys, "--no-open-prs")
    row = _by_name(report, "claude/claim-only", "remote")
    assert row["state"] == "UNMERGED" and row["ahead"] == 1
    assert row["subject"] == "Claim Session 66" and row["age_days"] == 7
    assert "UNMERGED_BRANCH" in _codes(report["for_ben"])
    assert report["claude_commands"] == []
    assert code == 0, "an unmerged branch is Ben's to decide, not a blocker"


def test_a_merged_remote_head_without_pr_evidence_is_not_deleted(world, capsys):
    """Ancestry alone cannot tell a merged PR's head from a sibling's fresh branch."""
    world.branch("claude/finished")
    world.merge("claude/finished")
    code, report = world.check(capsys, "--no-open-prs")
    assert _by_name(report, "claude/finished", "remote")["state"] == "MERGED"
    assert report["claude_commands"] == []
    assert "MERGED_NO_PR_EVIDENCE" in _codes(report["for_ben"])
    assert code == 0


def test_a_fresh_sibling_branch_at_the_tip_of_main_is_never_deletable(world, capsys):
    git(world.work, "push", "origin", "main:refs/heads/claude/sibling-just-started")
    git(world.work, "fetch", "origin")
    code, report = world.check(capsys, "--no-open-prs")
    assert _by_name(report, "claude/sibling-just-started", "remote")["state"] == "MERGED"
    assert report["claude_commands"] == []


def test_a_merged_head_with_matching_pr_evidence_gets_one_delete_command(world, capsys):
    sha = world.branch("claude/finished")
    world.merge("claude/finished")
    code, report = world.check(capsys, "--no-open-prs", "--merged-pr-head", f"claude/finished={sha}")
    assert report["claude_commands"] == ["git push origin --delete claude/finished"]
    assert code == 1 and report["verdict"] == "ACTIONS_PENDING"


def test_a_pr_evidence_sha_that_does_not_match_the_tip_is_refused(world, capsys):
    world.branch("claude/finished")
    world.merge("claude/finished")
    code, report = world.check(capsys, "--no-open-prs", "--merged-pr-head", "claude/finished=" + "0" * 40)
    assert report["claude_commands"] == []
    assert "PR_EVIDENCE_MISMATCH" in _codes(report["for_ben"])


def test_without_the_open_pr_list_no_delete_is_emitted_and_the_run_is_blocked(world, capsys):
    sha = world.branch("claude/finished")
    world.merge("claude/finished")
    code, report = world.check(capsys, "--merged-pr-head", f"claude/finished={sha}")
    assert report["claude_commands"] == []
    assert "OPEN_PRS_UNKNOWN" in _codes(report["blockers"])
    assert code == 2


def test_an_open_pr_head_is_never_deleted_even_with_merged_looking_evidence(world, capsys):
    sha = world.branch("claude/reused-name")
    world.merge("claude/reused-name")
    code, report = world.check(
        capsys, "--open-pr-head", "claude/reused-name", "--merged-pr-head", f"claude/reused-name={sha}"
    )
    assert _by_name(report, "claude/reused-name", "remote")["state"] == "OPEN_PR"
    assert report["claude_commands"] == []


def test_the_current_branch_is_never_touched(world, capsys):
    sha = world.branch("claude/mine")
    world.merge("claude/mine")
    git(world.work, "switch", "claude/mine")
    code, report = world.check(capsys, "--no-open-prs", "--merged-pr-head", f"claude/mine={sha}")
    assert _by_name(report, "claude/mine", "remote")["state"] == "CURRENT"
    assert _by_name(report, "claude/mine", "local")["state"] == "CURRENT"
    assert report["claude_commands"] == []
    assert report["current_branch"] == "claude/mine"


def test_branches_that_are_not_claude_branches_are_not_mine(world, capsys):
    sha = world.branch("codex/other-tool")
    world.merge("codex/other-tool")
    world.branch("codex/unmerged")
    code, report = world.check(capsys, "--no-open-prs", "--merged-pr-head", f"codex/other-tool={sha}")
    assert _by_name(report, "codex/other-tool", "remote")["state"] == "NOT_MINE"
    assert _by_name(report, "codex/unmerged", "remote")["state"] == "NOT_MINE"
    assert report["claude_commands"] == []
    assert "UNMERGED_BRANCH" not in _codes(report["for_ben"])


def test_main_itself_is_never_a_branch_row(world, capsys):
    code, report = world.check(capsys, "--no-open-prs")
    assert all(row["name"] != "main" for row in report["branches"])


# --- blocked states --------------------------------------------------------


def test_a_dirty_tree_blocks(world, capsys):
    (world.work / "scratch.txt").write_bytes(b"not committed\n")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "DIRTY_TREE" in _codes(report["blockers"])
    assert report["dirty_paths"] == 1


def test_unpushed_commits_block_and_pushing_clears_them(world, capsys):
    git(world.work, "switch", "-c", "claude/work")
    world.commit("new.txt", "new\n", "only here")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "UNPUSHED_COMMITS" in _codes(report["blockers"])
    assert report["unpushed_commits"] == 1
    git(world.work, "push", "-u", "origin", "claude/work")
    code, report = world.check(capsys, "--no-open-prs")
    assert "UNPUSHED_COMMITS" not in _codes(report["blockers"])


def test_a_merged_and_deleted_session_branch_is_not_unpushed(world, capsys):
    """The cloud's normal end state: the branch merged and GitHub deleted its head."""
    world.branch("claude/session")
    git(world.work, "switch", "claude/session")
    world.merge("claude/session")
    git(world.work, "switch", "claude/session")
    git(world.work, "push", "origin", "--delete", "claude/session")
    git(world.work, "fetch", "--prune", "origin")
    code, report = world.check(capsys, "--no-open-prs")
    assert report["unpushed_commits"] == 0
    assert code == 0, report["blockers"]


def test_a_fetch_that_fails_blocks_by_name(world, capsys):
    git(world.work, "remote", "set-url", "origin", (world.root / "missing.git").as_uri())
    code, report = world.check(capsys, "--no-open-prs", fetch=True)
    assert code == 2 and "FETCH_FAILED" in _codes(report["blockers"])
    assert report["fetch"]["ok"] is False


def test_a_directory_that_is_not_a_repository_is_a_named_blocker(tmp_path, capsys):
    code = post_merge.main(["--repo", str(tmp_path), "--no-fetch", "--format", "json", "--now", NOW])
    report = json.loads(capsys.readouterr().out)
    assert code == 2 and "NOT_A_REPO" in _codes(report["blockers"])


# --- things only Ben can see or decide -------------------------------------


def test_a_stash_and_an_extra_worktree_are_listed_and_never_touched(world, capsys):
    (world.work / "README.md").write_bytes(b"changed\n")
    git(world.work, "stash", "push", "-m", "ben's work")
    extra = world.root / "extra"
    git(world.work, "worktree", "add", "-b", "codex/extra", str(extra))
    code, report = world.check(capsys, "--no-open-prs")
    assert {"STASH", "WORKTREE"} <= _codes(report["for_ben"])
    assert git(world.work, "stash", "list") != ""
    assert extra.is_dir()
    assert report["claude_commands"] == []


def test_a_shallow_clone_never_says_unmerged(world, tmp_path, capsys):
    world.branch("claude/old")
    for index in range(3):
        world.commit("more.txt", str(index), f"more {index}")
        git(world.work, "push", "origin", "main")
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "--depth", "1", "--no-single-branch", world.origin.as_uri(), str(shallow))
    code = post_merge.main(["--repo", str(shallow), "--no-fetch", "--no-open-prs", "--format", "json", "--now", NOW])
    report = json.loads(capsys.readouterr().out)
    assert report["shallow"] is True
    assert report["claude_commands"][0] == "git fetch --unshallow origin"
    assert code == 1 and report["verdict"] == "ACTIONS_PENDING"
    states = {row["state"] for row in report["branches"] if row["name"] == "claude/old"}
    assert states == {"UNKNOWN_SHALLOW"}, states
    git(shallow, "fetch", "--unshallow", "origin")
    code = post_merge.main(["--repo", str(shallow), "--no-fetch", "--no-open-prs", "--format", "json", "--now", NOW])
    report = json.loads(capsys.readouterr().out)
    assert report["shallow"] is False and "git fetch --unshallow origin" not in report["claude_commands"]
    assert _by_name(report, "claude/old", "remote")["state"] == "UNMERGED"


def test_a_fetch_sees_a_branch_merged_a_second_ago(world, tmp_path, capsys):
    """The 300 s fetch cache in repo_state.py must not be what check uses."""
    sibling = tmp_path / "sibling"
    git(tmp_path, "clone", world.origin.as_uri(), str(sibling))
    git(sibling, "switch", "-c", "claude/quick")
    world.commit("quick.txt", "q", "quick", cwd=sibling)
    git(sibling, "switch", "main")
    git(sibling, "merge", "--no-ff", "claude/quick", "-m", "Merge claude/quick")
    git(sibling, "push", "origin", "main")
    before = git(world.work, "rev-parse", "origin/main")
    code, report = world.check(capsys, "--no-open-prs", fetch=True)
    assert report["fetch"]["ok"] is True
    assert git(world.work, "rev-parse", "origin/main") != before
    assert report["origin_main"] == git(sibling, "rev-parse", "HEAD")


# --- the script never writes ------------------------------------------------


def test_every_git_call_is_read_only(world, capsys, monkeypatch):
    world.branch("claude/a")
    sha = world.branch("claude/b")
    world.merge("claude/b")
    world.branch("codex/c")
    git(world.work, "switch", "-c", "claude/mine")
    calls: list[list[str]] = []
    real = subprocess.run

    def recording(command, *args, **kwargs):
        if command and command[0] == "git":
            calls.append([str(part) for part in command[1:]])
        return real(command, *args, **kwargs)

    monkeypatch.setattr(post_merge.subprocess, "run", recording)
    for fmt in ("json", "text", "commands", "powershell", "local-merged-names"):
        world.check(capsys, "--no-open-prs", "--merged-pr-head", f"claude/b={sha}", fmt=fmt, fetch=True)
    assert calls, "the recording wrapper saw nothing"
    for call in calls:
        verb = call[0] if call[0] != "-C" else call[2]
        assert verb in READ_ONLY_SUBCOMMANDS, call
        if verb == "stash":
            assert "list" in call and "push" not in call and "pop" not in call
        if verb == "worktree":
            assert "list" in call and "add" not in call and "remove" not in call
        if verb == "fetch":
            assert call[-3:] == ["fetch", "--prune", "origin"] or call[-2:] == ["--prune", "origin"], call


@pytest.mark.parametrize(
    "args",
    [
        ("branch", "-d", "x"),
        ("branch", "-D", "x"),
        ("push", "origin", "--delete", "x"),
        ("switch", "main"),
        ("checkout", "main"),
        ("merge", "origin/main"),
        ("reset", "--hard"),
        ("stash", "push"),
        ("fetch", "origin", "main:main"),
        ("worktree", "remove", "x"),
    ],
)
def test_the_script_refuses_to_run_a_mutating_git_command(world, args):
    with pytest.raises(post_merge.ForbiddenGit):
        post_merge.git(world.work, *args)


# --- output for people and for the shell -----------------------------------

_CHECKOUT = r"C:\\Users\\benja\\Documents\\Claude\\nfl-dfs"
_POWERSHELL_COMMANDS = (
    re.compile(r"^Sync-NflDfs$"),
    re.compile(r"^Sync-NflDfs -Clean$"),
    re.compile(r"^& '" + _CHECKOUT + r"\\sync\.ps1' -Clean$"),
    # git -C, so the block works from whatever folder Ben's PowerShell opened in.
    re.compile(r"^git -C '" + _CHECKOUT + r"' log origin/main\.\.origin/claude/[A-Za-z0-9._/-]+ --oneline$"),
    re.compile(r"^git -C '" + _CHECKOUT + r"' log main\.\.claude/[A-Za-z0-9._/-]+ --oneline$"),
    re.compile(r"^git -C '" + _CHECKOUT + r"' push origin --delete claude/[A-Za-z0-9._/-]+$"),
)


def test_powershell_output_is_copy_paste_blocks_of_whitelisted_commands(world, capsys):
    world.branch("claude/claim-only", message="Claim Session 66")
    world.branch("claude/local-only", push=False)
    code, text = world.check(capsys, "--no-open-prs", fmt="powershell")
    blocks = re.findall(r"```powershell\n(.*?)\n```", text, re.DOTALL)
    assert len(blocks) >= 5
    for block in blocks:
        assert "\n" not in block, "one command per block"
        assert any(pattern.match(block) for pattern in _POWERSHELL_COMMANDS), block
    assert blocks[0] == "Sync-NflDfs -Clean"
    joined = "\n".join(blocks)
    for banned in ("-D ", "Remove-Item", "add -A", "reset", "stash", "--force", "clean -"):
        assert banned not in joined
    text.encode("ascii")


def test_a_branch_name_with_shell_characters_never_reaches_a_command(world, capsys):
    """Merged on both sides, so each of the three outputs that carry names is really exercised."""
    sha = world.branch("claude/odd;name")
    world.merge("claude/odd;name")
    world.branch("claude/unmerged$(x)", push=False)
    code, text = world.check(capsys, "--no-open-prs", fmt="powershell")
    blocks = "".join(re.findall(r"```powershell\n(.*?)\n```", text, re.DOTALL))
    assert "odd;name" not in blocks and "$(x)" not in blocks
    assert "UNSAFE_BRANCH_NAME" in text
    code, names = world.check(capsys, "--no-open-prs", fmt="local-merged-names")
    assert "odd;name" not in names and "$(x)" not in names
    code, report = world.check(capsys, "--no-open-prs", "--merged-pr-head", f"claude/odd;name={sha}")
    assert report["claude_commands"] == []
    assert "UNSAFE_BRANCH_NAME" in _codes(report["for_ben"])
    assert _by_name(report, "claude/odd;name", "remote")["state"] == "MERGED"


def test_commands_output_passes_the_bash_guard(world, capsys):
    sha = world.branch("claude/finished")
    world.merge("claude/finished")
    code, text = world.check(
        capsys, "--no-open-prs", "--merged-pr-head", f"claude/finished={sha}", fmt="commands"
    )
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert lines == ["git push origin --delete claude/finished"]
    for line in lines:
        assert guard_bash.forbidden_reason(line) is None


def test_commands_output_with_nothing_to_do_is_a_comment(world, capsys):
    code, text = world.check(capsys, "--no-open-prs", fmt="commands")
    assert text.strip().startswith("#")


def test_local_merged_names_lists_only_merged_claude_branches_that_are_not_current(world, capsys):
    world.branch("claude/done-local", push=False)
    world.merge("claude/done-local")
    world.branch("claude/not-merged-local", push=False)
    world.branch("codex/merged-but-not-mine", push=False)
    world.merge("codex/merged-but-not-mine")
    code, text = world.check(capsys, "--no-open-prs", fmt="local-merged-names")
    assert text.split() == ["claude/done-local"]


def test_text_output_is_ascii_even_when_a_commit_subject_is_not(world, capsys):
    world.branch("claude/accent", message="Caf\u00e9 \u2014 the plan")
    code, text = world.check(capsys, "--no-open-prs", fmt="text")
    text.encode("ascii")
    assert "claude/accent" in text


def test_the_report_is_deterministic(world, capsys):
    world.branch("claude/claim-only")
    first = world.check(capsys, "--no-open-prs")
    second = world.check(capsys, "--no-open-prs")
    assert first == second
    assert json.dumps(first[1], sort_keys=True) == json.dumps(second[1], sort_keys=True)


# --- what the first review found: states that read IN_SYNC and were not ---------


def test_a_local_only_claude_branch_with_commits_blocks_even_when_head_is_on_main(world, capsys):
    """Archiving would lose its commits: they exist only in this container."""
    world.branch("claude/side", push=False)
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "LOCAL_ONLY_COMMITS" in _codes(report["blockers"])
    assert any(b.get("branch") == "claude/side" for b in report["blockers"])


def test_a_local_claude_branch_ahead_of_its_remote_blocks(world, capsys):
    world.branch("claude/x")
    git(world.work, "switch", "claude/x")
    world.commit("more.txt", "more", "only here")
    git(world.work, "switch", "main")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "LOCAL_ONLY_COMMITS" in _codes(report["blockers"])


def test_a_follow_up_pushed_after_the_merge_is_not_in_sync(world, capsys):
    """The session branch merged, then more work landed on a re-created head: pushed, never merged."""
    world.branch("claude/e")
    world.merge("claude/e")
    git(world.work, "switch", "claude/e")
    world.commit("followup.txt", "follow-up", "after the merge")
    git(world.work, "push", "origin", "claude/e")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "HEAD_NOT_IN_ORIGIN_MAIN" in _codes(report["blockers"])
    assert "UNPUSHED_COMMITS" not in _codes(report["blockers"])


def test_local_only_commits_on_a_branch_that_is_not_mine_are_ben_s_to_see_not_a_blocker(world, capsys):
    world.branch("codex/mine-not", push=False)
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 0
    assert any(i["code"] == "LOCAL_ONLY_COMMITS" and i["branch"] == "codex/mine-not" for i in report["for_ben"])


def test_local_main_with_commits_the_remote_lacks_blocks(world, capsys):
    world.commit("local_only.txt", "x", "committed on main, never pushed")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 2 and "MAIN_HAS_LOCAL_COMMITS" in _codes(report["blockers"])


def test_local_main_that_is_only_behind_is_not_a_blocker(world, tmp_path, capsys):
    sibling = tmp_path / "sibling"
    git(tmp_path, "clone", world.origin.as_uri(), str(sibling))
    world.commit("ahead.txt", "x", "pushed by a sibling", cwd=sibling)
    git(sibling, "push", "origin", "main")
    code, report = world.check(capsys, "--no-open-prs", fetch=True)
    assert code == 0 and report["blockers"] == []


def test_a_stash_alone_leaves_the_default_exit_at_zero_and_strict_exit_at_one(world, capsys):
    (world.work / "README.md").write_bytes(b"changed\n")
    git(world.work, "stash", "push", "-m", "ben's work")
    code, report = world.check(capsys, "--no-open-prs")
    assert code == 0 and report["verdict"] == "IN_SYNC"
    code, report = world.check(capsys, "--no-open-prs", "--strict")
    assert code == 1 and report["verdict"] == "ITEMS_FOR_BEN"


def test_strict_does_not_soften_a_block(world, capsys):
    (world.work / "scratch.txt").write_bytes(b"x\n")
    code, report = world.check(capsys, "--no-open-prs", "--strict")
    assert code == 2 and report["verdict"] == "BLOCKED"


def test_a_git_error_in_the_ancestry_test_is_unknown_never_merged(world, capsys, monkeypatch):
    world.branch("claude/a")
    real = post_merge.run

    def fake(repo, *args):
        if args[0] == "merge-base":
            return subprocess.CompletedProcess(args, 128, "", "fatal: not a valid object name")
        return real(repo, *args)

    monkeypatch.setattr(post_merge, "run", fake)
    code, report = world.check(capsys, "--no-open-prs")
    assert _by_name(report, "claude/a", "remote")["state"] == "UNKNOWN"
    assert report["claude_commands"] == []


@pytest.mark.parametrize(
    "args",
    [
        ("rev-list", "--output=x", "HEAD"),
        ("diff", "--output=x", "--name-only"),
        ("diff", "--ext-diff", "--name-only", "a", "b"),
        ("log", "--output=x"),
        ("show", "HEAD"),
        ("rev-parse", "-c", "core.pager=x", "HEAD"),
    ],
)
def test_the_allowlist_refuses_options_that_write_and_verbs_the_script_does_not_use(world, args):
    with pytest.raises(post_merge.ForbiddenGit):
        post_merge.git(world.work, *args)


def test_git_runs_with_prompts_and_index_refresh_switched_off(world, monkeypatch):
    seen = {}
    real = subprocess.run

    def spy(command, *args, **kwargs):
        seen.update(kwargs.get("env") or {})
        return real(command, *args, **kwargs)

    monkeypatch.setattr(post_merge.subprocess, "run", spy)
    post_merge.git(world.work, "status", "--porcelain")
    assert seen.get("GIT_TERMINAL_PROMPT") == "0" and seen.get("GIT_OPTIONAL_LOCKS") == "0"


# --- PowerShell for a checkout whose sync.ps1 is about to change ------------------


def test_the_first_powershell_block_is_plain_sync_when_the_last_merge_changed_sync_ps1(world, capsys):
    """An old sync.ps1 has no -Clean parameter: the first run has to pull the new one."""
    git(world.work, "switch", "-c", "claude/sync-change")
    world.commit("sync.ps1", "# new\n", "change sync.ps1")
    git(world.work, "push", "-u", "origin", "claude/sync-change")
    world.merge("claude/sync-change")
    code, text = world.check(capsys, "--no-open-prs", fmt="powershell")
    blocks = re.findall(r"```powershell\n(.*?)\n```", text, re.DOTALL)
    assert blocks[:2] == ["Sync-NflDfs", "Sync-NflDfs -Clean"]
    assert "switch to main yourself" in text


def test_the_first_powershell_block_is_the_clean_sync_when_sync_ps1_did_not_change(world, capsys):
    world.branch("claude/other")
    world.merge("claude/other")
    code, text = world.check(capsys, "--no-open-prs", fmt="powershell")
    assert re.findall(r"```powershell\n(.*?)\n```", text, re.DOTALL)[0] == "Sync-NflDfs -Clean"


def test_a_delete_command_for_ben_needs_the_open_pr_list_to_have_been_read(world, capsys):
    """Without it a live branch with an open pull request looks unmerged."""
    world.branch("claude/looks-abandoned", message="work in progress")
    code, text = world.check(capsys, fmt="powershell")
    assert "push origin --delete" not in text
    assert "log origin/main..origin/claude/looks-abandoned" in text
    code, text = world.check(capsys, "--no-open-prs", fmt="powershell")
    assert "push origin --delete claude/looks-abandoned" in text
