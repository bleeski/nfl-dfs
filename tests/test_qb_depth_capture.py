"""Session 53 (R36): `run-slate` captures the quarterback depth package from frozen depth-chart bytes.

Every chart here is synthetic. The module is the script's logic moved into `src/`, so the
script's own tests (`tests/test_qb_depth_roles.py`) keep passing and one test here pins the
two to the same bytes. A capture never raises: each failure is a named limitation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nfl_dfs import qb_depth_capture as capture
from nfl_dfs.qb_depth_roles import DEPTH_CHART_COLUMNS, resolve_qb_depth_roles

from . import test_qb_depth_roles as depth

URI = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv"


def _chart(tmp_path, rows=depth._CHART_ROWS, **kwargs):
    path = depth._depth_chart_file(tmp_path, rows, **kwargs)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _capture(tmp_path, *, rows=depth._CHART_ROWS, as_of=depth.AS_OF, **kwargs):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _slate, _model, _contract, _splits = depth._setup(tmp_path)
    path, digest = _chart(tmp_path, rows, **kwargs)
    return capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv",
        depth_chart=(path, digest, URI),
        as_of=as_of,
        out_dir=tmp_path / "qb_depth",
    )


# --------------------------------------------------------------------------- #
# The reader
# --------------------------------------------------------------------------- #


def test_the_streaming_reader_keeps_only_quarterbacks_and_the_digest_of_every_byte(tmp_path):
    path, digest = _chart(tmp_path)
    rows, _stamps, read_digest = capture.read_quarterback_rows(path)
    assert read_digest == digest
    assert rows and {row["pos_abb"] for row in rows} == {"QB"}
    # The chart also holds a wide receiver; the full reader keeps him, this one does not.
    everyone, _ = capture.read_depth_chart(path)
    assert len(everyone) > len(rows)


def test_the_streaming_reader_refuses_a_chart_whose_columns_changed(tmp_path):
    path = depth._write_csv(tmp_path / "chart.csv", ("dt", "team"), [["2026-09-14T00:00:00Z", "KC"]])
    with pytest.raises(capture.ProducerError):
        capture.read_quarterback_rows(path)


# --------------------------------------------------------------------------- #
# The locator
# --------------------------------------------------------------------------- #


def test_the_locator_finds_the_chart_in_a_proposal_manifest_and_in_a_frozen_package(tmp_path):
    raw = tmp_path / "proposal" / "raw"
    raw.mkdir(parents=True)
    chart = raw / "abc.csv"
    chart.write_bytes(b"x\n")
    (tmp_path / "proposal" / "source_manifest.json").write_text(
        json.dumps({"artifacts": [{"name": "depth_charts", "relative_path": "raw/abc.csv",
                                   "sha256": "abc", "source_uri": URI}]}),
        encoding="utf-8",
    )
    assert capture.locate_frozen_depth_chart(proposal_dir=tmp_path / "proposal") == (chart.resolve(), "abc", URI)

    frozen = tmp_path / "frozen"
    (frozen / "raw").mkdir(parents=True)
    (frozen / "raw" / "def.csv").write_bytes(b"y\n")
    (frozen / "prior_package.json").write_text(
        json.dumps({"season": 2026, "frozen_sources": {"depth_charts": "def"}}), encoding="utf-8"
    )
    path, digest, uri = capture.locate_frozen_depth_chart(package_dir=frozen)
    assert (path.name, digest, uri) == ("def.csv", "def", capture.depth_chart_url(2026))


def test_the_locator_says_none_when_no_chart_was_frozen(tmp_path):
    (tmp_path / "proposal").mkdir()
    assert capture.locate_frozen_depth_chart(proposal_dir=tmp_path / "proposal") is None
    assert capture.locate_frozen_depth_chart(package_dir=tmp_path / "nowhere") is None
    assert capture.locate_frozen_depth_chart() is None


# --------------------------------------------------------------------------- #
# The capture
# --------------------------------------------------------------------------- #


def test_a_captured_package_is_accepted_by_the_resolver_and_names_the_starter(tmp_path):
    outcome = _capture(tmp_path)
    assert outcome.captured and outcome.status == "CAPTURED" and outcome.limitation is None
    (tmp_path / "again").mkdir()
    slate, model, contract, _splits = depth._setup(tmp_path / "again")
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=outcome.package, as_of=depth.AS_OF
    )
    assert resolution.report["starters_by_team"]["KC"] == depth._person(slate, "KC Starter QB")
    assert outcome.as_report()["package"] == str(outcome.package)


def test_the_run_time_capture_and_the_script_write_the_same_package_bytes(tmp_path):
    outcome = _capture(tmp_path / "run")
    scripted = tmp_path / "script"
    path, _digest = _chart(tmp_path / "run")
    assert depth._run_producer([
        "--salaries", str(tmp_path / "run" / "DKSalaries.csv"),
        "--capture", str(path), "--source-uri", URI,
        "--as-of", depth.AS_OF.isoformat(), "--out-dir", str(scripted),
    ]) == 0
    assert outcome.package.read_bytes() == (scripted / "qb_depth_roles.json").read_bytes()


def test_the_capture_is_deterministic(tmp_path):
    first = _capture(tmp_path / "one")
    second = _capture(tmp_path / "two")
    assert first.package.read_bytes() == second.package.read_bytes()


def test_a_snapshot_older_than_its_window_is_named_stale_and_no_package_is_written(tmp_path):
    outcome = _capture(tmp_path, observed=depth.AS_OF - timedelta(hours=40))
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_STALE
    assert outcome.limitation.startswith("QB_DEPTH_CAPTURE_STALE:")
    assert not (tmp_path / "qb_depth" / "qb_depth_roles.json").exists()


def test_a_quarterback_draftkings_does_not_list_leaves_that_team_undeclared_by_name(tmp_path):
    """Edited by Session 63, named in the changelog (was `..._is_refused_by_name`).

    Until then one team's unmatched quarterback refused the whole package. The capture now builds each
    team on its own, so Kansas City is named here and Denver is still declared.
    """

    rows = depth._CHART_ROWS + (("KC", "Somebody Else", "00-0099999", "QB", "Quarterback", 3),)
    outcome = _capture(tmp_path, rows=rows)
    assert outcome.captured and outcome.declared_teams == ("DEN",)
    assert list(outcome.undeclared_teams) == ["KC"]
    assert "does not list him" in outcome.undeclared_teams["KC"]


def test_a_snapshot_from_the_runs_future_is_never_the_one_read(tmp_path):
    """Edited by Session 63, named in the changelog (was `test_a_chart_from_the_runs_future_is_refused`).

    The fixture also writes an older snapshot with the ranks reversed. The old expectation (a refusal) held
    only because Denver's older snapshot has no rank-1 quarterback, which refused the whole package. The
    claim worth keeping is that the snapshot read is the latest at or before the run, never tomorrow's; the
    refusal when every snapshot is from the future is the next test.
    """

    outcome = _capture(tmp_path, observed=depth.AS_OF + timedelta(days=1))
    assert outcome.observed_at == depth.AS_OF - timedelta(days=1)
    assert "DEN" in outcome.undeclared_teams and "no rank-1 quarterback" in outcome.undeclared_teams["DEN"]


def test_a_chart_whose_every_snapshot_is_from_the_runs_future_is_refused(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    depth._setup(tmp_path)
    future = (depth.AS_OF + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    row = [future, "KC", "KC Starter QB", "", "00-0033873", "16", "3WR 1TE", "9", "Quarterback", "QB", "9", "1"]
    path = depth._write_csv(tmp_path / "depth_charts_2026.csv", DEPTH_CHART_COLUMNS, [row])
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv",
        depth_chart=(path, hashlib.sha256(path.read_bytes()).hexdigest(), URI),
        as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth",
    )
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED
    assert "later than" in outcome.detail


def test_an_absent_chart_is_named_unavailable(tmp_path):
    depth._setup(tmp_path)
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=None, as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth"
    )
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_UNAVAILABLE
    missing = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv",
        depth_chart=(Path(tmp_path / "gone.csv"), "00", URI),
        as_of=depth.AS_OF,
        out_dir=tmp_path / "qb_depth",
    )
    assert missing.status == capture.QB_DEPTH_CAPTURE_UNAVAILABLE


def test_a_chart_whose_bytes_no_longer_match_their_hash_is_refused(tmp_path):
    depth._setup(tmp_path)
    path, _digest = _chart(tmp_path)
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv",
        depth_chart=(path, "0" * 64, URI),
        as_of=depth.AS_OF,
        out_dir=tmp_path / "qb_depth",
    )
    assert outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED and "hash" in outcome.detail


# --------------------------------------------------------------------------- #
# Review findings (2026-10-02): the reader matches the script, and a capture never raises
# --------------------------------------------------------------------------- #


def test_the_snapshot_is_picked_from_every_row_not_only_the_quarterback_rows(tmp_path):
    # A newer snapshot holding only a wide receiver: the script path (whole file) picks it and
    # finds no quarterback in it, so the run path must refuse the same way, not fall back to an
    # older snapshot's order.
    newer = depth.OBSERVED + timedelta(hours=2)
    path, digest = _chart(tmp_path)
    with path.open("ab") as handle:
        handle.write(
            (newer.isoformat().replace("+00:00", "Z")
             + ",KC,KC Alpha WR,,00-0031111,16,3WR 1TE,9,Wide Receiver,WR,9,1\n").encode("utf-8")
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _slate, _model, _contract, _splits = depth._setup(tmp_path)
    rows, stamps, _ = capture.read_quarterback_rows(path)
    assert newer in stamps and all(row["pos_abb"] == "QB" for row in rows)
    whole, _digest = capture.read_depth_chart(path)
    assert capture.pick_snapshot(stamps, as_of=depth.AS_OF, observed_at=None) == capture.select_snapshot(
        whole, as_of=depth.AS_OF, observed_at=None
    ) == newer
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=(path, digest, URI),
        as_of=depth.AS_OF + timedelta(hours=3), out_dir=tmp_path / "qb_depth",
    )
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED


def test_a_chart_that_changes_while_it_is_read_is_refused(tmp_path, monkeypatch):
    path, _digest = _chart(tmp_path)
    real = capture._file_digest
    calls = []

    def changing(target):
        calls.append(target)
        return real(target) if len(calls) == 1 else "f" * 64

    monkeypatch.setattr(capture, "_file_digest", changing)
    with pytest.raises(capture.ProducerError, match="changed while it was being read"):
        capture.read_quarterback_rows(path)


@pytest.mark.parametrize(
    "boom", [__import__("csv").Error("field larger than field limit"), KeyError("relative_path"),
             AttributeError("'list' object has no attribute 'get'"), RuntimeError("anything")]
)
def test_nothing_a_capture_hits_can_raise_out_of_it(tmp_path, monkeypatch, boom):
    depth._setup(tmp_path)
    path, digest = _chart(tmp_path)

    def explode(*_args, **_kwargs):
        raise boom

    monkeypatch.setattr(capture, "read_quarterback_rows", explode)
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=(path, digest, URI),
        as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth",
    )
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED
    assert type(boom).__name__ in outcome.detail


@pytest.mark.parametrize("manifest", [{"artifacts": [{"name": "depth_charts"}]}, [1, 2], {"artifacts": 3}])
def test_a_malformed_frozen_manifest_is_a_named_refusal_not_an_exception(tmp_path, manifest):
    depth._setup(tmp_path)
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    (proposal / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", proposal_dir=proposal, as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth"
    )
    assert not outcome.captured
    assert outcome.status in {capture.QB_DEPTH_CAPTURE_REFUSED, capture.QB_DEPTH_CAPTURE_UNAVAILABLE}


def test_a_team_subset_declares_only_those_teams(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, _splits = depth._setup(tmp_path)
    path, digest = _chart(tmp_path)
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=(path, digest, URI),
        as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth_without_KC", teams=("DEN",),
    )
    assert outcome.captured
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=outcome.package, as_of=depth.AS_OF
    )
    assert set(resolution.report["starters_by_team"]) == {"DEN"}


# --------------------------------------------------------------------------- #
# Session 63: a team the chart cannot build never loses the rest
# --------------------------------------------------------------------------- #

_KC_STARTER = ("KC", "KC Starter QB", "00-0033873", "QB", "Quarterback", 1)
_KC_BACKUP = ("KC", "KC Backup QB", "00-0036945", "QB", "Quarterback", 2)
_KC_WR = ("KC", "KC Alpha WR", "00-0031111", "WR", "Wide Receiver", 1)
_DEN = ("DEN", "DEN Starter QB", "00-0034857", "QB", "Quarterback", 1)
_THIRD_QB_POOL = depth._POOL + (("KC", "QB", "KC Third QB", "", 4500),)
# "Jr" is a generational suffix `normalize_person_name` drops, so both KC rows normalize to one name.
_AMBIGUOUS_POOL = depth._POOL + (("KC", "QB", "KC Starter QB Jr", "", 4000),)


class _TextRank(int):
    """A rank the fixture can still do arithmetic on, which the chart file prints as text."""

    def __str__(self) -> str:
        return "first"


def _capture_pool(tmp_path, pool, rows, **kwargs):
    """A capture over a slate file alone (no model): the chart-level checks need nothing more."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    depth._slate(tmp_path, pool=pool)
    path, digest = _chart(tmp_path, rows)
    return capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=(path, digest, URI),
        as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth", **kwargs,
    )


