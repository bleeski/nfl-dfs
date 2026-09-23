"""The harness that orients a starting Claude Code instance (chunk H2).

Several instances work this repository without knowing about each other. Four
things are asserted here, and every one of them is offline: the fetch that keeps
`origin/main` honest, the staleness label that replaces a false zero, the
changelog headings the digest surfaces, the push gate that catches drift
mid-session, and the chunk claim that stops two instances taking one chunk.

No test may reach the network (`.claude/rules/tests.md`), so the one function
that touches it is injected everywhere. Clocks are passed in rather than
hardcoded, for the same reason the 2026-09-17 preflight clock test was wrong.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo_state():
    return _load(PROJECT_ROOT / "scripts" / "repo_state.py", "repo_state_under_test")


@pytest.fixture
def freshness():
    return _load(PROJECT_ROOT / ".claude" / "hooks" / "push_freshness.py", "push_freshness_under_test")


@pytest.fixture
def guard():
    return _load(PROJECT_ROOT / ".claude" / "hooks" / "guard_bash.py", "guard_bash_under_test")


@pytest.fixture
def claim():
    return _load(PROJECT_ROOT / "scripts" / "claim.py", "claim_under_test")


# --------------------------------------------------------------------------
# Fetching before deriving state. `origin/main` moves on fetch and nothing else.
# --------------------------------------------------------------------------


class _Runner:
    """Stands in for the one function that would reach the network."""

    def __init__(self, ok: bool = True, reason: str | None = None) -> None:
        self.ok, self.reason, self.calls = ok, reason, []

    def __call__(self, timeout_seconds):
        self.calls.append(timeout_seconds)
        return self.ok, self.reason


def test_a_cold_clone_fetches_before_measuring(repo_state, tmp_path, monkeypatch):
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setattr(repo_state, "STATE_DIR", tmp_path)
    runner = _Runner()

    result = repo_state.fetch_origin_main(now=NOW, runner=runner)

    assert result["attempted"] and result["ok"]
    assert len(runner.calls) == 1, "a clone with no fetch marker must fetch"


def test_the_fetch_asks_only_for_main_and_writes_the_tracking_ref(repo_state):
    """The refspec is explicit rather than relying on git's opportunistic update."""
    assert repo_state.FETCH_ARGS[0] == "fetch"
    assert "+refs/heads/main:refs/remotes/origin/main" in repo_state.FETCH_ARGS
    assert "--no-tags" in repo_state.FETCH_ARGS


def test_the_ttl_stops_clear_and_compact_paying_for_the_network(repo_state, tmp_path, monkeypatch):
    """The hook fires on startup|resume|clear|compact, so repeats must be free."""
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setattr(repo_state, "STATE_DIR", tmp_path)
    runner = _Runner()

    repo_state.fetch_origin_main(now=NOW, ttl_seconds=300, runner=runner)
    second = repo_state.fetch_origin_main(now=NOW + timedelta(seconds=60), ttl_seconds=300, runner=runner)
    third = repo_state.fetch_origin_main(now=NOW + timedelta(seconds=600), ttl_seconds=300, runner=runner)

    assert len(runner.calls) == 2, "inside the TTL the fetch must be skipped, outside it must run"
    assert second["attempted"] is False and second["ok"] is True
    assert third["attempted"] is True


def test_the_fetch_timeout_is_passed_through(repo_state, tmp_path, monkeypatch):
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setattr(repo_state, "STATE_DIR", tmp_path)
    runner = _Runner()

    repo_state.fetch_origin_main(now=NOW, timeout_seconds=1.5, runner=runner)

    assert runner.calls == [1.5]


def test_a_failed_fetch_is_reported_never_raised(repo_state, tmp_path, monkeypatch):
    """An offline session must still start. The staleness is labelled, not fatal."""
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setattr(repo_state, "STATE_DIR", tmp_path)

    result = repo_state.fetch_origin_main(now=NOW, runner=_Runner(ok=False, reason="timeout after 3s"))

    assert result["attempted"] is True
    assert result["ok"] is False
    assert result["reason"] == "timeout after 3s"


