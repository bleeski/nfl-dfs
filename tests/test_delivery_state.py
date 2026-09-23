"""`DELIVERY_STATE`, the fifth run truth (R28, Session 03).

It says whether a valid file exists to hand over, and nothing else. It is
derived from three things only: whether the delivered bytes are valid, which
authorized rows they cover, and which integrity gates fired. Model status and
evidence state never reach it, and it never changes `RELEASE_DECISION`.

The central property is the card's: `DELIVERABLE` never co-occurs with an
integrity blocker. Integrity gates (class `V`) stop the file, or the rows, they
protect; every other gate travels with the file as a named limitation.
"""

from __future__ import annotations

import inspect
import itertools
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nfl_dfs.contracts import (
    CertificationBasis,
    DeliveryLimitation,
    DeliveryState,
    DeliveryTruth,
    GateClass,
    GateProvenance,
    GateStops,
    ModelStatus,
    ProvenanceKind,
    ReleaseDecision,
    ReleaseEvidenceState,
    ReleaseTruthsV2,
)
from nfl_dfs.release import (
    DeliveryStateError,
    derive_delivery_state,
    derive_release_policy,
    release_truths_v2,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORIZED = ("5263200000", "5263200001", "5263200002")

R28 = GateProvenance(kind=ProvenanceKind.RULING, ref="R28")
EXACT_IDS = GateProvenance(
    kind=ProvenanceKind.CLAUDE_MD_BOUNDARY,
    ref="Only exact current-slate DraftKings IDs enter runtime joins.",
)


def limitation(code, cls, stops, entry_ids=(), people=(), provenance=EXACT_IDS):
    return DeliveryLimitation(code=code, gate_class=cls, stops=stops,
                              provenance=provenance, entry_ids=entry_ids, people=people)


def integrity(code="DK_ID_NOT_IN_POOL", entry_ids=()):
    return limitation(code, GateClass.V, GateStops.FILE, entry_ids)


WEATHER = limitation("WEATHER_CAPTURE_REQUIRED", GateClass.P, GateStops.CERTIFICATION,
                     provenance=R28)
STACK = limitation("CLASSIC_POLICY_STACK_INFEASIBLE", GateClass.S,
                   GateStops.CONSTRUCTION_PREFERENCE, provenance=R28)


def derive(delivered=AUTHORIZED, *, file_valid=True, limitations=(), authorized=AUTHORIZED):
    return derive_delivery_state(file_valid=file_valid, authorized_entry_ids=authorized,
                                 delivered_entry_ids=delivered, limitations=limitations)


def codes(truth) -> list[str]:
    return [item.code for item in truth.delivery_limitations]


# ----------------------------------------------------------------- the three values

def test_every_authorized_row_filled_and_valid_is_deliverable():
    truth = derive()
    assert truth.delivery_state is DeliveryState.DELIVERABLE
    assert truth.delivered_entry_ids == AUTHORIZED
    assert truth.unfilled_entry_ids == ()
    assert truth.delivery_limitations == ()


def test_some_rows_delivered_is_partial_and_lists_the_rest_by_entry_id():
    truth = derive(AUTHORIZED[:1])
    assert truth.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert truth.delivered_entry_ids == AUTHORIZED[:1]
    assert truth.unfilled_entry_ids == AUTHORIZED[1:]
    # A gap nobody explained is still named: silence is the one error R28 forbids.
    (gap,) = truth.delivery_limitations
    assert gap.code == "UNFILLED_AUTHORIZED_ROWS"
    assert gap.entry_ids == AUTHORIZED[1:]
    assert (gap.gate_class, gap.stops) == (GateClass.V, GateStops.FILE)


def test_unfilled_rows_keep_template_order_whatever_order_delivery_arrives_in():
    truth = derive((AUTHORIZED[2],))
    assert truth.unfilled_entry_ids == AUTHORIZED[:2]
    truth = derive((AUTHORIZED[2], AUTHORIZED[0]))
    assert truth.delivered_entry_ids == (AUTHORIZED[0], AUTHORIZED[2])


def test_a_valid_file_with_no_row_filled_is_no_deliverable():
    truth = derive(())
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE
    assert truth.unfilled_entry_ids == AUTHORIZED
    assert codes(truth) == ["UNFILLED_AUTHORIZED_ROWS"]


def test_an_invalid_file_delivers_nothing_whatever_it_claims_to_cover():
    truth = derive(file_valid=False)
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE
    assert truth.delivered_entry_ids == ()
    assert truth.unfilled_entry_ids == AUTHORIZED
    assert "FILE_VALIDATION_INCOMPLETE" in codes(truth)


def test_no_authorized_row_is_nothing_to_hand_over():
    truth = derive((), authorized=())
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE
    assert "NO_AUTHORIZED_ROWS" in codes(truth)


# ----------------------------------------------------------------- integrity blockers

def test_a_file_wide_integrity_blocker_stops_the_whole_file():
    truth = derive(limitations=(integrity("SOURCE_HASH_MISMATCH"),))
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE
    assert truth.delivered_entry_ids == ()
    assert truth.unfilled_entry_ids == AUTHORIZED


def test_an_entry_scoped_integrity_blocker_stops_only_its_rows():
    blocked = integrity(entry_ids=AUTHORIZED[1:])
    truth = derive(AUTHORIZED[:1], limitations=(blocked,))
    assert truth.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    assert truth.unfilled_entry_ids == AUTHORIZED[1:]
    # The rows are already named, so no second, generic limitation is added.
    assert codes(truth) == ["DK_ID_NOT_IN_POOL"]


def test_only_the_rows_no_limitation_names_get_the_generic_gap():
    blocked = integrity(entry_ids=(AUTHORIZED[1],))
    truth = derive(AUTHORIZED[:1], limitations=(blocked,))
    assert codes(truth) == ["DK_ID_NOT_IN_POOL", "UNFILLED_AUTHORIZED_ROWS"]
    assert truth.delivery_limitations[1].entry_ids == (AUTHORIZED[2],)


def test_a_delivered_row_an_integrity_gate_blocks_is_refused():
    """The file would hold bytes its own record calls undeliverable."""

    with pytest.raises(DeliveryStateError, match="DELIVERY_ROW_BLOCKED_BY_INTEGRITY_GATE"):
        derive(limitations=(integrity(entry_ids=(AUTHORIZED[0],)),))


def test_an_integrity_gate_on_a_row_outside_the_template_stops_the_whole_file():
    """It cannot be scoped to a delivered or an unfilled row, so it covers the file."""

    truth = derive(limitations=(integrity("UNKNOWN_ENTRY_ID", entry_ids=("5263299999",)),))
    assert truth.delivery_state is DeliveryState.NO_DELIVERABLE
    assert truth.delivered_entry_ids == ()


def test_a_delivered_row_the_template_never_authorized_is_refused():
    with pytest.raises(DeliveryStateError, match="DELIVERY_ENTRY_NOT_AUTHORIZED"):
        derive(AUTHORIZED + ("5263299999",))


@pytest.mark.parametrize("field", ["authorized", "delivered"])
def test_a_repeated_entry_id_is_refused(field):
    doubled = AUTHORIZED + AUTHORIZED[:1]
    kwargs = {"authorized": doubled} if field == "authorized" else {"delivered": doubled}
    with pytest.raises(DeliveryStateError, match="DELIVERY_ENTRY_ID_REPEATED"):
        derive(**kwargs)


def test_truth_claim_and_strategy_limitations_travel_without_stopping_the_file():
    """R28: missing weather stops certification, not delivery; a construction
    preference is relaxable. Both ride along, named."""

    truth = derive(limitations=(WEATHER, STACK))
    assert truth.delivery_state is DeliveryState.DELIVERABLE
    assert codes(truth) == ["WEATHER_CAPTURE_REQUIRED", "CLASSIC_POLICY_STACK_INFEASIBLE"]


def _limitation_pool():
    yield integrity("SOURCE_HASH_MISMATCH")
    for eid in AUTHORIZED:
        yield integrity(entry_ids=(eid,))
    yield WEATHER
    yield STACK


def test_deliverable_never_co_occurs_with_an_integrity_blocker():
    """Every combination of validity, coverage and a pool of six limitations."""

    pool = list(_limitation_pool())
    checked = 0
    for file_valid in (True, False):
        for k in range(len(AUTHORIZED) + 1):
            for delivered in itertools.combinations(AUTHORIZED, k):
                for r in range(len(pool) + 1):
                    for chosen in itertools.combinations(pool, r):
                        try:
                            truth = derive(delivered, file_valid=file_valid, limitations=chosen)
                        except DeliveryStateError:
                            continue
                        checked += 1
                        has_v = any(item.gate_class is GateClass.V
                                    for item in truth.delivery_limitations)
                        assert (truth.delivery_state is DeliveryState.DELIVERABLE) == (not has_v)
                        if truth.delivery_state is DeliveryState.DELIVERABLE:
                            assert file_valid and set(delivered) == set(AUTHORIZED)
    assert checked > 100


# ----------------------------------------------------------------- the record's own invariants

def test_a_deliverable_record_with_an_integrity_blocker_cannot_be_constructed():
    with pytest.raises(ValidationError, match="DELIVERABLE"):
        DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE="DELIVERABLE", delivered_entry_ids=AUTHORIZED,
                      delivery_limitations=(integrity(),))