@pytest.mark.parametrize(
    ("pool", "kc_rows", "expected"),
    [
        pytest.param(depth._POOL, (_KC_WR,), "lists no quarterback for KC", id="no-quarterback-rows"),
        pytest.param(
            depth._POOL,
            (_KC_STARTER, _KC_BACKUP, ("KC", "Somebody Else", "00-0099999", "QB", "Quarterback", 3)),
            "does not list him", id="not-on-draftkings",
        ),
        pytest.param(_AMBIGUOUS_POOL, (_KC_STARTER, _KC_BACKUP), "matches 2 DraftKings people", id="ambiguous-name"),
        pytest.param(
            depth._POOL, (_KC_BACKUP, ("KC", "KC Starter QB", "00-0033873", "QB", "Quarterback", 3)),
            "no rank-1 quarterback", id="no-rank-one",
        ),
        pytest.param(
            depth._POOL, (_KC_STARTER, ("KC", "KC Backup QB", "00-0036945", "QB", "Quarterback", 1)),
            "QB_DEPTH_EXCERPT_DUPLICATE_RANK", id="two-rank-ones",
        ),
        pytest.param(
            _THIRD_QB_POOL,
            (_KC_STARTER, _KC_BACKUP, ("KC", "KC Third QB", "00-0037777", "QB", "Quarterback", 2)),
            "QB_DEPTH_EXCERPT_DUPLICATE_RANK", id="duplicate-rank",
        ),
        pytest.param(
            depth._POOL, (("KC", "KC Starter QB", "00-0033873", "QB", "Quarterback", _TextRank(1)),),
            "ValueError", id="non-integer-rank",
        ),
        pytest.param(
            depth._POOL, (_KC_STARTER, ("KC", "KC Starter QB", "00-0033873", "QB", "Quarterback", 2)),
            "a person may appear once", id="one-person-at-two-ranks",
        ),
    ],
)
def test_one_teams_chart_failure_names_that_team_and_declares_the_other(tmp_path, pool, kc_rows, expected):
    outcome = _capture_pool(tmp_path, pool, (*kc_rows, _DEN))
    assert outcome.captured and outcome.status == "CAPTURED"
    assert outcome.declared_teams == ("DEN",)
    assert list(outcome.undeclared_teams) == ["KC"]
    reason = outcome.undeclared_teams["KC"]
    assert expected in reason and "\n" not in reason and len(reason) <= 200
    report = outcome.as_report()
    assert report["declared_teams"] == ["DEN"] and report["undeclared_teams"] == {"KC": reason}
    package = json.loads(outcome.package.read_text(encoding="utf-8"))
    assert [item["team"] for item in package["declarations"]] == ["DEN"] and len(package["sources"]) == 1
    # No file is written for a team that was not declared: every source on disk is in the manifest.
    assert [path.name for path in (outcome.package.parent / "sources").glob("*.csv")] == [
        f"{package['sources'][0]['sha256']}.csv"
    ]


