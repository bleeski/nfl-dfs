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
    assert "\u2014" not in text


def test_the_prompt_generator_keeps_the_retired_prompt_files_retired():
    for relative in (".claude/rules/ledger.md", "docs/session-prompts/README.md"):
        assert "never stored" in " ".join(_read(relative).split()), relative


# Ben, 2026-10-08, second ruling: the next prompt, the sync check, the branch cleanup and the
# archive belong to a roadmap dev session only. A lineup run never starts the routine; a typed
# /post-merge still runs it anywhere, but only the marker (or Ben's words) archives.
LINEUP_RUN_RULE = "A lineup run never starts the post-merge routine"

FILES_THAT_NAME_THE_LINEUP_RUN_EXCLUSION = (
    "docs/claude/post_merge.md",
    "docs/claude/working.md",
    ".claude/skills/post-merge/SKILL.md",
    ".claude/rules/stops-and-reports.md",
    ".claude/rules/slate-operation.md",
    "docs/RUNBOOK.md",
    "docs/CLAUDE_CODE_SETUP.md",
)


def _flat(relative: str) -> str:
    return " ".join(_read(relative).split())


def test_every_place_a_lineup_run_reads_says_the_routine_is_not_its_own():
    for relative in FILES_THAT_NAME_THE_LINEUP_RUN_EXCLUSION:
        assert LINEUP_RUN_RULE in _flat(relative), relative


def test_the_procedure_scopes_itself_to_roadmap_dev_sessions_and_names_the_marker_as_the_test():
    text = _flat("docs/claude/post_merge.md")
    assert "Roadmap dev sessions only" in text
    assert "The mechanical test is the marker" in text
    assert "Never write the `Session close:` line outside `/close-out`" in text
    # a lineup run's own pull request is a mid-session merge, whatever it contains
    assert (
        "A pull request a lineup run opens or merges (slate inputs, records, a procedure fix) is a mid-session merge"
        in text
    )


def test_a_typed_post_merge_runs_anywhere_but_alone_does_not_archive():
    text = _flat("docs/claude/post_merge.md")
    assert "That runs the routine in any session" in text
    assert "typing `/post-merge` alone does not ask for it" in text
    # the old condition archived on any typed command
    assert "carries the `Session close:` marker, or Ben typed `/post-merge`" not in text
    assert (
        "this session's merged pull request carries the `Session close:` marker (the strict check above), "
        "or Ben asks for the archive in this session after the merge"
    ) in text
    # the standing quote at the top is the original request, not a standing ask to archive
    assert "narrows all of it to roadmap dev sessions" in text
    assert "and neither does the standing quote at the top of this file" in text
    assert "or asks for the archive, is not a write" in text


def test_the_marker_belongs_to_this_sessions_own_pull_request_not_the_newest_merged_one():
    text = _flat("docs/claude/post_merge.md")
    assert "and again for step 8's first condition whatever triggered the routine" in text
    assert "A typed `/post-merge` finds its pull request by that `head.ref`, never as the newest merged pull request" in text
    assert "None of the eight steps runs for it on its own" in text


def test_the_post_merge_skill_and_close_out_agree_on_who_each_one_is_for():
    skill = _flat(".claude/skills/post-merge/SKILL.md")
    assert "closes a roadmap dev session" in skill
    assert "typed command works in any session" in skill
    assert "Typing `/post-merge` alone does not ask for the archive" in skill
    assert "(found by `head.ref`, never the newest merged one)" in skill
    assert "or Ben asks for it in this session after the merge" in skill
    assert (
        "only when this session's merged pull request carries the marker or Ben asks for it"
        in _flat("docs/claude/working.md")
    )
    close_out = _flat(".claude/skills/close-out/SKILL.md")
    assert "`/close-out` ends a roadmap dev session only" in close_out
    assert "Never write the `Session close:` line in any other pull request" in close_out
    assert MARKER in close_out


def test_a_lineup_run_ends_at_its_report_and_stays_open():
    slate = _flat(".claude/rules/slate-operation.md")
    assert "A lineup run ends at the handoff" in slate
    assert "stays open for late swap" in slate
    ends = _flat(".claude/rules/stops-and-reports.md")
    assert "A lineup run ends at the three parts above" in ends


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
