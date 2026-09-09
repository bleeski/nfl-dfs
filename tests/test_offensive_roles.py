"""SD2 synthetic captures: exact identities, arithmetic, exclusions and replay."""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from nfl_dfs import cli
from nfl_dfs.cowork import CoworkRunRequest, CoworkInputError
from nfl_dfs.hashing import sha256_file, sha256_bytes
from nfl_dfs.offensive_roles import (
    FIELDS, VERSION, TRANSFORM, OFFENSE, OffensiveRoleError,
    resolve_offensive_roles, verify_offensive_resolution,
)
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.prior_score import score_pool, team_volumes
from nfl_dfs.selection import select_prior_lineups
from .test_participation import _slate, _model
from .test_prior_selection import _splits

AS_OF = datetime(2026, 9, 8, 18, tzinfo=timezone.utc)


def _setup(tmp_path):
    slate = _slate(tmp_path)
    return slate, _model(tmp_path, slate), build_participation_contract(slate), _splits(tmp_path)


def _binding(slate, person):
    rows = {p.role: p for p in slate.players if p.underlying_id == person}
    return {"underlying_id": person, "cpt_dk_id": rows["CPT"].dk_id, "flex_dk_id": rows["FLEX"].dk_id}


def _declaration(slate, model, team="NE"):
    recipients = []
    for p in model.players:
        if p.team != team or p.position not in OFFENSE:
            continue
        shares = {f: getattr(p, f) for f in FIELDS}
        if p.underlying_id == "NE|RB|Lead RB":
            shares["carry_share"] = 0.0
        if p.underlying_id == "NE|RB|Backup RB":
            shares["carry_share"] = 0.75
        recipients.append({**_binding(slate, p.underlying_id), "shares": shares, "receiving_efficiency": None})
    return {"team": team, "game_id": slate.games[0].game_id,
            "totals": dict.fromkeys(FIELDS, 1.0), "unallocated": dict.fromkeys(FIELDS, 0.0),
            "recipients": recipients}


def _package(root, slate, declarations=(), facts=(), as_of=AS_OF):
    root.mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(exist_ok=True)
    sources, bound_declarations, bound_facts = [], [], []
    def capture(excerpt, kind):
        content = ("TEST_ONLY_SYNTHETIC_EVIDENCE\n" + excerpt + "\n").encode()
        digest = sha256_bytes(content)
        (root / "sources" / f"{digest}.txt").write_bytes(content)
        sources.append({"path": f"sources/{digest}.txt", "sha256": digest,
                        "source_uri": "https://raw.githubusercontent.com/nfl-role/test/main/synthetic.txt",
                        "observed_at": (as_of - timedelta(hours=1)).isoformat(),
                        "captured_at": (as_of - timedelta(minutes=30)).isoformat(),
                        "expires_at": (as_of + timedelta(hours=2)).isoformat(),
                        "license_decision": "PERMITTED_REPOSITORY_LICENSE", "parser_version": "sd2_synthetic_v1",
                        "transformation_version": TRANSFORM, "support_kind": kind,
                        "supporting_excerpt": excerpt, "synthetic": True})
        return digest
    for d in declarations:
        digest = capture(json.dumps(d, sort_keys=True), "NUMERICAL_ALLOCATION")
        bound_declarations.append({**d, "source_sha256": digest})
    for person, fact in facts:
        p = next(p for p in slate.players if p.underlying_id == person)
        phrase = {"NAMED_STARTER": "is the starter", "NAMED_BACKUP": "is the backup",
                  "MATERIAL_ROLE_CHANGE": "has an unresolved role change",
                  "EXPLICIT_NONPARTICIPATION": "will not participate"}[fact]
        digest = capture(f"{p.name} {phrase} for {p.team} in {p.game_id}.", "QUALITATIVE_FACT")
        bound_facts.append({**_binding(slate, person), "team": p.team, "game_id": p.game_id, "fact": fact, "source_sha256": digest})
    path = root / "offensive_roles.json"
    path.write_text(json.dumps({"schema_version": VERSION, "transformation_version": TRANSFORM,
                               "salary_sha256": slate.salary_hash, "game_id": slate.games[0].game_id,
                               "sources": sources, "declarations": bound_declarations, "facts": bound_facts}), encoding="utf-8")
    return path