def test_a_partial_package_is_accepted_by_the_resolver_and_the_dropped_team_stays_undeclared(tmp_path):
    slate, model, contract, _splits = depth._setup(tmp_path)
    path, digest = _chart(tmp_path, (_KC_WR, _DEN))
    outcome = capture.capture_for_run(
        salaries=tmp_path / "DKSalaries.csv", depth_chart=(path, digest, URI),
        as_of=depth.AS_OF, out_dir=tmp_path / "qb_depth",
    )
    assert outcome.captured and list(outcome.undeclared_teams) == ["KC"]
    resolution = resolve_qb_depth_roles(slate, model, contract, evidence_path=outcome.package, as_of=depth.AS_OF)
    assert resolution.report["starters_by_team"] == {"DEN": depth._person(slate, "DEN Starter QB")}


def test_every_team_failing_refuses_the_capture_writes_nothing_and_names_each(tmp_path):
    outcome = _capture_pool(tmp_path, depth._POOL, (_KC_WR,))
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED
    assert outcome.declared_teams == () and sorted(outcome.undeclared_teams) == ["DEN", "KC"]
    assert "2 teams" in outcome.detail and outcome.limitation.startswith("QB_DEPTH_CAPTURE_REFUSED:")
    assert outcome.as_report()["undeclared_teams"] == dict(sorted(outcome.undeclared_teams.items()))
    out = tmp_path / "qb_depth"
    assert not out.exists() or not list(out.rglob("*"))