@pytest.mark.parametrize("state, delivered, unfilled", [
    ("DELIVERABLE", AUTHORIZED[:1], AUTHORIZED[1:]),
    ("DELIVERABLE", (), ()),
    ("DELIVERABLE_PARTIAL", AUTHORIZED, ()),
    ("NO_DELIVERABLE", AUTHORIZED[:1], AUTHORIZED[1:]),
])
def test_a_record_whose_state_contradicts_its_coverage_cannot_be_constructed(state, delivered, unfilled):
    gap = limitation("UNFILLED_AUTHORIZED_ROWS", GateClass.V, GateStops.FILE, unfilled, provenance=R28)
    with pytest.raises(ValidationError):
        DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE=state, delivered_entry_ids=delivered,
                      unfilled_entry_ids=unfilled, delivery_limitations=(gap,) if unfilled else ())


def test_a_partial_record_must_name_every_unfilled_row():
    with pytest.raises(ValidationError, match="unfilled"):
        DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE="DELIVERABLE_PARTIAL", delivered_entry_ids=AUTHORIZED[:1],
                      unfilled_entry_ids=AUTHORIZED[1:], delivery_limitations=())


def test_a_partial_record_cannot_carry_an_integrity_gate_outside_its_unfilled_rows():
    """Found in review: the derivation treats such a gate as file-wide, so a record
    that holds one beside delivered rows contradicts it."""

    gap = limitation("UNFILLED_AUTHORIZED_ROWS", GateClass.V, GateStops.FILE, AUTHORIZED[1:], provenance=R28)
    stray = integrity("UNKNOWN_ENTRY_ID", entry_ids=("5263299999",))
    with pytest.raises(ValidationError, match="unfilled"):
        DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE="DELIVERABLE_PARTIAL", delivered_entry_ids=AUTHORIZED[:1],
                      unfilled_entry_ids=AUTHORIZED[1:], delivery_limitations=(gap, stray))


