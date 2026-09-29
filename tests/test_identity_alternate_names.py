"""Session 21, F8: alternate-name identity proposals.

nflverse ships `first_name`, `last_name` and `football_name` beside the display
name, and DraftKings spells some people differently. A same-team hit on those
forms is a *proposal* for a reviewer. It never resolves, never auto-accepts and
never reaches a runtime join; the auto-accept rule is the one Session 47 wrote.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

from nfl_dfs import priors
from nfl_dfs.priors import (
    IdentityProposal,
    PriorsBuildError,
    alternate_name_keys,
    propose_identities,
)
from nfl_dfs.prior_review import AUTO_ACCEPT_MATCH_METHOD, apply_identity_gate

from .test_priors_adapter import _ROSTER, package  # noqa: F401  (pytest fixture)

# Pinned on the pre-Session-21 code: the four methods that resolve a proposal.
RESOLVED_METHODS = frozenset(
    {
        "NORMALIZED_NAME_TEAM_POSITION",
        "NORMALIZED_NAME_TEAM",
        "PLAYERS_INDEX_NAME_TEAM_POSITION",
        "TEAM_DEFENSE_NICKNAME",
    }
)
RESOLVED_PROPERTY_SHA256 = "22471bea08d5593eaf8fcfe1438ddd90d962254d9a2bbdbd65e6cc5e47d63d6a"

PUKA = "00-0039337"


def _roster(**changes):
    """The fixture roster, with `changes` applied to Puka Nacua's row(s)."""

    rows = []
    for team, position, name, gsis, pfr in _ROSTER:
        row = {
            "season": "2026", "week": "1", "team": team, "position": position,
            "full_name": name, "gsis_id": gsis, "pfr_id": pfr, "status": "ACT",
            "first_name": name.split()[0], "last_name": name.split()[-1],
            "football_name": name.split()[0],
        }
        if gsis == PUKA:
            row.update(changes)
        rows.append(row)
    return rows


def _propose(package, roster, **kwargs):
    return propose_identities(
        package["slate"], roster, package["crosswalk"], season=2026, **kwargs
    )


def _puka(proposals):
    return next(item for item in proposals if item.dk_name == "Puka Nacua")


def test_the_resolving_methods_and_the_auto_accept_rule_are_unchanged():
    resolved_source = inspect.getsource(IdentityProposal.resolved.fget)
    assert hashlib.sha256(resolved_source.encode()).hexdigest() == RESOLVED_PROPERTY_SHA256
    assert AUTO_ACCEPT_MATCH_METHOD == "NAME_POSITION_OTHER_TEAM"
    for method in RESOLVED_METHODS:
        assert _proposal(method).resolved
    for method in ("ALTERNATE_NAME_TEAM_POSITION", "ALTERNATE_NAME_TEAM", "AMBIGUOUS", "UNMATCHED"):
        assert not _proposal(method).resolved


def _proposal(method):
    return IdentityProposal(
        dk_id="1", captain_dk_id="", dk_name="X", dk_team="LAR", dk_position="WR",
        underlying_id="u", nflverse_team="LA", provider_player_id="p", provider_name="X",
        provider_pfr_id="", provider_team="LA", provider_status="ACT",
        match_method=method, candidates=(),
    )


def test_a_nickname_on_the_football_name_is_proposed_not_resolved(package):
    # nflverse lists "Peter Nacua" (football name "Puka"); DraftKings says "Puka".
    roster = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Puka")
    proposal = _puka(_propose(package, roster))
    assert proposal.match_method == "ALTERNATE_NAME_TEAM_POSITION"
    assert proposal.provider_player_id == PUKA and not proposal.resolved
    assert any(candidate.startswith(f"{PUKA}|") for candidate in proposal.candidates)


def test_an_accent_only_difference_is_proposed(package):
    roster = _roster(full_name="Púka Nacúa", first_name="Púka", football_name="Púka", last_name="Nacúa")
    proposal = _puka(_propose(package, roster))
    assert proposal.match_method == "ALTERNATE_NAME_TEAM_POSITION"
    assert alternate_name_keys("José Ramírez") == alternate_name_keys("Jose Ramirez") | {"JOSÉ RAMÍREZ"}


def test_an_alternate_hit_on_the_wrong_position_is_a_weaker_proposal(package):
    roster = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Puka", position="TE")
    proposal = _puka(_propose(package, roster))
    assert proposal.match_method == "ALTERNATE_NAME_TEAM" and not proposal.resolved


def test_two_alternate_hits_are_ambiguous_and_choose_nobody(package):
    roster = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Puka")
    roster.append({**roster[2], "gsis_id": "00-DUPLICATE", "full_name": "Paul Nacua",
                   "first_name": "Paul", "football_name": "Puka"})
    proposal = _puka(_propose(package, roster))
    assert proposal.match_method == "AMBIGUOUS" and proposal.provider_player_id == ""
    assert len(proposal.candidates) == 2


def test_no_alternate_key_means_the_old_outcome(package):
    roster = _roster(full_name="Somebody Else", first_name="Somebody", football_name="Else", last_name="Else")
    assert _puka(_propose(package, roster)).match_method == "UNMATCHED"


def test_the_base_fixture_proposals_are_the_same_with_or_without_the_name_columns(package):
    with_columns = _propose(package, _roster())
    without = _propose(
        package,
        [{key: value for key, value in row.items() if key not in {"first_name", "last_name", "football_name"}}
         for row in _roster()],
    )
    assert [item.as_payload() for item in with_columns] == [item.as_payload() for item in without]
    assert not any(item.match_method.startswith("ALTERNATE") for item in with_columns)


def test_an_alternate_proposal_cannot_certify_or_enter_a_join(package, tmp_path):
    roster = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Puka")
    proposals = _propose(package, roster)
    proposal = _puka(proposals)
    # The review file leaves the decision blank, so freeze refuses the person.
    review = tmp_path / "review.csv"
    review.write_bytes(priors.review_csv_bytes(proposals))
    decisions = priors.read_reviewed_decisions(review)
    assert decisions[proposal.dk_id]["DECISION"] == ""
    with pytest.raises(PriorsBuildError, match="IDENTITY_NOT_ACCEPTED"):
        priors._resolve_reviewed(proposals, decisions)
    # The prior-review gate does not auto-accept it, even for an unavailable person.
    gate = apply_identity_gate(proposals, {proposal.dk_id: "OUT"})
    assert any(item.dk_id == proposal.dk_id for item in gate.blocked)
    assert proposal.dk_id not in {item.dk_id for item in gate.auto_accepted}


def test_alternate_proposals_are_deterministic(package):
    roster = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Puka")
    first = [item.as_payload() for item in _propose(package, roster)]
    second = [item.as_payload() for item in _propose(package, list(roster))]
    assert first == second
    mutated = _roster(full_name="Peter Nacua", first_name="Peter", football_name="Poka")
    assert _puka(_propose(package, mutated)).match_method == "UNMATCHED"
