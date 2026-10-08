"""`scripts/next_prompt.py` builds the next session's handoff from `origin/main`.

Ben asked (2026-10-08) that every merge be followed by a prompt for the next
chunk "in the same format" as the Session 23d handoff written by hand that day.
The script fills what is mechanical (session, card, acceptance, size,
housekeeping, the last suite line) and leaves `<<CLAUDE:slot: ...>>` markers for
the parts that take reading the card, so a prompt cannot ship half-written and
cannot skip the judgment. `--check` is the gate.

Fixtures are a tiny git repository with a ROADMAP the real parser accepts, and
they are written with `write_bytes` so the Windows CI job sees the same bytes.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = PROJECT_ROOT / "tests" / "fixtures" / "next_prompt" / "session_23d_handoff.md"
TEMPLATE = PROJECT_ROOT / "docs" / "claude" / "next_session_prompt.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


next_prompt = _load("next_prompt_under_test", PROJECT_ROOT / "scripts" / "next_prompt.py")

_MARKER = re.compile(r"<<CLAUDE:[a-z-]+:.*?>>")
_HEADING = re.compile(r"^## .*$", re.MULTILINE)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}"
    return result.stdout.strip()


def roadmap(status_02: str = "Pending", extra_ledger: str = "") -> str:
    return (
        "# NFL DFS master roadmap\n\n"
        "## 1. Next Session Quick-Start\n\n"
        "Paste this into a fresh Claude Code session:\n\n"
        "> Read `docs/ROADMAP.md` and execute Session 02 exactly as its card in §2.3 specifies.\n\n"
        "## 2. The queue\n\n"
        "### 2.2 Status board\n\n"
        "<!-- roadmap-table:start -->\n"
        "| Session ID | Type | Work Unit & Scope | Source Origin | Target Files | Classification | Depends on "
        "| Verification Command / Breakpoint | Status |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| Session 01 | Standalone | First | Chunk P1 | a.py | V | none | `pytest tests/test_a.py` | Complete |\n"
        f"| Session 02 | Standalone | Second | Chunk P1 | b.py | S | Session 01 | `pytest tests/test_b.py -x` | {status_02} |\n"
        "| Session 02b | Standalone | Second b | Chunk P1 | b2.py | S | Session 02 | `pytest tests/test_b2.py` | Pending |\n"
        "| Session 03 | Standalone | Third | none | c.py | P | Session 02 | `pytest tests/test_c.py` | Pending |\n"
        "| Session 04 | Standalone | Fourth | none | d.py | S | Session 03 | `pytest tests/test_d.py` | Pending |\n"
        "| Session 05 | Standalone | Fifth | none | e.py | S | Session 01 | `pytest tests/test_e.py` | Complete |\n"
        "| Session 06 | Standalone | Sixth | none | f.py | S | Session 01 | `pytest tests/test_f.py` | Pending |\n"
        "| Session 07 | Standalone | Seventh | none | g.py | S | Session 01 | `pytest tests/test_g.py` | Pending |\n"
        "<!-- roadmap-table:end -->\n\n"
        "<!-- operator-table:start -->\n"
        "| ID | Item | Unblocks | Status |\n"
        "|---|---|---|---|\n"
        "<!-- operator-table:end -->\n\n"
        "### 2.3 Cards\n\n"
        "#### Session 02: P1 part 2, the second thing\n\n"
        "- **Depends on.** Session 01.\n"
        "- **Scope.** Do the second thing, as `docs/chunks/P1-first.md` says.\n"
        "- **Size.** Two files, about 120 changed lines. One session.\n"
        "- **Breakpoint.** Stop after the parser if the diff passes 1,000 lines.\n"
        "- **Acceptance.** A bad row is refused by name; the fixture's entries\n"
        "  are labelled from supplied numbers only; suite green.\n\n"
        "#### Session 02b: P1 part 2b, the second thing again\n\n"
        "- **Depends on.** Session 02.\n"
        "- **Acceptance.** The b card's own acceptance; suite green.\n\n"
        "#### Session 03: P1 part 3, the third thing\n\n"
        "- **Depends on.** Session 02.\n"
        "- **Scope.** Do the third thing.\n"
        "- **Size.** One file.\n\n"
        "#### Sessions 04 to 05: the batch\n\n"
        "- **Depends on.** Session 03.\n"
        "- **Acceptance.** The batch's acceptance for both sessions.\n\n"
        "#### Session 06: the sixth thing\n\n"
        "- **Size and breakpoint.** One file; stop at the parser.\n"
        f"- **Acceptance.** A row with a dash {chr(0x2014)} and a section sign § is refused; suite green.\n\n"
        "## 4. Ledger\n\n"
        "| Date | Session ID | Status Change | Commit SHA | Operator Notes |\n"
        "|---|---|---|---|---|\n"
        "| 2026-10-06 | Session 00 | In Progress to Complete | recorded by the next session | An old row |\n"
        f"{extra_ledger}"
    )


CHANGELOG = (
    "# Changelog\n\n## Unreleased\n\n"
    "### 2026-10-07: Session 01 -- the first thing\n\nBody.\n\n"
    "### 2026-10-06: Session 00 -- the zeroth thing\n\nBody.\n"
)

NEW_ROW = "| 2026-10-07 | Session 01 | In Progress to Complete | recorded by the next session | The first |\n"


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    config = tmp_path / "gitconfig"
    config.write_bytes(
        b"[core]\n\tautocrlf = false\n[init]\n\tdefaultBranch = main\n"
        b"[user]\n\tname = Test\n\temail = test@example.invalid\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init")
    (work / "docs" / "chunks").mkdir(parents=True)
    (work / "docs" / "ROADMAP.md").write_bytes(roadmap().encode("utf-8"))
    (work / "docs" / "chunks" / "P1-first.md").write_bytes(b"brief\n")
    (work / "changelog.md").write_bytes(CHANGELOG.encode("utf-8"))
    git(work, "add", "--", "docs", "changelog.md")
    git(work, "commit", "-m", "base")
    git(work, "switch", "-c", "feature")
    (work / "docs" / "ROADMAP.md").write_bytes(roadmap(extra_ledger=NEW_ROW).encode("utf-8"))
    git(work, "add", "--", "docs/ROADMAP.md")
    git(work, "commit", "-m", "Close out Session 01")
    git(work, "switch", "main")
    git(work, "merge", "--no-ff", "feature", "-m", "Merge pull request #7 from bleeski/feature")
    git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    # The checkout disagrees with origin/main on purpose: Session 02 looks done.
    (work / "docs" / "ROADMAP.md").write_bytes(roadmap(status_02="Complete").encode("utf-8"))
    return work


def materialize_paths(work: Path, text: str) -> None:
    """Create every standing path the prompt cites, so `--check` has a repo to read."""
    for path in next_prompt.paths_in(text):
        if path.startswith(next_prompt.PATH_EXEMPT_PREFIXES):
            continue
        target = work / path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x\n")


def run_fill(repo: Path, capsys, *extra: str) -> tuple[int, str]:
    code = next_prompt.main(["--repo", str(repo), "--no-fetch", *extra])
    return code, capsys.readouterr().out


def fill_in(text: str) -> str:
    """What Claude does: replace every marker with a real sentence."""
    return _MARKER.sub("A decision, with the reason it was made and the file that shows it.", text)


def lessons_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("- Lessons:"))


# --- what the prompt names, and from where --------------------------------


def test_the_session_comes_from_origin_main_not_the_checkout(repo, capsys):
    code, out = run_fill(repo, capsys)
    assert code == 0
    assert "starting Session 02 in the nfl-dfs repo (P1 part 2, the second thing)" in out
    assert "Session 03" not in out.split("## 0.")[0]


def test_an_explicit_session_overrides_the_first_startable(repo, capsys):
    code, out = run_fill(repo, capsys, "S03")
    assert code == 0 and "starting Session 03 in the nfl-dfs repo" in out


def test_an_unknown_session_is_a_named_refusal(repo, capsys):
    code = next_prompt.main(["--repo", str(repo), "--no-fetch", "S99"])
    captured = capsys.readouterr()
    assert code == 2 and "SESSION_NOT_FOUND" in captured.err and captured.out == ""


def test_the_acceptance_is_copied_from_the_card_with_its_wrapped_lines_joined(repo, capsys):
    code, out = run_fill(repo, capsys)
    expected = (
        "A bad row is refused by name; the fixture's entries are labelled from supplied numbers only; "
        "suite green."
    )
    assert f'Acceptance, verbatim: "{expected}"' in out


def test_a_card_without_an_acceptance_bullet_falls_back_and_says_so(repo, capsys):
    code, out = run_fill(repo, capsys, "S03")
    assert "<<CLAUDE:acceptance:" in out
    assert "pytest tests/test_c.py" in out, "the §2.2 verification cell is the fallback"


def test_size_breakpoint_and_brief_come_from_the_card(repo, capsys):
    code, out = run_fill(repo, capsys)
    assert "Two files, about 120 changed lines. One session." in out
    assert "Stop after the parser if the diff passes 1,000 lines." in out
    assert "docs/chunks/P1-first.md" in out


def test_the_last_merge_and_the_last_changelog_entry_are_named(repo, capsys):
    code, out = run_fill(repo, capsys)
    assert "Merge pull request #7 from bleeski/feature" in out
    assert "- Last session: 2026-10-07: Session 01 -- the first thing" in out


def test_housekeeping_lists_only_ledger_rows_the_closing_merge_added(repo, capsys):
    code, out = run_fill(repo, capsys)
    assert "The first" in out, "the row the merge added says 'recorded by the next session'"
    assert "An old row" not in out, "rows from earlier merges are not nagged about forever"


def test_a_root_commit_as_origin_main_has_no_housekeeping_and_no_crash(repo, capsys):
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "rev-list", "--max-parents=0", "HEAD"))
    code, out = run_fill(repo, capsys)
    assert code == 0 and "Housekeeping owed from the last merge: none" in out


def test_the_last_suite_line_is_read_from_state_or_says_unknown(repo, capsys):
    code, out = run_fill(repo, capsys)
    assert "suite count unknown" in out
    (repo / "state").mkdir()
    (repo / "state" / "last-verify.json").write_bytes(
        json.dumps({"result_line": "2921 passed, 1 skipped in 833.41s"}).encode("utf-8")
    )
    code, out = run_fill(repo, capsys)
    assert "2921 passed, 1 skipped in 833.41s" in out and "suite count unknown" not in out


def test_a_roadmap_section_one_that_disagrees_with_the_board_is_flagged(repo, capsys):
    text = roadmap().replace("execute Session 02", "execute Session 03")
    (repo / "docs" / "ROADMAP.md").write_bytes(text.encode("utf-8"))
    git(repo, "add", "--", "docs/ROADMAP.md")
    git(repo, "commit", "-m", "break section one")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    code, out = run_fill(repo, capsys)
    assert "<<CLAUDE:quick-start:" in out


def test_the_output_is_deterministic_and_written_with_lf_bytes(repo, capsys, tmp_path):
    first = run_fill(repo, capsys)
    second = run_fill(repo, capsys)
    assert first == second
    target = tmp_path / "out.md"
    assert next_prompt.main(["--repo", str(repo), "--no-fetch", "--out", str(target)]) == 0
    data = target.read_bytes()
    assert b"\r" not in data
    assert data.decode("utf-8") == first[1]
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


# --- the shape: the Session 23d handoff is the golden -----------------------


def test_the_filled_prompt_has_the_golden_sections_in_order(repo, capsys):
    code, out = run_fill(repo, capsys)
    golden = GOLDEN.read_text(encoding="utf-8")
    assert _HEADING.findall(out) == _HEADING.findall(golden)
    assert out.startswith("/plan\n")
    assert "\n/plan\n" in golden, "the golden also opens with /plan, after its provenance comment"


def test_the_golden_handoff_still_passes_the_standing_checks():
    golden = GOLDEN.read_text(encoding="utf-8")
    assert "\u2014" not in golden
    assert not _MARKER.findall(golden)


def test_the_template_has_the_standing_content_a_handoff_needs():
    text = TEMPLATE.read_text(encoding="utf-8")
    for phrase in (
        "EnterPlanMode",
        "/advisor",
        "set: Illegal option -o pipefail",
        "one of the three exits",
        "write_bytes",
        "Needs Ben",
        "PRIOR_ONLY",
        "record_verify.py",
    ):
        assert phrase in text, phrase


def test_the_template_has_no_em_dash():
    assert "\u2014" not in TEMPLATE.read_text(encoding="utf-8")


def test_every_token_and_slot_in_the_template_is_one_the_script_knows():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert set(re.findall(r"\{\{([A-Z_]+)\}\}", text)) <= set(next_prompt.TOKENS)
    assert {m.split(":")[1] for m in _MARKER.findall(text)} <= set(next_prompt.SLOTS)


def test_every_path_the_template_cites_exists_in_this_repository():
    text = TEMPLATE.read_text(encoding="utf-8")
    missing = [
        path
        for path in next_prompt.paths_in(text)
        if not path.startswith(next_prompt.PATH_EXEMPT_PREFIXES) and not (PROJECT_ROOT / path).exists()
    ]
    assert not missing, f"the template cites files that are gone: {missing}"


# --- --check is the gate -----------------------------------------------------


def _checked(repo: Path, capsys, text: str, *, materialize: bool = False) -> list[str]:
    """Check a prompt. Only an unmutated prompt may create the files it cites:
    a mutated one must be judged against the repository as it is."""
    if materialize:
        materialize_paths(repo, text)
    return next_prompt.check_prompt(text, repo, "origin/main")


@pytest.fixture
def filled(repo, capsys) -> str:
    code, out = run_fill(repo, capsys)
    text = fill_in(out)
    materialize_paths(repo, text)
    return text


def test_a_properly_filled_prompt_passes_check(repo, capsys, filled):
    assert next_prompt.check_prompt(filled, repo, "origin/main") == []
    target = repo.parent / "filled.md"
    target.write_bytes(filled.encode("utf-8"))
    assert next_prompt.main(["--repo", str(repo), "--check", str(target)]) == 0


def test_the_unfilled_prompt_fails_check_and_names_each_slot(repo, capsys):
    code, out = run_fill(repo, capsys)
    problems = _checked(repo, capsys, out, materialize=True)
    left = [p for p in problems if p.startswith("MARKER_LEFT:")]
    assert {p.split(":")[1] for p in left} >= {"what-to-do", "decisions", "lessons"}
    target = repo.parent / "unfilled.md"
    target.write_bytes(out.encode("utf-8"))
    assert next_prompt.main(["--repo", str(repo), "--check", str(target)]) == 1


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda t: t + "\nsee <<this>> later\n", "STRAY_ANGLE_BRACKETS"),
        (lambda t: t + "\nSession {{SESSION}}\n", "PLACEHOLDER_LEFT"),
        (lambda t: t.replace("## 3. How to verify", "## 3. Verification"), "SECTION_MISSING"),
        (lambda t: t + "\nsee `docs/does_not_exist.md`\n", "PATH_MISSING"),
        (lambda t: t + "\nthe plan \u2014 as before\n", "EM_DASH"),
        (lambda t: t.replace("suite green.", "suite passes."), "ACCEPTANCE_MISSING"),
        (lambda t: t.replace("/plan\n", "", 1), "NOT_PLAN_FIRST"),
    ],
)
def test_check_fails_each_way_a_prompt_can_be_wrong(repo, capsys, filled, mutate, code):
    problems = _checked(repo, capsys, mutate(filled))
    assert any(p.startswith(code) for p in problems), (code, problems)


def test_a_one_word_lessons_fill_fails_check(repo, capsys, filled):
    short = filled.replace(lessons_line(filled), "- Lessons: none")
    problems = _checked(repo, capsys, short)
    assert any(p.startswith("LESSONS_TOO_SHORT") for p in problems)


def test_sections_out_of_order_fail_check(repo, capsys, filled):
    first, second = "## 1. What to do", "## 2. How much effort"
    swapped = filled.replace(first, "@@A").replace(second, first).replace("@@A", second)
    assert any(p.startswith("SECTION_ORDER") for p in _checked(repo, capsys, swapped))


def test_paths_under_state_and_data_are_exempt_from_the_existence_check(repo, capsys, filled):
    text = filled + "\nwrite `state/tasks/S02.md` and read `data/runs/x/report.json`\n"
    assert _checked(repo, capsys, text) == []


def test_paths_in_ignores_placeholders_and_globs():
    text = "see docs/chunks/<ID>-slug.md, tests/test_contest*.py and `docs/RUNBOOK.md`."
    assert next_prompt.paths_in(text) == ["docs/RUNBOOK.md"]


def test_a_template_token_the_script_does_not_know_is_refused_not_left_in_the_prompt():
    with pytest.raises(next_prompt.Refusal) as caught:
        next_prompt.fill("hello {{NOT_A_TOKEN}}", {"SESSION": "Session 01"})
    assert caught.value.code == "TEMPLATE_TOKEN_UNKNOWN"


# --- what the first review found ----------------------------------------------


def _write_prompt(repo: Path, text: str, name: str = "prompt.md") -> Path:
    target = repo.parent / name
    target.write_bytes(text.encode("utf-8"))
    return target


def test_check_cannot_pass_when_it_cannot_read_the_card(repo, capsys, filled):
    """A bad ref used to skip the acceptance comparison and print OK."""
    changed = filled.replace("suite green.", "suite is whatever.")
    target = _write_prompt(repo, changed)
    code = next_prompt.main(["--repo", str(repo), "--check", str(target), "--ref", "origin/nonexistent"])
    out = capsys.readouterr().out
    assert code == 1 and "ROADMAP_NOT_AT_REF" in out and "OK:" not in out


def test_check_says_so_when_the_opening_line_no_longer_names_the_session(repo, capsys, filled):
    changed = filled.replace("You are starting Session 02", "You are beginning Session 02")
    problems = next_prompt.check_prompt(changed, repo, "origin/main")
    assert any(p.startswith("SESSION_NOT_NAMED") for p in problems)


def test_a_repository_that_does_not_exist_is_a_refusal_not_a_traceback(tmp_path, capsys):
    code = next_prompt.main(["--repo", str(tmp_path / "nowhere"), "--no-fetch"])
    captured = capsys.readouterr()
    assert code == 2 and "REPO_NOT_FOUND" in captured.err and "Traceback" not in captured.err
    code = next_prompt.main(["--repo", str(tmp_path / "nowhere"), "--check", str(tmp_path / "x.md")])
    assert code == 2


def test_a_prompt_file_that_does_not_exist_is_a_refusal_not_a_failed_check(repo, capsys):
    code = next_prompt.main(["--repo", str(repo), "--check", str(repo.parent / "absent.md")])
    assert code == 2 and "FILE_NOT_READABLE" in capsys.readouterr().err


def test_a_refusal_writes_no_output_file(repo, tmp_path, capsys):
    target = tmp_path / "never.md"
    code = next_prompt.main(["--repo", str(repo), "--no-fetch", "--out", str(target), "S99"])
    assert code == 2 and not target.exists()


def test_a_file_the_session_will_create_can_be_allowed(repo, capsys, filled):
    text = filled + "\nwrite `tests/test_contest_facts.py` first\n"
    assert any(p.startswith("PATH_MISSING:tests/test_contest_facts.py") for p in _checked(repo, capsys, text))
    problems = next_prompt.check_prompt(text, repo, "origin/main", allow_paths=("tests/test_contest_facts.py",))
    assert problems == []
    target = _write_prompt(repo, text)
    code = next_prompt.main(["--repo", str(repo), "--check", str(target), "--allow-path", "tests/test_contest_facts.py"])
    assert code == 0


def test_a_card_that_uses_a_dash_and_a_section_sign_still_passes_check(repo, capsys):
    """The acceptance is printed with the dash as ' -- ' (Ben's rule), and check compares the same way."""
    code, out = run_fill(repo, capsys, "S06")
    assert code == 0
    assert "A row with a dash -- and a section sign § is refused; suite green." in out
    assert chr(0x2014) not in out
    filled_text = fill_in(out)
    materialize_paths(repo, filled_text)
    assert next_prompt.check_prompt(filled_text, repo, "origin/main") == []


def test_size_and_breakpoint_on_one_card_line_fills_both(repo, capsys):
    code, out = run_fill(repo, capsys, "S06")
    assert "The card says: One file; stop at the parser." in out
    assert "Breakpoint, from the card: One file; stop at the parser." in out


def test_a_batched_card_heading_serves_each_session_it_covers(repo, capsys):
    code, out = run_fill(repo, capsys, "S04")
    assert code == 0 and "the batch" in out.split("## 0.")[0]
    assert 'Acceptance, verbatim: "The batch\'s acceptance for both sessions."' in out


def test_a_card_for_02_is_not_taken_from_the_02b_card(repo, capsys):
    code, out = run_fill(repo, capsys, "S02")
    assert "The b card's own acceptance" not in out and "A bad row is refused by name" in out
    code, out = run_fill(repo, capsys, "S02b")
    assert 'Acceptance, verbatim: "The b card\'s own acceptance; suite green."' in out


def test_a_session_with_no_card_says_so_instead_of_naming_the_id_as_a_title(repo, capsys):
    code, out = run_fill(repo, capsys, "S07")
    assert code == 0 and "<<CLAUDE:card:" in out and "<<CLAUDE:acceptance:" in out


def test_a_session_that_is_not_startable_yet_gets_a_marker_and_a_complete_one_is_refused(repo, capsys):
    code, out = run_fill(repo, capsys, "S04")
    assert "<<CLAUDE:not-startable:" in out
    code = next_prompt.main(["--repo", str(repo), "--no-fetch", "S05"])
    assert code == 2 and "SESSION_NOT_STARTABLE" in capsys.readouterr().err
