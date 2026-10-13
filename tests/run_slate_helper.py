"""A real Showdown `run-slate` on the shared synthetic pre-lock sources, for any test that needs one (Session 72b).

Lifted from `tests/test_concentration_run_slate.py::_run` (Session 56), which now imports it, so a test that needs a real
run imports this module rather than another test module's private function. Not collected: the name has no `test_`
prefix. Its own building blocks still come from the sibling modules they always lived in.

`real_projection=True` swaps the projection stub for the real producer (`projection.build_projection_package`). The stub
writes a ledger `evidence.validate_source_ledger` refuses and keeps its CSVs outside the run folder; the real producer
writes `team_projections.csv`, `player_opportunities.csv` and an `nfl_source_ledger_v2` that binds both by hash, in the
run's own `projected/` folder. It is fed source payloads built for the run's own salary file
(`tests/test_projection_producer._payloads`), their timestamps moved to the run's clock, and distinct market numbers per
team so a swapped team, or a total read as a spread, cannot pass a test unnoticed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import cli
from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_file

from .test_deadline_controller import FakeClock, _clocked
from .test_prior_review_profile import AS_OF, _attachments, _cowork_args, _prepared_run
from .test_prior_selection import _entries_bytes

ENTRY_COUNT = 20
# Market numbers the real projection is fed: (total, spread) for a game's away team, then its home team.
MARKET_AWAY = (46.5, 3.5)
MARKET_HOME = (43.5, -3.5)


def entry_ids(count: int) -> tuple[str, ...]:
    return tuple(str(900000001 + index) for index in range(count))


def run_paths(tmp_path: Path, run_id: str) -> dict[str, Path]:
    """The salary file and entries template a run read, its output folder and its run-data folder."""

    return {
        "salaries": tmp_path / "DKSalaries.csv",
        "entries": tmp_path / "DKEntries.csv",
        "run_dir": tmp_path / "outputs" / run_id,
        "run_data": tmp_path / "runs" / run_id,
    }


def thesis_policy(slate, entry_ids_, folder: Path) -> Path:
    """A v4 policy of three theses over the synthetic pool (Session 23c's `_portfolio_controls`), for `policy=`."""

    from nfl_dfs.portfolio_policy import POLICY_SCHEMA_VERSION_V4, portfolio_policy_template

    from .test_showdown_thesis_run_slate import _portfolio_controls

    path = folder / "policy" / "portfolio.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(portfolio_policy_template(
        slate, list(entry_ids_), controls=_portfolio_controls(slate), schema_version=POLICY_SCHEMA_VERSION_V4)).encode())
    return path


def _real_project(tmp_path: Path):
    """A `project` callable: the real producer, fed payloads for the run's salary file at the run's clock."""

    from nfl_dfs.projection import build_projection_package

    from .test_projection_producer import CAPTURED, EXPIRES, OBSERVED, _payloads, _write_json

    def project(**kwargs):
        as_of = datetime.fromisoformat(str(kwargs["as_of"]).replace("Z", "+00:00"))
        moved = {
            OBSERVED: (as_of - timedelta(hours=2)).isoformat(),
            CAPTURED: (as_of - timedelta(hours=1, minutes=55)).isoformat(),
            EXPIRES: (as_of + timedelta(hours=24)).isoformat(),
        }
        salary = Path(kwargs["salaries"])
        slate = parse_salaries(salary)
        home = {game.home_team for game in slate.games}
        sources = tmp_path / "real-sources" / Path(kwargs["output_dir"]).parent.name
        sources.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, payload in zip(("team_source", "player_source", "identity_map"), _payloads(salary)):
            if name == "team_source":
                for record in payload["records"]:
                    team = record["provider_team_id"].removeprefix("TEAM-")
                    record["market_total"], record["market_spread"] = MARKET_HOME if team in home else MARKET_AWAY
            text = json.dumps(payload, sort_keys=True)
            for old, new in moved.items():
                text = text.replace(old, new)
            paths[name] = _write_json(sources / f"{name}.json", json.loads(text))
        return build_projection_package(
            salaries=salary,
            salary_sha256=kwargs["salary_sha256"],
            team_source=paths["team_source"],
            team_source_sha256=sha256_file(paths["team_source"]),
            player_source=paths["player_source"],
            player_source_sha256=sha256_file(paths["player_source"]),
            identity_map=paths["identity_map"],
            identity_map_sha256=sha256_file(paths["identity_map"]),
            as_of=kwargs["as_of"],
            output_dir=kwargs["output_dir"],
        )

    return project


def run_showdown_slate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, run_id: str = "concentration",
                       entries: int = ENTRY_COUNT, policy=None, before_review=None, real_projection: bool = False,
                       window: float | None = None, **overrides):
    """A Showdown `run-slate` over `entries` template rows on the shared synthetic pre-lock sources.

    `policy` is a callable `(slate, entry_ids, folder) -> Path` that writes a supplied policy; none supplies none.
    `before_review` is called with the review's keyword arguments just before each attempt runs. `window` puts the run on
    a clock only the test moves, `window` seconds before the improvement stops (Session 56's short-deadline cases: 40 s
    ends at rung 4, a negative window ships the baseline alone). Each call needs its own `tmp_path`: the export refuses
    an output folder that already exists.
    """

    from nfl_dfs import prior_review as prior_review_module

    if window is not None:
        _clocked(monkeypatch, FakeClock())
        overrides.update(as_of=AS_OF.isoformat(),
                         delivery_deadline_utc=(AS_OF + timedelta(minutes=5, seconds=window)).isoformat())
    tmp_path.mkdir(parents=True, exist_ok=True)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
    if real_projection:
        project = _real_project(tmp_path)
    entry_path.write_bytes(_entries_bytes(entry_ids(entries)))
    attachments = _attachments(tmp_path, salary_path, entry_path)
    slate = parse_salaries(salary_path)
    if policy is not None:
        overrides["portfolio_policy_json"] = str(policy(slate, entry_ids(entries), tmp_path))
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review

    def review(**kwargs):
        if before_review is not None:
            before_review(kwargs)
        return real(**kwargs, project=project)

    monkeypatch.setattr(cli, "run_prior_review", review)
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id=run_id, prior_package_dir=str(package_dir), **overrides))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, root, slate
