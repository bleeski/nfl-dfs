#!/usr/bin/env python3
"""Build the next session's handoff prompt from `origin/main`, and gate it.

Ben asked (2026-10-08) that every merge be followed by a prompt for the next
chunk of work "in the same format" as the Session 23d handoff that was written
by hand that day. `docs/claude/next_session_prompt.md` is that format. This
script fills what is mechanical from the repository, never from the checkout (a
stale clone must not name the wrong session):

    session and title, the card's acceptance, size and breakpoint, the brief the
    card cites, the last merge, the last changelog entry, the last recorded suite
    line, and the ledger rows the closing merge left saying "recorded by the next
    session"

and leaves `<<CLAUDE:slot: ...>>` markers for what takes reading the card (the
decisions to settle in the plan, out of scope, card-specific checks, the lessons
of the session just ended). `--check FILE` fails while any marker, placeholder,
stray `<<`, missing or reordered section, missing path, em dash or missing
acceptance remains, so a prompt cannot ship half-written and the judgment cannot
be skipped. Nothing is stored: per-session prompt files stay retired
(`.claude/rules/ledger.md`); this derives a handoff from the card.

Exit codes: 0 ok, 1 `--check` found problems, 2 a refusal (stderr names it).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS.parent
DEFAULT_TEMPLATE = PROJECT_ROOT / "docs" / "claude" / "next_session_prompt.md"

TOKENS = (
    "SESSION",
    "SHORT",
    "SHORT_LOWER",
    "TITLE",
    "ACCEPTANCE_LINE",
    "BREAKPOINT_LINE",
    "BRIEFS_CLAUSE",
    "SIZE",
    "LAST_MERGE",
    "LAST_ENTRY",
    "LAST_SUITE",
    "HOUSEKEEPING",
    "QUICK_START_NOTE",
)
SLOTS = (
    "what-to-do",
    "decisions",
    "out-of-scope",
    "effort",
    "fixtures",
    "acceptance-checks",
    "neighbors",
    "attack",
    "lessons",
    "acceptance",
    "quick-start",
    "not-startable",
    "card",
)
# Paths the prompt tells the next session to create or to read from a run.
PATH_EXEMPT_PREFIXES = ("state/", "data/", "outputs/")
MIN_LESSON_WORDS = 8

_TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")
_MARKER = re.compile(r"<<CLAUDE:([a-z-]+):.*?>>")
_HEADING = re.compile(r"^## .*$", re.MULTILINE)
_PATH = re.compile(
    r"(?<![\w/.<>{}*-])"
    r"((?:docs|scripts|src|tests|config|templates|\.claude|\.github)/[A-Za-z0-9_./-]*?\.[A-Za-z0-9]+)"
    r"(?![\w/*<{-])"
)
_BRIEF = re.compile(r"docs/chunks/[A-Za-z0-9._-]+\.md")
_SESSION_NAME = re.compile(r"^Session [0-9]{2}[a-z]?$")


class Refusal(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


_EM_DASH = chr(0x2014)  # a code point, so no source file carries the character
_CARD_HEADING = re.compile(r"^#### Sessions? (?P<first>[0-9]{2})(?P<suffix>[a-z]?)(?: to (?P<last>[0-9]{2}))?(?=[:\s]|$)")
_SESSION_PARTS = re.compile(r"^Session (?P<number>[0-9]{2})(?P<suffix>[a-z]?)$")


def _plain(text: str) -> str:
    """Card and git text as the prompt prints it: whitespace joined, and Ben's no-em-dash rule applied
    the way the changelog does (' -- '), so a card that uses one still passes --check."""
    return " ".join(text.replace(_EM_DASH, " -- ").split())


def _covers(heading: str, session: str) -> bool:
    """Does this `#### Session 02: ...` or `#### Sessions 31 to 36: ...` heading hold the session's card?"""
    found, wanted = _CARD_HEADING.match(heading), _SESSION_PARTS.match(session)
    if not found or not wanted:
        return False
    if found.group("last") is None:
        return (found.group("first"), found.group("suffix")) == (wanted.group("number"), wanted.group("suffix"))
    return int(found.group("first")) <= int(wanted.group("number")) <= int(found.group("last"))


