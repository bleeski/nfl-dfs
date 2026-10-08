"""The post-merge routine is a procedure plus two scripts, and the text must agree.

The trigger is a line in a pull request body, spelled in four places. If they
drift, the routine silently never runs (or runs on a mid-session merge and
archives the session before its close-out pull request exists). These tests pin
the spelling and the places that must mention the routine.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_bytes().decode("utf-8")


def _post_merge():
    spec = importlib.util.spec_from_file_location("post_merge_for_procedure", PROJECT_ROOT / "scripts" / "post_merge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKER = _post_merge().SESSION_CLOSE_MARKER


def test_the_marker_is_spelled_the_same_where_it_is_written_and_where_it_is_read():
    assert MARKER.startswith("Session close:")
    assert MARKER in _read(".claude/skills/close-out/SKILL.md").replace("\n     ", " ")
    assert MARKER in _read("docs/claude/post_merge.md")


def test_the_prompt_template_and_working_md_name_the_marker_line():
    assert "`Session close:` line" in _read("docs/claude/next_session_prompt.md")
    assert "`Session close:` line" in _read("docs/claude/working.md")


def test_close_out_subscribes_and_runs_the_routine_after_the_merge():
    text = " ".join(_read(".claude/skills/close-out/SKILL.md").split())
    assert "subscribe_pr_activity" in text
    assert "docs/claude/post_merge.md" in text
    assert text.index("subscribe_pr_activity") < text.index("run the post-merge routine")


def test_the_post_merge_skill_exists_and_points_at_the_procedure():
    skill = _read(".claude/skills/post-merge/SKILL.md")
    assert re.search(r"^name: post-merge$", skill, re.MULTILINE)
    assert "docs/claude/post_merge.md" in skill


def test_working_md_carries_the_after_a_merge_rule_and_claude_md_still_imports_it():
    assert "## After a merge" in _read("docs/claude/working.md")
    assert "@docs/claude/working.md" in _read("CLAUDE.md")


def test_the_procedure_names_each_step_the_scripts_serve():
    text = _read("docs/claude/post_merge.md")
    for needle in (
        "scripts/post_merge.py",
        "scripts/next_prompt.py",
        "--format powershell",
        "--format commands",
        "archive_session",
        "get_session",
        "unarchive_session",
        "git fetch --unshallow origin",
        "Sync-NflDfs -Clean",
        "never runs a mutating git command",
    ):
        assert needle in text, needle
    assert "—" not in text


def test_the_prompt_generator_keeps_the_retired_prompt_files_retired():
    for relative in (".claude/rules/ledger.md", "docs/session-prompts/README.md"):
        assert "never stored" in " ".join(_read(relative).split()), relative


def test_the_allow_entries_the_procedure_asks_ben_for_are_all_in_one_block():
    text = _read("docs/claude/post_merge.md")
    entries = re.findall(r'"(mcp__claude-code-remote__[a-z_]+)"', text)
    assert sorted(entries) == sorted(
        f"mcp__claude-code-remote__{name}"
        for name in (
            "get_session",
            "archive_session",
            "send_later",
            "delete_trigger",
            "subscribe_pr_activity",
            "unsubscribe_pr_activity",
        )
    )