def _edit(path, mutate):
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_promoted_backup_conserved_without_historical_ceiling(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)])
    result = resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    promoted = next(p for p in result.model.players if p.underlying_id == "NE|RB|Backup RB")
    assert promoted.carry_share == .75 > promoted.role_capacity == .20
    for field in FIELDS:
        assert sum(getattr(p, field) for p in result.model.players if p.team == "NE") == pytest.approx(1)
    scores = score_pool(slate, result.model, splits, offensive_roles=result)
    volume = team_volumes(model, splits)["NE"]
    assert scores.stat_lines[promoted.underlying_id].rushing_yards == pytest.approx(volume.carries * volume.rush_yards_per_attempt * .75)
    assert scores.by_dk_id[_binding(slate, promoted.underlying_id)["cpt_dk_id"]] == pytest.approx(scores.by_person[promoted.underlying_id] * 1.5)
    finding = next(f for f in result.report["findings"] if f["person"] == promoted.underlying_id)
    assert finding["before"]["carry_share"] == .15
    assert finding["after"]["carry_share"] == .75
    assert finding["state"] == "SOURCE_SUPPORTED_ADJUSTMENT"
    assert result.report["synthetic_note"] == "TEST_ONLY_SYNTHETIC_EVIDENCE"
    assert result.report["unallocated_by_team"]["SEA"]["carry_share"] == pytest.approx(.55)


@pytest.mark.parametrize("state,reason", [("MISSING_HISTORY", "OFFENSIVE_MISSING_HISTORY"), ("CURRENT_ROLE_UNKNOWN", "OFFENSIVE_TRANSFER_REQUIRES_CURRENT_TEAM_ROLE")])
def test_missing_or_transfer_is_one_finding_and_cannot_be_a_zero_punt(tmp_path, state, reason):
    slate, model, contract, splits = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    model = replace(model, offensive_history_by_person={person: {"state": state, "incompatible_transfer": state == "CURRENT_ROLE_UNKNOWN"}})
    with pytest.raises(OffensiveRoleError, match=reason) as error:
        select_prior_lineups(slate, model, splits, contract, count=1)
    matches = [f for f in error.value.report["findings"] if f["person"] == person]
    assert len(matches) == 1 and matches[0]["selection_action"] == "BLOCK"
    assert matches[0]["after"] is None
    assert error.value.report["evidence_state"] == "UNKNOWN"


def test_observed_zero_is_excluded_and_not_mapped_to_missing(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    model = replace(model, players=tuple(replace(p, **dict.fromkeys(FIELDS, 0.0)) if p.underlying_id == person else p for p in model.players),
                    offensive_history_by_person={person: {"state": "OBSERVED_HISTORY_ZERO"}})
    lineups, scores, report = select_prior_lineups(slate, model, splits, contract, count=1)
    assert person not in scores.by_person
    f = next(f for f in report["offensive_roles"]["findings"] if f["person"] == person)
    assert f["state"] == "OBSERVED_HISTORY_ZERO" and f["selection_action"] == "EXCLUDE"
    assert all(i not in lineups[0].roster for i in _binding(slate, person).values())


@pytest.mark.parametrize("fact", ["NAMED_STARTER", "NAMED_BACKUP", "MATERIAL_ROLE_CHANGE"])
def test_qualitative_role_never_invents_shares(tmp_path, fact):
    slate, model, contract, splits = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, facts=[("NE|RB|Backup RB", fact)])
    with pytest.raises(OffensiveRoleError, match="OFFENSIVE_CURRENT_ROLE_UNRESOLVED"):
        select_prior_lineups(slate, model, splits, contract, count=1, offensive_role_evidence_json=path, as_of=AS_OF)


def test_nonparticipation_excludes_without_transfer(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, facts=[("NE|RB|Lead RB", "EXPLICIT_NONPARTICIPATION")])
    result = resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    assert "NE|RB|Lead RB" in result.excluded_people
    assert next(p for p in result.model.players if p.underlying_id == "NE|RB|Backup RB").carry_share == .15
    assert result.report["unallocated_by_team"]["NE"]["carry_share"] == pytest.approx(.60)


@pytest.mark.parametrize("exclusion", ["operator", "salary", "nonparticipation"])
def test_excluded_positive_recipient_invalidates_allocation(tmp_path, exclusion):
    slate, model, contract, splits = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)],
                    facts=[(person, "EXPLICIT_NONPARTICIPATION")] if exclusion == "nonparticipation" else [])
    if exclusion == "operator":
        contract = build_participation_contract(slate, operator_excluded_dk_ids=[_binding(slate, person)["cpt_dk_id"]])
    if exclusion == "salary":
        slate = slate.model_copy(update={"players": tuple(p.model_copy(update={"status_raw": "OUT"}) if p.underlying_id == person else p for p in slate.players)})
        contract = build_participation_contract(slate)
    with pytest.raises(OffensiveRoleError, match="RECIPIENT_EXCLUDED"):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)