def test_an_air_gapped_session_can_switch_the_fetch_off(repo_state, tmp_path, monkeypatch):
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setenv("NFL_DFS_NO_FETCH", "1")
    runner = _Runner()

    result = repo_state.fetch_origin_main(now=NOW, runner=runner)

    assert runner.calls == []
    assert result["ok"] is False and "NFL_DFS_NO_FETCH" in result["reason"]


def test_the_real_runner_is_never_invoked_by_these_tests(repo_state):
    """Guards the guard: the default must be the subprocess one, so an injected
    runner is a deliberate substitution rather than the normal path."""
    import inspect

    default = inspect.signature(repo_state.fetch_origin_main).parameters["runner"].default
    assert default is repo_state._run_fetch


# --------------------------------------------------------------------------
# The staleness label. A false zero is the bug this whole chunk exists to fix.
# --------------------------------------------------------------------------


def _state_with_fetch(fetch: dict, behind: str = "0") -> dict:
    return {
        "git": {
            "branch": "claude/x",
            "head": "abc1234",
            "dirty_paths": 0,
            "untracked_paths": 0,
            "behind_origin_main": behind,
            "ahead_of_origin_main": "0",
            "origin_main_fetch": fetch,
            "recent_commits": ["abc1234 A commit"],
        },
        "ready_chunks": [],
        "in_progress_chunks": [],
        "changelog_headings": [],
        "claims": {"active": [], "stale": [], "stale_after_hours": 6},
        "verification": {"known": False},
        "calibration": {
            "slates_graded": 0,
            "slates_recorded": 0,
            "model_status": "PRIOR_ONLY",
            "release_decision": "DO_NOT_UPLOAD",
        },
        "ben_flags": [],
    }


def test_a_failed_fetch_never_prints_an_unqualified_zero(repo_state):
    text = repo_state.digest(
        _state_with_fetch({"attempted": True, "ok": False, "reason": "timeout after 3s", "age_seconds": 7200.0})
    )

    assert "origin/main NOT fetched" in text
    assert "timeout after 3s" in text
    assert "2.0h ago" in text


def test_a_clone_that_never_fetched_says_so(repo_state):
    text = repo_state.digest(
        _state_with_fetch({"attempted": True, "ok": False, "reason": "no route to host", "age_seconds": None})
    )

    assert "never been fetched" in text


def test_a_good_fetch_adds_no_noise(repo_state):
    text = repo_state.digest(
        _state_with_fetch({"attempted": True, "ok": True, "reason": None, "age_seconds": 0.0})
    )

    assert "NOT fetched" not in text


# --------------------------------------------------------------------------
# The prose record. A commit subject is not a substitute for it.
# --------------------------------------------------------------------------


CHANGELOG_FIXTURE = """\
# NFL DFS Implementation Changelog

## Unreleased

### 2026-09-17 (CI unblock): the newest one

Body text that must never be read into the digest.

### 2026-09-16 (harness): the middle one

More body.

### 2026-09-15 (hygiene): the oldest kept one

### 2026-09-14 (ignored): one entry too many

## 0.9.0 - 2026-09-01

### 2026-08-01 (released): must not appear
"""


def test_the_digest_shows_three_headings_newest_first(repo_state, tmp_path):
    path = tmp_path / "changelog.md"
    path.write_text(CHANGELOG_FIXTURE, encoding="utf-8")

    headings = repo_state.changelog_headings(path=path)

    assert headings == [
        "2026-09-17 (CI unblock): the newest one",
        "2026-09-16 (harness): the middle one",
        "2026-09-15 (hygiene): the oldest kept one",
    ]


def test_a_released_section_is_never_reached(repo_state, tmp_path):
    path = tmp_path / "changelog.md"
    path.write_text(CHANGELOG_FIXTURE, encoding="utf-8")

    assert all("released" not in heading for heading in repo_state.changelog_headings(path=path, limit=99))


