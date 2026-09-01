from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs.candidate_families import classify_candidate, coverage_report
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.sources import SourcePolicyError, capture_local_artifact, validate_url_policy


def test_candidate_family_classification(classic_slate) -> None:
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    result = LineupOptimizer(classic_slate).solve(scores)
    assert result.roster is not None
    features = classify_candidate(classic_slate, result.roster)
    assert features.family_labels
    report = coverage_report(classic_slate, [result.roster])
    assert sum(report.counts.values()) >= 2
    assert report.missing_registered_families


def test_source_policy_rejects_scraping_and_unknown_hosts(tmp_path: Path) -> None:
    with pytest.raises(SourcePolicyError, match="prohibited"):
        validate_url_policy("https://www.nfl.com/inactives/")
    with pytest.raises(SourcePolicyError, match="not approved"):
        validate_url_policy("https://example.com/data")
    with pytest.raises(SourcePolicyError, match="explicitly configured"):
        validate_url_policy("https://api.the-odds-api.com/v4/sports", optional_odds_key_configured=False)
    validate_url_policy("https://api.weather.gov/points/39,-77")
    local = tmp_path / "artifact.txt"
    local.write_text("evidence", encoding="utf-8")
    artifact = capture_local_artifact(
        local,
        source="OPERATOR",
        license_decision="OPERATOR_SUPPLIED",
        parser_version="text_v1",
    )
    assert artifact.byte_count == 8
    assert len(artifact.sha256) == 64