@pytest.mark.parametrize("mutation,expected", [
    (lambda d: d["recipients"][0].update(flex_dk_id="99999"), "EXACT_ID_MISMATCH"),
    (lambda d: d.update(team="SEA"), "TEAM_GAME_MISMATCH"),
    (lambda d: d["recipients"].append(d["recipients"][0]), "DUPLICATE_PERSON"),
    (lambda d: d["totals"].update(carry_share=.9), "INVALID_TOTAL"),
    (lambda d: d["recipients"][2]["shares"].update(carry_share=.5), "INVALID_TOTAL"),
    (lambda d: d["recipients"][1]["shares"].update(qb_attempt_share=.1), "POSITION_CONFLICT"),
    (lambda d: d["recipients"].pop(), "COVERAGE_MISSING"),
])
def test_invalid_captured_allocations_fail_named(tmp_path, mutation, expected):
    slate, model, contract, _splits = _setup(tmp_path)
    d = _declaration(slate, model)
    mutation(d)
    path = _package(tmp_path / "roles", slate, [d])
    with pytest.raises(OffensiveRoleError, match=expected):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, True, "0.75", None])
def test_invalid_number_types(tmp_path, value):
    slate, model, contract, _ = _setup(tmp_path)
    d = _declaration(slate, model)
    d["recipients"][2]["shares"]["carry_share"] = value
    path = _package(tmp_path / "roles", slate, [d])
    with pytest.raises(OffensiveRoleError, match="EVIDENCE_INVALID"):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)


@pytest.mark.parametrize("mutation,expected", [
    (lambda p: p.update(salary_sha256="a" * 64), "SALARY_HASH_MISMATCH"),
    (lambda p: p["declarations"].append(p["declarations"][0]), "DUPLICATE_TEAM"),
    (lambda p: p["sources"][0].update(source_uri="https://www.draftkings.com/"), "SOURCE_POLICY"),
    (lambda p: p["sources"][0].update(path="../escape.txt"), "PATH_ESCAPE"),
    (lambda p: p["sources"][0].update(captured_at=(AS_OF + timedelta(minutes=2)).isoformat()), "CAPTURE_FUTURE"),
    (lambda p: p["sources"][0].update(observed_at=(AS_OF + timedelta(minutes=1)).isoformat(), captured_at=(AS_OF + timedelta(minutes=2)).isoformat()), "SOURCE_FUTURE"),
    (lambda p: p["sources"][0].update(expires_at=(AS_OF - timedelta(minutes=1)).isoformat()), "SOURCE_STALE"),
    (lambda p: p["sources"][0].update(support_kind="QUALITATIVE_FACT"), "NUMERICAL_SOURCE_REQUIRED"),
    (lambda p: p["sources"][0].update(transformation_version="invented"), "EVIDENCE_INVALID"),
    (lambda p: p["declarations"][0]["recipients"][2]["shares"].update(carry_share=.6), "SUPPORT_MISMATCH"),
])
def test_package_mutations_fail_closed(tmp_path, mutation, expected):
    slate, model, contract, _ = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)])
    _edit(path, mutation)
    with pytest.raises(OffensiveRoleError, match=expected):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)


def test_missing_history_can_be_resolved_only_with_explicit_efficiency(tmp_path):
    slate, model, contract, _ = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    model = replace(model, offensive_history_by_person={person: {"state": "MISSING_HISTORY", "receiving_efficiency_observed": False}})
    d = _declaration(slate, model)
    path = _package(tmp_path / "roles", slate, [d])
    with pytest.raises(OffensiveRoleError, match="RECEIVING_EFFICIENCY_REQUIRED"):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    d["recipients"][2]["receiving_efficiency"] = {"catch_rate": .6, "yards_per_target": 6.5}
    path = _package(tmp_path / "resolved", slate, [d])
    result = resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    assert next(p for p in result.model.players if p.underlying_id == person).yards_per_target == 6.5