def test_headings_only_never_body(repo_state, tmp_path):
    path = tmp_path / "changelog.md"
    path.write_text(CHANGELOG_FIXTURE, encoding="utf-8")

    assert all("Body text" not in heading for heading in repo_state.changelog_headings(path=path))


def test_a_long_heading_is_truncated_to_protect_the_line_budget(repo_state, tmp_path):
    path = tmp_path / "changelog.md"
    path.write_text("## Unreleased\n\n### " + "x" * 200 + "\n", encoding="utf-8")

    (heading,) = repo_state.changelog_headings(path=path)

    assert len(heading) == repo_state.CHANGELOG_HEADING_WIDTH
    assert heading.endswith("…")


def test_a_missing_changelog_is_not_fatal(repo_state, tmp_path):
    assert repo_state.changelog_headings(path=tmp_path / "absent.md") == []


def test_the_real_changelog_yields_three_dated_headings(repo_state):
    headings = repo_state.changelog_headings()

    assert len(headings) == 3
    assert all(heading[:4].isdigit() for heading in headings), headings


# --------------------------------------------------------------------------
# The session-start line budget. 60 lines is what protects the context window.
# --------------------------------------------------------------------------


def test_the_session_start_hook_stays_inside_sixty_lines():
    """Run for real: the headings and the staleness line had to fit, not extend."""
    result = subprocess.run(
        (sys.executable, str(PROJECT_ROOT / ".claude" / "hooks" / "session_start.py")),
        capture_output=True,
        text=True,
        timeout=60,
        # The interpreter running the suite, not whatever `python3` resolves to,
        # and the real environment plus the offline switch: CI runs Python from
        # a uv path that a hand-built PATH would not contain.
        env={**os.environ, "NFL_DFS_NO_FETCH": "1"},
        cwd=PROJECT_ROOT,
    )

    lines = result.stdout.splitlines()
    assert result.returncode == 0, "the hook must exit 0 no matter what"
    assert 0 < len(lines) <= 60, f"session start printed {len(lines)} lines"


def test_the_session_start_hook_exits_zero_from_an_unrelated_directory(tmp_path):
    """A hook that can fail a session start is worse than no hook.

    It resolves its paths from `__file__`, not the working directory, so this
    pins that it still works when Claude Code launches it from elsewhere.
    """
    result = subprocess.run(
        (sys.executable, str(PROJECT_ROOT / ".claude" / "hooks" / "session_start.py")),
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "NFL_DFS_NO_FETCH": "1"},
        cwd=str(tmp_path),
    )

    assert result.returncode == 0


# --------------------------------------------------------------------------
# The freshness gate. Drift arriving forty minutes into a session.
# --------------------------------------------------------------------------


class _Git:
    """A fake git. `main_moved` decides whether the merge base is behind."""

    def __init__(self, remote="r3", base="r3", count="3", log="c1 Third\nc2 Second\nc3 First"):
        self.remote, self.base, self.count, self.log = remote, base, count, log

    def __call__(self, *args):
        if args[0] == "rev-parse":
            return self.remote
        if args[0] == "merge-base":
            return self.base
        if args[0] == "rev-list":
            return self.count
        if args[0] == "log":
            return self.log
        return None


def _ok_fetch(**kwargs):
    return {"attempted": True, "ok": True, "reason": None}


def _failed_fetch(**kwargs):
    return {"attempted": True, "ok": False, "reason": "offline"}


PUSH = "git push -u origin claude/h2-multi-instance-orientation"


def test_a_push_is_refused_when_main_moved(freshness):
    reason = freshness.evaluate(PUSH, git=_Git(remote="r3", base="b0"), fetcher=_ok_fetch)

    assert reason is not None
    assert "moved 3 commits" in reason
    assert "c1 Third" in reason, "the gate must name what moved"
    assert "git merge origin/main" in reason, "it must say what to do about it"


def test_a_push_is_untouched_when_main_has_not_moved(freshness):
    assert freshness.evaluate(PUSH, git=_Git(remote="r3", base="r3"), fetcher=_ok_fetch) is None