@pytest.mark.parametrize("field", ["delivered_entry_ids", "unfilled_entry_ids"])
def test_a_record_refuses_a_repeated_or_blank_entry_id(field):
    gap = limitation("UNFILLED_AUTHORIZED_ROWS", GateClass.V, GateStops.FILE, ("2",), provenance=R28)
    base = {"delivered_entry_ids": ("1",), "unfilled_entry_ids": ("2",)}
    for bad in (base[field] * 2, ("",)):
        values = {**base, field: bad}
        with pytest.raises(ValidationError):
            DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE="DELIVERABLE_PARTIAL", delivery_limitations=(gap,), **values)


def test_the_derivation_refuses_a_blank_entry_id():
    with pytest.raises(DeliveryStateError, match="DELIVERY_ENTRY_ID_BLANK"):
        derive(("",), authorized=("",))


def test_a_limitation_refuses_a_blank_entry_id_or_person():
    with pytest.raises(ValidationError):
        integrity(entry_ids=("",))
    with pytest.raises(ValidationError):
        limitation("OFFICIAL_ACTIVITY_MISSING", GateClass.P, GateStops.CERTIFICATION,
                   people=(" ",), provenance=R28)


def test_a_row_cannot_be_both_delivered_and_unfilled():
    gap = limitation("UNFILLED_AUTHORIZED_ROWS", GateClass.V, GateStops.FILE, AUTHORIZED[:1], provenance=R28)
    with pytest.raises(ValidationError):
        DeliveryTruth(delivered_file_valid=True, DELIVERY_STATE="DELIVERABLE_PARTIAL", delivered_entry_ids=AUTHORIZED[:2],
                      unfilled_entry_ids=AUTHORIZED[:1], delivery_limitations=(gap,))


