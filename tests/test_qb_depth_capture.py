"""Session 53 (R36): `run-slate` captures the quarterback depth package from frozen depth-chart bytes.

Every chart here is synthetic. The module is the script's logic moved into `src/`, so the
script's own tests (`tests/test_qb_depth_roles.py`) keep passing and one test here pins the
two to the same bytes. A capture never raises: each failure is a named limitation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
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


def test_a_quarterback_draftkings_does_not_list_is_refused_by_name(tmp_path):
    rows = depth._CHART_ROWS + (("KC", "Somebody Else", "00-0099999", "QB", "Quarterback", 3),)
    outcome = _capture(tmp_path, rows=rows)
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED
    assert "does not list him" in outcome.detail


def test_a_chart_from_the_runs_future_is_refused(tmp_path):
    outcome = _capture(tmp_path, observed=depth.AS_OF + timedelta(days=1))
    assert not outcome.captured and outcome.status == capture.QB_DEPTH_CAPTURE_REFUSED


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