def test_one_commit_is_not_pluralised(freshness):
    reason = freshness.evaluate(PUSH, git=_Git(remote="r1", base="b0", count="1"), fetcher=_ok_fetch)

    assert "moved 1 commit ahead" in reason


def test_a_failed_fetch_never_blocks_the_push(freshness):
    """The gate fails open. A network problem must not stop work."""
    assert freshness.evaluate(PUSH, git=_Git(remote="r3", base="b0"), fetcher=_failed_fetch) is None


def test_a_missing_origin_main_never_blocks_the_push(freshness):
    assert freshness.evaluate(PUSH, git=_Git(remote=None), fetcher=_ok_fetch) is None


@pytest.mark.parametrize(
    "command",
    (
        "git push origin --delete claude/h2-multi-instance-orientation",
        "git push origin :claude/h2-multi-instance-orientation",
        "git push --dry-run origin claude/x",
        "git status --short",
        "sh ./nfl.sh test",
        "echo 'git push is refused when stale'",
    ),
)
def test_these_never_reach_the_gate(freshness, command):
    """A deletion, a dry run and every non-push must cost nothing."""

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"the gate ran git for {command!r}")

    assert freshness.evaluate(command, git=explode, fetcher=explode) is None


def test_the_push_probe_is_one_regex_and_no_io(freshness):
    assert freshness.mentions_push("git push -u origin claude/x") is True
    assert freshness.mentions_push("git status --short --branch") is False


def test_the_gate_asks_for_a_fresh_answer_not_a_cached_one(freshness):
    """A five-minute-old fetch could miss the merge that happened four minutes
    ago, which is the case this gate exists to catch."""
    seen = {}

    def fetcher(**kwargs):
        seen.update(kwargs)
        return {"attempted": True, "ok": True, "reason": None}

    freshness.evaluate(PUSH, git=_Git(base="r3"), fetcher=fetcher)

    assert seen["ttl_seconds"] == 0.0


def test_a_non_push_bash_call_does_not_import_the_gate(guard):
    """The gate rides the existing hook rather than a second process, so the
    cost on an ordinary Bash call has to stay at zero."""
    import sys

    sys.modules.pop("push_freshness", None)

    assert guard.stale_push_reason("ls -la && grep -rn thing src/") is None
    assert "push_freshness" not in sys.modules


# --------------------------------------------------------------------------
# The chunk claim. `state/claims.json` had a reader and no writer.
# --------------------------------------------------------------------------


def test_a_chunk_can_be_claimed(claim, tmp_path):
    path = tmp_path / "claims.json"

    code, message = claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    assert code == 0 and "Claimed P0" in message
    (entry,) = json.loads(path.read_text())["claims"]
    assert entry["chunk"] == "P0"
    assert entry["agent"] == "instance-A"
    assert entry["claimed_at"] == "2026-09-17T12:00:00Z"


def test_a_second_instance_is_refused_the_same_chunk(claim, tmp_path):
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    code, message = claim.take("P0", "claude/p0-y", "instance-B", NOW + timedelta(hours=1), path=path)

    assert code == 1, "the second instance must not proceed"
    assert "already claimed by instance-A" in message
    assert "1.0h ago" in message
    (entry,) = json.loads(path.read_text())["claims"]
    assert entry["agent"] == "instance-A", "a refused take must not overwrite the claim"


def test_reclaiming_your_own_chunk_is_idempotent(claim, tmp_path):
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    code, _ = claim.take("P0", "claude/p0-x", "instance-A", NOW + timedelta(hours=1), path=path)

    assert code == 0
    assert len(json.loads(path.read_text())["claims"]) == 1