def test_snapshot_copy_replay_repeat_and_final_freshness(tmp_path, monkeypatch):
    slate, model, contract, splits = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)])
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    hashes = cli._snapshot_inputs("sd2", [path], allowed_roots=[tmp_path])
    snapshot = cli._snapshot_path("sd2", path, hashes[str(path)])
    copied = tmp_path / "copied"
    shutil.copytree(snapshot.parent, copied)
    replay = copied / snapshot.name
    path.rename(path.with_suffix(".original"))
    first = select_prior_lineups(slate, model, splits, contract, count=2, offensive_role_evidence_json=replay, as_of=AS_OF)
    second = select_prior_lineups(slate, model, splits, contract, count=2, offensive_role_evidence_json=replay, as_of=AS_OF)
    assert [l.roster for l in first[0]] == [l.roster for l in second[0]]
    assert first[1].by_person == second[1].by_person
    resolution = first[1].offensive_role_resolution
    with pytest.raises(OffensiveRoleError, match="EXPIRED_DURING_SELECTION"):
        verify_offensive_resolution(resolution, at=AS_OF + timedelta(hours=3))
    replay.write_text(replay.read_text() + " ")
    with pytest.raises(OffensiveRoleError, match="MANIFEST_CHANGED"):
        verify_offensive_resolution(resolution, at=AS_OF)


def test_request_roundtrip_and_confinement(tmp_path):
    slate, model, contract, _ = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)])
    request = CoworkRunRequest.from_mapping({"offensive_role_evidence_json": str(path)}, allowed_roots=[tmp_path])
    assert CoworkRunRequest.from_mapping(request.to_dict(), allowed_roots=[tmp_path]) == request
    with pytest.raises(CoworkInputError, match="traversal"):
        CoworkRunRequest.from_mapping({"offensive_role_evidence_json": "../escape.json"}, base_dir=tmp_path, allowed_roots=[tmp_path])


def test_explicit_unallocated_volume_is_not_normalized_away(tmp_path):
    slate, model, contract, _ = _setup(tmp_path)
    d = _declaration(slate, model)
    d["recipients"][2]["shares"]["carry_share"] = .5
    d["unallocated"]["carry_share"] = .25
    path = _package(tmp_path / "roles", slate, [d])
    result = resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    assert result.report["declared_unallocated"]["NE"]["carry_share"] == .25
    assert result.report["unallocated_by_team"]["NE"]["carry_share"] == pytest.approx(.25)
    assert next(p for p in result.model.players if p.underlying_id == "NE|RB|Backup RB").carry_share == .5


def test_conflicting_facts_and_missing_history_coverage_fail(tmp_path):
    from nfl_dfs.offensive_roles import attach_history
    slate, model, contract, _ = _setup(tmp_path)
    path = _package(tmp_path / "roles", slate, facts=[("NE|RB|Backup RB", "NAMED_STARTER"), ("NE|RB|Backup RB", "NAMED_BACKUP")])
    with pytest.raises(OffensiveRoleError, match="DUPLICATE_FACT"):
        resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"metadata":{"coverage":{}}}')
    with pytest.raises(OffensiveRoleError, match="HISTORY_COVERAGE_REQUIRED"):
        attach_history(model, legacy, sha256_file(legacy))


def test_complete_team_capture_is_not_limited_to_kicker_excerpt_size(tmp_path):
    slate, model, contract, _ = _setup(tmp_path)
    original = next(p for p in model.players if p.underlying_id == "NE|RB|Backup RB")
    salaries, players = list(slate.players), list(model.players)
    rows = [p for p in slate.players if p.underlying_id == original.underlying_id]
    for i in range(14):
        person = f"NE|RB|Synthetic Reserve {i}"
        flex, cpt = str(99000002 + 2 * i), str(99000001 + 2 * i)
        salaries.extend(p.model_copy(update={"underlying_id": person, "name": f"Synthetic Reserve {i}",
                                            "dk_id": flex if p.role == "FLEX" else cpt}) for p in rows)
        players.append(replace(original, underlying_id=person, source_dk_id=flex, **dict.fromkeys(FIELDS, 0.0)))
    slate = slate.model_copy(update={"players": tuple(salaries)})
    model = replace(model, players=tuple(players))
    contract = build_participation_contract(slate)
    path = _package(tmp_path / "roles", slate, [_declaration(slate, model)])
    assert len(json.loads(path.read_text())["sources"][0]["supporting_excerpt"]) > 4000
    result = resolve_offensive_roles(slate, model, contract, evidence_path=path, as_of=AS_OF)
    assert len(result.report["findings"]) == 26
