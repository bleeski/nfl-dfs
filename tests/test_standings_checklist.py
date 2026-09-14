"""The standings pull checklist must stay a one-click list of real contests.

`scripts/standings_checklist.py` is logistics, not settlement, and the whole
point of it is the working surface: every contest Ben entered but has not
pulled an export for, oldest evidence first, one click per contest. These
tests pin the parts that would silently ruin that: a contest discovered but
rendered without its export link, a contest already filed that keeps being
listed, a disposition quietly overwritten, and date grouping that puts the
newest contests (the ones least at risk of DraftKings' export ageing out) at
the top.

Discovery itself is deliberately tested against a stub parser rather than DK
fixture bytes. The tool reuses `nfl_dfs.dk.parse_entries`, the engine's own
parser, so the parser has its own tests; what is unproven here is this tool's
bookkeeping around it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from nfl_dfs.dk import DraftKingsParseError


def _checklist():
    path = Path(__file__).resolve().parents[1] / "scripts" / "standings_checklist.py"
    spec = importlib.util.spec_from_file_location("standings_checklist", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Registered before exec: the module's dataclasses resolve their string
    # annotations (`from __future__ import annotations`) through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HEADER = "mode,contest_id,contest_name,entry_fee,entry_id"


@dataclass(frozen=True)
class _Auth:
    contest_id: str
    contest_name: str
    entry_fee: float
    entry_id: str


@dataclass(frozen=True)
class _Mode:
    value: str


@dataclass(frozen=True)
class _Template:
    mode: _Mode
    authorizations: list


def _stub_parse_entries(path: Path) -> _Template:
    """Parse the toy entry format below; reject anything else like the real parser."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].strip() != HEADER:
        raise DraftKingsParseError(f"not a reserved-entry template: {path}")
    auths = []
    mode = "SHOWDOWN"
    for line in lines[1:]:
        mode, contest_id, contest_name, entry_fee, entry_id = line.split(",")
        auths.append(_Auth(contest_id, contest_name, float(entry_fee), entry_id))
    return _Template(mode=_Mode(mode), authorizations=auths)


