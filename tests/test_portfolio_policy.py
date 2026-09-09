"""SD3: exact, deterministic Showdown portfolio-policy contract coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nfl_dfs.cowork import CoworkInputError, CoworkRunRequest, required_next_inputs
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_policy import (
    ENFORCEMENT_BLOCKER,
    FRACTION_UNIT,
    POLICY_SCHEMA_VERSION,
    canonical_showdown_lineup_identity,
    portfolio_policy_template,
    salary_person_bindings,
    summarize_showdown_portfolio,
    validate_portfolio_policy_bytes,
    validate_portfolio_policy_file,
)

from .test_participation import _salary_bytes, _slate
from .test_prior_selection import _entries_bytes


def _reference(slate, index: int = 0) -> dict[str, str]:
    return salary_person_bindings(slate)[index].as_mapping()


def _document(slate, entry_ids=("900000001", "900000002"), **controls):
    return portfolio_policy_template(slate, entry_ids, controls=controls)


def _validate(slate, document, entry_ids=("900000001", "900000002"), **kwargs):
    raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
    return validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, **kwargs
    )


def _codes(validation) -> set[str]:
    return {problem.code for problem in validation.problems}


@pytest.mark.parametrize(
    ("entries", "fraction", "expected"),
    [
        (("1", "2"), 0.49, 0),
        (("1", "2"), 0.50, 1),
        (("1", "2"), 1.00, 2),
        (("1", "2", "3"), 0.66, 1),
        (("1", "2", "3"), 0.67, 2),
    ],
)
def test_exact_decimal_floor_boundaries(entries, fraction, expected, tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    reference = _reference(slate)
    document = _document(
        slate,
        entries,
        max_combined_person_exposure={
            "default_fraction": None,
            "overrides": [{**reference, "fraction": fraction}],
        },
    )

    validation = _validate(slate, document, entries)

    assert validation.valid, validation.blockers()
    limit = next(
        item
        for item in validation.policy.effective_limits
        if item.person.underlying_id == reference["underlying_id"]
    )
    assert limit.combined_max_entries == expected
    if expected == 0:
        assert limit.captain_max_entries == 0


def test_omitted_default_zero_full_and_override_precedence(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    target = _reference(slate, 0)
    zero_captain = _reference(slate, 1)
    document = _document(
        slate,
        max_combined_person_exposure={
            "default_fraction": 0.50,
            "overrides": [{**target, "fraction": 1.00}],
        },
        max_captain_exposure={
            "default_fraction": 0.50,
            "overrides": [{**zero_captain, "fraction": 0}],
        },
    )

    validation = _validate(slate, document)

    assert validation.valid, validation.blockers()
    limits = {item.person.underlying_id: item for item in validation.policy.effective_limits}
    assert limits[target["underlying_id"]].combined_source == "PERSON_OVERRIDE"
    assert limits[target["underlying_id"]].combined_max_entries == 2
    assert limits[zero_captain["underlying_id"]].combined_max_entries == 1
    assert limits[zero_captain["underlying_id"]].captain_max_entries == 0
    omitted = _validate(slate, _document(slate))
    assert omitted.valid
    assert all(item.combined_max_entries == 2 for item in omitted.policy.effective_limits)
    assert all(item.captain_max_entries == 2 for item in omitted.policy.effective_limits)


def test_captain_subset_contradiction_is_tightened_and_reported(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    target = _reference(slate)
    document = _document(
        slate,
        max_combined_person_exposure={
            "default_fraction": None,
            "overrides": [{**target, "fraction": 0.50}],
        },
        max_captain_exposure={
            "default_fraction": None,
            "overrides": [{**target, "fraction": 1.00}],
        },
    )

    validation = _validate(slate, document)

    assert validation.valid
    limit = next(
        item
        for item in validation.policy.effective_limits
        if item.person.underlying_id == target["underlying_id"]
    )
    assert limit.declared_captain_max_entries == 2
    assert limit.captain_max_entries == limit.combined_max_entries == 1
    assert {finding.code for finding in validation.findings} == {
        "PORTFOLIO_POLICY_CAPTAIN_TIGHTENED_BY_COMBINED"
    }


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (True, "PORTFOLIO_POLICY_FRACTION_TYPE_INVALID"),
        ("0.5", "PORTFOLIO_POLICY_FRACTION_TYPE_INVALID"),
        (-0.01, "PORTFOLIO_POLICY_FRACTION_OUT_OF_RANGE"),
        (1.01, "PORTFOLIO_POLICY_FRACTION_OUT_OF_RANGE"),
        (50, "PORTFOLIO_POLICY_FRACTION_OUT_OF_RANGE"),
    ],
)
def test_malformed_fraction_types_and_ranges_are_rejected(
    value, code, tmp_path: Path
) -> None:
    slate = _slate(tmp_path)
    document = _document(
        slate,
        max_combined_person_exposure={
            "default_fraction": value,
            "overrides": [],
        },
    )
    validation = _validate(slate, document)
    assert code in _codes(validation)


def test_nonfinite_number_and_ambiguous_unit_are_rejected(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    document = _document(slate)
    raw = json.dumps(document).replace(
        '"default_fraction": null', '"default_fraction": NaN', 1
    ).encode("utf-8")
    nonfinite = validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=("900000001", "900000002")
    )
    assert "PORTFOLIO_POLICY_FRACTION_NONFINITE" in _codes(nonfinite)

    document["controls"]["fraction_unit"] = "PERCENT_0_TO_100"
    unit = _validate(slate, document)
    assert "PORTFOLIO_POLICY_FRACTION_UNIT_INVALID" in _codes(unit)


def test_unknown_ids_conflicting_roles_and_duplicate_overrides_are_rejected(
    tmp_path: Path,
) -> None:
    slate = _slate(tmp_path)
    first = _reference(slate, 0)
    second = _reference(slate, 1)
    unknown = _document(
        slate,
        max_captain_exposure={
            "default_fraction": None,
            "overrides": [{**first, "cpt_dk_id": "99999999", "fraction": 0.5}],
        },
    )
    assert "PORTFOLIO_POLICY_UNKNOWN_DK_ID" in _codes(_validate(slate, unknown))

    conflicting = _document(
        slate,
        max_captain_exposure={
            "default_fraction": None,
            "overrides": [
                {**first, "flex_dk_id": second["flex_dk_id"], "fraction": 0.5}
            ],
        },
    )
    assert "PORTFOLIO_POLICY_CONFLICTING_ROLE_IDENTITY" in _codes(
        _validate(slate, conflicting)
    )

    duplicate = _document(
        slate,
        max_captain_exposure={
            "default_fraction": None,
            "overrides": [
                {**first, "fraction": 0.5},
                {**first, "fraction": 0.6},
            ],
        },
    )
    assert "PORTFOLIO_POLICY_DUPLICATE_OVERRIDE" in _codes(
        _validate(slate, duplicate)
    )


def test_duplicate_and_subset_entry_bindings_are_rejected(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    duplicate = _document(slate, ("900000001", "900000001"))
    validation = _validate(slate, duplicate)
    assert "PORTFOLIO_POLICY_DUPLICATE_ENTRY_ID" in _codes(validation)
    assert "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH" in _codes(validation)

    subset = _document(slate, ("900000001",))
    assert "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH" in _codes(
        _validate(slate, subset)
    )


def test_complete_person_identity_binding_detects_mutated_identity(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    document = _document(slate)
    document["bindings"]["person_identities"][0]["underlying_id"] = "NE|QB|Wrong"
    validation = _validate(slate, document)
    assert "PORTFOLIO_POLICY_UNKNOWN_PERSON_ID" in _codes(validation)
    assert "PORTFOLIO_POLICY_PERSON_IDENTITY_COVERAGE_MISMATCH" in _codes(validation)


def test_policy_hash_is_stable_under_nonsemantic_order_and_tracks_source_bytes(
    tmp_path: Path,
) -> None:
    slate = _slate(tmp_path)
    first = _reference(slate, 0)
    second = _reference(slate, 1)
    controls = {
        "max_combined_person_exposure": {
            "default_fraction": 1,
            "overrides": [
                {**first, "fraction": 0.5},
                {**second, "fraction": 0.75},
            ],
        }
    }
    document = _document(slate, **controls)
    raw_a = json.dumps(document, sort_keys=True).encode("utf-8")
    reordered = json.loads(json.dumps(document))
    reordered["bindings"]["person_identities"].reverse()
    reordered["controls"]["max_combined_person_exposure"]["overrides"].reverse()
    raw_b = (json.dumps(reordered, indent=2) + "\n").encode("utf-8")

    first_validation = validate_portfolio_policy_bytes(
        raw_a, slate=slate, entry_ids=("900000001", "900000002")
    )
    second_validation = validate_portfolio_policy_bytes(
        raw_b, slate=slate, entry_ids=("900000001", "900000002")
    )

    assert first_validation.valid and second_validation.valid
    assert first_validation.source_sha256 != second_validation.source_sha256
    assert first_validation.normalized_sha256 == second_validation.normalized_sha256
    assert first_validation.policy.canonical_bytes() == second_validation.policy.canonical_bytes()


def test_expected_hash_detects_policy_input_mutation(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(_document(slate)), encoding="utf-8")
    original = sha256_bytes(path.read_bytes())
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    validation = validate_portfolio_policy_file(
        path,
        slate=slate,
        entry_ids=("900000001", "900000002"),
        expected_sha256=original,
    )

    assert "PORTFOLIO_POLICY_INPUT_MUTATED" in _codes(validation)


def test_policy_and_source_exclusions_are_exact_and_stricter_than_caps(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    policy_excluded = _reference(slate, 0)
    source_excluded = _reference(slate, 1)
    document = _document(
        slate,
        excluded_people=[policy_excluded],
        max_combined_person_exposure={"default_fraction": 1, "overrides": []},
        max_captain_exposure={"default_fraction": 1, "overrides": []},
    )

    validation = _validate(
        slate,
        document,
        externally_excluded_people=(source_excluded["underlying_id"],),
    )

    assert validation.valid, validation.blockers()
    limits = {item.person.underlying_id: item for item in validation.policy.effective_limits}
    assert limits[policy_excluded["underlying_id"]].combined_max_entries == 0
    assert limits[source_excluded["underlying_id"]].captain_max_entries == 0
    assert limits[source_excluded["underlying_id"]].exclusion_source == (
        "SOURCE_OR_PARTICIPATION_PRECEDENCE"
    )
    assert sum(
        finding.code == "PORTFOLIO_POLICY_EXCLUSION_TAKES_PRECEDENCE"
        for finding in validation.findings
    ) == 2


def test_necessary_capacity_checks_are_named_without_solver_claims(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    zero = _document(
        slate,
        max_combined_person_exposure={"default_fraction": 0, "overrides": []},
        max_captain_exposure={"default_fraction": 0, "overrides": []},
    )
    zero_validation = _validate(slate, zero)
    assert {
        "PORTFOLIO_POLICY_PERSON_CAPACITY_INSUFFICIENT",
        "PORTFOLIO_POLICY_COMBINED_EXPOSURE_CAPACITY_INSUFFICIENT",
        "PORTFOLIO_POLICY_CAPTAIN_CAPACITY_INSUFFICIENT",
    } <= _codes(zero_validation)
    assert all("solver" not in problem.message.casefold() for problem in zero_validation.problems)

    people = salary_person_bindings(slate)
    keep = {item.underlying_id for item in people[:3]} | {
        item.underlying_id for item in people[-4:]
    }
    excluded = [item.as_mapping() for item in people if item.underlying_id not in keep]
    overlap = _document(
        slate,
        excluded_people=excluded,
        max_pairwise_person_overlap=4,
    )
    overlap_validation = _validate(slate, overlap)
    assert "PORTFOLIO_POLICY_PAIRWISE_OVERLAP_CAPACITY_INSUFFICIENT" in _codes(
        overlap_validation
    )


def _legal_roster(slate):
    by_person = {
        binding.underlying_id: binding for binding in salary_person_bindings(slate)
    }
    flex_rows = sorted(
        (row for row in slate.players if row.role == "FLEX"),
        key=lambda row: (row.salary, row.dk_id),
    )
    for captain in sorted(
        (row for row in slate.players if row.role == "CPT"),
        key=lambda row: (row.salary, row.dk_id),
    ):
        flex = [row for row in flex_rows if row.underlying_id != captain.underlying_id]
        for start in range(max(1, len(flex) - 4)):
            selected = flex[start : start + 5]
            if len(selected) != 5:
                continue
            roster = (captain.dk_id, *(row.dk_id for row in selected))
            identity, _people, _captain = canonical_showdown_lineup_identity(slate, roster)
            assert identity
            return roster, by_person
    raise AssertionError("fixture did not contain a legal lineup")


def test_canonical_uniqueness_overlap_and_role_agnostic_person_counts(tmp_path: Path) -> None:
    slate = _slate(tmp_path)
    roster, by_person = _legal_roster(slate)
    reversed_flex = (roster[0], *reversed(roster[1:]))
    summary = summarize_showdown_portfolio(
        slate, {"1": roster, "2": reversed_flex}
    )
    assert len(summary.duplicate_canonical_lineups) == 1
    assert summary.pairwise_person_overlap == (("1", "2", 6),)
    assert set(dict(summary.combined_person_counts).values()) == {2}
    assert sum(dict(summary.captain_counts).values()) == 2

    old_captain = next(row for row in slate.players if row.dk_id == roster[0])
    new_captain_flex = next(row for row in slate.players if row.dk_id == roster[1])
    swapped = (
        by_person[new_captain_flex.underlying_id].cpt_dk_id,
        by_person[old_captain.underlying_id].flex_dk_id,
        *roster[2:],
    )
    distinct = summarize_showdown_portfolio(slate, {"1": roster, "2": swapped})
    assert distinct.duplicate_canonical_lineups == ()
    assert distinct.pairwise_person_overlap == (("1", "2", 6),)


def test_request_round_trip_and_path_confinement_include_policy(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    policy = root / "policy.json"
    policy.write_text("{}", encoding="utf-8")
    request = CoworkRunRequest.from_mapping(
        {"profile": "prior_review", "portfolio_policy_json": str(policy)},
        allowed_roots=(root,),
    )
    assert CoworkRunRequest.from_mapping(
        request.to_dict(), allowed_roots=(root,)
    ) == request
    assert required_next_inputs(CoworkRunRequest()) == tuple(
        blocker
        for blocker in required_next_inputs(CoworkRunRequest())
        if blocker != ENFORCEMENT_BLOCKER
    )
    assert ENFORCEMENT_BLOCKER in required_next_inputs(request)

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(CoworkInputError, match="portfolio_policy_json is outside"):
        CoworkRunRequest.from_mapping(
            {"portfolio_policy_json": str(outside)}, allowed_roots=(root,)
        )


def test_appg_never_changes_policy_integer_math(tmp_path: Path) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    first_path.write_bytes(_salary_bytes())
    second_path.write_bytes(_salary_bytes().replace(b",0,", b",98765.4321,"))
    first_slate = parse_salaries(first_path)
    second_slate = parse_salaries(second_path)
    controls = {
        "max_combined_person_exposure": {
            "default_fraction": 0.67,
            "overrides": [],
        }
    }
    first = _validate(first_slate, _document(first_slate, ("1", "2", "3"), **controls), ("1", "2", "3"))
    second = _validate(second_slate, _document(second_slate, ("1", "2", "3"), **controls), ("1", "2", "3"))
    assert first.valid and second.valid
    assert [item.combined_max_entries for item in first.policy.effective_limits] == [
        item.combined_max_entries for item in second.policy.effective_limits
    ]


def test_cowork_policy_is_snapshotted_refused_and_replays_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from .test_prior_review_profile import _attachments, _cowork_args

    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _slate(prepared)
    salary_path = prepared / "DKSalaries.csv"
    entry_path = prepared / "DKEntries.csv"
    entry_path.write_bytes(_entries_bytes())
    attachments = _attachments(tmp_path, salary_path, entry_path)
    slate = parse_salaries(salary_path)
    entries = parse_entries(entry_path)
    policy_path = tmp_path / "policy" / "portfolio.json"
    policy_path.parent.mkdir()
    policy_path.write_text(
        json.dumps(
            portfolio_policy_template(
                slate,
                [entry.entry_id for entry in entries.authorizations],
                controls={"max_pairwise_person_overlap": 4},
            )
        ),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    outputs = tmp_path / "outputs"
    retained = outputs / "earlier" / "DK_REVIEW_ENTRY_keep.csv"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b"preserve me")
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)

    first_code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            run_id="sd3-first",
            output_dir=str(outputs),
            portfolio_policy_json=str(policy_path),
            build_priors=True,
            lineup_count=1,
        )
    )
    assert first_code == 2
    first_report = json.loads(
        (outputs / "sd3-first" / "cowork_run.json").read_text(encoding="utf-8")
    )
    assert first_report["FILE_VALID"] is False
    assert first_report["EVIDENCE_STATE"] == "UNKNOWN"
    assert first_report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert first_report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert first_report["bulk_entry_csv"] is None
    assert first_report["portfolio_policy"]["valid"] is True
    assert sha256_bytes(
        Path(first_report["portfolio_policy"]["normalized_policy"]).read_bytes()
    ) == first_report["portfolio_policy"]["normalized_policy_sha256"]
    assert any(
        blocker.startswith("PORTFOLIO_POLICY_ENFORCEMENT_UNSUPPORTED_SD3:")
        for blocker in first_report["blockers"]
    )
    assert any(
        blocker.startswith("PORTFOLIO_POLICY_LINEUP_COUNT_MUST_MATCH_ENTRIES:")
        for blocker in first_report["blockers"]
    )
    assert retained.read_bytes() == b"preserve me"
    assert list((outputs / "sd3-first").rglob("DK_REVIEW_ENTRY_*.csv")) == []
    snapshotted_request = runs / "sd3-first" / "run_request.json"
    request = json.loads(snapshotted_request.read_text(encoding="utf-8"))
    snapshotted_policy = Path(request["portfolio_policy_json"])
    assert snapshotted_policy.parent == runs / "sd3-first" / "inputs"
    assert snapshotted_policy.read_bytes() == policy_path.read_bytes()

    policy_path.write_text(policy_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    second_code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            request=str(snapshotted_request),
            input_dir=None,
            profile=None,
            run_id="sd3-replay",
            output_dir=str(outputs),
            portfolio_policy_json=None,
            build_priors=False,
        )
    )
    assert second_code == 2
    second_report = json.loads(
        (outputs / "sd3-replay" / "cowork_run.json").read_text(encoding="utf-8")
    )
    assert second_report["portfolio_policy"]["source_policy_sha256"] == (
        first_report["portfolio_policy"]["source_policy_sha256"]
    )
    assert second_report["portfolio_policy"]["normalized_policy_sha256"] == (
        first_report["portfolio_policy"]["normalized_policy_sha256"]
    )
    assert list((outputs / "sd3-replay").rglob("DK_REVIEW_ENTRY_*.csv")) == []