# ----------------------------------------------------------------- limitation shape

def test_a_validity_gate_can_never_stop_only_certification():
    """Card: a `V` gate can never have `stops=CERTIFICATION`."""

    with pytest.raises(ValidationError, match="V"):
        limitation("DK_ID_NOT_IN_POOL", GateClass.V, GateStops.CERTIFICATION)


def test_a_validity_gate_is_never_a_relaxable_preference():
    with pytest.raises(ValidationError, match="V"):
        limitation("DK_ID_NOT_IN_POOL", GateClass.V, GateStops.CONSTRUCTION_PREFERENCE)


@pytest.mark.parametrize(("cls", "stops"), [
    (GateClass.S, GateStops.CERTIFICATION),
    (GateClass.P, GateStops.CONSTRUCTION_PREFERENCE),
])
def test_a_limitation_carries_one_of_the_registrys_three_pairs(cls, stops):
    """Session 04 holds a hand-built limitation to the registry's pairs, not only off `FILE`."""

    with pytest.raises(ValidationError, match="never"):
        limitation("A_GATE_CODE", cls, stops, provenance=R28)


@pytest.mark.parametrize("cls", [GateClass.S, GateClass.P])
def test_only_a_validity_gate_may_stop_the_file(cls):
    """R28: truth-claim gates and construction preferences no longer stop delivery."""

    with pytest.raises(ValidationError, match="FILE"):
        limitation("WEATHER_CAPTURE_REQUIRED", cls, GateStops.FILE, provenance=R28)


@pytest.mark.parametrize("code", ["", "lower_case", "NOSEPARATOR", "HAS:DETAIL", "TRAILING_"])
def test_a_limitation_code_is_one_upper_snake_token(code):
    with pytest.raises(ValidationError):
        limitation(code, GateClass.P, GateStops.CERTIFICATION, provenance=R28)


def test_provenance_names_its_source():
    with pytest.raises(ValidationError):
        GateProvenance(kind=ProvenanceKind.RULING, ref="")
    assert {kind.value for kind in ProvenanceKind} == {"CLAUDE_MD_BOUNDARY", "RULING", "CONTRACT"}


def test_a_limitation_names_the_people_it_affects():
    item = limitation("OFFICIAL_ACTIVITY_MISSING", GateClass.P, GateStops.CERTIFICATION,
                      people=("SEA|WR|Sea Alpha WR",), provenance=R28)
    truth = derive(limitations=(item,))
    assert truth.delivery_limitations[0].people == ("SEA|WR|Sea Alpha WR",)


# ----------------------------------------------------------------- independence

def test_derivation_takes_no_model_or_evidence_input():
    params = set(inspect.signature(derive_delivery_state).parameters)
    assert params == {"file_valid", "authorized_entry_ids", "delivered_entry_ids", "limitations"}