def _write_entries(path: Path, rows: list[tuple[str, str, str, str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([HEADER] + [",".join(r) for r in rows]) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A synthetic nfl-dfs tree with the module's paths pointed at it."""
    module = _checklist()
    monkeypatch.setattr(module, "parse_entries", _stub_parse_entries)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "RUNS_DIR", tmp_path / "data" / "runs")
    monkeypatch.setattr(module, "STANDINGS_DIR", tmp_path / "data" / "standings")
    monkeypatch.setattr(module, "INBOX_DIR", tmp_path / "data" / "standings" / "inbox")
    # Without these two the tests read the real repo's normalized and settled
    # state, so a contest Ben actually settled would change an unrelated
    # assertion. Isolated here rather than relying on synthetic IDs not colliding.
    monkeypatch.setattr(
        module, "NORMALIZED_DIR", tmp_path / "data" / "standings" / "normalized"
    )
    monkeypatch.setattr(module, "SETTLEMENTS_DIR", tmp_path / "outputs" / "settlements")
    monkeypatch.setattr(
        module, "DISPOSITIONS_PATH", tmp_path / "data" / "standings" / "dispositions.json"
    )
    monkeypatch.setattr(
        module,
        "MARKDOWN_PATH",
        tmp_path / "data" / "standings" / "CONTESTS_AWAITING_STANDINGS.md",
    )
    monkeypatch.setattr(
        module,
        "HTML_PATH",
        tmp_path / "data" / "standings" / "CONTESTS_AWAITING_STANDINGS.html",
    )
    (tmp_path / "data" / "standings" / "inbox").mkdir(parents=True)

    # One contest captured by a dated run snapshot, one that only ever existed
    # as a loose repo-root CSV (the 2026-09-13 DAL@NYG lock-clock case).
    _write_entries(
        tmp_path / "data" / "runs" / "20260910-showdown-sf-lar" / "inputs" / "DKEntries.csv",
        [("SHOWDOWN", "195379585", "NFL Showdown $0.25 Contest (SF vs LAR)", "0.25", "4801")],
    )
    _write_entries(
        tmp_path / "DKEntries_DAL_NYG_REVIEW.csv",
        [("SHOWDOWN", "195520918", "NFL Showdown Winner Take All (DAL @ NYG)", "0.25", "4802")],
    )
    (tmp_path / "DKSalaries.csv").write_text("Position,Name,Salary\nQB,Someone,7000\n", encoding="utf-8")
    return module, tmp_path


def test_discovery_separates_snapshot_from_loose(repo):
    module, _ = repo
    contests = module.discover_entered_contests()
    assert set(contests) == {"195379585", "195520918"}
    assert contests["195379585"].confidence == "snapshot"
    assert contests["195520918"].confidence == "loose"


def test_salary_csv_is_skipped_not_guessed_at(repo):
    module, tmp_path = repo
    assert "DKSalaries.csv" in {p.name for p in module._candidate_csv_paths()}
    assert all("Someone" not in r.contest_name for r in module.discover_entered_contests().values())


def test_evidence_date_comes_from_the_run_id_when_there_is_one(repo):
    module, tmp_path = repo
    snapshot = tmp_path / "data" / "runs" / "20260910-showdown-sf-lar" / "inputs" / "DKEntries.csv"
    assert module._evidence_date_for(snapshot) == "2026-09-10"
    loose = tmp_path / "DKEntries_DAL_NYG_REVIEW.csv"
    assert module._evidence_date_for(loose) != module.UNKNOWN_DATE  # falls back to mtime


def test_newest_evidence_date_wins(repo):
    module, _ = repo
    assert module._newest_date({"2026-09-01", "2026-09-13"}) == "2026-09-13"
    assert module._newest_date({module.UNKNOWN_DATE}) == module.UNKNOWN_DATE


def test_grouping_is_oldest_first_with_unknown_last(repo):
    module, _ = repo
    rows = [
        {"contest_id": "3", "evidence_date": module.UNKNOWN_DATE},
        {"contest_id": "2", "evidence_date": "2026-09-13"},
        {"contest_id": "1", "evidence_date": "2026-09-09"},
    ]
    assert [key for key, _ in module.group_by_evidence_date(rows)] == [
        "2026-09-09",
        "2026-09-13",
        module.UNKNOWN_DATE,
    ]


def test_a_filed_export_drops_the_contest_off_the_pull_list(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.csv").write_text(
        "EntryId,Rank\n1,1\n", encoding="utf-8"
    )
    report = module.build_report()
    statuses = {r["contest_id"]: r["status"] for r in report["contests"]}
    assert statuses == {"195379585": "filed", "195520918": "awaiting"}
    assert report["counts"]["awaiting"] == 1


def test_inbox_file_for_an_unknown_contest_is_named_not_swallowed(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-999888777.csv").write_text(
        "EntryId,Rank\n1,1\n", encoding="utf-8"
    )
    assert module.build_report()["unresolved_inbox_contest_ids"] == ["999888777"]


def test_duplicate_disposition_is_refused_rather_than_overwritten(repo):
    module, _ = repo
    module._mark("195520918", "unrecoverable", "zero bytes on second pull")
    with pytest.raises(module.ChecklistError):
        module._mark("195520918", "placeholder", "changed my mind")
    recorded = json.loads(module.DISPOSITIONS_PATH.read_text(encoding="utf-8"))
    assert recorded["195520918"]["reason"] == "zero bytes on second pull"
    assert [r["status"] for r in module.build_report()["contests"] if r["contest_id"] == "195520918"] == [
        "unrecoverable"
    ]


def test_every_awaiting_contest_gets_a_checkbox_and_its_own_export_link(repo):
    module, _ = repo
    report = module.build_report()
    page = module.render_html(report)
    for row in report["contests"]:
        url = module.DK_EXPORT_URL.format(contest_id=row["contest_id"])
        assert url in page, f"no one-click export for {row['contest_id']}"
    assert page.count('<li class="row">') == report["counts"]["awaiting"]
    assert page.count('type="checkbox"') == report["counts"]["awaiting"]
    assert "progressFill" in page and "boxes[i].checked = true" in page


def test_filed_contests_are_listed_but_not_checkable(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.csv").write_text(
        "EntryId,Rank\n1,1\n", encoding="utf-8"
    )
    report = module.build_report()
    page = module.render_html(report)
    assert page.count('<li class="row">') == 1
    assert "Filed, normalized, settled or dispositioned" in page
    assert "195379585" in page
    # Filed is not normalized. A raw DraftKings export carries no prize column
    # and names its lineups, so it satisfies nothing downstream on its own.
    assert report["counts"]["filed"] == 1
    assert report["counts"]["normalized"] == 0
    assert report["counts"]["settled"] == 0


def test_contest_names_are_escaped(repo):
    module, tmp_path = repo
    _write_entries(
        tmp_path / "DKEntries_XSS.csv",
        [("SHOWDOWN", "195999999", "<script>alert(1)</script>", "0.25", "4803")],
    )
    page = module.render_html(module.build_report())
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_markdown_groups_by_date_and_carries_the_export_url(repo):
    module, _ = repo
    report = module.build_report()
    text = module.render_markdown(report)
    assert "## Awaiting a pull" in text
    dates = [key for key, _ in module.group_by_evidence_date(
        [r for r in report["contests"] if r["status"] == "awaiting"]
    )]
    positions = [text.index(f"### {d} (") for d in dates]
    assert positions == sorted(positions), "markdown sections are not oldest-first"
    assert module.DK_EXPORT_URL.format(contest_id="195379585") in text


def test_main_writes_the_dated_checklist_and_the_stable_copy(repo, capsys):
    module, tmp_path = repo
    assert module.main([]) == 0
    report_date = module.build_report()["report_date"]
    dated = tmp_path / "data" / "standings" / f"standings_pulls_{report_date}.html"
    assert dated.is_file()
    assert module.HTML_PATH.read_text(encoding="utf-8") == dated.read_text(encoding="utf-8")
    assert module.MARKDOWN_PATH.is_file()
    assert "awaiting=2" in capsys.readouterr().out


def test_json_mode_writes_nothing(repo, capsys):
    module, tmp_path = repo
    assert module.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["awaiting"] == 2
    assert not module.MARKDOWN_PATH.exists()
    assert not list((tmp_path / "data" / "standings").glob("*.html"))


# ---------------------------------------------------------------------------
# Q1B: filed, normalized and settled are three different states
# ---------------------------------------------------------------------------


def _normalize(tmp_path: Path, contest_id: str, digest: str = "a" * 64) -> Path:
    destination = tmp_path / "data" / "standings" / "normalized" / contest_id
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{digest}.csv"
    path.write_text("EntryId,Rank,Points,Prize,Lineup\r\n", encoding="utf-8")
    return path


def _settle(tmp_path: Path, contest_id: str, settlement_id: str = "s1") -> Path:
    package = tmp_path / "outputs" / "settlements" / settlement_id
    package.mkdir(parents=True, exist_ok=True)
    (package / "settlement_bundle.json").write_text(
        json.dumps({"contest": {"contest_id": contest_id}}), encoding="utf-8"
    )
    return package


def test_a_raw_export_is_filed_but_not_normalized(repo):
    """The state the checklist collapsed before Q1B.

    A raw DraftKings export carries no prize column and names its lineups, so
    dropping one in the inbox satisfies nothing downstream. Reporting it as the
    same state as a contract artifact is what made the pipeline look finished.
    """
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    counts = module.build_report()["counts"]
    assert (counts["filed"], counts["normalized"], counts["settled"]) == (1, 0, 0)


def test_a_normalized_artifact_outranks_a_raw_export(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    _normalize(tmp_path, "195379585")
    rows = {r["contest_id"]: r["status"] for r in module.build_report()["contests"]}
    assert rows["195379585"] == "normalized"


def test_a_settlement_bundle_outranks_everything(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    _normalize(tmp_path, "195379585")
    _settle(tmp_path, "195379585")
    rows = {r["contest_id"]: r["status"] for r in module.build_report()["contests"]}
    assert rows["195379585"] == "settled"


def test_a_settled_contest_outranks_a_stale_disposition(repo):
    """A contest that actually settled is settled, whatever was recorded earlier.

    Dispositions are recorded when a contest looks unrecoverable. If one later
    settles anyway, the bundle is the fact and the disposition is the stale note.
    """
    module, tmp_path = repo
    module._mark("195379585", "unrecoverable", "export aged out")
    _settle(tmp_path, "195379585")
    rows = {r["contest_id"]: r["status"] for r in module.build_report()["contests"]}
    assert rows["195379585"] == "settled"


def test_a_disposition_outranks_an_unnormalized_raw_export(repo):
    """Ben's ruling wins over the file states it was made in spite of."""
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    module._mark("195379585", "placeholder", "no pre-lock manifest exists for this run")
    rows = {r["contest_id"]: (r["status"], r["disposition_reason"])
            for r in module.build_report()["contests"]}
    assert rows["195379585"] == ("placeholder", "no pre-lock manifest exists for this run")


def test_a_half_written_settlement_package_does_not_count_as_settled(repo):
    """Settled is read out of the bundle, never inferred from a directory name."""
    module, tmp_path = repo
    package = tmp_path / "outputs" / "settlements" / "195379585"
    package.mkdir(parents=True)
    (package / "replay_request.json").write_text("{}", encoding="utf-8")
    counts = module.build_report()["counts"]
    assert counts["settled"] == 0


def test_the_three_states_reach_the_rendered_surfaces(repo):
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    _normalize(tmp_path, "195379585")
    report = module.build_report()
    text = module.render_markdown(report)
    page = module.render_html(report)
    assert "Normalized: **1**" in text
    assert "Settled: **0**" in text
    assert "1 normalized" in page and "0 settled" in page


def test_artifact_presence_is_reported_independently_of_status(repo):
    """A disposition is a ruling about workflow, not a claim the bytes are gone.

    Ben's 18 contests are all dispositioned and all 18 raw exports are safely on
    disk. Collapsing those into one number would report the preserved evidence as
    absent.
    """
    module, tmp_path = repo
    (tmp_path / "data" / "standings" / "inbox" / "contest-standings-195379585.zip").write_bytes(b"raw")
    _normalize(tmp_path, "195379585")
    module._mark("195379585", "placeholder", "no pre-lock manifest exists for this run")
    report = module.build_report()
    row = next(r for r in report["contests"] if r["contest_id"] == "195379585")
    assert row["status"] == "placeholder"
    assert row["raw_export_filed"] is True
    assert row["normalized_artifact"] is True
    assert row["settlement_bundle"] is False
    counts = report["counts"]
    assert counts["dispositioned"] == 1
    assert (counts["raw_exports_filed"], counts["normalized_artifacts"]) == (1, 1)
    assert (counts["filed"], counts["normalized"]) == (0, 0)
    assert "Raw exports on disk: **1**" in module.render_markdown(report)
