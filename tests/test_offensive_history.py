"""SD2 regressions using tiny, explicitly synthetic historical captures."""

from decimal import Decimal

import pytest

from nfl_dfs import priors
from .test_priors_adapter import package, _player_stats_bytes, _PLAYER_STAT_COLUMNS


def _records(package, tmp_path, mutate=lambda rows: rows):
    source = tmp_path / "synthetic-player-history.csv"
    source.write_bytes(_player_stats_bytes())
    rows = mutate(priors.read_csv_rows(source, _PLAYER_STAT_COLUMNS, label="synthetic"))
    resolved = {p.underlying_id: (p, p.provider_player_id) for p in package["proposals"]}
    return priors.build_player_records(
        package["slate"], resolved, crosswalk=package["crosswalk"],
        player_stat_rows=rows, snap_rows=[], prior_season=2025, season=2026,
    )


def test_missing_history_is_not_observed_zero(package, tmp_path):
    def missing(rows):
        return [r for r in rows if r["player_id"] != "00-0039337"]
    records, mappings, report = _records(package, tmp_path, missing)
    record = next(r for r in records if r["provider_player_id"] == "00-0039337")
    person = next(m["underlying_id"] for m in mappings if m["provider_player_id"] == "00-0039337")
    assert record["target_weight"] == 0
    assert record["evidence_state"] == "UNKNOWN"
    assert report["offensive_history_by_person"][person]["state"] == "MISSING_HISTORY"


def test_transfer_carries_his_own_old_team_share_as_an_unverified_prior(package, tmp_path):
    # SD2 (2026-09-09) zeroed a transfer because his old-team counts must not
    # enter the current team's denominator raw. 2026-09-10 (R17): his *share* of
    # his old team's volume is carried as a pseudo-count into the current pool's
    # normalization, flagged, with EVIDENCE_STATE=UNKNOWN. It is his own
    # source-bound rate, not an invented number, and not a current-team role.
    def transfer(rows):
        return [{**r, "team": "DEN"} if r["player_id"] == "00-0039337" else r for r in rows]
    baseline, _b_mappings, _b_report = _records(package, tmp_path)
    records, mappings, report = _records(package, tmp_path, transfer)
    record = next(r for r in records if r["provider_player_id"] == "00-0039337")
    before = next(r for r in baseline if r["provider_player_id"] == "00-0039337")
    person = next(m["underlying_id"] for m in mappings if m["provider_player_id"] == "00-0039337")
    history = report["offensive_history_by_person"][person]
    assert history["state"] == "CURRENT_ROLE_UNKNOWN" and history["incompatible_transfer"] is True
    prior = history["transfer_prior"]
    assert prior["basis"] == "OWN_OLD_TEAM_SHARE" and prior["old_teams"] == ["DEN"]
    assert prior["basis_version"] == priors.TRANSFER_PRIOR_VERSION
    assert Decimal(prior["own_old_share"]["targets"]) > 0
    assert set(prior["pseudo_counts"]) == set(priors._RAW_COLUMNS)
    assert Decimal("0") < record["target_weight"] < before["target_weight"]
    assert record["evidence_state"] == "UNKNOWN"
    # The current team's target shares still sum to one, incumbents scaled down.
    team = next(m["team"] for m in mappings if m["provider_player_id"] == "00-0039337")
    members = {m["provider_player_id"] for m in mappings if m["team"] == team and m["position"] in {"RB", "WR", "TE"}}
    total = sum(r["target_weight"] for r in records if r["provider_player_id"] in members)
    assert abs(total - Decimal("1")) < Decimal("0.00001")


def test_transfer_with_zero_old_team_production_gets_a_zero_basis(package, tmp_path):
    def transfer_zero(rows):
        return [{**r, "team": "DEN", **{c: "0" for c in priors._RAW_COLUMNS}} if r["player_id"] == "00-0039337" else r for r in rows]
    records, mappings, report = _records(package, tmp_path, transfer_zero)
    record = next(r for r in records if r["provider_player_id"] == "00-0039337")
    person = next(m["underlying_id"] for m in mappings if m["provider_player_id"] == "00-0039337")
    assert report["offensive_history_by_person"][person]["transfer_prior"]["basis"] == "OWN_OLD_TEAM_SHARE_ZERO"
    assert record["target_weight"] == 0 and record["evidence_state"] == "UNKNOWN"


def test_observed_zero_has_its_own_machine_readable_basis(package, tmp_path):
    def zero(rows):
        return [{**r, **{c: "0" for c in priors._RAW_COLUMNS}} if r["player_id"] == "00-0039337" else r for r in rows]
    records, mappings, report = _records(package, tmp_path, zero)
    record = next(r for r in records if r["provider_player_id"] == "00-0039337")
    assert record["target_weight"] == Decimal("0")
    person = next(m["underlying_id"] for m in mappings if m["provider_player_id"] == "00-0039337")
    assert report["offensive_history_by_person"][person]["state"] == "OBSERVED_HISTORY_ZERO"


def test_blank_historical_count_is_missing_not_observed_zero(package, tmp_path):
    def blank(rows):
        return [{**r, "targets": ""} if r["player_id"] == "00-0039337" else r for r in rows]
    records, mappings, report = _records(package, tmp_path, blank)
    assert report["offensive_history_by_person"]["LAR|WR|Puka Nacua"]["state"] == "MISSING_HISTORY"
    record = next(r for r in records if r["provider_player_id"] == "00-0039337")
    assert record["target_weight"] == 0 and record["evidence_state"] == "UNKNOWN"


def test_sd2_unknown_projection_path_does_not_extend_classic(tmp_path):
    import json
    from nfl_dfs.projection import build_projection_package, ProjectionBuildError
    from .test_projection_producer import _prepare, _rewrite_input, CLASSIC_SALARY
    args = _prepare(tmp_path, CLASSIC_SALARY)
    payload = json.loads(args["player_source"].read_text())
    identity = json.loads(args["identity_map"].read_text())
    payload["metadata"]["coverage"].update(
        adapter_version="nflverse_prior_adapter_v2",
        offensive_history_by_person={m["underlying_id"]: {"state": "MISSING_HISTORY"} for m in identity["player_mappings"]},
    )
    payload["records"][0]["evidence_state"] = "UNKNOWN"
    _rewrite_input(args, "player_source", payload)
    with pytest.raises(ProjectionBuildError, match="PLAYER_EVIDENCE_NOT_PASS"):
        build_projection_package(**args)