@pytest.mark.parametrize("evidence", list(ReleaseEvidenceState))
@pytest.mark.parametrize("model", list(ModelStatus))
@pytest.mark.parametrize("basis", list(CertificationBasis))
@pytest.mark.parametrize("delivered", [AUTHORIZED, AUTHORIZED[:2]])
def test_release_truths_never_move_the_delivery_state(evidence, model, basis, delivered):
    delivery = derive(delivered, limitations=(WEATHER,))
    policy = derive_release_policy(file_valid=True, evidence_state=evidence,
                                   model_status=model, certification_basis=basis)
    certified = policy.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
    if certified and delivery.delivery_state is not DeliveryState.DELIVERABLE:
        # The only combination the record refuses: a certified package that
        # leaves authorized rows blank. It is refused, never re-derived.
        with pytest.raises(ValidationError, match="CERTIFIED"):
            release_truths_v2(policy, delivery)
        return
    truths = release_truths_v2(policy, delivery)
    assert truths.delivery_state is delivery.delivery_state
    assert truths.release_decision is policy.release_decision
    assert truths.unfilled_entry_ids == delivery.unfilled_entry_ids


# ----------------------------------------------------------------- the v2 record

def test_the_v2_record_carries_five_truths_under_their_names():
    policy = derive_release_policy(file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN,
                                   model_status=ModelStatus.PRIOR_ONLY,
                                   certification_basis=CertificationBasis.MODEL_ASSISTED)
    record = release_truths_v2(policy, derive(limitations=(WEATHER,)))
    dumped = json.loads(record.model_dump_json(by_alias=True))
    assert dumped["schema_version"] == "nfl_release_truths_v2"
    assert {k: dumped[k] for k in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS",
                                    "RELEASE_DECISION", "DELIVERY_STATE")} == {
        "FILE_VALID": True, "EVIDENCE_STATE": "UNKNOWN", "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD", "DELIVERY_STATE": "DELIVERABLE"}
    assert dumped["delivery_limitations"][0]["class"] == "P"
    assert ReleaseTruthsV2.model_validate(dumped) == record


def test_a_certified_package_must_be_fully_deliverable():
    policy = derive_release_policy(file_valid=True, evidence_state=ReleaseEvidenceState.PASS,
                                   model_status=ModelStatus.UNVALIDATED,
                                   certification_basis=CertificationBasis.MANUAL_GUARDRAIL)
    assert policy.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
    assert release_truths_v2(policy, derive()).delivery_state is DeliveryState.DELIVERABLE
    with pytest.raises(ValidationError, match="CERTIFIED"):
        release_truths_v2(policy, derive(AUTHORIZED[:1]))


def test_a_valid_baseline_beside_an_invalid_improvement_can_be_recorded():
    """Found in review: v2 used to force FILE_VALID to agree with delivery, so the
    Session 06 case (the improvement fails, the baseline ships) could not be written.
    FILE_VALID keeps its v1 meaning; the delivered file's validity is its own field."""

    policy = derive_release_policy(file_valid=False, evidence_state=ReleaseEvidenceState.PASS,
                                   model_status=ModelStatus.PRIOR_ONLY,
                                   certification_basis=CertificationBasis.MODEL_ASSISTED)
    record = release_truths_v2(policy, derive())
    assert (record.file_valid, record.delivered_file_valid) == (False, True)
    assert record.delivery_state is DeliveryState.DELIVERABLE


def test_the_delivery_records_the_validity_of_the_file_it_describes():
    """Found in review: FILE_VALID=True could sit beside FILE_VALIDATION_INCOMPLETE."""

    policy = derive_release_policy(file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN,
                                   model_status=ModelStatus.PRIOR_ONLY,
                                   certification_basis=CertificationBasis.MODEL_ASSISTED)
    record = release_truths_v2(policy, derive(file_valid=False))
    assert (record.file_valid, record.delivered_file_valid) == (True, False)
    assert record.delivery_state is DeliveryState.NO_DELIVERABLE
    with pytest.raises(ValidationError, match="delivered_file_valid"):
        DeliveryTruth(DELIVERY_STATE="DELIVERABLE", delivered_file_valid=False,
                      delivered_entry_ids=AUTHORIZED)


def test_the_contract_is_registered_and_v1_still_is_four_truths():
    text = (REPO_ROOT / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    assert "`nfl_release_truths_v2`" in text and "`nfl_release_truths_v1`" in text
    assert "DELIVERY_STATE" in text