def _git(repo: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    return result.returncode, result.stdout


def read_at(repo: Path, ref: str, path: str) -> str | None:
    code, out = _git(repo, "show", f"{ref}:{path}")
    return out if code == 0 else None


def _repo_state():
    sys.path.insert(0, str(SCRIPTS))
    import repo_state  # noqa: PLC0415 - a sibling script, loaded when needed

    return repo_state


def board(roadmap_text: str) -> list[dict]:
    """The validated status board of a ROADMAP given as text (not as the checkout's file)."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "ROADMAP.md"
        path.write_bytes(roadmap_text.encode("utf-8"))
        queue = _repo_state().session_queue(path)
    if queue["error"]:
        raise Refusal("ROADMAP_UNREADABLE", str(queue["error"]))
    return queue["rows"]


def resolve_session(rows: list[dict], wanted: str | None) -> dict:
    if wanted is None:
        for row in rows:
            if row.get("startable"):
                return row
        raise Refusal("NOTHING_STARTABLE", "no Pending row has its dependencies satisfied")
    key = wanted.strip().lower()
    for row in rows:
        if key in (row["short"].lower(), row["session"].lower()):
            if row["status"] in ("Complete", "Deferred"):
                raise Refusal("SESSION_NOT_STARTABLE", f"{row['session']} is {row['status']}, so it needs no handoff")
            return row
    raise Refusal("SESSION_NOT_FOUND", f"{wanted!r} is not on the status board")


def card(roadmap_text: str, session: str) -> dict:
    """The card's title and its `- **Label.** text` bullets, wrapped lines joined."""
    lines = roadmap_text.splitlines()
    start = next((i for i, line in enumerate(lines) if _covers(line, session)), None)
    if start is None:
        return {"found": False, "title": session, "fields": {}, "text": ""}
    end = next((j for j in range(start + 1, len(lines)) if re.match(r"^#{1,4} ", lines[j])), len(lines))
    heading = lines[start]
    title = heading.split(":", 1)[1].strip() if ":" in heading else session
    fields: dict[str, list[str]] = {}
    label = None
    for line in lines[start + 1 : end]:
        bullet = re.match(r"^- \*\*(.+?)\*\*\s?(.*)$", line)
        if bullet:
            label = bullet.group(1).strip().rstrip(".").strip()
            fields[label] = [bullet.group(2)]
        elif label and line.strip() and not line.startswith("- "):
            fields[label].append(line.strip())
        elif line.startswith("- "):
            label = None
    return {
        "found": True,
        "title": title,
        "fields": {key: " ".join(" ".join(parts).split()) for key, parts in fields.items()},
        "text": "\n".join(lines[start:end]),
    }


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def _last_merge(repo: Path, ref: str) -> str:
    code, out = _git(repo, "log", "-1", "--format=%h %s", ref)
    return _plain(out.strip()) if code == 0 and out.strip() else "unknown"


def _last_entry(repo: Path, ref: str) -> str:
    text = read_at(repo, ref, "changelog.md") or ""
    inside = False
    for line in text.splitlines():
        if line.startswith("## Unreleased"):
            inside = True
        elif inside and line.startswith("### "):
            return _plain(line[4:].strip())
        elif inside and line.startswith("## "):
            break
    return "no changelog entry found"


def _last_suite(repo: Path) -> str:
    try:
        recorded = json.loads((repo / "state" / "last-verify.json").read_text(encoding="utf-8"))
        line = str(recorded.get("result_line") or "").strip()
        if line:
            return _plain(line)
    except (OSError, ValueError):
        pass
    return "suite count unknown (state/last-verify.json is not in this container; take it from the first full run and record it)"


def _housekeeping(repo: Path, ref: str) -> str:
    code, out = _git(repo, "diff", f"{ref}^1", ref, "--", "docs/ROADMAP.md")
    if code != 0:
        return "none"
    rows = [
        line[1:].strip().strip("|").strip()
        for line in out.splitlines()
        if line.startswith("+|") and "recorded by the next session" in line
    ]
    if not rows:
        return "none"
    shown = "; ".join(_plain(" ".join(row.split())[:240]) for row in rows)
    return (
        'ledger rows the last merge added that still say "recorded by the next session": '
        f"{shown}. Fill each row's commit cell with that pull request's merge SHA (git log --first-parent origin/main)."
    )


def _quick_start_session(roadmap_text: str) -> str | None:
    section = roadmap_text.split("## 1. Next Session Quick-Start", 1)
    if len(section) < 2:
        return None
    named = re.search(r"execute (Session [0-9]{2}[a-z]?)", section[1].split("\n## ", 1)[0])
    return named.group(1) if named else None


def build_values(repo: Path, ref: str, wanted: str | None) -> dict[str, str]:
    roadmap_text = read_at(repo, ref, "docs/ROADMAP.md")
    if roadmap_text is None:
        raise Refusal("ROADMAP_NOT_AT_REF", f"{ref}:docs/ROADMAP.md does not exist")
    rows = board(roadmap_text)
    row = resolve_session(rows, wanted)
    session, short = row["session"], row["short"]
    info = card(roadmap_text, session)
    fields = info["fields"]

    if "Acceptance" in fields:
        acceptance = f'Acceptance, verbatim: "{fields["Acceptance"]}"'
    else:
        cell = row["verification"].replace(">>", "> >")
        acceptance = (
            "<<CLAUDE:acceptance: the card has no Acceptance bullet, so write the acceptance from its Scope and "
            f"this status-board verification cell: {cell}>>"
        )
    briefs = list(dict.fromkeys(_BRIEF.findall(info["text"])))
    if briefs:
        noun = "the brief" if len(briefs) == 1 else "the briefs"
        briefs_clause = f" {noun} {', '.join(briefs)};"
    else:
        briefs_clause = ""
    named = _quick_start_session(roadmap_text)
    note = ""
    if wanted is None and named != session:
        note = (
            f" <<CLAUDE:quick-start: ROADMAP section 1 names {named or 'no session'} but the board's first startable "
            f"row is {session}; say which is right and fix section 1 first.>>"
        )
    elif not row.get("startable"):
        waiting = ", ".join(row["depends_on"]) or "its status"
        note += (
            f" <<CLAUDE:not-startable: {session} is not startable yet ({row['status']}; depends on {waiting}); "
            "say what has to land first and whether this handoff should wait.>>"
        )
    size = fields.get("Size") or fields.get("Size and breakpoint")
    breakpoint_text = fields.get("Breakpoint") or fields.get("Size and breakpoint")
    if not info["found"]:
        note += (
            f" <<CLAUDE:card: no card heading was found for {session} in ROADMAP section 2.3, so read its status-board "
            "row and brief instead and say so in the plan.>>"
        )
    return {
        "SESSION": session,
        "SHORT": short,
        "SHORT_LOWER": short.lower(),
        "TITLE": _plain(info["title"]),
        "ACCEPTANCE_LINE": _plain(acceptance),
        "BREAKPOINT_LINE": _plain(
            f"Breakpoint, from the card: {breakpoint_text}" if breakpoint_text else "The card names no breakpoint."
        ),
        "BRIEFS_CLAUSE": briefs_clause,
        "SIZE": _plain(_sentence(size) if size else "the card states no size."),
        "LAST_MERGE": _last_merge(repo, ref),
        "LAST_ENTRY": _last_entry(repo, ref),
        "LAST_SUITE": _last_suite(repo),
        "HOUSEKEEPING": _housekeeping(repo, ref),
        "QUICK_START_NOTE": note,
    }


def fill(template: str, values: dict[str, str]) -> str:
    unknown = set(_TOKEN.findall(template)) - set(values)
    if unknown:
        raise Refusal("TEMPLATE_TOKEN_UNKNOWN", ", ".join(sorted(unknown)))
    text = _TOKEN.sub(lambda match: values[match.group(1)], template)
    return text.rstrip("\n") + "\n"


def headings(text: str) -> list[str]:
    return _HEADING.findall(text)


def paths_in(text: str) -> list[str]:
    return list(dict.fromkeys(_PATH.findall(text)))


def _words(text: str) -> int:
    return len(text.split())


def check_prompt(
    text: str,
    repo: Path,
    ref: str = "origin/main",
    template_text: str | None = None,
    allow_paths: tuple[str, ...] = (),
) -> list[str]:
    """Why this prompt is not ready, one code per problem; empty means it is. `allow_paths` names files the
    session will create, which cannot exist yet."""
    problems: list[str] = []
    if not text.startswith("/plan\n"):
        problems.append("NOT_PLAN_FIRST: the prompt must open with /plan")
    for slot in dict.fromkeys(match.group(1) for match in _MARKER.finditer(text)):
        problems.append(f"MARKER_LEFT:{slot}: replace the <<CLAUDE:{slot}: ...>> marker with the real content")
    without_markers = _MARKER.sub(" ", text)
    if "<<" in without_markers or ">>" in without_markers:
        problems.append("STRAY_ANGLE_BRACKETS: a << or >> is left that is not a marker")
    if "{{" in text:
        problems.append("PLACEHOLDER_LEFT: a {{TOKEN}} was never filled")
    if "\u2014" in text:
        problems.append("EM_DASH: Ben edits em dashes out; use a comma, colon or parentheses")

    required = headings(template_text if template_text is not None else DEFAULT_TEMPLATE.read_text(encoding="utf-8"))
    present = headings(text)
    for heading in required:
        if heading not in present:
            problems.append(f"SECTION_MISSING:{heading}")
    if all(heading in present for heading in required) and [h for h in present if h in required] != required:
        problems.append("SECTION_ORDER: the numbered sections are out of order")

    for path in paths_in(text):
        if path.startswith(PATH_EXEMPT_PREFIXES) or path in allow_paths:
            continue
        if not (repo / path).exists():
            problems.append(f"PATH_MISSING:{path}")

    # The acceptance is the one claim the prompt makes about the card, so a check that cannot read
    # the card says so instead of passing.
    named = re.search(r"starting (Session [0-9]{2}[a-z]?)", text)
    roadmap_text = read_at(repo, ref, "docs/ROADMAP.md")
    if roadmap_text is None:
        problems.append(f"ROADMAP_NOT_AT_REF:{ref}: cannot compare the acceptance with the card")
    elif named is None:
        problems.append("SESSION_NOT_NAMED: the opening line no longer says 'starting Session NN'")
    else:
        accepted = card(roadmap_text, named.group(1))["fields"].get("Acceptance")
        if accepted and _plain(accepted) not in " ".join(text.split()):
            problems.append("ACCEPTANCE_MISSING: the card's acceptance is not in the prompt verbatim")

    lessons = next((line for line in text.splitlines() if line.startswith("- Lessons:")), None)
    if lessons is None:
        problems.append("LESSONS_MISSING: the '- Lessons:' line is gone")
    elif _words(lessons.split(":", 1)[1]) < MIN_LESSON_WORDS:
        problems.append(f"LESSONS_TOO_SHORT: fewer than {MIN_LESSON_WORDS} words after '- Lessons:'")
    return problems


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise Refusal("FILE_NOT_READABLE", f"{path}: {error.strerror or error}") from error


def _fetch(repo: Path) -> None:
    code, _ = _git(repo, "fetch", "origin", "main")
    if code != 0:
        print("WARNING: git fetch origin main failed; the prompt may name a stale session.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session", nargs="?", help="a session such as S23d (default: the first startable row)")
    parser.add_argument("--repo", default=".", help="the checkout to read git from (default: the current directory)")
    parser.add_argument("--ref", default="origin/main", help="the ref the ROADMAP and changelog are read from")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--out", help="write the prompt here (LF bytes) instead of stdout")
    parser.add_argument("--no-fetch", action="store_true", help="do not run git fetch origin main first (tests, offline)")
    parser.add_argument("--check", metavar="FILE", help="check a filled prompt instead of building one")
    parser.add_argument("--allow-path", action="append", default=[], metavar="PATH", help="a file the session will create, so --check does not need it to exist (repeatable)")
    args = parser.parse_args(argv)
    repo = Path(args.repo)

    try:
        if not repo.is_dir():
            raise Refusal("REPO_NOT_FOUND", f"{repo} is not a directory")
        if args.check:
            template_text = _read_text(Path(args.template))
            prompt = _read_text(Path(args.check))
            problems = check_prompt(prompt, repo, args.ref, template_text, tuple(args.allow_path))
            for problem in problems:
                print(problem)
            if problems:
                return 1
            print("OK: the prompt passes every standing check")
            return 0
        if not args.no_fetch:
            _fetch(repo)
        values = build_values(repo, args.ref, args.session)
        text = fill(_read_text(Path(args.template)), values)
    except Refusal as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).write_bytes(text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