def test_a_claim_older_than_six_hours_is_reclaimable_and_the_reclaim_is_recorded(claim, tmp_path):
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    code, message = claim.take("P0", "claude/p0-y", "instance-B", NOW + timedelta(hours=7), path=path)

    assert code == 0
    assert "Reclaimed P0" in message and "changelog" in message
    (entry,) = json.loads(path.read_text())["claims"]
    assert entry["agent"] == "instance-B"
    assert entry["reclaimed_from"]["agent"] == "instance-A"
    assert entry["reclaimed_from"]["age_hours"] == 7.0


def test_six_hours_exactly_is_still_held(claim, tmp_path):
    """The boundary is stated as `older than six hours`, so six is not older."""
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    code, _ = claim.take("P0", "claude/p0-y", "instance-B", NOW + timedelta(hours=6), path=path)

    assert code == 1


def test_a_claim_is_released_at_close_out(claim, tmp_path):
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    code, message = claim.release("P0", "instance-A", path=path)

    assert code == 0 and "Released P0" in message
    assert json.loads(path.read_text())["claims"] == []


def test_releasing_nothing_is_not_an_error(claim, tmp_path):
    code, message = claim.release("P0", "instance-A", path=tmp_path / "claims.json")

    assert code == 0 and "No claim" in message


def test_two_chunks_coexist(claim, tmp_path):
    path = tmp_path / "claims.json"
    claim.take("P1", "claude/p1-x", "instance-B", NOW, path=path)
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    chunks = [entry["chunk"] for entry in json.loads(path.read_text())["claims"]]
    assert chunks == ["P0", "P1"], "sorted, so concurrent instances get a small diff"


def test_a_corrupt_claims_file_does_not_stop_a_claim(claim, tmp_path):
    path = tmp_path / "claims.json"
    path.write_text("{ this is not json", encoding="utf-8")

    code, _ = claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    assert code == 0


def test_what_the_writer_produces_is_what_the_reader_expects(claim, repo_state, tmp_path, monkeypatch):
    """The two halves have to agree, or the digest shows nothing."""
    path = tmp_path / "claims.json"
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)
    monkeypatch.setattr(repo_state, "CLAIMS_FILE", path)

    state = repo_state.claims(NOW + timedelta(hours=1))

    assert len(state["active"]) == 1 and not state["stale"]
    assert state["active"][0]["chunk"] == "P0"
    assert state["active"][0]["age_hours"] == 1.0


def test_the_writer_and_the_reader_share_one_staleness_threshold(claim, repo_state):
    assert claim.STALE_CLAIM_HOURS is repo_state.STALE_CLAIM_HOURS


# --------------------------------------------------------------------------
# Task files. `.claude/rules/stops-and-reports.md`: the list survives compaction,
# and the hook that runs on `compact` is what points the session back at it.
# --------------------------------------------------------------------------


def test_task_files_are_counted_and_finished_lists_left_out(repo_state, tmp_path):
    (tmp_path / "S03.md").write_text(
        "# S03\nAcceptance: ...\n- [x] tests first\n- [X] registry\n- [ ] truth record\n",
        encoding="utf-8",
    )
    (tmp_path / "S02.md").write_text("- [x] one\n- [x] two\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("no checkboxes yet\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("- [ ] not markdown\n", encoding="utf-8")

    found = {Path(task["path"]).name: task for task in repo_state.task_files(tmp_path)}

    assert set(found) == {"S03.md", "notes.md"}
    assert (found["S03.md"]["done"], found["S03.md"]["open"]) == (2, 1)
    assert (found["notes.md"]["done"], found["notes.md"]["open"]) == (0, 0)


def test_task_files_are_listed_most_recently_touched_first(repo_state, tmp_path):
    for age, name in enumerate(("newest.md", "middle.md", "oldest.md")):
        path = tmp_path / name
        path.write_text("- [ ] one\n", encoding="utf-8")
        stamp = 1_800_000_000 - age * 3600
        os.utime(path, (stamp, stamp))

    names = [Path(task["path"]).name for task in repo_state.task_files(tmp_path)]

    assert names == ["newest.md", "middle.md", "oldest.md"]


def test_a_directory_named_like_a_task_file_is_skipped(repo_state, tmp_path):
    (tmp_path / "odd.md").mkdir()

    assert repo_state.task_files(tmp_path) == []


def test_the_state_the_hook_reads_carries_the_task_files(repo_state, tmp_path, monkeypatch):
    """The wiring, not just the helper: `build_state` is what the hook digests."""
    monkeypatch.setenv("NFL_DFS_NO_FETCH", "1")
    monkeypatch.setattr(repo_state, "LAST_FETCH_FILE", tmp_path / "last-fetch.json")
    monkeypatch.setattr(repo_state, "STATE_DIR", tmp_path)
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "S03.md").write_text("- [x] one\n- [ ] two\n", encoding="utf-8")
    monkeypatch.setattr(repo_state, "TASKS_DIR", tasks)

    state = repo_state.build_state(NOW)

    assert [(Path(t["path"]).name, t["done"], t["open"]) for t in state["task_files"]] == [("S03.md", 1, 1)]
    assert "S03.md: 1/2 done" in repo_state.digest(state)


