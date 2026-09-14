"""SD1 current-role contract, conservation, replay and failure coverage."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import cli
from nfl_dfs.cowork import CoworkInputError, CoworkRunRequest
from nfl_dfs.hashing import sha256_file
from nfl_dfs.kicker_roles import (
    KICKER_ROLE_ALLOCATION_VERSION,
    KICKER_ROLE_EVIDENCE_VERSION,
    KICKER_ROLE_SHARE_TOLERANCE,
    KickerRoleError,
    resolve_kicker_roles,
    verify_kicker_role_resolution,
)
from nfl_dfs.participation import build_participation_contract, redistribute_opportunity
from nfl_dfs.selection import select_prior_lineups

from .test_prior_selection import _prepared


AS_OF = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)


def _two_kicker_setup(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    original = next(
        player for player in model.players if player.team == "NE" and player.position == "K"
    )
    backup_person = "NE|K|Backup Kicker"
    backup = replace(
        original,
        underlying_id=backup_person,
        source_dk_id="99000002",
        role_capacity=0.0,
    )
    originals = {
        player.role: player
        for player in slate.players
        if player.underlying_id == original.underlying_id
    }
    slate = slate.model_copy(
        update={
            "players": (
                *slate.players,
                originals["FLEX"].model_copy(
                    update={
                        "dk_id": "99000002",
                        "name": "Backup Kicker",
                        "underlying_id": backup_person,
                    }
                ),
                originals["CPT"].model_copy(
                    update={
                        "dk_id": "99000001",
                        "name": "Backup Kicker",
                        "underlying_id": backup_person,
                    }
                ),
            )
        }
    )
    model = replace(model, players=(*model.players, backup))
    contract = build_participation_contract(slate)
    return slate, model, contract, splits, original.underlying_id, backup_person


def _recipient(slate, person: str, share: float) -> dict[str, object]:
    rows = {player.role: player for player in slate.players if player.underlying_id == person}
    return {
        "underlying_id": person,
        "cpt_dk_id": rows["CPT"].dk_id,
        "flex_dk_id": rows["FLEX"].dk_id,
        "share": share,
    }


def _write_evidence(
    root: Path,
    slate,
    allocations: dict[str, list[tuple[str, float]]],
    *,
    as_of: datetime = AS_OF,
    kinds: dict[str, str] | None = None,
    observed_at: datetime | None = None,
    captured_at: datetime | None = None,
    expires_at: datetime | None = None,
    synthetic: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source_dir = root / "sources"
    source_dir.mkdir(exist_ok=True)
    sources = []
    declarations = []
    game_id = slate.games[0].game_id
    observed = observed_at or as_of - timedelta(hours=1)
    captured = captured_at or as_of - timedelta(minutes=30)
    expires = expires_at or as_of + timedelta(hours=2)
    for team, team_allocations in sorted(allocations.items()):
        recipients = [_recipient(slate, person, share) for person, share in team_allocations]
        allocation_kind = "SOLE" if len(recipients) == 1 else "SPLIT"
        support_kind = (kinds or {}).get(
            team,
            "QUALITATIVE_SOLE" if allocation_kind == "SOLE" else "NUMERICAL_SPLIT",
        )
        if support_kind == "NUMERICAL_SPLIT":
            excerpt = json.dumps(
                {
                    "allocations": recipients,
                    "game_id": game_id,
                    "team": team,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            person = team_allocations[0][0]
            name = next(player.name for player in slate.players if player.underlying_id == person)
            excerpt = f"{name} is the sole kicker for {team}."
        content = f"captured role note\n{excerpt}\n"
        temporary = source_dir / f"{team.lower()}-role.tmp"
        temporary.write_text(content, encoding="utf-8")
        digest = sha256_file(temporary)
        source_path = source_dir / f"{digest}.txt"
        temporary.replace(source_path)
        sources.append(
            {
                "path": f"sources/{source_path.name}",
                "sha256": digest,
                "source_uri": (
                    "https://raw.githubusercontent.com/nfl-role/test/main/"
                    f"{source_path.name}"
                ),
                "observed_at": observed.isoformat(),
                "captured_at": captured.isoformat(),
                "expires_at": expires.isoformat(),
                "license_decision": "PERMITTED_REPOSITORY_LICENSE",
                "parser_version": "kicker_role_test_capture_v1",
                "transformation_version": "kicker_role_test_transform_v1",
                "support_kind": support_kind,
                "supporting_excerpt": excerpt,
                "synthetic": synthetic,
            }
        )
        declarations.append(
            {
                "game_id": game_id,
                "team": team,
                "allocation_kind": allocation_kind,
                "recipients": recipients,
                "source_sha256s": [digest],
            }
        )
    manifest = {
        "schema_version": KICKER_ROLE_EVIDENCE_VERSION,
        "allocation_version": KICKER_ROLE_ALLOCATION_VERSION,
        "salary_sha256": slate.salary_hash,
        "game_id": game_id,
        "share_tolerance": KICKER_ROLE_SHARE_TOLERANCE,
        "sources": sources,
        "declarations": declarations,
    }
    path = root / "kicker_roles.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_two_eligible_kickers_without_evidence_are_blocked_and_zero_snaps_do_not_help(
    tmp_path,
):
    slate, model, contract, splits, _starter, _backup = _two_kicker_setup(tmp_path)
    assert [player.role_capacity for player in model.players if player.position == "K"] == [
        0.0,
        0.0,
        0.0,
    ]
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_UNRESOLVED:team=NE"):
        select_prior_lineups(slate, model, splits, contract, count=1, as_of=AS_OF)


def test_supported_split_conserves_team_points_and_applies_captain_last(tmp_path):
    slate, model, contract, splits, starter, backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [(starter, 0.625), (backup, 0.375)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
    )
    _lineups, scores, report = select_prior_lineups(
        slate,
        model,
        splits,
        contract,
        count=1,
        role_evidence_json=evidence,
        as_of=AS_OF,
    )
    conservation = scores.kicker_roles["conservation"]["NE"]
    assert conservation["full_team_points"] == pytest.approx(8.4)
    assert conservation["allocated_points"] == pytest.approx(8.4)
    assert scores.by_person[starter] == pytest.approx(8.4 * 0.625)
    assert scores.by_person[backup] == pytest.approx(8.4 * 0.375)
    rows = {(player.underlying_id, player.role): player.dk_id for player in slate.players}
    for person in (starter, backup):
        assert scores.by_dk_id[rows[(person, "CPT")]] == pytest.approx(
            1.5 * scores.by_dk_id[rows[(person, "FLEX")]]
        )
    assert report["kicker_roles"]["evidence_state"] == "PASS"
    assert report["kicker_roles"]["synthetic_note"] == "TEST_ONLY_SYNTHETIC_EVIDENCE"


def test_supported_sole_role_excludes_the_other_eligible_kicker(tmp_path):
    slate, model, contract, splits, starter, backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [(starter, 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
    )
    lineups, scores, report = select_prior_lineups(
        slate,
        model,
        splits,
        contract,
        count=1,
        role_evidence_json=evidence,
        as_of=AS_OF,
    )
    backup_ids = {player.dk_id for player in slate.players if player.underlying_id == backup}
    assert scores.by_person[backup] == 0
    assert backup in report["kicker_role_excluded_people"]
    assert not backup_ids.intersection(lineups[0].roster)


def test_single_kicker_fallback_is_visible_only_as_a_prior_assumption(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    _lineups, scores, report = select_prior_lineups(
        slate, model, splits, contract, count=1, as_of=AS_OF
    )
    role = report["kicker_roles"]
    assert role["evidence_state"] == "UNKNOWN"
    assert role["allocation_basis"] == "PRIOR_ONLY_SOLE_LISTED_ASSUMPTION"
    assert len(role["assumptions"]) == 2
    assert "OFFICIAL_ACTIVE_STATUS" in role["does_not_establish"]
    assert scores.by_person["SEA|K|Sea Kicker"] > 0


def test_no_eligible_kicker_allocates_no_points_but_k_free_selection_can_continue(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    kicker_ids = [player.dk_id for player in slate.players if player.position == "K"]
    contract = build_participation_contract(
        slate, operator_excluded_dk_ids=kicker_ids
    )
    reduced, _report = redistribute_opportunity(model, contract)
    lineups, scores, report = select_prior_lineups(
        slate, reduced, splits, contract, count=1, as_of=AS_OF
    )
    assert len(report["kicker_roles"]["coverage_gaps"]) == 2
    assert not any(player.position == "K" and player.underlying_id in scores.by_person for player in slate.players)
    assert not any(
        next(player for player in slate.players if player.dk_id == dk_id).position == "K"
        for dk_id in lineups[0].roster
    )


def test_invalid_supplied_artifact_never_falls_back_to_single_kicker_assumption(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [("NE|K|NE Kicker", 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    payload = _manifest(evidence)
    payload["salary_sha256"] = "0" * 64
    _rewrite(evidence, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SALARY_HASH_MISMATCH"):
        select_prior_lineups(
            slate,
            model,
            splits,
            contract,
            count=1,
            role_evidence_json=evidence,
            as_of=AS_OF,
        )


@pytest.mark.parametrize(
    "bad_share", [-0.1, float("nan"), float("inf"), True, "1.0"]
)
def test_nonfinite_and_negative_shares_fail_closed(tmp_path, bad_share):
    slate, _model, contract, _splits = _prepared(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [("NE|K|NE Kicker", 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    payload = _manifest(evidence)
    payload["declarations"][0]["recipients"][0]["share"] = bad_share
    _rewrite(evidence, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_EVIDENCE_INVALID"):
        resolve_kicker_roles(slate, contract, evidence_path=evidence, as_of=AS_OF)


def test_share_totals_duplicates_unknown_ids_and_wrong_role_ids_fail_closed(tmp_path):
    slate, _model, contract, _splits, starter, backup = _two_kicker_setup(tmp_path)
    base = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [(starter, 0.6), (backup, 0.4)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
    )
    cases = []
    bad_total = _manifest(base)
    bad_total["declarations"][0]["recipients"][1]["share"] = 0.3
    cases.append((bad_total, "KICKER_ROLE_SHARE_TOTAL_INVALID"))
    duplicate = _manifest(base)
    duplicate["declarations"].append(duplicate["declarations"][0])
    cases.append((duplicate, "KICKER_ROLE_TEAM_DECLARATION_DUPLICATE"))
    unknown = _manifest(base)
    unknown["declarations"][0]["recipients"][0]["underlying_id"] = "NE|K|Unknown"
    cases.append((unknown, "KICKER_ROLE_UNKNOWN_PERSON"))
    wrong_id = _manifest(base)
    wrong_id["declarations"][0]["recipients"][0]["cpt_dk_id"] = "99000002"
    cases.append((wrong_id, "KICKER_ROLE_IDENTITY_MISMATCH"))
    wrong_team = _manifest(base)
    wrong_team["declarations"][0]["recipients"][0] = _recipient(
        slate, "SEA|K|Sea Kicker", 0.6
    )
    cases.append((wrong_team, "KICKER_ROLE_IDENTITY_MISMATCH"))
    duplicate_recipient = _manifest(base)
    duplicate_recipient["declarations"][0]["recipients"][1] = dict(
        duplicate_recipient["declarations"][0]["recipients"][0]
    )
    duplicate_recipient["declarations"][0]["recipients"][1]["share"] = 0.4
    cases.append((duplicate_recipient, "KICKER_ROLE_PERSON_DECLARATION_DUPLICATE"))
    for index, (payload, error) in enumerate(cases):
        path = base.parent / f"bad-{index}.json"
        _rewrite(path, payload)
        with pytest.raises(KickerRoleError, match=error):
            resolve_kicker_roles(slate, contract, evidence_path=path, as_of=AS_OF)


def test_future_stale_changed_unbound_and_escaped_sources_fail_closed(tmp_path):
    slate, _model, contract, _splits = _prepared(tmp_path)
    allocations = {
        "NE": [("NE|K|NE Kicker", 1.0)],
        "SEA": [("SEA|K|Sea Kicker", 1.0)],
    }
    future = _write_evidence(
        tmp_path / "future",
        slate,
        allocations,
        observed_at=AS_OF + timedelta(minutes=1),
        captured_at=AS_OF + timedelta(minutes=2),
    )
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_FUTURE"):
        resolve_kicker_roles(slate, contract, evidence_path=future, as_of=AS_OF)

    stale = _write_evidence(
        tmp_path / "stale",
        slate,
        allocations,
        expires_at=AS_OF - timedelta(seconds=1),
        captured_at=AS_OF - timedelta(hours=2),
        observed_at=AS_OF - timedelta(hours=3),
    )
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_STALE"):
        resolve_kicker_roles(slate, contract, evidence_path=stale, as_of=AS_OF)

    changed = _write_evidence(tmp_path / "changed", slate, allocations)
    changed_payload = _manifest(changed)
    changed_source = changed.parent / changed_payload["sources"][0]["path"]
    changed_source.write_text("tampered", encoding="utf-8")
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_HASH_MISMATCH"):
        resolve_kicker_roles(slate, contract, evidence_path=changed, as_of=AS_OF)

    unbound = _write_evidence(tmp_path / "unbound", slate, allocations)
    payload = _manifest(unbound)
    payload["declarations"][0]["source_sha256s"] = ["0" * 64]
    _rewrite(unbound, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_REFERENCE_UNKNOWN"):
        resolve_kicker_roles(slate, contract, evidence_path=unbound, as_of=AS_OF)

    escaped = _write_evidence(tmp_path / "escaped", slate, allocations)
    payload = _manifest(escaped)
    payload["sources"][0]["path"] = "../outside.txt"
    _rewrite(escaped, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_PATH_ESCAPE"):
        resolve_kicker_roles(slate, contract, evidence_path=escaped, as_of=AS_OF)

    unapproved = _write_evidence(tmp_path / "unapproved", slate, allocations)
    payload = _manifest(unapproved)
    payload["sources"][0]["source_uri"] = "https://example.com/role.txt"
    _rewrite(unapproved, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_POLICY"):
        resolve_kicker_roles(slate, contract, evidence_path=unapproved, as_of=AS_OF)


def test_qualitative_prose_cannot_supply_a_fractional_split(tmp_path):
    slate, _model, contract, _splits, starter, backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [(starter, 0.5), (backup, 0.5)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        kinds={"NE": "QUALITATIVE_SOLE"},
    )
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SPLIT_QUALITATIVE_SOURCE_NOT_ALLOWED"):
        resolve_kicker_roles(slate, contract, evidence_path=evidence, as_of=AS_OF)


def test_qualitative_sole_source_must_actually_name_the_role_and_person(tmp_path):
    slate, _model, contract, _splits = _prepared(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [("NE|K|NE Kicker", 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    payload = _manifest(evidence)
    payload["sources"][0]["supporting_excerpt"] = "captured role note"
    _rewrite(evidence, payload)
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_QUALITATIVE_SUPPORT_INSUFFICIENT"):
        resolve_kicker_roles(slate, contract, evidence_path=evidence, as_of=AS_OF)


def test_inactive_declared_starter_requires_refreshed_role_resolution(tmp_path):
    slate, _model, _contract, _splits, starter, backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [(starter, 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    starter_id = next(
        player.dk_id
        for player in slate.players
        if player.underlying_id == starter and player.role == "FLEX"
    )
    contract = build_participation_contract(
        slate, operator_excluded_dk_ids=[starter_id]
    )
    assert backup in contract.selectable_people
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_POSITIVE_SHARE_NOT_ELIGIBLE"):
        resolve_kicker_roles(slate, contract, evidence_path=evidence, as_of=AS_OF)


def test_final_hash_and_expiry_are_rechecked_after_selection(tmp_path):
    slate, _model, contract, _splits = _prepared(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [("NE|K|NE Kicker", 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
        expires_at=AS_OF + timedelta(minutes=1),
    )
    resolution = resolve_kicker_roles(
        slate, contract, evidence_path=evidence, as_of=AS_OF
    )
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_EXPIRED_DURING_SELECTION"):
        verify_kicker_role_resolution(
            resolution, at=AS_OF + timedelta(minutes=2)
        )
    source = Path(resolution.source_paths[0])
    source.write_text(source.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    with pytest.raises(KickerRoleError, match="KICKER_ROLE_SOURCE_CHANGED_DURING_SELECTION"):
        verify_kicker_role_resolution(resolution, at=AS_OF)


def test_cowork_request_round_trip_confines_role_evidence_path(tmp_path):
    root = tmp_path / "request"
    root.mkdir()
    role = root / "roles.json"
    role.write_text("{}", encoding="utf-8")
    request_path = root / "run_request.json"
    request_path.write_text(
        json.dumps({"profile": "prior_review", "role_evidence_json": "roles.json"}),
        encoding="utf-8",
    )
    request = CoworkRunRequest.from_json(request_path)
    assert request.role_evidence_json == str(role.resolve())
    assert CoworkRunRequest.from_mapping(
        request.to_dict(), allowed_roots=(root,)
    ) == request
    with pytest.raises(CoworkInputError, match="must not contain traversal"):
        CoworkRunRequest.from_mapping(
            {"role_evidence_json": "../escape.json"},
            base_dir=root,
            allowed_roots=(root,),
        )


def test_cowork_snapshot_copies_role_sources_for_portable_replay(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    slate, _model, contract, _splits = _prepared(fixture)
    evidence = _write_evidence(
        tmp_path / "package",
        slate,
        {"NE": [("NE|K|NE Kicker", 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    hashes = cli._snapshot_inputs("sd1-copy", [evidence])
    copied = cli._snapshot_path("sd1-copy", evidence, hashes[str(evidence.resolve())])
    assert copied.is_file()
    assert len(list((copied.parent / "sources").iterdir())) == 2
    resolution = resolve_kicker_roles(
        slate, contract, evidence_path=copied, as_of=AS_OF
    )
    assert resolution.evidence_sha256 == sha256_file(copied)
    assert all(Path(path).parent == copied.parent / "sources" for path in resolution.source_paths)


# --------------------------------------------------------------------------- #
# P0-1: the scored-pool export, promoted out of a slate-day debug hook
# --------------------------------------------------------------------------- #


def test_the_scored_pool_export_writes_a_versioned_document(tmp_path):
    """The engine's real product, written through a named function.

    On 2026-09-13 these scores were the one engine artifact that reached the
    shipped portfolio, and they left through an unnamed environment variable
    read in the middle of the scoring path. Backlog P1-4 replaces this with a
    hash-bound first-class artifact and deletes it.
    """

    import json

    from nfl_dfs.selection import POOL_SCORES_SCHEMA

    slate, model, contract, splits, starter, _backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [(starter, 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    target = tmp_path / "scores.json"
    _lineups, scores, _report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        role_evidence_json=evidence, as_of=AS_OF, pool_scores_path=target,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == POOL_SCORES_SCHEMA
    assert payload["score_version"] == scores.score_version
    assert payload["by_dk_id"] == scores.by_dk_id
    # It is a diagnostic. Nothing downstream may read it as an authorization.
    assert payload["status"] == "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION"


def test_the_scored_pool_export_is_off_unless_asked_for(tmp_path):
    slate, model, contract, splits, starter, _backup = _two_kicker_setup(tmp_path)
    evidence = _write_evidence(
        tmp_path / "roles",
        slate,
        {"NE": [(starter, 1.0)], "SEA": [("SEA|K|Sea Kicker", 1.0)]},
    )
    select_prior_lineups(
        slate, model, splits, contract, count=1,
        role_evidence_json=evidence, as_of=AS_OF,
    )
    assert not list(tmp_path.glob("*scores*.json"))


def test_the_scored_pool_export_refuses_an_unwritable_destination(tmp_path):
    """Validated, not just handed to `open`."""

    from nfl_dfs.selection import SelectionError, resolve_pool_scores_path

    with pytest.raises(SelectionError, match="POOL_SCORES_PARENT_MISSING"):
        resolve_pool_scores_path(tmp_path / "nope" / "scores.json")
    with pytest.raises(SelectionError, match="POOL_SCORES_PATH_IS_A_DIRECTORY"):
        resolve_pool_scores_path(tmp_path)
    assert resolve_pool_scores_path(None) is None