def test_the_requested_teams_are_the_only_ones_a_failure_can_name(tmp_path):
    # `teams=` is the selection-time rebuild's list: a team left out of it is not a chart failure.
    outcome = _capture_pool(tmp_path, depth._POOL, (_KC_WR, _DEN), teams=("DEN",))
    assert outcome.captured and outcome.declared_teams == ("DEN",) and outcome.undeclared_teams == {}


def test_the_strict_producer_raises_the_first_failing_team_and_writes_nothing(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    depth._slate(tmp_path)
    path, _digest = _chart(tmp_path, (_DEN, _KC_WR))
    rows, _stamps, upstream = capture.read_quarterback_rows(path)
    out = tmp_path / "strict"
    with pytest.raises(capture.ProducerError, match="lists no quarterback for KC"):
        capture.build_package(
            tmp_path / "DKSalaries.csv", rows, upstream_sha256=upstream, source_uri=URI,
            observed_at=depth.OBSERVED, as_of=depth.AS_OF, out_dir=out,
        )
    # Denver sorts first and was built before Kansas City failed. Before Session 63 its capture file stayed.
    assert not out.exists() or not list(out.rglob("*"))


def test_a_partial_package_is_deterministic_down_to_its_bytes(tmp_path):
    first = _capture_pool(tmp_path / "one", depth._POOL, (_KC_WR, _DEN))
    second = _capture_pool(tmp_path / "two", depth._POOL, (_KC_WR, _DEN))
    assert first.captured and first.package.read_bytes() == second.package.read_bytes()
    assert first.undeclared_teams == second.undeclared_teams == {"KC": first.undeclared_teams["KC"]}
    sources = lambda outcome: sorted(path.read_bytes() for path in (outcome.package.parent / "sources").glob("*.csv"))  # noqa: E731
    assert sources(first) == sources(second) and len(sources(first)) == 1


def test_the_strict_producer_names_a_slate_with_no_quarterback_team_as_a_producer_error(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    depth._slate(tmp_path, pool=tuple(row for row in depth._POOL if row[1] != "QB"))
    path, _digest = _chart(tmp_path, (_DEN,))
    rows, _stamps, upstream = capture.read_quarterback_rows(path)
    with pytest.raises(capture.ProducerError, match="no quarterback team"):
        capture.build_package(
            tmp_path / "DKSalaries.csv", rows, upstream_sha256=upstream, source_uri=URI,
            observed_at=depth.OBSERVED, as_of=depth.AS_OF, out_dir=tmp_path / "strict",
        )


def test_the_strict_producer_refuses_a_conflicted_chart_as_a_producer_error(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    depth._slate(tmp_path)
    conflicted = ("KC", "KC Backup QB", "00-0036945", "QB", "Quarterback", 1)
    path, _digest = _chart(tmp_path, (_KC_STARTER, conflicted, _DEN))
    rows, _stamps, upstream = capture.read_quarterback_rows(path)
    with pytest.raises(capture.ProducerError, match="DUPLICATE_RANK"):
        capture.build_package(
            tmp_path / "DKSalaries.csv", rows, upstream_sha256=upstream, source_uri=URI,
            observed_at=depth.OBSERVED, as_of=depth.AS_OF, out_dir=tmp_path / "strict",
        )


WEEK_4 = Path(__file__).resolve().parents[1] / "data" / "inbox" / "slates" / "wk4-classic-2026-10-04"


def test_a_week_4_shaped_chart_declares_the_23_teams_it_can_and_names_lar(tmp_path):
    """The committed Week 4 Classic slate: 24 teams, and a chart that listed no LAR quarterback.

    The chart is rebuilt from the 23 verbatim excerpts the committed package carries (the real 51 MB chart
    is not in the repository), so the per-team result must equal what Ben's session built by hand with
    `--teams` naming the other 23. Only the digest of the whole chart differs, and that is not compared.
    """

    committed = json.loads((WEEK_4 / "qb_depth" / "qb_depth_roles.json").read_text(encoding="utf-8"))
    body: list[list[str]] = []
    for source in committed["sources"]:
        excerpt = list(csv.reader(io.StringIO(source["supporting_excerpt"])))
        assert tuple(excerpt[0]) == DEPTH_CHART_COLUMNS
        body.extend(excerpt[1:])
    chart = depth._write_csv(tmp_path / "depth_charts_2026.csv", DEPTH_CHART_COLUMNS, body)
    digest = hashlib.sha256(chart.read_bytes()).hexdigest()
    first = committed["sources"][0]
    outcome = capture.capture_for_run(
        salaries=WEEK_4 / "DKSalaries.csv", depth_chart=(chart, digest, first["source_uri"]),
        as_of=datetime.fromisoformat(first["captured_at"]), out_dir=tmp_path / "qb_depth",
    )
    teams = sorted(item["team"] for item in committed["declarations"])
    assert len(teams) == 23 and outcome.captured and list(outcome.declared_teams) == teams
    assert list(outcome.undeclared_teams) == ["LAR"]
    assert "lists no quarterback for LAR" in outcome.undeclared_teams["LAR"]
    built = json.loads(outcome.package.read_text(encoding="utf-8"))
    assert built["declarations"] == committed["declarations"]
    without_upstream = lambda source: {key: value for key, value in source.items() if key != "upstream_sha256"}  # noqa: E731
    assert [without_upstream(item) for item in built["sources"]] == [without_upstream(item) for item in committed["sources"]]
    assert built["salary_sha256"] == committed["salary_sha256"] and built["game_ids"] == committed["game_ids"]