def test_a_missing_tasks_directory_is_not_fatal(repo_state, tmp_path):
    assert repo_state.task_files(tmp_path / "absent") == []


def test_the_digest_points_a_compacted_session_at_its_task_file(repo_state):
    state = _state_with_fetch({"attempted": True, "ok": True, "reason": None, "age_seconds": 0.0})
    state["task_files"] = [{"path": "state/tasks/S03.md", "done": 2, "open": 1}]

    text = repo_state.digest(state)

    assert "state/tasks/S03.md: 2/3 done" in text


def test_no_task_file_adds_no_line(repo_state):
    text = repo_state.digest(
        _state_with_fetch({"attempted": True, "ok": True, "reason": None, "age_seconds": 0.0})
    )

    assert "task files" not in text


def test_the_digest_shows_at_most_three_task_files(repo_state):
    state = _state_with_fetch({"attempted": True, "ok": True, "reason": None, "age_seconds": 0.0})
    state["task_files"] = [{"path": f"state/tasks/S0{n}.md", "done": 0, "open": 1} for n in range(5)]

    text = repo_state.digest(state)

    assert "(+2 more)" in text
    assert "S03.md" not in text and "S02.md" in text


def test_task_files_never_reach_a_diff():
    """Working notes, not status: `state/` is ignored apart from `claims.json`."""
    ignored = subprocess.run(
        ("git", "check-ignore", "--quiet", "--no-index", "state/tasks/S03.md"),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert ignored.returncode == 0, "state/tasks/ must stay gitignored"


def test_the_claims_file_is_tracked_on_purpose():
    """A claim that does not travel cannot coordinate anything."""
    tracked = subprocess.run(
        ("git", "ls-files", "state/"),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    ).stdout.split()

    assert "state/claims.json" in tracked
    assert "state/repo-state.json" not in tracked, "the derived digest must stay ignored"


def test_the_claims_writer_is_deterministic(claim, tmp_path):
    """`.claude/rules/tests.md` asks every new writer for a determinism test.

    Same claims in, byte-identical file out, whatever order they were written:
    two instances editing this file must not produce a spurious diff on top of
    the real one. The rule's other half, a mutation test withholding the
    artifact, does not apply here: `claims.json` is a coordination file, not an
    evidence artifact bound to a hash, and there is nothing to withhold.
    """
    first, second = tmp_path / "a.json", tmp_path / "b.json"

    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=first)
    claim.take("P1", "claude/p1-y", "instance-B", NOW, path=first)

    claim.take("P1", "claude/p1-y", "instance-B", NOW, path=second)
    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=second)

    assert first.read_bytes() == second.read_bytes()


def test_the_claims_file_is_written_lf_with_a_trailing_newline(claim, tmp_path):
    path = tmp_path / "claims.json"

    claim.take("P0", "claude/p0-x", "instance-A", NOW, path=path)

    raw = path.read_bytes()
    assert b"\r\n" not in raw, "the ledger files in this repository are LF"
    assert raw.endswith(b"\n")
